"""Where the curriculum comes from: a public git repository, with each version pinned to one commit."""

import subprocess  # nosec B404: only runs git, see _git
from pathlib import Path

from pydantic import BaseModel, Field

from . import docusaurus
from .config import read_yaml
from .curriculum import Attribution, Curriculum


class CurriculumVersion(BaseModel):
    name: str  # as the curriculum site names its version: "current", or a date such as "2026-10-06"
    label: str
    ref: str  # full commit hash
    site_url: str  # where this version's docs live on the site
    # Whether modules state what finishes them under completion headings ("Expected output", "Finish this
    # module") rather than only in a tick-box checklist, as the current curriculum does.
    completion_headings: bool = False


class CurriculumSource(BaseModel):
    repository: str
    docs_dir: str
    versions: list[CurriculumVersion] = Field(min_length=1)  # newest first
    attribution: Attribution

    @classmethod
    def from_file(cls, path: Path) -> "CurriculumSource":
        return cls.model_validate(read_yaml(path))

    @property
    def default(self) -> CurriculumVersion:
        """The version new paths are planned for."""
        return self.versions[0]

    def version(self, name: str | None = None) -> CurriculumVersion:
        if name is None:
            return self.default
        for version in self.versions:
            if version.name == name:
                return version
        names = ", ".join(version.name for version in self.versions)
        raise ValueError(f"Unknown curriculum version '{name}'; config has: {names}")


def checkout(
    source: CurriculumSource, version: CurriculumVersion, data_dir: Path
) -> Path:
    """The version's docs directory, checked out under `data_dir` from one shared clone.

    `data_dir/repository` holds the clone; each version is a git worktree in `data_dir/<name>`.
    """
    clone = data_dir / "repository"
    if not (clone / ".git").exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        # Some of the course's paths are longer than Windows allows by default.
        _git(
            "clone",
            "--quiet",
            "-c",
            "core.longpaths=true",
            source.repository,
            str(clone),
        )
    target = data_dir / version.name
    if not (target / ".git").exists():
        if not _has_commit(clone, version.ref):
            _git("-C", str(clone), "fetch", "--quiet", "origin")
        _git(
            "-C",
            str(clone),
            "worktree",
            "add",
            "--quiet",
            "--detach",
            str(target.resolve()),
            version.ref,
        )
    elif _git("-C", str(target), "rev-parse", "HEAD") != version.ref:
        if not _has_commit(clone, version.ref):
            _git("-C", str(clone), "fetch", "--quiet", "origin")
        _git("-C", str(target), "checkout", "--quiet", "--detach", version.ref)
    return target / source.docs_dir


def load_curriculum(
    source: CurriculumSource, version: CurriculumVersion, data_dir: Path
) -> Curriculum:
    docs_dir = checkout(source, version, data_dir)
    return Curriculum(
        version=version.ref,
        site_version=version.name,
        attribution=source.attribution,
        modules=docusaurus.parse_modules(
            docs_dir, version.site_url, version.completion_headings
        ),
    )


def _has_commit(repository: Path, ref: str) -> bool:
    try:
        _git("-C", str(repository), "cat-file", "-e", f"{ref}^{{commit}}")
        return True
    except RuntimeError:
        return False


def _git(*args: str) -> str:
    # git gets its arguments from config/curriculum.yaml, never from a user, and runs without a shell.
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True
    )  # nosec B603 B607
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()
