"""Reads a Docusaurus docs directory into curriculum modules, in the order the site's sidebar shows them.

Docusaurus conventions this relies on:
- `_category_.yml` gives a directory its label, its position and, optionally, an overview page (`link.id`);
- `sidebar_position` orders pages, and items without a position come after those with one;
- number prefixes such as `02-` are dropped from page ids and URLs, and a `slug` replaces the URL;
- `unlisted: true` and `draft: true` pages are not in the sidebar: authors use them for retired modules.

Authors state what finishes a module in two ways: tick boxes under a "Checklist" heading (versions up to
October 2026), or what the completion headings say: "Finish this module", "Expected output", "Assessment"
(the current one). `completion_headings` reads the second as well; both become the module's checklist.

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
from .curriculum import Hours, Module, Resource, Topic

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
_HEADING_ID = re.compile(r"\s*\{#[^}]*\}\s*$")
_TIME_ESTIMATE = re.compile(
    r"<TimeEstimate\b[^>]*?minHours=\{([\d.]+)\}[^>]*?maxHours=\{([\d.]+)\}", re.DOTALL
)
_DURATION = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*(minutes?|min|hours?|hrs?|h)\b",
    re.IGNORECASE,
)
_COMPLETION_HEADINGS = (
    "finish this module",
    "expected output",
    "assessment",
    "completion criteria",
)
# Headings whose paragraph, when it has no bullet points, still states what this module asks for. The
# paragraph under "Finish this module" is the same boilerplate on every page, so it is left out.
_OUTCOME_PARAGRAPHS = ("expected output", "what you’ll build", "what you'll build")


def parse_modules(
    docs_dir: Path, site_url: str, completion_headings: bool = False
) -> list[Module]:
    """The course modules under `docs_dir`, in sidebar order."""
    overview_ids = _overview_ids(docs_dir)
    return [
        _module(page, section, docs_dir, site_url, completion_headings)
        for page, section in _pages_in_sidebar_order(docs_dir, section=[])
        if section
        and _page_id(page.path, docs_dir) not in overview_ids
        and not page.frontmatter.get("unlisted")
        and not page.frontmatter.get("draft")
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


def _module(
    page: _Page,
    section: list[str],
    docs_dir: Path,
    site_url: str,
    completion_headings: bool = False,
) -> Module:
    page_id = _page_id(page.path, docs_dir)
    return Module(
        id=page_id,
        title=page.frontmatter.get("title", page.path.stem),
        description=page.frontmatter.get("description", ""),
        section=section,
        url=_page_url(page_id, page.frontmatter.get("slug"), site_url),
        resources=(
            resources := [_resource(card) for card in _RESOURCE_CARD.findall(page.body)]
        ),
        prerequisites=_prerequisites(page.body),
        checklist=_checklist(page.body, completion_headings),
        topics=_topics(page.body),
        hours=_hours(page.body, resources),
    )


def _prerequisites(body: str) -> list[str]:
    """The bullet points under "Prerequisites" or "Before you start" headings, as plain text; a section
    without bullet points counts as one item."""
    items: list[str] = []
    for section in _sections_titled(body, ("prerequisites", "before you start")):
        bullets = [_plain_text(item) for item in _BULLET.findall(section)]
        paragraph = " ".join(_plain_text(line) for line in section.strip().splitlines())
        items += bullets or ([paragraph] if paragraph else [])
    return items


def _checklist(body: str, completion_headings: bool = False) -> list[str]:
    """What finishes the module, as Markdown so that links stay usable: the tick boxes under a "Checklist"
    heading, or else, if asked, what the completion headings say."""
    ticks = [
        _TAG.sub("", item).strip()
        for item in _CHECKBOX.findall(_section_text(body, "Checklist"))
    ]
    if ticks or not completion_headings:
        return ticks
    items: list[str] = []
    for section in _sections_titled(body, _COMPLETION_HEADINGS):
        items += [_TAG.sub("", item).strip() for item in _BULLET.findall(section)]
    if not items:
        for section in _sections_titled(body, _OUTCOME_PARAGRAPHS):
            paragraph = " ".join(line.strip() for line in section.strip().splitlines())
            items += [_TAG.sub("", paragraph).strip()] if paragraph else []
    return [item for item in items if item]


def _sections_titled(markdown: str, words: tuple[str, ...]) -> list[str]:
    """The text under every heading whose title starts with one of `words`."""
    text = _CODE_BLOCK.sub("", markdown)
    headings = list(_HEADING.finditer(text))
    sections = []
    for index, match in enumerate(headings):
        if not _plain_text(match.group(2)).lower().startswith(words):
            continue
        level = len(match.group(1))
        ends = (
            later.start()
            for later in headings[index + 1 :]
            if len(later.group(1)) <= level
        )
        sections.append(text[match.end() : next(ends, len(text))])
    return sections


def _hours(body: str, resources: list[Resource]) -> Hours | None:
    """The authors' estimate for the module, or else the sum of its resources' durations, where every
    duration can be read."""
    if match := _TIME_ESTIMATE.search(body):
        return Hours(low=float(match.group(1)), high=float(match.group(2)))
    spans = [duration_hours(resource.duration) for resource in resources]
    if not spans or any(span is None for span in spans):
        return None
    return Hours(
        low=round(sum(span.low for span in spans if span), 1),
        high=round(sum(span.high for span in spans if span), 1),
    )


def duration_hours(duration: str) -> Hours | None:
    """ "2-3 hours" or "30-45 minutes" as hours; None for anything else, such as "4-6 weeks"."""
    match = _DURATION.search(duration)
    if match is None:
        return None
    low = float(match.group(1))
    high = float(match.group(2) or low)
    if match.group(3).lower().startswith("m"):
        low, high = low / 60, high / 60
    return Hours(low=low, high=high)


# Parts of a page that are not taught content.
_NOT_A_TOPIC = (
    "checklist",
    "goal",
    "prerequisites",
    "resources",
    "next steps",
    "workload",
    "finish this module",
)


def _topics(body: str) -> list[Topic]:
    """The page's second-level headings with the bullet points under them, as plain text."""
    text = _CODE_BLOCK.sub("", body)
    headings = [match for match in _HEADING.finditer(text) if len(match.group(1)) == 2]
    topics = []
    for index, match in enumerate(headings):
        title = _plain_text(match.group(2))
        if not title or any(word in title.lower() for word in _NOT_A_TOPIC):
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[match.end() : end]
        outcomes = [
            _plain_text(item)
            for item in _BULLET.findall(section)
            if not item.lstrip().startswith("[")
        ]
        topics.append(Topic(title=title, outcomes=outcomes))
    return topics


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
            "type": attributes.get("type", ""),
            # The current curriculum leaves these out of most cards.
            "difficulty": attributes.get("difficulty"),
            "duration": attributes.get("duration", ""),
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
    text = _HEADING_ID.sub("", markdown)
    text = _LINK.sub(r"\1", text)
    text = _TAG.sub("", text)
    return text.replace("**", "").replace("`", "").strip()
