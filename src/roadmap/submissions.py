"""Project submissions: a learner hands in a capstone as a link, an archive, or both. A model reviews it against
the capstone's rubric (roadmap.project_review) and it is accepted or sent back with feedback; a person who
reviews can look at every review and decide otherwise.

The server never opens what it is given. A link is stored as text and shown as a link; it is never fetched,
so it cannot make the server reach anything. An archive is checked to be a zip or a gzip file by its first
bytes, kept under a random name outside any served folder, never unpacked or run, and handed back only to its
learner and to reviewers, as a download.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel

from .project_review import ProjectReview

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
REVIEWS_PER_DAY = 5  # projects a learner can hand in for a review by the model, each day
MAX_LINK_LENGTH = 500
MAX_NOTE_LENGTH = 2000
_CHUNK = 64 * 1024

# What an archive must start with: a zip (also an empty one), or gzip (a .tar.gz).
_ARCHIVES = {
    b"PK\x03\x04": "zip",
    b"PK\x05\x06": "zip",
    b"\x1f\x8b": "gzip",
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


class SubmissionError(ValueError):
    """A submission that cannot be kept, with a message for the learner."""


class Status(StrEnum):
    REVIEWING = "reviewing"  # the model is reading it
    SUBMITTED = "submitted"  # waiting for a person: no model could review it
    ACCEPTED = "accepted"
    RETURNED = "returned"


class Submission(BaseModel):
    id: str
    account_id: str
    email: str  # the learner's, for the reviewer
    module_id: str
    module_title: str
    curriculum_version: str
    link: str | None
    note: str
    file_name: str | None
    file_size: int | None
    status: Status
    review_comment: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    reviewed_by: str | None = None  # "model", or the email of the person
    ai_review: ProjectReview | None = None


def check_link(link: str | None) -> str | None:
    link = (link or "").strip()
    if not link:
        return None
    parsed = urlparse(link)
    if (
        len(link) > MAX_LINK_LENGTH
        or parsed.scheme not in ("http", "https")
        or not parsed.netloc
    ):
        raise SubmissionError(
            "Give a link that starts with https://, such as your repository."
        )
    return link


def safe_file_name(name: str | None) -> str:
    """The archive's name as shown and as it is downloaded: letters, digits and a few signs only."""
    base = Path(name or "project").name
    cleaned = _SAFE_NAME.sub("_", base).strip(" .") or "project"
    return cleaned[:120]


