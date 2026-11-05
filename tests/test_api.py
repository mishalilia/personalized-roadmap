from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import FakeLLM, study_all

from roadmap import Choice, Curriculum, LearningPath, Roadmap
from roadmap.api import Edition, RateLimiter, create_app
from roadmap.checkpoints import Checkpoint, CheckpointQuestion, CodingProblem
from roadmap.events import EventLog
from roadmap.llm import LLMUnavailable

SITE = "https://curriculum.example"
TERMINAL = "basics/terminal"
ASSESSMENT = {
    "level": "beginner",
    "evidence": ["Finished an introductory Python course last month"],
    "confidence": "medium",
}
PROBLEM = CodingProblem(
    title="Double",
    prompt="Write `double(x)`.",
    starter_code="def double(x):\n    ...\n",
    tests="assert double(2) == 4\n",
    solution="def double(x):\n    return 2 * x\n",
)


def terminal_checkpoint(
    version: str, problem: CodingProblem | None = None
) -> Checkpoint:
    """Ten questions whose right answer is always the second option as written."""
    return Checkpoint(
        module_id=TERMINAL,
        curriculum_version=version,
        generated_by="test",
        questions=[
            CheckpointQuestion(
                id=f"q{n}",
                topic=f"Topic {n % 2}",
                text=f"Question {n}?",
                options=["a", "b", "c", "d"],
                answer=1,
                explanation="Because.",
            )
            for n in range(1, 11)
        ],
        problem=problem,
    )


def client_for(
    *roadmaps: Roadmap,
    limit: int = 100,
    problem: CodingProblem | None = None,
    events: EventLog | None = None,
    token: str | None = None,
) -> TestClient:
    editions = [
        Edition(
            roadmap,
            {TERMINAL: terminal_checkpoint(roadmap.curriculum.version, problem)},
        )
        for roadmap in roadmaps
    ]
    app = create_app(editions, [SITE], RateLimiter(limit, window=3600), events, token)
    return TestClient(app)


def older(curriculum: Curriculum) -> Curriculum:
    return curriculum.model_copy(
        update={"version": "older", "site_version": "2026-01-01"}
    )


def confirmed_path(client: TestClient, choices: dict[str, str] | None = None) -> dict:
    path = client.post(
        "/path", json={"answers": {"goal": "Computer vision"}, "level": None}
    ).json()
    for item in path["items"]:
        item["choice"] = (choices or {}).get(item["module"]["id"], item["choice"])
    return client.post("/path/confirm", json={"path": path}).json()


def answer(client: TestClient, path: dict, attempt: int, right: int) -> dict:
    """Answers the attempt's questions as shown, `right` of them correctly."""
    asked = client.get(
        f"/checkpoints/{TERMINAL}",
        params={"attempt": attempt, "version": path["curriculum_version"]},
    ).json()
    answers = {
        question["id"]: (
            question["options"].index("b")
            if index < right
            else question["options"].index("a")
        )
        for index, question in enumerate(asked["questions"])
    }
    return client.post(
        f"/attempts/{TERMINAL}",
        json={"path": path, "attempt": attempt, "answers": answers},
    ).json()


# Questions, level and path


def test_questions_come_with_the_curriculum_versions(curriculum, questions):
    client = client_for(
        Roadmap(
            curriculum.model_copy(update={"site_version": "current"}),
            questions,
            llm=None,
        ),
        Roadmap(older(curriculum), questions, llm=None),
    )

    body = client.get("/questions").json()

    assert [question["id"] for question in body["questions"]] == [
        q.id for q in questions
    ]
    assert body["curriculum"]["site_version"] == "current"
    assert [v["site_version"] for v in body["versions"]] == ["current", "2026-01-01"]
    assert body["personalization_available"] is False


def test_a_level_and_a_path_for_the_level_the_learner_chose(
    curriculum, questions, module_ids
):
    llm = FakeLLM(ASSESSMENT, study_all(curriculum))
    client = client_for(Roadmap(curriculum, questions, llm))
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
    assert not path.confirmed and path.answers == answers and path.id


