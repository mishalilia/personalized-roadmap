"""Learner accounts: an email and a password, or a Google account; a session per signed-in browser; and the
learner's path.

The path lives here, not in the browser, so progress cannot be edited on the learner's side: the server keeps
the attempts, locks and checkpoint results, and every change to a path goes through its rules.

A path planned before signing in is kept as a draft for a day, under its random id, so that signing up or in
afterwards keeps it.

Passwords are stored as scrypt hashes; sessions as SHA-256 hashes of random tokens, so a copy of the database
signs nobody in. One SQLite file, safe for the API's worker threads.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from .path import LearningPath

SESSION_DAYS = 30
DRAFT_HOURS = 24
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200  # scrypt hashes any length; a cap keeps a request cheap

# scrypt cost: about 50 ms and 16 MB per hash, the interactive-login setting from the scrypt paper.
_N, _R, _P = 2**14, 8, 1


class Account(BaseModel):
    id: str
    email: str
    # False for an account made with Google: it has no password of its own.
    has_password: bool = True


class AccountError(ValueError):
    """A sign-up or sign-in that cannot go through, with a message for the learner."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        found = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p)
        )
    except ValueError:
        return False
    return hmac.compare_digest(found.hex(), digest)


# Checked against when the email is unknown, so a sign-in takes as long whether or not the account exists.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email or len(email) > 254:
        raise AccountError("Enter a valid email address.")
    return email


