"""The files of a submitted project, read as text for a review: from its archive, or from a public GitHub
repository.

Nothing is unpacked to disk and nothing is run. Archives are read in memory member by member, with limits on
the number of members, the size of each and the total read, so a zip bomb costs a bounded amount of work.
GitHub is reached only at api.github.com and codeload.github.com, never at an address the learner chose, so a
link cannot make the server reach anything else.
"""

from __future__ import annotations

import io
import json
import re
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import httpx

MAX_MEMBERS = 5000  # entries looked at in an archive
MAX_FILE_BYTES = 200 * 1024  # a larger file is listed, not read
# Notebooks keep their outputs, images among them, so they may be larger; only their text is read.
MAX_NOTEBOOK_BYTES = 3 * 1024 * 1024
MAX_OUTPUT_CHARS = 1500  # of one cell's output
MAX_READ_BYTES = 8 * 1024 * 1024  # all files read, together
MAX_PROMPT_CHARS = 120_000  # project text a review sees, about 30 000 tokens
MAX_FILE_CHARS = 12_000  # of one file, in the review
MAX_TREE = 400  # paths listed
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

_GITHUB = re.compile(
    r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:[#?].*)?$"
)
_SKIPPED_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    ".ipynb_checkpoints",
    ".idea",
    ".vscode",
    "data",
    "datasets",
    "models",
    "checkpoints",
    "weights",
}
_TEXT = {
    ".py",
    ".ipynb",
    ".md",
    ".rst",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
    ".yaml",
    ".yml",
    ".json",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".sql",
    ".sh",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".r",
    ".env.example",
    ".csv",
    ".tsv",
    ".log",
    ".out",
    ".xml",
}
# Where projects keep what their code produced: results, logs, predictions, reports.
_OUTPUT_DIRS = {
    "results",
    "result",
    "outputs",
    "output",
    "logs",
    "log",
    "reports",
    "report",
    "runs",
    "predictions",
    "eval",
    "evaluation",
    "metrics",
}
_OUTPUT_EXTENSIONS = (".log", ".out")
_NAMED = {
    "dockerfile",
    "makefile",
    "procfile",
    "requirements.txt",
    "compose.yml",
    "docker-compose.yml",
}


class ProjectError(Exception):
    """The project cannot be read, with a message for the learner."""


@dataclass
class ProjectFiles:
    """What a review sees: every path, and the text of the files that matter most, within the limits."""

    tree: list[str] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    source: str = ""  # "archive" or the repository's address
    # Texts that the project's code produced rather than its author wrote: notebook outputs, logs, files in
    # results/ or outputs/. A notebook's outputs are their own entry, "<notebook> (outputs)".
    outputs: set[str] = field(default_factory=set)

    def contains(self, path: str, quote: str) -> bool:
        """Whether the quote appears in the file, ignoring differences in whitespace. An empty quote asks
        only that the file exists."""
        if path not in self.texts:
            return not quote.strip() and path in self.tree
        return _squash(quote) in _squash(self.texts[path])

    def prompt(self) -> str:
        """The project for the model: the list of paths, then each file read, between markers."""
        parts = [
            "Files in the project (images and other binary files are listed, not shown):",
            *self.tree[:MAX_TREE],
        ]
        if len(self.tree) > MAX_TREE:
            parts.append(f"... and {len(self.tree) - MAX_TREE} more")
        for path, text in self.texts.items():
            kind = "PROGRAM OUTPUT" if path in self.outputs else "FILE"
            parts.append(f"\n<<<{kind} {path}>>>\n{text}\n<<<END {kind} {path}>>>")
        return "\n".join(parts)


def _squash(text: str) -> str:
    return " ".join(text.split()).lower()


def read_archive(data: bytes) -> ProjectFiles:
    if data.startswith(b"PK"):
        return _collect(_zip_members(data), "archive")
    if data.startswith(b"\x1f\x8b"):
        return _collect(_tar_members(data), "archive")
    raise ProjectError("The archive is neither a zip nor a gzip file.")


