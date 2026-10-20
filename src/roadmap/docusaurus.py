"""Reads a Docusaurus docs directory into curriculum modules, in the order the site's sidebar shows them.

Docusaurus conventions this relies on:
- `_category_.yml` gives a directory its label, its position and, optionally, an overview page (`link.id`);
- `sidebar_position` orders pages, and items without a position come after those with one;
- number prefixes such as `02-` are dropped from page ids and URLs, and a `slug` replaces the URL.

A module is a page inside a category, other than a category's overview page. Pages at the top level
(the site introduction, the contributors guide) are not part of the course.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import read_yaml
from .curriculum import Module, Resource

_PAGE_SUFFIXES = (".md", ".mdx")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_NUMBER_PREFIX = re.compile(r"^\d+\s*[-_.]+\s*(?=[^-_.\s])")
_RESOURCE_CARD = re.compile(r"<ResourceCard\b(.*?)/>", re.DOTALL)
_ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
_CODE_BLOCK = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
_CHECKBOX = re.compile(r"^\s*[-*]\s+\[ \]\s+(.+)$", re.MULTILINE)
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG = re.compile(r"<[^>]*>")


def parse_modules(docs_dir: Path, site_url: str) -> list[Module]:
    """The course modules under `docs_dir`, in sidebar order."""
    overview_ids = _overview_ids(docs_dir)
    return [
        _module(page, section, docs_dir, site_url)
        for page, section in _pages_in_sidebar_order(docs_dir, section=[])
        if section and _page_id(page.path, docs_dir) not in overview_ids
    ]


@dataclass(frozen=True)
class _Page:
    path: Path
    frontmatter: dict[str, Any]
    body: str

    @classmethod
    def read(cls, path: Path) -> _Page:
        text = path.read_text(encoding="utf-8")
        match = _FRONTMATTER.match(text)
        if match is None:
            return cls(path, {}, text)
        return cls(path, yaml.safe_load(match.group(1)) or {}, text[match.end() :])

    @property
    def position(self) -> float | None:
        return self.frontmatter.get("sidebar_position")


@dataclass(frozen=True)
class _Category:
    directory: Path
    label: str
    position: float | None
    overview_id: str | None

    @classmethod
    def read(cls, directory: Path) -> _Category:
        config_file = directory / "_category_.yml"
        config = read_yaml(config_file) if config_file.exists() else {}
        link = config.get("link") or {}
        return cls(
            directory,
            config.get("label", directory.name),
            config.get("position"),
            link.get("id"),
        )


def _overview_ids(docs_dir: Path) -> set[str]:
    categories = (
        _Category.read(config_file.parent)
        for config_file in docs_dir.rglob("_category_.yml")
    )
    return {category.overview_id for category in categories if category.overview_id}


def _pages_in_sidebar_order(
    directory: Path, section: list[str]
) -> Iterator[tuple[_Page, list[str]]]:
    children: list[_Page | _Category] = [
        _Category.read(child) if child.is_dir() else _Page.read(child)
        for child in sorted(directory.iterdir())
        if child.is_dir() or child.suffix in _PAGE_SUFFIXES
    ]
    for child in sorted(children, key=_sidebar_order):
        if isinstance(child, _Category):
            yield from _pages_in_sidebar_order(child.directory, [*section, child.label])
        else:
            yield child, section


def _sidebar_order(item: _Page | _Category) -> tuple[bool, float]:
    """Positioned items first, by position; the sort is stable, so ties keep file-name order."""
    return item.position is None, item.position or 0


def _module(page: _Page, section: list[str], docs_dir: Path, site_url: str) -> Module:
    page_id = _page_id(page.path, docs_dir)
    return Module(
        id=page_id,
        title=page.frontmatter.get("title", page.path.stem),
        description=page.frontmatter.get("description", ""),
        section=section,
        url=_page_url(page_id, page.frontmatter.get("slug"), site_url),
        resources=[_resource(card) for card in _RESOURCE_CARD.findall(page.body)],
        prerequisites=_prerequisites(page.body),
        checklist=_checklist(page.body),
    )


def _prerequisites(body: str) -> list[str]:
    """The bullet points under a "Prerequisites" heading, as plain text."""
    section = _section_text(body, "Prerequisites")
    return [_plain_text(item) for item in _BULLET.findall(section)]


def _checklist(body: str) -> list[str]:
    """The tick boxes under a "Checklist" heading, as Markdown so that links stay usable."""
    section = _section_text(body, "Checklist")
    return [_TAG.sub("", item).strip() for item in _CHECKBOX.findall(section)]


def _page_id(path: Path, docs_dir: Path) -> str:
    parts = path.relative_to(docs_dir).with_suffix("").parts
    return "/".join(_NUMBER_PREFIX.sub("", part) for part in parts)


def _page_url(page_id: str, slug: str | None, site_url: str) -> str:
    directory, name = posixpath.split(page_id)
    if slug is None:
        path = f"{directory}/" if name == "index" else page_id
    elif slug.startswith("/"):
        path = slug.lstrip("/")
    else:
        path = posixpath.join(directory, slug)
    return f"{site_url.rstrip('/')}/{path}"


def _resource(card: str) -> Resource:
    attributes = dict(_ATTRIBUTE.findall(card))
    return Resource.model_validate(
        {
            "title": attributes["title"],
            "url": attributes["url"],
            "type": attributes["type"],
            "difficulty": attributes["difficulty"],
            "duration": attributes["duration"],
            "note": attributes.get("why") or attributes.get("description", ""),
        }
    )


def _section_text(markdown: str, word: str) -> str:
    """The text under the first heading containing `word`, up to the next heading of the same
    or a higher level. Authors vary the wording: "Completion Checklist", "Checklist & Troubleshooting".
    """
    text = _CODE_BLOCK.sub("", markdown)
    headings = list(_HEADING.finditer(text))
    for index, match in enumerate(headings):
        if word.lower() in _plain_text(match.group(2)).lower():
            level = len(match.group(1))
            ends = (
                later.start()
                for later in headings[index + 1 :]
                if len(later.group(1)) <= level
            )
            return text[match.end() : next(ends, len(text))]
    return ""


def _plain_text(markdown: str) -> str:
    text = _LINK.sub(r"\1", markdown)
    text = _TAG.sub("", text)
    return text.replace("**", "").replace("`", "").strip()