class SubmissionStore:
    def __init__(self, file: Path, uploads: Path) -> None:
        file.parent.mkdir(parents=True, exist_ok=True)
        uploads.mkdir(parents=True, exist_ok=True)
        self._uploads = uploads
        self._db = sqlite3.connect(file, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS submissions ("
                " id TEXT PRIMARY KEY, account_id TEXT NOT NULL, email TEXT NOT NULL,"
                " module_id TEXT NOT NULL, module_title TEXT NOT NULL,"
                " curriculum_version TEXT NOT NULL, link TEXT, note TEXT NOT NULL,"
                " file_name TEXT, file_size INTEGER, stored_as TEXT, status TEXT NOT NULL,"
                " review_comment TEXT, submitted_at TEXT NOT NULL, reviewed_at TEXT,"
                " UNIQUE (account_id, module_id))"
            )
            columns = {
                row[1] for row in self._db.execute("PRAGMA table_info(submissions)")
            }
            for column in ("reviewed_by", "ai_review"):
                if column not in columns:  # databases made before reviews by a model
                    self._db.execute(
                        f"ALTER TABLE submissions ADD COLUMN {column} TEXT"
                    )

    def keep_archive(self, upload: BinaryIO) -> tuple[str, int]:
        """Copies an uploaded archive to the uploads folder under a random name; returns the name and size.
        Refuses anything that is not a zip or gzip file, and anything over the size limit, before it is kept.
        """
        head = upload.read(4)
        if not any(head.startswith(magic) for magic in _ARCHIVES):
            raise SubmissionError("Attach a .zip or a .tar.gz archive.")
        stored = f"{uuid4().hex}.bin"
        target = self._uploads / stored
        size = len(head)
        try:
            with target.open("wb") as out:
                out.write(head)
                while chunk := upload.read(_CHUNK):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise SubmissionError(
                            f"The archive is over {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB. "
                            "Leave out data, models and dependencies, or give a link instead."
                        )
                    out.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return stored, size

    def submit(
        self,
        *,
        account_id: str,
        email: str,
        module_id: str,
        module_title: str,
        curriculum_version: str,
        link: str | None,
        note: str,
        archive: (
            tuple[str, int, str] | None
        ),  # stored name, size, the name the learner gave
    ) -> Submission:
        """Keeps the learner's submission for the module, replacing an earlier one and its archive."""

        now = datetime.now(UTC).isoformat()
        stored, size, name = archive if archive else (None, None, None)
        with self._lock, self._db:
            previous = self._db.execute(
                "SELECT stored_as FROM submissions WHERE account_id = ? AND module_id = ?",
                (account_id, module_id),
            ).fetchone()
            self._db.execute(
                "DELETE FROM submissions WHERE account_id = ? AND module_id = ?",
                (account_id, module_id),
            )
            self._db.execute(
                "INSERT INTO submissions (id, account_id, email, module_id, module_title,"
                " curriculum_version, link, note, file_name, file_size, stored_as, status,"
                " submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid4().hex,
                    account_id,
                    email,
                    module_id,
                    module_title,
                    curriculum_version,
                    link,
                    note,
                    name,
                    size,
                    stored,
                    Status.SUBMITTED,
                    now,
                ),
            )
        if previous and previous[0]:
            (self._uploads / previous[0]).unlink(missing_ok=True)
        found = self.for_module(account_id, module_id)
        assert found is not None  # nosec B101: just written
        return found

    def for_module(self, account_id: str, module_id: str) -> Submission | None:
        return next(
            self._select("account_id = ? AND module_id = ?", (account_id, module_id)),
            None,
        )

    def get(self, submission_id: str) -> Submission | None:
        return next(self._select("id = ?", (submission_id,)), None)

    def waiting(self) -> list[Submission]:
        """Submissions no model could review, for a person, oldest first."""
        return list(self._select("status = ?", (Status.SUBMITTED,)))

    def recent(self, limit: int = 50) -> list[Submission]:
        """The latest reviewed submissions, newest first."""
        found = list(
            self._select("status IN (?, ?)", (Status.ACCEPTED, Status.RETURNED))
        )
        return sorted(
            found, key=lambda s: s.reviewed_at or s.submitted_at, reverse=True
        )[:limit]

    def archive_of(self, submission_id: str) -> Path | None:
        with self._lock:
            row = self._db.execute(
                "SELECT stored_as FROM submissions WHERE id = ?", (submission_id,)
            ).fetchone()
        return self._uploads / row[0] if row and row[0] else None

    def set_status(self, submission_id: str, status: Status) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE submissions SET status = ? WHERE id = ?",
                (status, submission_id),
            )

    def review(
        self,
        submission_id: str,
        accepted: bool,
        comment: str,
        reviewed_by: str,
        ai_review: ProjectReview | None = None,
    ) -> Submission:
        """Records a decision: the model's, or a person's, who may also decide otherwise than the model did.
        Not while the model is still reading the project."""
        with self._lock, self._db:
            changed = self._db.execute(
                "UPDATE submissions SET status = ?, review_comment = ?, reviewed_at = ?,"
                " reviewed_by = ?, ai_review = COALESCE(?, ai_review)"
                " WHERE id = ? AND status != ?",
                (
                    Status.ACCEPTED if accepted else Status.RETURNED,
                    comment or None,
                    datetime.now(UTC).isoformat(),
                    reviewed_by,
                    ai_review.model_dump_json() if ai_review else None,
                    submission_id,
                    Status.REVIEWING if reviewed_by != "model" else "",
                ),
            ).rowcount
        if not changed:
            raise SubmissionError("The model is still reviewing this submission.")
        found = self.get(submission_id)
        assert found is not None  # nosec B101: just updated
        return found

    def delete_for(self, account_id: str) -> None:
        """Deletes an account's submissions and their archives, with the account."""
        with self._lock, self._db:
            stored = self._db.execute(
                "SELECT stored_as FROM submissions WHERE account_id = ?", (account_id,)
            ).fetchall()
            self._db.execute(
                "DELETE FROM submissions WHERE account_id = ?", (account_id,)
            )
        for (name,) in stored:
            if name:
                (self._uploads / name).unlink(missing_ok=True)

    def _select(self, where: str, args: tuple) -> Iterator[Submission]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, account_id, email, module_id, module_title, curriculum_version, link,"
                " note, file_name, file_size, status, review_comment, submitted_at, reviewed_at,"
                " reviewed_by, ai_review"
                f" FROM submissions WHERE {where} ORDER BY submitted_at",  # nosec B608: fixed clauses
                args,
            ).fetchall()
        for row in rows:
            *fields, review = row
            yield Submission(
                ai_review=ProjectReview.model_validate_json(review) if review else None,
                **dict(
                    zip(
                        (
                            "id",
                            "account_id",
                            "email",
                            "module_id",
                            "module_title",
                            "curriculum_version",
                            "link",
                            "note",
                            "file_name",
                            "file_size",
                            "status",
                            "review_comment",
                            "submitted_at",
                            "reviewed_at",
                            "reviewed_by",
                        ),
                        fields,
                        strict=True,
                    )
                ),
            )
