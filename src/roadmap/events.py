"""Where learners stop: anonymous progress events, for the platform that offers the course.

Only paths whose learner turned on "share my progress" are counted. An event holds a random path id, the
curriculum version, a module and what happened; never the learner's answers, their level, their address or
anything else about them. The report counts, for each module, how many shared paths include it, finish it,
fail its checkpoint, and stop at it.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from .path import LearningPath


class EventKind(StrEnum):
    INCLUDED = (
        "included"  # the learner confirmed a path that studies or proves the module
    )
    FAILED = "failed"  # a checkpoint attempt that did not pass
    PRACTICE = "practice"  # questions passed, coding problem next
    FINISHED = "finished"  # checkpoint passed, coding problem solved, or marked done
    GOAL_CHANGED = "goal_changed"


class ModuleReport(BaseModel):
    module_id: str
    included: int  # shared paths that study or prove the module
    finished: int
    failed_once: int  # paths with at least one failed checkpoint attempt
    stopped_here: int  # paths whose first unfinished module is this one


class Report(BaseModel):
    curriculum_version: str
    paths: int
    modules: list[ModuleReport]


class EventLog:
    """Events in one SQLite file. Thread-safe for the API's worker threads."""

    def __init__(self, file: Path) -> None:
        file.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(file, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                " path_id TEXT NOT NULL, curriculum_version TEXT NOT NULL,"
                " module_id TEXT, kind TEXT NOT NULL, at TEXT NOT NULL)"
            )

    def record(
        self, path: LearningPath, kind: EventKind, module_id: str | None = None
    ) -> None:
        """Records the event if the learner shares their progress; does nothing otherwise."""
        if not path.share_progress or path.id is None:
            return
        self._insert([(path.id, path.curriculum_version, module_id, kind)])

    def record_included(self, path: LearningPath) -> None:
        """At confirmation: the modules the path asks the learner to work through. A path confirmed again
        after a change replaces what it included before."""
        if not path.share_progress or path.id is None:
            return
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM events WHERE path_id = ? AND kind = ?",
                (path.id, EventKind.INCLUDED),
            )
        self._insert(
            [
                (path.id, path.curriculum_version, item.module.id, EventKind.INCLUDED)
                for item in path.included
            ]
        )

    def _insert(self, rows: list[tuple[str, str, str | None, str]]) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock, self._db:
            self._db.executemany(
                "INSERT INTO events (path_id, curriculum_version, module_id, kind, at)"
                " VALUES (?, ?, ?, ?, ?)",
                [(*row, now) for row in rows],
            )

    def report(self, curriculum_version: str, module_order: list[str]) -> Report:
        """Counts per module, in course order."""
        with self._lock:
            rows = self._db.execute(
                "SELECT path_id, module_id, kind FROM events WHERE curriculum_version = ?",
                (curriculum_version,),
            ).fetchall()
        included: dict[str, set[str]] = {}
        finished: dict[str, set[str]] = {}
        failed: dict[str, set[str]] = {}
        for path_id, module_id, kind in rows:
            target = {
                EventKind.INCLUDED: included,
                EventKind.FINISHED: finished,
                EventKind.FAILED: failed,
            }.get(kind)
            if target is not None and module_id is not None:
                target.setdefault(path_id, set()).add(module_id)
        stopped: dict[str, int] = {}
        for path_id, modules in included.items():
            done = finished.get(path_id, set())
            first_open = next(
                (
                    module
                    for module in module_order
                    if module in modules and module not in done
                ),
                None,
            )
            if first_open is not None:
                stopped[first_open] = stopped.get(first_open, 0) + 1

        def count(table: dict[str, set[str]], module_id: str) -> int:
            return sum(module_id in modules for modules in table.values())

        return Report(
            curriculum_version=curriculum_version,
            paths=len(included),
            modules=[
                ModuleReport(
                    module_id=module_id,
                    included=count(included, module_id),
                    finished=count(finished, module_id),
                    failed_once=count(failed, module_id),
                    stopped_here=stopped.get(module_id, 0),
                )
                for module_id in module_order
            ],
        )
