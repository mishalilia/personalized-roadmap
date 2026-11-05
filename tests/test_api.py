import pytest
from fastapi.testclient import TestClient
from helpers import ROOT, FakeLLM, study_all

from roadmap import Choice, LearningPath, Roadmap
from roadmap.api import RateLimiter, create_app
from roadmap.llm import LLMUnavailable
from roadmap.source import CurriculumSource

SITE = "https://curriculum.example"
ASSESSMENT = {
    "level": "beginner",
    "evidence": ["Finished an introductory Python course last month"],
    "confidence": "medium",
}


@pytest.fixture
def source() -> CurriculumSource:
    return CurriculumSource.from_file(ROOT / "config" / "curriculum.yaml")


def client_for(
    roadmap: Roadmap, source: CurriculumSource, limit: int = 100
) -> TestClient:
    app = create_app(roadmap, source, [SITE], RateLimiter(limit, window=3600))
    return TestClient(app)


def test_questions_come_with_the_curriculum_version(curriculum, questions, source):
    client = client_for(Roadmap(curriculum, questions, llm=None), source)

    body = client.get("/questions").json()

    assert [question["id"] for question in body["questions"]] == [
        question.id for question in questions
    ]
    assert body["curriculum"]["version"] == source.version
    assert body["curriculum"]["site_version"] == "2026-10-06"
    assert body["personalization_available"] is False


def test_a_level_and_a_path_for_the_level_the_learner_chose(
    curriculum, questions, source, module_ids
):
    llm = FakeLLM(ASSESSMENT, study_all(curriculum))
    client = client_for(Roadmap(curriculum, questions, llm), source)
    answers = {"programming": "One month of Python"}

    assessment = client.post("/level", json={"answers": answers}).json()["assessment"]
    response = client.post(
        "/path",
        json={"answers": answers, "level": "intermediate", "assessment": assessment},
    )

    path = LearningPath.model_validate(response.json())
    assert path.level == "intermediate"
    assert path.assessment is not None and path.assessment.level == "beginner"
    assert [item.module.id for item in path.items] == module_ids
    assert all(item.choice is Choice.STUDY for item in path.items)
    assert not path.confirmed


def test_without_a_model_the_level_is_left_to_the_learner_and_the_path_is_the_course(
    curriculum, questions, source
):
    llm = FakeLLM(LLMUnavailable("rate limited"), LLMUnavailable("rate limited"))
    client = client_for(Roadmap(curriculum, questions, llm), source)
    answers = {"goal": "Computer vision"}

    level = client.post("/level", json={"answers": answers})
    path = client.post("/path", json={"answers": answers, "level": None})

    assert level.status_code == 200 and level.json()["assessment"] is None
    assert path.status_code == 200 and path.json()["personalization_unavailable"]


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"programming": "   "},
        {"not_a_question": "Ten years of Rust"},
        {"programming": "x" * 2001},
    ],
)
def test_answers_are_checked_before_any_model_call(
    curriculum, questions, source, answers
):
    llm = FakeLLM()
    client = client_for(Roadmap(curriculum, questions, llm), source)

    response = client.post("/level", json={"answers": answers})

    assert response.status_code == 422
    assert llm.prompts == []


