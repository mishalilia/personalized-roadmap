import io
import json
import tarfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import FakeLLM

from roadmap import Roadmap
from roadmap.accounts import AccountStore
from roadmap.api import Edition, RateLimiter, create_app
from roadmap.llm import LLMUnavailable
from roadmap.project_files import (
    MAX_FILE_BYTES,
    ProjectError,
    github_repository,
    read_archive,
    read_github,
)
from roadmap.project_review import ModelReview, judge
from roadmap.submissions import SubmissionStore

PROJECT = "tracks/vision/capstone"
PASSWORD = "correct horse battery"  # nosec B105  # pragma: allowlist secret

README = "# Card detector\n\nRun `python app.py` and open http://localhost:8000.\n"
APP = "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.post('/detect')\ndef detect(): ...\n"


def tar_gz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def project(**extra: bytes) -> bytes:
    """A small project as GitHub packs it: everything under one folder."""
    files = {
        "card-detector-abc123/README.md": README.encode(),
        "card-detector-abc123/app.py": APP.encode(),
    }
    files |= {f"card-detector-abc123/{name}": data for name, data in extra.items()}
    return tar_gz(files)


def model_review(*criteria: dict, feedback: str = "Good start.") -> dict:
    return {
        "levels": [{"name": "Sufficient", "passing": True, "criteria": list(criteria)}],
        "feedback": feedback,
    }


def met(name: str, file: str, quote: str, about: str = "artefact") -> dict:
    return {
        "name": name,
        "about": about,
        "verdict": "met",
        "evidence": [{"file": file, "quote": quote}],
        "comment": "Shown.",
    }


# Reading a project


def test_an_archive_is_read_as_text_without_its_folder_data_or_binaries():
    files = read_archive(
        project(
            **{
                "data/train.csv": b"a,b\n1,2\n",
                "node_modules/x/index.js": b"x",
                "model.pt": b"\x00\x01binary",
                "notebook.ipynb": json.dumps(
                    {
                        "cells": [
                            {
                                "cell_type": "code",
                                "source": ["import cv2\n"],
                                "outputs": [{"big": "x" * 999}],
                            }
                        ]
                    }
                ).encode(),
                "big.py": b"#" * (MAX_FILE_BYTES + 1),
            }
        )
    )

    assert list(files.texts)[0] == "README.md"  # the README comes first
    assert "app.py" in files.texts and "import cv2" in files.texts["notebook.ipynb"]
    assert "big" not in files.texts["notebook.ipynb"]  # outputs left out
    assert "model.pt" in files.tree and "model.pt" not in files.texts
    assert "big.py" in files.tree and "big.py" not in files.texts  # listed, not read
    assert not any(path.startswith(("data/", "node_modules/")) for path in files.tree)


def test_quotes_are_found_in_their_files_whatever_the_spacing():
    files = read_archive(project())

    assert files.contains("app.py", "@app.post('/detect')   def detect()")
    assert files.contains("app.py", "")  # the file exists
    assert not files.contains("app.py", "pytest")
    assert not files.contains("tests/test_app.py", "")


def test_a_file_that_is_no_archive_is_refused():
    with pytest.raises(ProjectError):
        read_archive(b"MZ not an archive")


@pytest.mark.parametrize(
    ("link", "repository"),
    [
        ("https://github.com/learner/card-detector", ("learner", "card-detector")),
        ("https://github.com/learner/card-detector.git", ("learner", "card-detector")),
        ("https://github.com/learner/card-detector/", ("learner", "card-detector")),
        ("https://gitlab.com/learner/card-detector", None),
        ("https://github.com.evil.example/learner/x", None),
        ("https://github.com/learner/card-detector/tree/main/src", None),
    ],
)
def test_only_github_repositories_are_read_from_links(link, repository):
    assert github_repository(link) == repository


def test_github_is_read_only_through_its_own_download_address():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={
                    "location": "https://codeload.github.com/learner/x/tar.gz/main"
                },
            )
        assert request.url.host == "codeload.github.com"
        return httpx.Response(200, content=project())

    def elsewhere(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "http://169.254.169.254/latest/meta-data"}
        )

    files = read_github(
        "learner", "x", httpx.Client(transport=httpx.MockTransport(handler))
    )

    assert "README.md" in files.texts
    with pytest.raises(ProjectError):
        read_github(
            "learner", "x", httpx.Client(transport=httpx.MockTransport(elsewhere))
        )


# Judging


def test_a_criterion_counts_only_with_evidence_that_is_in_the_files():
    files = read_archive(project())
    answer = ModelReview.model_validate(
        model_review(
            met("Documentation", "README.md", "Run `python app.py`"),
            met("Testing", "tests/test_app.py", "def test_detect"),  # no such file
        )
    )

    review = judge(answer, files)

    documentation, testing = review.levels[0].criteria
    assert documentation.counts and not testing.counts and testing.evidence_missing
    assert not review.passed and review.level is None