class AccountStore:
    def __init__(self, file: Path) -> None:
        file.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(file, check_same_thread=False)
        self._lock = threading.Lock()
        self._path_locks: dict[str, threading.Lock] = {}
        with self._lock, self._db:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS paths (
                    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                    path TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL, created_at TEXT NOT NULL);
                """)
            columns = {
                row[1] for row in self._db.execute("PRAGMA table_info(accounts)")
            }
            if "google_sub" not in columns:  # databases made before sign-in with Google
                self._db.execute("ALTER TABLE accounts ADD COLUMN google_sub TEXT")
            self._db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS accounts_google ON accounts (google_sub)"
            )

    # Accounts and sessions

    def sign_up(self, email: str, password: str) -> tuple[Account, str]:
        """A new account and a session token for it."""
        email = normalize_email(email)
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise AccountError(
                f"Use a password of at least {MIN_PASSWORD_LENGTH} characters."
            )
        account = Account(id=uuid4().hex, email=email)
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT INTO accounts (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (account.id, email, hash_password(password), _now().isoformat()),
                )
        except sqlite3.IntegrityError as error:
            raise AccountError(
                "An account with this email already exists. Sign in instead."
            ) from error
        return account, self._new_session(account.id)

    def sign_in(self, email: str, password: str) -> tuple[Account, str]:
        try:
            email = normalize_email(email)
        except AccountError:
            email = ""
        with self._lock:
            row = self._db.execute(
                "SELECT id, email, password_hash FROM accounts WHERE email = ?",
                (email,),
            ).fetchone()
        # An unknown email is checked against a dummy hash, so the answer takes as long either way.
        matches = password_matches(
            password[:MAX_PASSWORD_LENGTH], row[2] if row else _DUMMY_HASH
        )
        if row is None or not matches:
            raise AccountError("The email or the password is wrong.")
        return Account(id=row[0], email=row[1]), self._new_session(row[0])

    def sign_in_with_google(self, subject: str, email: str) -> tuple[Account, str]:
        """The account of a Google user, made on their first sign-in, and a session token for it.

        `subject` is Google's id for the user, which stays when they change their address. An account that
        signed up with a password and the same address becomes the Google user's: Google has verified that the
        address is theirs."""
        email = normalize_email(email)
        with self._lock, self._db:
            row = (
                self._db.execute(
                    "SELECT id FROM accounts WHERE google_sub = ?", (subject,)
                ).fetchone()
                or self._db.execute(
                    "SELECT id FROM accounts WHERE email = ?", (email,)
                ).fetchone()
            )
            if row is None:
                account_id = uuid4().hex
                self._db.execute(
                    "INSERT INTO accounts (id, email, password_hash, created_at, google_sub)"
                    " VALUES (?, ?, '', ?, ?)",
                    (account_id, email, _now().isoformat(), subject),
                )
            else:
                account_id = row[0]
                self._db.execute(
                    "UPDATE accounts SET google_sub = ? WHERE id = ?",
                    (subject, account_id),
                )
        account = self._account(account_id)
        assert account is not None  # nosec B101: just written
        return account, self._new_session(account_id)

    def account_by_id(self, account_id: str) -> Account | None:
        return self._account(account_id)

    def _account(self, account_id: str) -> Account | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id, email, password_hash FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        return (
            Account(id=row[0], email=row[1], has_password=bool(row[2])) if row else None
        )

    def account_for(self, token: str | None) -> Account | None:
        """The account a session token belongs to, while the session lasts."""
        if not token:
            return None
        with self._lock:
            row = self._db.execute(
                "SELECT accounts.id, accounts.email, accounts.password_hash FROM sessions JOIN accounts"
                " ON accounts.id = sessions.account_id"
                " WHERE token_hash = ? AND expires_at > ?",
                (_token_hash(token), _now().isoformat()),
            ).fetchone()
        return (
            Account(id=row[0], email=row[1], has_password=bool(row[2])) if row else None
        )

    def sign_out(self, token: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),)
            )

    def delete(self, account: Account, confirmation: str) -> None:
        """Deletes the account, its sessions and its path. `confirmation` is the account's password, or, for an
        account made with Google, which has none, its email address typed again."""
        with self._lock:
            row = self._db.execute(
                "SELECT email, password_hash FROM accounts WHERE id = ?", (account.id,)
            ).fetchone()
        if row is None:
            raise AccountError("This account no longer exists.")
        email, stored = row
        if stored and not password_matches(confirmation, stored):
            raise AccountError("The password is wrong.")
        if not stored and confirmation.strip().lower() != email:
            raise AccountError("Type your email address to confirm.")
        with self._lock, self._db:
            for table, column in (
                ("sessions", "account_id"),
                ("paths", "account_id"),
                ("accounts", "id"),
            ):
                self._db.execute(
                    f"DELETE FROM {table} WHERE {column} = ?",  # nosec B608: fixed names
                    (account.id,),
                )

    def _new_session(self, account_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = _now()
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),)
            )
            self._db.execute(
                "INSERT INTO sessions (token_hash, account_id, expires_at) VALUES (?, ?, ?)",
                (
                    _token_hash(token),
                    account_id,
                    (now + timedelta(days=SESSION_DAYS)).isoformat(),
                ),
            )
        return token

    # Paths

    def path_of(self, account: Account) -> LearningPath | None:
        with self._lock:
            row = self._db.execute(
                "SELECT path FROM paths WHERE account_id = ?", (account.id,)
            ).fetchone()
        return LearningPath.model_validate_json(row[0]) if row else None

    def save_path(self, account: Account, path: LearningPath | None) -> None:
        with self._lock, self._db:
            if path is None:
                self._db.execute(
                    "DELETE FROM paths WHERE account_id = ?", (account.id,)
                )
            else:
                self._db.execute(
                    "INSERT INTO paths (account_id, path, updated_at) VALUES (?, ?, ?)"
                    " ON CONFLICT (account_id) DO UPDATE"
                    " SET path = excluded.path, updated_at = excluded.updated_at",
                    (account.id, path.model_dump_json(), _now().isoformat()),
                )

    @contextmanager
    def changing_path(self, account: Account) -> Iterator[None]:
        """Holds the account's path while one request changes it, so that two requests at once (two tabs)
        do not overwrite each other. Other accounts are not held up, even while a model call runs.
        """
        with self._lock:
            lock = self._path_locks.setdefault(account.id, threading.Lock())
        with lock:
            yield

    def change_path(
        self, account: Account, change: Callable[[LearningPath], LearningPath]
    ) -> LearningPath:
        """Applies `change` to the stored path and stores the result. Raises LookupError without a path."""
        with self.changing_path(account):
            path = self.path_of(account)
            if path is None:
                raise LookupError("You have no path yet. Plan one first.")
            changed = change(path)
            self.save_path(account, changed)
            return changed

    # Drafts: paths planned before signing in

    def keep_draft(self, path: LearningPath) -> str:
        draft_id = path.id or uuid4().hex
        now = _now()
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM drafts WHERE created_at <= ?",
                ((now - timedelta(hours=DRAFT_HOURS)).isoformat(),),
            )
            self._db.execute(
                "INSERT OR REPLACE INTO drafts (id, path, created_at) VALUES (?, ?, ?)",
                (draft_id, path.model_dump_json(), now.isoformat()),
            )
        return draft_id

    def draft(self, draft_id: str) -> LearningPath | None:
        cutoff = (_now() - timedelta(hours=DRAFT_HOURS)).isoformat()
        with self._lock:
            row = self._db.execute(
                "SELECT path FROM drafts WHERE id = ? AND created_at > ?",
                (draft_id, cutoff),
            ).fetchone()
        return LearningPath.model_validate_json(row[0]) if row else None

    def claim_draft(self, account: Account, draft_id: str) -> LearningPath | None:
        """Makes the draft the account's path, replacing any path it had. None if the draft is gone."""
        with self.changing_path(account):
            path = self.draft(draft_id)
            if path is None:
                return None
            self.save_path(account, path)
            with self._lock, self._db:
                self._db.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
            return path
