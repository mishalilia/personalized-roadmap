from datetime import timedelta
from pathlib import Path

import pytest

from roadmap import Roadmap
from roadmap import accounts as accounts_module
from roadmap.accounts import AccountError, AccountStore, password_matches

PASSWORD = "correct horse battery"  # nosec B105  # pragma: allowlist secret


def test_neither_passwords_nor_session_tokens_are_stored_as_they_are(tmp_path: Path):
    file = tmp_path / "accounts.sqlite"
    store = AccountStore(file)

    account, token = store.sign_up("a@example.com", PASSWORD)

    with store._db.transaction() as tx:  # everything kept, whichever database keeps it
        queries = [f"SELECT * FROM {t}" for t in ("accounts", "sessions")]  # nosec B608
        content = repr([tx.execute(query).fetchall() for query in queries])
    assert PASSWORD not in content and token not in content
    assert store.account_for(token) == account
    assert store.account_for("forged token") is None


def test_a_password_hash_matches_only_its_password():
    stored = accounts_module.hash_password(PASSWORD)

    assert password_matches(PASSWORD, stored)
    assert not password_matches(PASSWORD + "!", stored)
    assert not password_matches(PASSWORD, "not a hash")


def test_sessions_and_drafts_expire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, curriculum, questions
):
    store = AccountStore(tmp_path / "accounts.sqlite")
    _, token = store.sign_up("a@example.com", PASSWORD)
    draft_id = store.keep_draft(
        Roadmap(curriculum, questions, llm=None).build_path({}, None)
    )
    later = accounts_module._now() + timedelta(days=accounts_module.SESSION_DAYS)
    monkeypatch.setattr(accounts_module, "_now", lambda: later)

    assert store.account_for(token) is None
    assert store.draft(draft_id) is None


def test_an_account_needs_its_own_email(tmp_path: Path):
    store = AccountStore(tmp_path / "accounts.sqlite")
    store.sign_up("a@example.com", PASSWORD)

    with pytest.raises(AccountError):
        store.sign_up("A@EXAMPLE.COM", PASSWORD)


def test_a_password_needs_six_characters(tmp_path: Path):
    store = AccountStore(tmp_path / "accounts.db")

    with pytest.raises(AccountError, match="at least 6"):
        store.sign_up("short@example.com", "12345")
    account, _ = store.sign_up("six@example.com", "123456")

    assert account.email == "six@example.com"