def test_model_calls_are_limited_per_client(curriculum, questions, source):
    client = client_for(Roadmap(curriculum, questions, llm=None), source, limit=2)
    request = {"answers": {"goal": "Computer vision"}, "level": None}

    statuses = [client.post("/path", json=request).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    assert client.get("/questions").status_code == 200  # costs no quota


def test_the_limit_frees_up_as_calls_age():
    now = [0.0]
    limiter = RateLimiter(limit=1, window=60, clock=lambda: now[0])

    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    now[0] = 60
    assert limiter.allow("a")


def test_only_the_allowed_site_may_call_from_a_browser(curriculum, questions, source):
    client = client_for(Roadmap(curriculum, questions, llm=None), source)

    allowed = client.get("/questions", headers={"Origin": SITE})
    other = client.get("/questions", headers={"Origin": "https://elsewhere.example"})

    assert allowed.headers.get("access-control-allow-origin") == SITE
    assert "access-control-allow-origin" not in other.headers


# Checkpoints: questions without answers, grading here, and the path that comes back.

from roadmap.checkpoints import Checkpoint, CheckpointQuestion  # noqa: E402

TERMINAL = "basics/terminal"


def terminal_checkpoint(version: str) -> Checkpoint:
    return Checkpoint(
        module_id=TERMINAL,
        curriculum_version=version,
        generated_by="test",
        questions=[
            CheckpointQuestion(
                id=f"q{n}",
                topic="Shell Basics",
                text=f"Question {n}?",
                options=["a", "b", "c", "d"],
                answer=1,
                explanation="Because.",
            )
            for n in range(1, 11)
        ],
    )


def checkpoint_client(roadmap: Roadmap, source: CurriculumSource) -> TestClient:
    app = create_app(
        roadmap,
        source,
        [SITE],
        RateLimiter(100, window=3600),
        checkpoints={TERMINAL: terminal_checkpoint(roadmap.curriculum.version)},
    )
    return TestClient(app)


def confirmed_path(client: TestClient, choices: dict[str, str] | None = None) -> dict:
    path = client.post(
        "/path", json={"answers": {"goal": "Computer vision"}, "level": None}
    ).json()
    for item in path["items"]:
        item["choice"] = (choices or {}).get(item["module"]["id"], item["choice"])
    path["confirmed_at"] = "2026-11-05T10:00:00Z"
    return path


def answer_all(client: TestClient, path: dict, attempt: int, right: int) -> dict:
    """Answers the attempt's questions, `right` of them correctly."""
    asked = client.get(f"/checkpoints/{TERMINAL}", params={"attempt": attempt}).json()
    answers = {
        question["id"]: 1 if index < right else 0
        for index, question in enumerate(asked["questions"])
    }
    return client.post(
        f"/attempts/{TERMINAL}",
        json={"path": path, "attempt": attempt, "answers": answers},
    ).json()


def test_questions_are_sent_without_their_answers(curriculum, questions, source):
    client = checkpoint_client(Roadmap(curriculum, questions, llm=None), source)

    listed = client.get("/checkpoints").json()
    asked = client.get(f"/checkpoints/{TERMINAL}").json()

    assert listed == {
        TERMINAL: {"status": "draft", "questions_per_attempt": 5, "pass_mark": 4}
    }
    assert len(asked["questions"]) == 5
    assert all("answer" not in q and "explanation" not in q for q in asked["questions"])
    assert client.get("/checkpoints/basics/algebra").status_code == 404


def test_a_failed_attempt_locks_the_rest_and_a_passed_retake_opens_it(
    curriculum, questions, source
):
    client = checkpoint_client(Roadmap(curriculum, questions, llm=None), source)
    path = confirmed_path(client, {TERMINAL: "prove"})

    failed = answer_all(client, path, attempt=0, right=2)

    assert failed["grade"]["score"] == 2 and not failed["grade"]["passed"]
    assert failed["grade"]["feedback"][4]["explanation"] == "Because."
    after = failed["path"]
    assert after["blocking_module_id"] == TERMINAL
    assert "basics/algebra" in after["locked_module_ids"]
    assert after["items"][0]["choice"] == "study"  # a failed "prove" becomes "study"
    locked = client.post(
        "/path/done", json={"path": after, "module_id": "basics/algebra"}
    )
    assert locked.status_code == 409

    passed = answer_all(client, after, attempt=1, right=5)

    assert passed["grade"]["passed"] and not passed["grade"]["effortless"]
    assert passed["path"]["locked_module_ids"] == []


def test_an_attempt_must_follow_the_last_one_and_the_path_must_be_confirmed(
    curriculum, questions, source
):
    client = checkpoint_client(Roadmap(curriculum, questions, llm=None), source)
    path = confirmed_path(client)

    out_of_turn = client.post(
        f"/attempts/{TERMINAL}", json={"path": path, "attempt": 1, "answers": {}}
    )
    unconfirmed = client.post(
        f"/attempts/{TERMINAL}",
        json={
            "path": path | {"confirmed_at": None},
            "attempt": 0,
            "answers": {f"q{n}": 1 for n in range(1, 6)},
        },
    )

    assert out_of_turn.status_code == 409
    assert unconfirmed.status_code == 409


def test_a_path_for_another_curriculum_version_is_refused(
    curriculum, questions, source
):
    client = checkpoint_client(Roadmap(curriculum, questions, llm=None), source)
    path = confirmed_path(client) | {"curriculum_version": "another"}

    response = client.post(
        "/path/done", json={"path": path, "module_id": "basics/algebra"}
    )

    assert response.status_code == 409


def test_a_module_without_a_checkpoint_is_marked_done_and_suggestions_are_answered(
    curriculum, questions, source
):
    client = checkpoint_client(Roadmap(curriculum, questions, llm=None), source)
    path = confirmed_path(client)
    path["proposals"] = [
        {"module_id": "tracks/notes", "choice": "skip", "reason": "Known."}
    ]

    done = client.post("/path/done", json={"path": path, "module_id": "basics/algebra"})
    with_checkpoint = client.post(
        "/path/done", json={"path": path, "module_id": TERMINAL}
    )
    accepted = client.post(
        "/path/accept", json={"path": path, "module_id": "tracks/notes"}
    )

    assert done.json()["items"][1]["progress"] == "done"
    assert with_checkpoint.status_code == 409
    notes = next(
        i for i in accepted.json()["items"] if i["module"]["id"] == "tracks/notes"
    )
    assert notes["choice"] == "skip" and accepted.json()["proposals"] == []
