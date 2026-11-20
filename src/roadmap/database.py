"""Where the API keeps its state: PostgreSQL in production, a SQLite file for tests and for trying it out.

The stores (accounts, submissions, question reports, progress events) write SQL that both understand and
reach the database through `Database`:

    with db.transaction() as tx:
        tx.execute("UPDATE accounts SET google_sub = ? WHERE id = ?", (subject, account_id))

`?` marks a parameter in both. A transaction commits when its block ends and is rolled back if the block
raises; a unique or foreign-key violation comes out as `IntegrityError`, whichever database it came from.

PostgreSQL: `Database.open("postgresql://…")` keeps a pool of connections, so the API's worker threads, and
several API processes, use the database at once. SQLite: one connection behind a lock, as before.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class IntegrityError(Exception):
    """A unique or foreign-key constraint refused a write."""


class Cursor(Protocol):
    rowcount: int

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


def _plain(params: Sequence[Any]) -> tuple[Any, ...]:
    # Enums go in as their values ("submitted"), whichever driver writes them.
    return tuple(p.value if isinstance(p, Enum) else p for p in params)


class Transaction(Protocol):
    def execute(self, sql: str, params: Sequence[Any] = ()) -> Cursor: ...

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None: ...


class Database:
    """A SQLite file or a PostgreSQL server. Make one with `Database.open`."""

    kind: str

    @staticmethod
    def open(target: str | Path) -> Database:
        """A PostgreSQL URL (postgresql://user:password@host:5432/name) or a SQLite file (":memory:" for one
        that lasts as long as the process)."""
        text = str(target)
        if text.startswith(("postgresql://", "postgres://")):
            return PostgresDatabase(text)
        return SqliteDatabase(Path(target))

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        raise NotImplementedError
        yield  # pragma: no cover

    def columns(self, table: str) -> set[str]:
        """The names of the table's columns, to add columns to tables made by an earlier version."""
        raise NotImplementedError

    @contextmanager
    def held(self, key: str) -> Iterator[None]:
        """Holds `key` until the block ends: no other block holding the same key, in this process or (on
        PostgreSQL) in another API process, runs meanwhile. For changes that take long, such as a model call."""
        raise NotImplementedError
        yield  # pragma: no cover


class SqliteDatabase(Database):
    kind = "sqlite"

    def __init__(self, file: Path) -> None:
        if str(file) != ":memory:":
            file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(file, check_same_thread=False)
        self._lock = threading.Lock()
        self._keys: dict[str, threading.Lock] = {}

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        with self._lock:
            try:
                with self._connection:
                    yield _SqliteTransaction(self._connection)
            except sqlite3.IntegrityError as error:
                raise IntegrityError(str(error)) from error

    def columns(self, table: str) -> set[str]:
        with self.transaction() as tx:
            return {row[1] for row in tx.execute(f"PRAGMA table_info({table})").fetchall()}

    @contextmanager
    def held(self, key: str) -> Iterator[None]:
        with self._lock:
            lock = self._keys.setdefault(key, threading.Lock())
        with lock:
            yield


class _SqliteTransaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Cursor:
        return self._connection.execute(sql, _plain(params))

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        self._connection.executemany(sql, [_plain(row) for row in rows])


class PostgresDatabase(Database):
    kind = "postgres"

    def __init__(self, url: str, max_connections: int = 10) -> None:
        from psycopg_pool import ConnectionPool  # only a PostgreSQL deployment needs the driver

        # Each connection is checked before it is handed out, so one the server dropped is replaced.
        self._pool = ConnectionPool(
            url,
            min_size=1,
            max_size=max_connections,
            open=True,
            check=ConnectionPool.check_connection,
            name="roadmap",
        )

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        import psycopg

        try:
            # The pool commits when the block ends and rolls back if it raises.
            with self._pool.connection() as connection:
                yield _PostgresTransaction(connection)
        except psycopg.errors.IntegrityError as error:
            raise IntegrityError(str(error)) from error

    def columns(self, table: str) -> set[str]:
        with self.transaction() as tx:
            rows = tx.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = ?",
                (table,),
            ).fetchall()
        return {row[0] for row in rows}

    @contextmanager
    def held(self, key: str) -> Iterator[None]:
        # A session-level advisory lock on a connection kept for the block: it holds across API processes,
        # and the server lets it go if the process dies.
        with self._pool.connection() as connection:
            connection.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (key,))
            connection.commit()
            try:
                yield
            finally:
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (key,))
                connection.commit()


def _postgres_sql(sql: str) -> str:
    # The stores write `?` for a parameter; psycopg wants %s. They write no literal % signs.
    return sql.replace("?", "%s")


class _PostgresTransaction:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Cursor:
        return self._connection.execute(_postgres_sql(sql), _plain(params))

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(_postgres_sql(sql), [_plain(row) for row in rows])


def as_database(target: Database | str | Path) -> Database:
    """A store may be given a Database, or a file or URL to open one."""
    return target if isinstance(target, Database) else Database.open(target)
