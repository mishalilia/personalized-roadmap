"""Learners' reports of checkpoint questions they think are wrong, for reviewers to check.

Checkpoint questions are generated and still drafts, so a learner who meets one with a wrong answer key or an
unclear wording can say so. A report keeps the question it is about, why, and an optional comment; one per
learner and question, the latest replacing the earlier. Reviewers see the open ones with the question in full.

A reviewer can also take a reported question out of its checkpoint at once: learners stop getting it, and the
topic's other questions take its place, until someone fixes it in the checkpoint's file and puts it back.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, StringConstraints

from .database import Database, as_database

MAX_COMMENT = 1000


class ReportReason(StrEnum):
    WRONG_ANSWER = "wrong_answer"  # the answer counted as right is wrong, or another one is right too
    UNCLEAR = "unclear"  # the question or its options can be read more than one way
    OFF_TOPIC = "off_topic"  # the module does not teach what the question asks
    WRONG_MARK = "wrong_mark"  # an open answer marked wrong that the learner thinks is right; the comment has it
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
    """Reports in one table, beside the accounts (roadmap.database). Thread-safe for the API's worker threads."""

    def __init__(self, database: Database | Path | str) -> None:
        self._db = as_database(database)
        with self._db.transaction() as tx:
            tx.execute(
                "CREATE TABLE IF NOT EXISTS question_reports ("
                " id TEXT PRIMARY KEY, account_id TEXT NOT NULL, module_id TEXT NOT NULL,"
                " curriculum_version TEXT NOT NULL, question_id TEXT NOT NULL, reason TEXT NOT NULL,"
                " comment TEXT NOT NULL, reported_at TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0,"
                " UNIQUE (account_id, curriculum_version, module_id, question_id))"
            )
            tx.execute(
                "CREATE TABLE IF NOT EXISTS retired_questions ("
                " curriculum_version TEXT NOT NULL, module_id TEXT NOT NULL, question_id TEXT NOT NULL,"
                " retired_by TEXT NOT NULL, retired_at TEXT NOT NULL,"
                " PRIMARY KEY (curriculum_version, module_id, question_id))"
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
        with self._db.transaction() as tx:
            tx.execute(
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
        with self._db.transaction() as tx:
            rows = tx.execute(
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

    def get(self, report_id: str) -> QuestionReport | None:
        return next(
            (report for report in self.listed(10_000) if report.id == report_id), None
        )

    def retired(self, curriculum_version: str, module_id: str) -> frozenset[str]:
        """The ids of the questions taken out of this checkpoint."""
        with self._db.transaction() as tx:
            rows = tx.execute(
                "SELECT question_id FROM retired_questions WHERE curriculum_version = ? AND module_id = ?",
                (curriculum_version, module_id),
            ).fetchall()
        return frozenset(row[0] for row in rows)

    def set_retired(
        self,
        curriculum_version: str,
        module_id: str,
        question_id: str,
        retired: bool,
        by: str,
    ) -> None:
        """Takes a question out of its checkpoint, or puts it back. Taking it out resolves its reports."""
        with self._db.transaction() as tx:
            if retired:
                tx.execute(
                    "INSERT INTO retired_questions (curriculum_version, module_id, question_id, retired_by,"
                    " retired_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT (curriculum_version, module_id, question_id)"
                    " DO NOTHING",
                    (
                        curriculum_version,
                        module_id,
                        question_id,
                        by,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                tx.execute(
                    "UPDATE question_reports SET resolved = 1 WHERE curriculum_version = ? AND module_id = ?"
                    " AND question_id = ?",
                    (curriculum_version, module_id, question_id),
                )
            else:
                tx.execute(
                    "DELETE FROM retired_questions WHERE curriculum_version = ? AND module_id = ?"
                    " AND question_id = ?",
                    (curriculum_version, module_id, question_id),
                )

    def set_resolved(self, report_id: str, resolved: bool) -> bool:
        """False when there is no such report."""
        with self._db.transaction() as tx:
            changed = tx.execute(
                "UPDATE question_reports SET resolved = ? WHERE id = ?",
                (int(resolved), report_id),
            ).rowcount
        return changed > 0