def github_repository(link: str | None) -> tuple[str, str] | None:
    """The owner and name of a GitHub repository link, or None for any other link."""
    match = _GITHUB.match((link or "").strip())
    return (match.group(1), match.group(2)) if match else None


def read_github(
    owner: str, repo: str, http: httpx.Client, token: str | None = None
) -> ProjectFiles:
    """The default branch of a public repository, as GitHub packs it."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "personalized-roadmap",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        pointer = http.get(
            f"https://api.github.com/repos/{owner}/{repo}/tarball",
            headers=headers,
            follow_redirects=False,
        )
        if pointer.status_code in (404, 403):
            raise ProjectError(
                "The repository cannot be read: make it public, or attach an archive of the code."
            )
        location = pointer.headers.get("location", "")
        if pointer.status_code not in (301, 302, 307) or not location.startswith(
            "https://codeload.github.com/"
        ):
            raise ProjectError(
                "GitHub did not send the repository. Try again later, or attach an archive."
            )
        data = bytearray()
        with http.stream(
            "GET", location, headers={"User-Agent": "personalized-roadmap"}
        ) as response:
            if response.status_code != 200:
                raise ProjectError(
                    "GitHub did not send the repository. Try again later, or attach an archive."
                )
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise ProjectError(
                        "The repository is over 20 MB. Attach an archive of the code without data and models."
                    )
    except httpx.HTTPError as error:
        raise ProjectError(
            "GitHub cannot be reached right now. Try again later."
        ) from error
    files = _collect(_tar_members(bytes(data)), f"https://github.com/{owner}/{repo}")
    return files


def _zip_members(data: bytes):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ProjectError("The zip archive is damaged.") from error
    for number, info in enumerate(archive.infolist()):
        if number >= MAX_MEMBERS:
            break
        if info.is_dir():
            continue
        yield info.filename, info.file_size, lambda limit, info=info: archive.open(
            info
        ).read(limit)


def _tar_members(data: bytes):
    try:
        archive = tarfile.open(
            fileobj=io.BytesIO(data), mode="r:gz"
        )  # nosec B202: read in memory, never extracted
        for number, member in enumerate(archive):
            if number >= MAX_MEMBERS:
                break
            if not member.isreg():
                continue

            def read(limit: int, member=member) -> bytes:
                handle = archive.extractfile(member)
                return handle.read(limit) if handle else b""

            yield member.name, member.size, read
    except (tarfile.TarError, EOFError, OSError) as error:
        raise ProjectError("The archive is damaged or not a .tar.gz.") from error


def _collect(members, source: str) -> ProjectFiles:
    entries = []
    for name, size, read in members:
        path = PurePosixPath(name.replace("\\", "/"))
        parts = [part for part in path.parts if part not in ("", ".", "..", "/")]
        if parts:
            entries.append((parts, size, read))
    # GitHub, and many zips, put everything under one folder: drop it from the paths.
    tops = {parts[0] for parts, _, _ in entries if len(parts) > 1}
    strip = len(tops) == 1 and all(len(parts) > 1 for parts, _, _ in entries)
    files = ProjectFiles(source=source)
    candidates = []
    for parts, size, read in entries:
        parts = parts[1:] if strip else parts
        path = "/".join(parts)
        if any(part.lower() in _SKIPPED_DIRS for part in parts[:-1]):
            continue
        files.tree.append(path)
        if size <= _limit(path) and _is_text_name(parts[-1]):
            candidates.append((_priority(parts), path, read))
    files.tree.sort()
    budget_read = MAX_READ_BYTES
    budget_chars = MAX_PROMPT_CHARS
    for _, path, read in sorted(candidates):
        if budget_read <= 0 or budget_chars <= 0:
            break
        try:
            raw = read(_limit(path))
        except (
            zipfile.BadZipFile,
            tarfile.TarError,
            RuntimeError,
            OSError,
            EOFError,
            ValueError,
        ):
            continue  # an encrypted, damaged or oddly packed member: listed, not read
        budget_read -= len(raw)
        if path.lower().endswith(".ipynb"):
            cells = _notebook(raw)
            if cells is None:
                continue
            entries_read = [(path, cells[0]), (f"{path} (outputs)", cells[1])]
        else:
            text = _text_of(raw)
            if text is None:
                continue
            entries_read = [(path, text)]
        for name, text in entries_read:
            if not text.strip() or budget_chars <= 0:
                continue
            if len(text) > MAX_FILE_CHARS:
                text = text[:MAX_FILE_CHARS] + "\n[... the rest is not shown]"
            files.texts[name] = text[:budget_chars]
            budget_chars -= len(files.texts[name])
            if name.endswith(" (outputs)") or _is_output(path):
                files.outputs.add(name)
    if not files.tree:
        raise ProjectError("The archive is empty.")
    return files


def _limit(path: str) -> int:
    return MAX_NOTEBOOK_BYTES if path.lower().endswith(".ipynb") else MAX_FILE_BYTES


def _is_output(path: str) -> bool:
    """Whether a file holds what the code produced: by its folder, or a log by its name."""
    parts = path.lower().split("/")
    return any(part in _OUTPUT_DIRS for part in parts[:-1]) or parts[-1].endswith(
        _OUTPUT_EXTENSIONS
    )


def _is_text_name(name: str) -> bool:
    lower = name.lower()
    return (
        lower in _NAMED
        or lower.startswith("readme")
        or any(lower.endswith(ext) for ext in _TEXT)
    )


def _priority(parts: list[str]) -> tuple[int, int, str]:
    """README first, then the files that describe the project, then code, shallow before deep."""
    name = parts[-1].lower()
    if name.startswith("readme"):
        rank = 0
    elif name in _NAMED or name.endswith((".toml", ".cfg", ".yml", ".yaml")):
        rank = 1
    elif name.endswith(
        (
            ".py",
            ".ipynb",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".go",
            ".rs",
            ".java",
            ".kt",
            ".r",
            ".sql",
        )
    ):
        rank = 2
    elif name.endswith((".log", ".out", ".csv", ".tsv", ".json", ".xml", ".txt")):
        rank = 3  # results and logs, after the code that made them
    elif name.endswith(".md"):
        rank = 3
    else:
        rank = 4
    return rank, len(parts), "/".join(parts)


def _text_of(raw: bytes) -> str | None:
    if b"\x00" in raw[:2048]:
        return None
    try:
        return raw[:MAX_FILE_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        return None


def _joined(value: object) -> str:
    return "".join(value) if isinstance(value, list) else str(value or "")


def _notebook(raw: bytes) -> tuple[str, str] | None:
    """A notebook's cells, and apart from them the text its cells printed when they ran: what the code
    produced. Images in the outputs are named, not read."""
    try:
        cells = json.loads(raw.decode("utf-8")).get("cells", [])
    except (ValueError, AttributeError):
        return None
    sources, outputs = [], []
    for number, cell in enumerate(cells, start=1):
        sources.append(
            f"# [cell {number}, {cell.get('cell_type', 'cell')}]\n{_joined(cell.get('source'))}"
        )
        for output in cell.get("outputs", []) or []:
            if output.get("output_type") == "stream":
                text = _joined(output.get("text"))
            elif output.get("output_type") == "error":
                text = f"{output.get('ename')}: {output.get('evalue')}"
            else:
                data = output.get("data", {}) or {}
                text = _joined(data.get("text/plain"))
                images = [kind for kind in data if kind.startswith("image/")]
                if images:
                    text = f"{text}\n[{', '.join(images)} output]".strip()
            if text.strip():
                outputs.append(
                    f"# [output of cell {number}]\n{text[:MAX_OUTPUT_CHARS]}"
                )
    return "\n\n".join(sources), "\n\n".join(outputs)
