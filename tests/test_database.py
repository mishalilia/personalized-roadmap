"""The database layer the stores share (SQLite here; PostgreSQL with ROADMAP_TEST_DATABASE_URL, see conftest)."""

import threading
import time
from pathlib import Path

import pytest

from roadmap.database import Database, IntegrityError


def test_a_refused_write_is_an_integrity_error_and_the_database_goes_on(tmp_path: Path):
    db = Database.open(tmp_path / "test.sqlite")
    with db.transaction() as tx:
        tx.execute("CREATE TABLE things (name TEXT PRIMARY KEY, size INTEGER)")
        tx.execute("INSERT INTO things (name, size) VALUES (?, ?)", ("a", 1))

    with pytest.raises(IntegrityError):
        with db.transaction() as tx:
            tx.execute("INSERT INTO things (name, size) VALUES (?, ?)", ("b", 2))
            tx.execute("INSERT INTO things (name, size) VALUES (?, ?)", ("a", 3))

    # The failed transaction left nothing behind, not even its first row, and the next one works.
    with db.transaction() as tx:
        tx.executemany(
            "INSERT INTO things (name, size) VALUES (?, ?)", [("c", 3), ("d", 4)]
        )
        rows = tx.execute("SELECT name, size FROM things ORDER BY name").fetchall()
    assert [tuple(row) for row in rows] == [("a", 1), ("c", 3), ("d", 4)]
    assert db.columns("things") == {"name", "size"}


def test_a_held_key_keeps_the_next_holder_waiting(tmp_path: Path):
    db = Database.open(tmp_path / "test.sqlite")
    order: list[str] = []

    def second() -> None:
        with db.held("path:1"):
            order.append("second")

    with db.held("path:1"):
        other = threading.Thread(target=second)
        other.start()
        time.sleep(0.3)
        order.append("first")
    other.join(timeout=10)

    assert order == ["first", "second"]
    with db.held("path:2"), db.held("path:3"):  # other keys are not held up
        pass