def test_without_a_model_the_level_is_left_to_the_learner_and_the_path_is_the_course(
    curriculum, questions
):
    llm = FakeLLM(LLMUnavailable("rate limited"), LLMUnavailable("rate limited"))
    client = client_for(Roadmap(curriculum, questions, llm))
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
def test_answers_are_checked_before_any_model_call(curriculum, questions, answers):
    llm = FakeLLM()
    client = client_for(Roadmap(curriculum, questions, llm))

    response = client.post("/level", json={"answers": answers})

    assert response.status_code == 422
    assert llm.prompts == []


def test_model_calls_are_limited_per_client(curriculum, questions):
    client = client_for(Roadmap(curriculum, questions, llm=None), limit=2)
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


def test_only_the_allowed_site_may_call_from_a_browser(curriculum, questions):
    client = client_for(Roadmap(curriculum, questions, llm=None))

    allowed = client.get("/questions", headers={"Origin": SITE})
    other = client.get("/questions", headers={"Origin": "https://elsewhere.example"})

    assert allowed.headers.get("access-control-allow-origin") == SITE
    assert "access-control-allow-origin" not in other.headers


# Curriculum versions


def test_new_paths_use_the_newest_version_and_older_paths_keep_working(
    curriculum, questions
):
    old_roadmap = Roadmap(older(curriculum), questions, llm=None)
    client = client_for(Roadmap(curriculum, questions, llm=None), old_roadmap)
    old_path = (
        old_roadmap.build_path({"goal": "x"}, None).confirm().model_dump(mode="json")
    )

    new_path = confirmed_path(client)
    done = client.post(
        "/path/done", json={"path": old_path, "module_id": "basics/algebra"}
    )
    retired = client.post(
        "/path/done",
        json={
            "path": old_path | {"curriculum_version": "retired"},
            "module_id": "basics/algebra",
        },
    )

    assert new_path["curriculum_version"] == curriculum.version
    assert done.status_code == 200 and done.json()["curriculum_version"] == "older"
    assert retired.status_code == 409


# Checkpoints


def test_questions_are_sent_without_answers_and_with_options_shuffled_per_attempt(
    curriculum, questions
):
    client = client_for(Roadmap(curriculum, questions, llm=None), problem=PROBLEM)

    listed = client.get("/checkpoints").json()
    first = client.get(f"/checkpoints/{TERMINAL}", params={"attempt": 0}).json()
    third = client.get(f"/checkpoints/{TERMINAL}", params={"attempt": 2}).json()

    assert listed == {
        TERMINAL: {
            "status": "draft",
            "questions_per_attempt": 5,
            "pass_mark": 4,  # nosec B105: a score, not a password
            "has_problem": True,
        }
    }
    assert all("answer" not in q and "explanation" not in q for q in first["questions"])
    assert [q["id"] for q in first["questions"]] == [
        q["id"] for q in third["questions"]
    ]
    assert [q["options"] for q in first["questions"]] != [
        q["options"] for q in third["questions"]
    ]
    assert client.get("/checkpoints/basics/algebra").status_code == 404


def test_a_failed_attempt_hides_the_answers_and_locks_the_rest_until_a_retake_passes(
    curriculum, questions
):
    client = client_for(Roadmap(curriculum, questions, llm=None))
    path = confirmed_path(client, {TERMINAL: "prove"})

    failed = answer(client, path, attempt=0, right=2)

    assert failed["grade"]["score"] == 2 and not failed["grade"]["passed"]
    assert all(
        f["answer"] is None and f["explanation"] is None
        for f in failed["grade"]["feedback"]
    )
    assert failed["grade"]["review_topics"]
    after = failed["path"]
    assert after["blocking_module_id"] == TERMINAL
    assert "basics/algebra" in after["locked_module_ids"]
    assert after["items"][0]["choice"] == "study"  # a failed "prove" becomes "study"
    locked = client.post(
        "/path/done", json={"path": after, "module_id": "basics/algebra"}
    )
    assert locked.status_code == 409

    passed = answer(client, after, attempt=1, right=5)

    assert passed["grade"]["passed"] and not passed["grade"]["effortless"]
    assert all(f["explanation"] == "Because." for f in passed["grade"]["feedback"])
    assert passed["path"]["locked_module_ids"] == []


def test_an_attempt_must_follow_the_last_one_and_the_path_must_be_confirmed(
    curriculum, questions
):
    client = client_for(Roadmap(curriculum, questions, llm=None))
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


