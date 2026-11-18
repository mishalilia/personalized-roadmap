"""Learners' reports of checkpoint questions they think are wrong, for reviewers to check.

Checkpoint questions are generated and still drafts, so a learner who meets one with a wrong answer key or an
unclear wording can say so. A report keeps the question it is about, why, and an optional comment; one per
learner and question, the latest replacing the earlier. Reviewers see the open ones with the question in full.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, StringConstraints

MAX_COMMENT = 1000


class ReportReason(StrEnum):
    WRONG_ANSWER = "wrong_answer"  # the answer counted as right is wrong, or another one is right too
    UNCLEAR = "unclear"  # the question or its options can be read more than one way
    OFF_TOPIC = "off_topic"  # the module does not teach what the question asks
    OTHER = "other"


class QuestionReportIn(BaseModel):
    question_id: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    reason: ReportReason
    comment: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=MAX_COMMENT)
    ] = ""


class QuestionReport(BaseModel):
    id: str
    module_id: str
    curriculum_version: str
    question_id: str
    reason: ReportReason
    comment: str
    reported_at: datetime
    resolved: bool = False


class QuestionReportStore:
    """Reports in one SQLite table, beside the accounts. Thread-safe for the API's worker threads."""

    def __init__(self, file: Path) -> None:
        if str(file) != ":memory:":
            file.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(file, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS question_reports ("
                " id TEXT PRIMARY KEY, account_id TEXT NOT NULL, module_id TEXT NOT NULL,"
                " curriculum_version TEXT NOT NULL, question_id TEXT NOT NULL, reason TEXT NOT NULL,"
                " comment TEXT NOT NULL, reported_at TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0,"
                " UNIQUE (account_id, curriculum_version, module_id, question_id))"
            )

    def add(
        self,
        account_id: str,
        module_id: str,
        curriculum_version: str,
        report: QuestionReportIn,
    ) -> QuestionReport:
        """Keeps the report; a learner's earlier report of the same question is replaced and opened again."""
        saved = QuestionReport(
            id=uuid4().hex,
            module_id=module_id,
            curriculum_version=curriculum_version,
            question_id=report.question_id,
            reason=report.reason,
            comment=report.comment,
            reported_at=datetime.now(UTC),
        )
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO question_reports (id, account_id, module_id, curriculum_version, question_id,"
                " reason, comment, reported_at, resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)"
                " ON CONFLICT (account_id, curriculum_version, module_id, question_id) DO UPDATE SET"
                " id = excluded.id, reason = excluded.reason, comment = excluded.comment,"
                " reported_at = excluded.reported_at, resolved = 0",
                (
                    saved.id,
                    account_id,
                    module_id,
                    curriculum_version,
                    saved.question_id,
                    saved.reason,
                    saved.comment,
                    saved.reported_at.isoformat(),
                ),
            )
        return saved

    def listed(self, limit: int = 100) -> list[QuestionReport]:
        """Open reports first, newest first within each group."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, module_id, curriculum_version, question_id, reason, comment, reported_at,"
                " resolved FROM question_reports ORDER BY resolved, reported_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            QuestionReport(
                id=row[0],
                module_id=row[1],
                curriculum_version=row[2],
                question_id=row[3],
                reason=ReportReason(row[4]),
                comment=row[5],
                reported_at=datetime.fromisoformat(row[6]),
                resolved=bool(row[7]),
            )
            for row in rows
        ]

    def set_resolved(self, report_id: str, resolved: bool) -> bool:
        """False when there is no such report."""
        with self._lock, self._db:
            changed = self._db.execute(
                "UPDATE question_reports SET resolved = ? WHERE id = ?",
                (int(resolved), report_id),
            ).rowcount
        return changed > 0
