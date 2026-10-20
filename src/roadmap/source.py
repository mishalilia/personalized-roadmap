"""Where the curriculum comes from: a public git repository, pinned to one commit."""

import subprocess  # nosec B404: only runs git, see _git
from pathlib import Path

from pydantic import BaseModel

from . import docusaurus
from .config import read_yaml
from .curriculum import Attribution, Curriculum


class CurriculumSource(BaseModel):
    repository: str
    version: str  # full commit hash
    docs_dir: str
    site_url: str
    attribution: Attribution

    @classmethod
    def from_file(cls, path: Path) -> "CurriculumSource":
        return cls.model_validate(read_yaml(path))


def checkout(source: CurriculumSource, target: Path) -> Path:
    """Clone the repository into `target` unless it is there, check out the pinned version, return the docs path."""
    if not (target / ".git").exists():
        # Some of the course's paths are longer than Windows allows by default.
        _git(
            "clone",
            "--quiet",
            "-c",
            "core.longpaths=true",
            source.repository,
            str(target),
        )
    if _git("-C", str(target), "rev-parse", "HEAD") != source.version:
        _git("-C", str(target), "fetch", "--quiet", "origin")
        _git("-C", str(target), "checkout", "--quiet", source.version)
    return target / source.docs_dir


def load_curriculum(source: CurriculumSource, target: Path) -> Curriculum:
    docs_dir = checkout(source, target)
    return Curriculum(
        version=source.version,
        attribution=source.attribution,
        modules=docusaurus.parse_modules(docs_dir, source.site_url),
    )


def _git(*args: str) -> str:
    # git gets its arguments from config/curriculum.yaml, never from a user, and runs without a shell.
    result = subprocess.run(  # nosec B603 B607
        ["git", *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()
