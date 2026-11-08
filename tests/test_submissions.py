from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roadmap import Roadmap
from roadmap.accounts import AccountStore
from roadmap.api import Edition, RateLimiter, create_app
from roadmap.submissions import MAX_ARCHIVE_BYTES, SubmissionStore

SITE = "https://curriculum.example"
PROJECT = "tracks/vision/capstone"
PASSWORD = "correct horse battery"  # nosec B105  # pragma: allowlist secret
REVIEWER = "reviewer@example.com"


def zipped() -> bytes:
    """Bytes that start like a zip file: the server checks only that, and never opens the archive."""
    return b"PK\x03\x04" + b"a zipped project"


@pytest.fixture
def site(tmp_path: Path, curriculum, questions):
    accounts = AccountStore(tmp_path / "accounts.sqlite")
    submissions = SubmissionStore(tmp_path / "accounts.sqlite", tmp_path / "uploads")
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=None), {})],
        [SITE],
        RateLimiter(100, window=3600),
        accounts=accounts,
        submissions=submissions,
        reviewers={REVIEWER},
    )

    def browser(email: str) -> TestClient:
        client = TestClient(app, base_url="https://testserver")
        client.post("/auth/sign-up", json={"email": email, "password": PASSWORD})
        return client

    return browser, tmp_path / "uploads"


def learner_with_path(browser) -> TestClient:
    client = browser("learner@example.com")
    client.post("/path", json={"answers": {"goal": "Computer vision"}, "level": None})
    client.post("/me/path/confirm")
    return client


def progress(client: TestClient, module_id: str = PROJECT) -> str:
    path = client.get("/me/path").json()
    return next(i for i in path["items"] if i["module"]["id"] == module_id)["progress"]


def test_a_capstone_is_a_project_and_cannot_just_be_marked_done(site):
    browser, _ = site
    client = learner_with_path(browser)

    path = client.get("/me/path").json()
    done = client.post("/me/path/done", json={"module_id": PROJECT})

    projects = [i["module"]["id"] for i in path["items"] if i["module"]["is_project"]]
    assert projects == [PROJECT]
    assert done.status_code == 409


def test_a_project_is_submitted_reviewed_and_returned_or_accepted(site):
    browser, uploads = site
    learner = learner_with_path(browser)
    reviewer = browser(REVIEWER)

    sent = learner.post(
        f"/me/submissions/{PROJECT}",
        data={"link": "https://github.com/learner/detector", "note": "See the README."},
        files={"archive": ("../../detector.zip", zipped(), "application/zip")},
    )

    assert sent.status_code == 200, sent.text
    submission = sent.json()
    assert (
        submission["status"] == "submitted"
        and submission["file_name"] == "detector.zip"
    )
    assert progress(learner) == "submitted"
    assert len(list(uploads.iterdir())) == 1
    queue = reviewer.get("/review/submissions").json()
    assert [s["email"] for s in queue["waiting"]] == ["learner@example.com"]

    download = reviewer.get(f"/submissions/{submission['id']}/archive")
    assert download.content == zipped()
    assert download.headers["content-type"] == "application/octet-stream"
    assert "attachment" in download.headers["content-disposition"]

    returned = reviewer.post(
        f"/review/submissions/{submission['id']}",
        json={"accept": False, "comment": "Add the evaluation numbers."},
    )
    assert returned.json()["status"] == "returned"
    assert progress(learner) == "returned"

    again = learner.post(
        f"/me/submissions/{PROJECT}",
        data={"link": "https://github.com/learner/detector"},
    ).json()
    assert len(list(uploads.iterdir())) == 0  # the replaced archive is gone
    reviewer.post(f"/review/submissions/{again['id']}", json={"accept": True})
    assert progress(learner) == "done"


@pytest.mark.parametrize(
    "form",
    [
        {"data": {}},
        {"data": {"link": "javascript:alert(1)"}},
        {"data": {"link": "file:///etc/passwd"}},
        {
            "files": {
                "archive": (
                    "project.exe",
                    b"MZ\x90\x00 not an archive",
                    "application/zip",
                )
            }
        },
    ],
)
def test_only_a_web_link_or_a_zip_or_gzip_archive_is_kept(site, form):
    browser, uploads = site
    client = learner_with_path(browser)

    response = client.post(f"/me/submissions/{PROJECT}", **form)

    assert response.status_code == 422
    assert list(uploads.iterdir()) == []


@pytest.mark.parametrize(
    ("extra", "status"),
    [
        (1024 * 1024, 413),  # refused by its declared size, before it is read
        (1, 422),  # just over: refused while it is copied, and the copy removed
    ],
)
def test_an_archive_over_the_limit_is_not_kept(site, extra, status):
    browser, uploads = site
    client = learner_with_path(browser)
    big = b"PK\x03\x04" + b"0" * (MAX_ARCHIVE_BYTES + extra)

    response = client.post(
        f"/me/submissions/{PROJECT}",
        files={"archive": ("big.zip", big, "application/zip")},
    )

    assert response.status_code == status
    assert list(uploads.iterdir()) == []


def test_only_the_learner_and_reviewers_see_a_submission(site):
    browser, _ = site
    learner = learner_with_path(browser)
    submission = learner.post(
        f"/me/submissions/{PROJECT}",
        files={"archive": ("p.zip", zipped(), "application/zip")},
    ).json()
    other = browser("other@example.com")

    assert other.get(f"/submissions/{submission['id']}/archive").status_code == 404
    assert other.get("/review/submissions").status_code == 403
    assert (
        other.post(
            f"/review/submissions/{submission['id']}", json={"accept": True}
        ).status_code
        == 403
    )
    assert learner.get(f"/submissions/{submission['id']}/archive").status_code == 200


def test_a_project_needs_a_confirmed_path_and_an_account(site):
    browser, _ = site
    client = browser("learner@example.com")
    client.post("/path", json={"answers": {"goal": "Computer vision"}, "level": None})
    anonymous = TestClient(client.app, base_url="https://testserver")
    link = {"link": "https://github.com/learner/detector"}

    assert client.post(f"/me/submissions/{PROJECT}", data=link).status_code == 409
    assert anonymous.post(f"/me/submissions/{PROJECT}", data=link).status_code == 401


def test_deleting_the_account_deletes_its_archives(site):
    browser, uploads = site
    client = learner_with_path(browser)
    client.post(
        f"/me/submissions/{PROJECT}",
        files={"archive": ("p.zip", zipped(), "application/zip")},
    )

    client.post("/auth/delete", json={"confirmation": PASSWORD})

    assert list(uploads.iterdir()) == []
