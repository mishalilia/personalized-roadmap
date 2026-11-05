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
