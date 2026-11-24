"""Builds a demo school's website: the HumbleBeeAI course's lessons as plain HTML pages, in a look of their own,
with no Docusaurus. Each page carries the one DotPath script tag. It also writes the page map the API serves to
this site (sites.json), as an engineer would when converting a school's course.

    python build_school.py --api http://localhost:8030 --site http://localhost:3020 --origin http://127.0.0.1:5050

Run it with the API's Python (it reads the course's modules with roadmap), from the API folder.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from pathlib import Path

from roadmap.api import ApiSettings, load_editions

HERE = Path(__file__).parent
SCHOOL = "Northwind Academy"
COURSE = "AI Engineering, from fundamentals to a capstone"


def lesson_path(module_id: str) -> str:
    return f"/course/{module_id}/"


# --- A small MDX reader: the parts of the course's lesson files a static page can show ---------------------------

ATTR = re.compile(r'(\w+)=(?:"([^"]*)"|\{([^}]*)\})')


def attrs(tag: str) -> dict[str, str]:
    return {
        name: quoted if quoted is not None else braced
        for name, quoted, braced in ATTR.findall(tag)
    }


def inline(text: str, modules: set[str]) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", out)

    def link(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith("/docs/"):
            page, _, anchor = target[len("/docs/") :].partition("#")
            page = page.rstrip("/")
            if page in modules:
                target = lesson_path(page) + (f"#{anchor}" if anchor else "")
            else:
                target = f"https://roadmap.humblebee.ai{target}"
        external = target.startswith("http")
        extra = ' target="_blank" rel="noopener"' if external else ""
        return f'<a href="{html.escape(target)}"{extra}>{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)


def resource_card(tag: str) -> str:
    found = attrs(tag)
    kind = html.escape(found.get("type", "resource"))
    title = html.escape(found.get("title", "Resource"))
    url = html.escape(found.get("url", "#"))
    about = html.escape(found.get("description", ""))
    return (
        f'<a class="resource" href="{url}" target="_blank" rel="noopener">'
        f'<span class="kind">{kind}</span><strong>{title}</strong>'
        + (f"<span>{about}</span>" if about else "")
        + "</a>"
    )


def mdx_to_html(source: str, modules: set[str]) -> tuple[str, str]:
    """The lesson's body as HTML, and its summary."""
    source = re.sub(r"^---\n.*?\n---\n", "", source, flags=re.S)
    lines = source.split("\n")
    out: list[str] = []
    summary = ""
    i = 0
    paragraph: list[str] = []
    list_kind: str | None = None

    def flush() -> None:
        nonlocal paragraph, list_kind
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph), modules)}</p>")
            paragraph = []
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith(("import ", "export ")):
            i += 1
            continue
        if stripped.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
            i += 1
            continue
        if stripped.startswith("<") and re.match(r"</?[A-Z]", stripped):
            flush()
            tag = stripped
            while not re.search(r"/?>\s*$", tag) and i + 1 < len(lines):
                i += 1
                tag += " " + lines[i].strip()
            if tag.startswith("<ResourceCard"):
                out.append(resource_card(tag))
            elif tag.startswith("<ModuleIntro"):
                summary = attrs(tag).get("summary", "")
                if summary:
                    out.append(f'<p class="summary">{inline(summary, modules)}</p>')
            i += 1
            continue
        if stripped.startswith("<"):
            i += 1  # other markup (divs, comments) adds nothing to a static page
            continue
        heading = re.match(r"^(#{1,4})\s+(.*?)(?:\s*\{#([\w-]+)\})?\s*$", stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            text = heading.group(2)
            anchor = heading.group(3) or re.sub(r"[^\w]+", "-", text.lower()).strip("-")
            if level == 1:
                i += 1
                continue  # the page's title comes from the course
            out.append(f'<h{level} id="{anchor}">{inline(text, modules)}</h{level}>')
            i += 1
            continue
        if (
            stripped.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|\s*:?-", lines[i + 1].strip())
        ):
            flush()
            head = [cell.strip() for cell in stripped.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(
                    [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                )
                i += 1
            table = (
                "<table><thead><tr>"
                + "".join(f"<th>{inline(c, modules)}</th>" for c in head)
                + "</tr></thead><tbody>"
            )
            for row in rows:
                table += (
                    "<tr>"
                    + "".join(f"<td>{inline(c, modules)}</td>" for c in row)
                    + "</tr>"
                )
            out.append(table + "</tbody></table>")
            continue
        item = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if item:
            if paragraph:
                out.append(f"<p>{inline(' '.join(paragraph), modules)}</p>")
                paragraph = []
            kind = "ol" if item.group(2)[0].isdigit() else "ul"
            if list_kind != kind:
                if list_kind:
                    out.append(f"</{list_kind}>")
                out.append(f"<{kind}>")
                list_kind = kind
            out.append(f"<li>{inline(item.group(3), modules)}</li>")
            i += 1
            continue
        if not stripped:
            flush()
            i += 1
            continue
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None
        paragraph.append(stripped)
        i += 1
    flush()
    return "\n".join(out), summary


# --- Pages ---------------------------------------------------------------------------------------------------------


def page(title: str, nav: str, body: str, script: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {SCHOOL}</title>
<link rel="stylesheet" href="/school.css">
</head>
<body>
<header class="top">
  <a class="brand" href="/"><span class="mark">N</span>{SCHOOL}</a>
  <nav><a href="/">Courses</a><a href="/">Community</a><a href="/">Pricing</a>
    <a class="cta" href="/">My account</a></nav>
</header>
<div class="layout">
  <aside class="outline">{nav}</aside>
  <main>{body}</main>
</div>
<footer>&copy; 2026 {SCHOOL}. A demo school site: not a real school.</footer>
{script}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8030")
    parser.add_argument("--site", default="http://localhost:3020")
    parser.add_argument("--origin", default="http://127.0.0.1:5050")
    parser.add_argument("--docs", default=str(HERE.parent.parent / "site" / "docs"))
    parser.add_argument("--out", default=str(HERE / "public"))
    parser.add_argument(
        "--designers", nargs="*", default=["embed-test-1795452033085@example.test"]
    )
    args = parser.parse_args()

    edition = load_editions(ApiSettings())[0]
    curriculum = edition.roadmap.curriculum
    modules = curriculum.modules
    ids = {module.id for module in modules}
    docs = Path(args.docs)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "course").mkdir(parents=True)
    shutil.copy(HERE / "school.css", out / "school.css")

    script = f'<script src="{args.api}/embed/dotpath.js" data-site="{args.site}" defer></script>'

    def nav(current: str | None) -> str:
        items = []
        section = None
        for module in modules:
            label = " › ".join(module.section)
            if label != section:
                if section is not None:
                    items.append("</ol>")
                items.append(f"<h4>{html.escape(label)}</h4><ol>")
                section = label
            mark = ' aria-current="page"' if module.id == current else ""
            items.append(
                f'<li><a href="{lesson_path(module.id)}"{mark}>{html.escape(module.title)}</a></li>'
            )
        items.append("</ol>")
        return "".join(items)

    for module in modules:
        source = next(
            (
                path
                for path in (docs / f"{module.id}.mdx", docs / module.id / "index.mdx")
                if path.is_file()
            ),
            None,
        )
        body, summary = (
            mdx_to_html(source.read_text(encoding="utf-8"), ids) if source else ("", "")
        )
        crumbs = " / ".join(html.escape(part) for part in module.section)
        article = (
            f'<p class="crumbs">{crumbs}</p><h1>{html.escape(module.title)}</h1>'
            f'<article class="lesson">{body or "<p>This lesson has no text yet.</p>"}</article>'
        )
        target = out / "course" / module.id / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            page(module.title, nav(module.id), article, script), encoding="utf-8"
        )

    first = lesson_path(modules[0].id)
    home = (
        f'<p class="crumbs">Course</p><h1>{COURSE}</h1>'
        '<article class="lesson"><p class="summary">Twenty modules: engineering fundamentals, core systems, '
        "and a specialization ending in a capstone project. Learn at your own pace; every module ends with "
        "a checklist.</p>"
        f'<p><a class="start" href="{first}">Start the first lesson →</a></p>'
        "<p>New here? Open <strong>Get your path</strong> at the right of the page: answer a few questions and "
        "get a path through this course that skips what you already know.</p></article>"
    )
    (out / "index.html").write_text(
        page(COURSE, nav(None), home, script), encoding="utf-8"
    )

    sites = {
        args.origin: {
            "versions": [
                {
                    "name": curriculum.site_version or "current",
                    "label": "Current",
                    "docs": [
                        {"id": module.id, "path": lesson_path(module.id)}
                        for module in modules
                    ],
                }
            ],
            "content": "main article.lesson",
            # Who at the school may change the panel's look: here, the local test learner.
            "designers": args.designers,
        }
    }
    (HERE / "sites.json").write_text(json.dumps(sites, indent=2), encoding="utf-8")
    print(f"{len(modules)} lessons in {out}; page map in {HERE / 'sites.json'}")


if __name__ == "__main__":
    main()