def test_a_coding_problem_follows_the_questions_before_the_module_counts_as_passed(
    curriculum, questions
):
    client = client_for(Roadmap(curriculum, questions, llm=None), problem=PROBLEM)
    path = confirmed_path(client)
    too_early = client.post(f"/problems/{TERMINAL}/solved", json={"path": path})

    after = answer(client, path, attempt=0, right=5)
    problem = client.get(f"/problems/{TERMINAL}").json()
    solved = client.post(f"/problems/{TERMINAL}/solved", json={"path": after["path"]})

    assert too_early.status_code == 409
    assert after["grade"]["problem_pending"]
    assert after["path"]["items"][0]["progress"] == "practice"
    assert "solution" not in problem and problem["tests"] == "assert double(2) == 4"
    assert solved.json()["items"][0]["progress"] == "passed"


def test_a_module_without_a_checkpoint_is_marked_done_and_suggestions_are_answered(
    curriculum, questions
):
    client = client_for(Roadmap(curriculum, questions, llm=None))
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


# Goal change


def test_a_new_goal_replans_what_is_not_started_and_asks_for_confirmation(
    curriculum, questions
):
    llm = FakeLLM(
        study_all(curriculum),
        study_all(
            curriculum,
            except_for={
                TERMINAL: (Choice.SKIP, "Not needed for speech."),
                "tracks/speech/resources": (Choice.STUDY, "The new goal."),
                "tracks/vision/resources": (Choice.SKIP, "No longer the goal."),
            },
        ),
    )
    client = client_for(Roadmap(curriculum, questions, llm))
    path = confirmed_path(client)
    started = answer(client, path, attempt=0, right=4)["path"]

    changed = client.post(
        "/path/goal", json={"path": started, "goal": "Speech recognition"}
    ).json()

    choices = {item["module"]["id"]: item["choice"] for item in changed["items"]}
    assert choices[TERMINAL] == "study"  # started, so kept
    assert choices["tracks/vision/resources"] == "skip"
    assert changed["answers"]["goal"] == "Speech recognition"
    assert changed["confirmed_at"] is None
    assert "changed their goal to: Speech recognition" in llm.prompts[-1]


def test_without_a_model_the_goal_cannot_change_and_the_path_stays(
    curriculum, questions
):
    client = client_for(Roadmap(curriculum, questions, llm=None))
    path = confirmed_path(client)

    response = client.post(
        "/path/goal", json={"path": path, "goal": "Speech recognition"}
    )

    assert response.status_code == 503


# Shared progress and the report


def test_only_shared_paths_are_counted_and_the_report_needs_its_token(
    tmp_path: Path, curriculum, questions
):
    events = EventLog(tmp_path / "events.sqlite")
    client = client_for(
        Roadmap(curriculum, questions, llm=None),
        events=events,
        token="secret",  # nosec B106: a test token
    )
    private = confirmed_path(client)
    shared_draft = client.post(
        "/path", json={"answers": {"goal": "Computer vision"}, "level": None}
    ).json()
    shared = client.post(
        "/path/confirm", json={"path": shared_draft | {"share_progress": True}}
    ).json()

    answer(client, private, attempt=0, right=1)
    failed = answer(client, shared, attempt=0, right=1)["path"]
    answer(client, failed, attempt=1, right=5)

    report = client.get("/report", headers={"Authorization": "Bearer secret"}).json()
    terminal, algebra = report["modules"][0], report["modules"][1]
    assert report["paths"] == 1
    assert (terminal["included"], terminal["finished"], terminal["failed_once"]) == (
        1,
        1,
        1,
    )
    assert terminal["stopped_here"] == 0 and algebra["stopped_here"] == 1
    assert client.get("/report").status_code == 403
    assert (
        client.get("/report", headers={"Authorization": "Bearer wrong"}).status_code
        == 403
    )


def test_invented_example_learners_are_offered_for_demos(curriculum, questions):
    from helpers import ROOT

    from roadmap import load_profiles

    profiles = load_profiles(ROOT / "config" / "profiles.yaml")
    editions = [Edition(Roadmap(curriculum, questions, llm=None), {})]
    client = TestClient(
        create_app(editions, [SITE], RateLimiter(10, window=60), profiles=profiles)
    )

    body = client.get("/profiles").json()

    assert [profile["id"] for profile in body] == ["p1", "p2", "p3"]
    assert set(body[0]["answers"]) <= {question.id for question in questions}
