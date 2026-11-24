from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roadmap import Roadmap
from roadmap.accounts import AccountStore
from roadmap.api import Edition, RateLimiter, create_app
from roadmap.llm import LLMUnavailable
from roadmap.submissions import MAX_ARCHIVE_BYTES, SubmissionStore
from helpers import FakeLLM
from test_project_review import model_review, project

SITE = "https://curriculum.example"
PROJECT = "tracks/vision/capstone"
PASSWORD = "correct horse battery"  # nosec B105  # pragma: allowlist secret
REVIEWER = "reviewer@example.com"


def zipped() -> bytes:
    """Bytes that start like a zip file: the server checks only that, and never opens the archive."""
    return b"PK\x03\x04" + b"a zipped project"


def site_with(tmp_path: Path, curriculum, questions, *answers):  # type: ignore[no-untyped-def]
    """A site whose model gives these answers in turn; planning takes the first."""
    accounts = AccountStore(tmp_path / "accounts.sqlite")
    submissions = SubmissionStore(tmp_path / "accounts.sqlite", tmp_path / "uploads")
    llm = FakeLLM(LLMUnavailable("no planning in these tests"), *answers)
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=llm), {})],
        [SITE],
        RateLimiter(100, window=3600),
        accounts=accounts,
        submissions=submissions,
        reviewers={REVIEWER},
        review_runs=1,
    )

    def browser(email: str) -> TestClient:
        client = TestClient(app, base_url="https://testserver")
        client.post("/auth/sign-up", json={"email": email, "password": PASSWORD})
        return client

    return browser, tmp_path / "uploads"


@pytest.fixture
def site(tmp_path: Path, curriculum, questions):
    # The model never answers: every submission is kept, then comes back unreviewed.
    return site_with(tmp_path, curriculum, questions, *[LLMUnavailable("busy")] * 20)


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


def test_a_reviewer_sees_the_models_decision_and_can_change_it(
    tmp_path, curriculum, questions
):
    not_shown = {
        "name": "Testing",
        "about": "behaviour",
        "verdict": "not_met",
        "evidence": [],
        "comment": "No results.",
    }
    browser, uploads = site_with(
        tmp_path,
        curriculum,
        questions,
        model_review(not_shown, feedback="Add results."),
    )
    learner = learner_with_path(browser)
    reviewer = browser(REVIEWER)

    sent = learner.post(
        f"/me/submissions/{PROJECT}",
        data={"note": "See the README."},
        files={"archive": ("../../detector.tar.gz", project(), "application/gzip")},
    ).json()

    submission = learner.get(f"/me/submissions/{PROJECT}").json()
    assert submission["status"] == "returned" and submission["reviewed_by"] == "model"
    assert (
        submission["file_name"] == "detector.tar.gz"
        and len(list(uploads.iterdir())) == 1
    )
    assert progress(learner) == "returned"
    queue = reviewer.get("/review/submissions").json()
    assert queue["waiting"] == []
    assert [s["id"] for s in queue["reviewed"]] == [sent["id"]]
    assert (
        queue["reviewed"][0]["ai_review"]["levels"][0]["criteria"][0]["name"]
        == "Testing"
    )

    download = reviewer.get(f"/submissions/{sent['id']}/archive")
    assert download.content == project()
    assert download.headers["content-type"] == "application/octet-stream"
    assert "attachment" in download.headers["content-disposition"]

    accepted = reviewer.post(
        f"/review/submissions/{sent['id']}",
        json={"accept": True, "comment": "The results are in the video."},
    )
    assert (
        accepted.json()["status"] == "accepted"
        and accepted.json()["reviewed_by"] == REVIEWER
    )
    assert progress(learner) == "done"


def test_without_a_model_nothing_is_submitted(tmp_path, curriculum, questions):
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=None), {})],
        [SITE],
        RateLimiter(100, window=3600),
        accounts=AccountStore(tmp_path / "a.sqlite"),
        submissions=SubmissionStore(tmp_path / "a.sqlite", tmp_path / "uploads"),
    )
    client = TestClient(app, base_url="https://testserver")
    client.post(
        "/auth/sign-up", json={"email": "learner@example.com", "password": PASSWORD}
    )
    client.post("/path", json={"answers": {"goal": "Computer vision"}, "level": None})
    client.post("/me/path/confirm")

    refused = client.post(
        f"/me/submissions/{PROJECT}", data={"link": "https://github.com/l/detector"}
    )

    assert (
        refused.status_code == 503
        and "nothing was submitted" in refused.json()["detail"]
    )
    assert progress(client) == "not_started"
    assert list((tmp_path / "uploads").iterdir()) == []


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