def test_a_project_passes_when_every_criterion_of_the_passing_level_holds():
    files = read_archive(project())
    answer = ModelReview.model_validate(
        model_review(
            met("Documentation", "README.md", "open http://localhost:8000"),
            met("Web UI", "app.py", "@app.post('/detect')"),
        )
    )

    review = judge(answer, files)

    assert review.passed and review.level == "Sufficient"


# Through the API


@pytest.fixture
def site(tmp_path: Path, curriculum, questions):
    def make(*answers, github=None):
        llm = FakeLLM(*answers)
        app = create_app(
            [Edition(Roadmap(curriculum, questions, llm=llm), {})],
            ["https://curriculum.example"],
            RateLimiter(100, window=3600),
            accounts=AccountStore(tmp_path / "accounts.sqlite"),
            submissions=SubmissionStore(
                tmp_path / "accounts.sqlite", tmp_path / "uploads"
            ),
            github=github,
            review_runs=1,
        )
        client = TestClient(app, base_url="https://testserver")
        client.post(
            "/auth/sign-up", json={"email": "learner@example.com", "password": PASSWORD}
        )
        return client, llm

    return make


def planned(client: TestClient) -> None:
    # Planning asks the model too; without a usable answer the path is the whole course.
    client.post("/path", json={"answers": {"goal": "Computer vision"}, "level": None})
    client.post("/me/path/confirm")


def progress(client: TestClient) -> str:
    items = client.get("/me/path").json()["items"]
    return next(i for i in items if i["module"]["id"] == PROJECT)["progress"]


def test_a_model_reviews_a_submitted_archive_and_the_path_follows(site):
    client, llm = site(
        LLMUnavailable("no planning in this test"),
        model_review(
            met("Documentation", "README.md", "Run `python app.py`"),
            feedback="Clear README.",
        ),
    )
    planned(client)

    sent = client.post(
        f"/me/submissions/{PROJECT}",
        files={"archive": ("detector.tar.gz", project(), "application/gzip")},
    )

    assert sent.json()["status"] == "reviewing"
    # TestClient runs the background review before it returns.
    after = client.get(f"/me/submissions/{PROJECT}").json()
    assert after["status"] == "accepted" and after["reviewed_by"] == "model"
    assert after["ai_review"]["passed"] and after["review_comment"] == "Clear README."
    assert progress(client) == "done"
    assert "<<<FILE README.md>>>" in llm.prompts[-1]


def test_a_project_without_the_evidence_is_sent_back_with_the_feedback(site):
    client, _ = site(
        LLMUnavailable("no planning in this test"),
        model_review(
            met("Testing", "tests/test_app.py", "def test_detect"),
            feedback="Add tests.",
        ),
    )
    planned(client)

    client.post(
        f"/me/submissions/{PROJECT}",
        files={"archive": ("detector.tar.gz", project(), "application/gzip")},
    )

    after = client.get(f"/me/submissions/{PROJECT}").json()
    assert after["status"] == "returned" and after["review_comment"] == "Add tests."
    assert after["ai_review"]["levels"][0]["criteria"][0]["evidence_missing"]
    assert progress(client) == "returned"


def test_a_link_the_review_cannot_read_is_refused_at_once(site):
    client, llm = site(LLMUnavailable("no planning in this test"))
    planned(client)

    refused = client.post(
        f"/me/submissions/{PROJECT}", data={"link": "https://my-demo.example"}
    )

    assert refused.status_code == 422 and "GitHub" in refused.json()["detail"]
    assert client.get(f"/me/submissions/{PROJECT}").json() is None
    assert progress(client) == "not_started"
    assert len(llm.prompts) == 1  # planning only: no model call for the review


def test_a_repository_that_cannot_be_read_is_the_learners_error_not_a_review(site):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client, llm = site(
        LLMUnavailable("no planning in this test"),
        github=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    planned(client)

    client.post(
        f"/me/submissions/{PROJECT}", data={"link": "https://github.com/l/private"}
    )

    after = client.get(f"/me/submissions/{PROJECT}").json()
    assert after["status"] == "failed" and after["review_comment"].startswith(
        "Your project could not be read"
    )
    assert after["reviewed_by"] is None
    assert (
        progress(client) == "not_started"
    )  # as before the submission: the learner submits again
    assert len(llm.prompts) == 1


def test_without_a_usable_answer_the_learner_is_told_and_nobody_else_is_asked(site):
    client, _ = site(LLMUnavailable("no planning"), LLMUnavailable("rate limited"))
    planned(client)

    client.post(
        f"/me/submissions/{PROJECT}",
        files={"archive": ("detector.tar.gz", project(), "application/gzip")},
    )

    after = client.get(f"/me/submissions/{PROJECT}").json()
    assert (
        after["status"] == "failed"
        and "nothing was sent to anyone" in after["review_comment"]
    )
    assert progress(client) == "not_started"


def test_a_public_github_repository_is_reviewed_from_its_link(site):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={"location": "https://codeload.github.com/l/card/tar.gz/main"},
            )
        return httpx.Response(200, content=project())

    client, _ = site(
        LLMUnavailable("no planning in this test"),
        model_review(met("Web UI", "app.py", "@app.post('/detect')")),
        github=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    planned(client)

    client.post(
        f"/me/submissions/{PROJECT}", data={"link": "https://github.com/l/card"}
    )

    after = client.get(f"/me/submissions/{PROJECT}").json()
    assert after["status"] == "accepted"
    assert after["ai_review"]["source"] == "https://github.com/l/card"


def test_several_reviews_count_a_criterion_by_majority():
    from roadmap.project_review import combine

    files = read_archive(project())
    readme = met("Documentation", "README.md", "Run `python app.py`")
    missing = {
        "name": "Documentation",
        "about": "artefact",
        "verdict": "not_met",
        "evidence": [],
        "comment": "No.",
    }
    reviews = [
        judge(
            ModelReview.model_validate(model_review(readme, feedback="Passed.")), files
        ),
        judge(
            ModelReview.model_validate(model_review(missing, feedback="Failed.")), files
        ),
        judge(
            ModelReview.model_validate(model_review(readme, feedback="Passed.")), files
        ),
    ]

    combined = combine(reviews)
    one_of_three = combine([reviews[1], reviews[0], reviews[1]])

    criterion = combined.levels[0].criteria[0]
    assert combined.passed and combined.runs == 3 and criterion.votes == "2/3"
    assert criterion.counts and combined.feedback == "Passed."
    assert not one_of_three.passed and one_of_three.feedback == "Failed."
    assert one_of_three.levels[0].criteria[0].votes == "1/3"


# What the code produced, and what its author wrote


NOTEBOOK = json.dumps(
    {
        "cells": [
            {
                "cell_type": "code",
                "source": ["detect('card.jpg')\n"],
                "outputs": [
                    {
                        "output_type": "stream",
                        "text": ["corners: [(12, 30), (410, 28)]\n"],
                    },
                    {"output_type": "display_data", "data": {"image/png": "iVBOR..."}},
                ],
            },
            {
                "cell_type": "code",
                "source": ["1 / 0"],
                "outputs": [
                    {
                        "output_type": "error",
                        "ename": "ZeroDivisionError",
                        "evalue": "division by zero",
                    },
                ],
            },
        ]
    }
).encode()


def test_notebook_outputs_and_result_files_are_read_as_program_output():
    files = read_archive(
        project(
            **{
                "demo.ipynb": NOTEBOOK,
                "results/eval.csv": b"image,iou\ncard.jpg,0.93\n",
                "logs/run.log": b"processed 12 images in 4.1 s\n",
                "notes.md": b"It works on 12 images.\n",
            }
        )
    )

    assert files.outputs == {"demo.ipynb (outputs)", "results/eval.csv", "logs/run.log"}
    assert "corners: [(12, 30), (410, 28)]" in files.texts["demo.ipynb (outputs)"]
    assert "[image/png output]" in files.texts["demo.ipynb (outputs)"]
    assert "ZeroDivisionError: division by zero" in files.texts["demo.ipynb (outputs)"]
    assert (
        "corners" not in files.texts["demo.ipynb"]
    )  # the cells, apart from what they printed
    assert "<<<PROGRAM OUTPUT logs/run.log>>>" in files.prompt()
    assert "<<<FILE notes.md>>>" in files.prompt()


def test_behaviour_counts_only_with_what_the_code_produced():
    files = read_archive(
        project(
            **{
                "logs/run.log": b"processed 12 images in 4.1 s\n",
                "notes.md": b"Works on 12 images.\n",
            }
        )
    )
    on_its_word = met(
        "Works on 10+ images", "notes.md", "Works on 12 images.", about="behaviour"
    )
    from_its_output = met(
        "Works on 10+ images", "logs/run.log", "processed 12 images", about="behaviour"
    )

    claimed = judge(ModelReview.model_validate(model_review(on_its_word)), files)
    shown = judge(ModelReview.model_validate(model_review(from_its_output)), files)

    assert not claimed.passed and claimed.levels[0].criteria[0].output_missing
    assert shown.passed and shown.outputs == ["logs/run.log"]


def test_the_assistant_sees_why_a_project_came_back(site):
    client, llm = site(
        LLMUnavailable("no planning in this test"),
        model_review(
            met("Testing", "tests/test_app.py", "def test_detect"),
            feedback="Add tests.",
        ),
        {"reply": "Add a tests folder with a test for /detect.", "modules": []},
    )
    planned(client)
    client.post(
        f"/me/submissions/{PROJECT}",
        files={"archive": ("detector.tar.gz", project(), "application/gzip")},
    )

    reply = client.post("/me/chat", json={"question": "Why was my project returned?"})

    assert reply.status_code == 200, reply.text
    sent = llm.prompts[-1]
    assert "State: sent back" in sent and "Feedback: Add tests." in sent
    assert (
        "Missing to pass: Testing (not counted: the quoted evidence is not in their files)"
        in sent
    )
    assert "archive detector.tar.gz" in sent
