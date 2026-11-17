from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import FakeLLM, study_all

from roadmap import Choice, Curriculum, LearningPath, Roadmap
from roadmap.accounts import AccountStore
from roadmap.path import Proposal
from roadmap.api import SESSION_COOKIE, Edition, RateLimiter, create_app
from roadmap.checkpoints import Checkpoint, CheckpointQuestion, CodingProblem
from roadmap.events import EventLog
from roadmap.llm import LLMUnavailable

SITE = "https://curriculum.example"
TERMINAL = "basics/terminal"
ALGEBRA = "basics/algebra"
PASSWORD = "correct horse battery"  # nosec B105  # pragma: allowlist secret
WRONG = "not the password"  # nosec B105  # pragma: allowlist secret
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


class Site:
    """The API as browsers reach it: each `learner()` is another browser, with its own cookies."""

    def __init__(
        self,
        *roadmaps: Roadmap,
        limit: int = 100,
        problem: CodingProblem | None = None,
        events: EventLog | None = None,
        token: str | None = None,
        reviewers: set[str] | None = None,
    ) -> None:
        editions = [
            Edition(
                roadmap,
                {TERMINAL: terminal_checkpoint(roadmap.curriculum.version, problem)},
            )
            for roadmap in roadmaps
        ]
        self.accounts = AccountStore(Path(":memory:"))
        self.app = create_app(
            editions,
            [SITE],
            RateLimiter(limit, window=3600),
            events,
            token,
            accounts=self.accounts,
            reviewers=reviewers,
        )

    def learner(self) -> TestClient:
        # HTTPS, as in production: the session cookie is sent over HTTPS only.
        return TestClient(self.app, base_url="https://testserver")

    def signed_in(self, email: str = "learner@example.com") -> TestClient:
        client = self.learner()
        response = client.post(
            "/auth/sign-up", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        return client


def site_for(*roadmaps: Roadmap, **options) -> Site:  # type: ignore[no-untyped-def]
    return Site(*roadmaps, **options)


def older(curriculum: Curriculum) -> Curriculum:
    return curriculum.model_copy(
        update={"version": "older", "site_version": "2026-01-01"}
    )


def plan(client: TestClient) -> dict:
    response = client.post(
        "/path", json={"answers": {"goal": "Computer vision"}, "level": None}
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirmed_path(client: TestClient, choices: dict[str, str] | None = None) -> dict:
    plan(client)
    for module_id, choice in (choices or {}).items():
        client.post("/me/path/choice", json={"module_id": module_id, "choice": choice})
    return client.post("/me/path/confirm").json()


def answer(client: TestClient, attempt: int, right: int) -> dict:
    """Answers the attempt's questions as shown, `right` of them correctly."""
    path = client.get("/me/path").json()
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
        f"/me/attempts/{TERMINAL}", json={"attempt": attempt, "answers": answers}
    ).json()


def item(path: dict, module_id: str) -> dict:
    return next(i for i in path["items"] if i["module"]["id"] == module_id)


# Questions, level and path


def test_questions_come_with_the_curriculum_versions(curriculum, questions):
    client = site_for(
        Roadmap(
            curriculum.model_copy(update={"site_version": "current"}),
            questions,
            llm=None,
        ),
        Roadmap(older(curriculum), questions, llm=None),
    ).learner()

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
    client = site_for(Roadmap(curriculum, questions, llm)).signed_in()
    answers = {"programming": "One month of Python"}

    assessment = client.post("/level", json={"answers": answers}).json()["assessment"]
    response = client.post(
        "/path",
        json={"answers": answers, "level": "intermediate", "assessment": assessment},
    )

    path = LearningPath.model_validate(response.json()["path"])
    assert response.json()["draft_id"] is None  # kept for the account instead
    assert path.level == "intermediate"
    assert path.assessment is not None and path.assessment.level == "beginner"
    assert [item.module.id for item in path.items] == module_ids
    assert all(item.choice is Choice.STUDY for item in path.items)
    assert not path.confirmed and path.answers == answers and path.id
    assert client.get("/me/path").json()["id"] == path.id


def test_without_a_model_the_level_is_left_to_the_learner_and_the_path_is_the_course(
    curriculum, questions
):
    llm = FakeLLM(LLMUnavailable("rate limited"), LLMUnavailable("rate limited"))
    client = site_for(Roadmap(curriculum, questions, llm)).learner()
    answers = {"goal": "Computer vision"}

    level = client.post("/level", json={"answers": answers})
    path = client.post("/path", json={"answers": answers, "level": None})

    assert level.status_code == 200 and level.json()["assessment"] is None
    assert (
        path.status_code == 200 and path.json()["path"]["personalization_unavailable"]
    )


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
    client = site_for(Roadmap(curriculum, questions, llm)).learner()

    response = client.post("/level", json={"answers": answers})

    assert response.status_code == 422
    assert llm.prompts == []


def test_model_calls_are_limited_per_client(curriculum, questions):
    client = site_for(Roadmap(curriculum, questions, llm=None), limit=2).learner()
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
    client = site_for(Roadmap(curriculum, questions, llm=None)).signed_in()

    allowed = client.get("/questions", headers={"Origin": SITE})
    other = client.get("/questions", headers={"Origin": "https://elsewhere.example"})
    forged = client.post(
        "/me/path/reset", headers={"Origin": "https://elsewhere.example"}
    )

    assert allowed.headers.get("access-control-allow-origin") == SITE
    assert allowed.headers.get("access-control-allow-credentials") == "true"
    assert "access-control-allow-origin" not in other.headers
    assert forged.status_code == 403


# Accounts


def test_a_path_planned_before_signing_up_is_kept_by_the_new_account(
    curriculum, questions
):
    site = site_for(Roadmap(curriculum, questions, llm=None))
    browser = site.learner()

    planned = plan(browser)
    without_account = browser.post("/me/path/confirm")
    draft = browser.get(f"/drafts/{planned['draft_id']}")
    signed_up = browser.post(
        "/auth/sign-up",
        json={
            "email": " Learner@Example.com ",
            "password": PASSWORD,
            "draft_id": planned["draft_id"],
        },
    )

    assert planned["draft_id"] == planned["path"]["id"]
    assert without_account.status_code == 401
    assert draft.json()["id"] == planned["path"]["id"]
    assert signed_up.json()["account"]["email"] == "learner@example.com"
    assert signed_up.json()["path"]["id"] == planned["path"]["id"]
    assert browser.get("/me/path").json()["id"] == planned["path"]["id"]
    # The draft became the account's path, so nobody else can take it.
    assert browser.get(f"/drafts/{planned['draft_id']}").status_code == 404


def test_the_session_cookie_is_http_only_and_signing_out_ends_it(curriculum, questions):
    site = site_for(Roadmap(curriculum, questions, llm=None))
    browser = site.learner()

    response = browser.post(
        "/auth/sign-up", json={"email": "a@example.com", "password": PASSWORD}
    )
    cookie = response.headers["set-cookie"]
    token = browser.cookies[SESSION_COOKIE]
    browser.post("/auth/sign-out")

    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert site.accounts.account_for(token) is None
    assert browser.get("/auth/session").json() == {"account": None, "path": None}
    assert browser.get("/me/path").status_code == 401


def test_signing_in_again_finds_the_path_and_wrong_passwords_are_refused(
    curriculum, questions
):
    site = site_for(Roadmap(curriculum, questions, llm=None))
    first = site.signed_in("a@example.com")
    path = confirmed_path(first)

    other_browser = site.learner()
    wrong = other_browser.post(
        "/auth/sign-in", json={"email": "a@example.com", "password": WRONG}
    )
    unknown = other_browser.post(
        "/auth/sign-in", json={"email": "b@example.com", "password": PASSWORD}
    )
    right = other_browser.post(
        "/auth/sign-in", json={"email": "A@example.com", "password": PASSWORD}
    )
    again = other_browser.post(
        "/auth/sign-up", json={"email": "a@example.com", "password": PASSWORD}
    )

    assert wrong.status_code == 401 and unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]
    assert right.json()["path"]["id"] == path["id"]
    assert again.status_code == 422


@pytest.mark.parametrize(
    "credentials",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "a@example.com", "password": PASSWORD[:5]},
    ],
)
def test_sign_up_needs_an_email_and_a_long_enough_password(
    curriculum, questions, credentials
):
    client = site_for(Roadmap(curriculum, questions, llm=None)).learner()

    assert client.post("/auth/sign-up", json=credentials).status_code == 422


def test_sign_in_attempts_are_limited(curriculum, questions):
    client = site_for(Roadmap(curriculum, questions, llm=None)).learner()
    wrong = {"email": "a@example.com", "password": WRONG}

    statuses = [client.post("/auth/sign-in", json=wrong).status_code for _ in range(11)]

    assert statuses[:10] == [401] * 10 and statuses[10] == 429


def test_deleting_the_account_deletes_its_path(curriculum, questions):
    site = site_for(Roadmap(curriculum, questions, llm=None))
    client = site.signed_in("a@example.com")
    confirmed_path(client)

    wrong = client.post("/auth/delete", json={"confirmation": WRONG})
    deleted = client.post("/auth/delete", json={"confirmation": PASSWORD})
    sign_in = site.learner().post(
        "/auth/sign-in", json={"email": "a@example.com", "password": PASSWORD}
    )

    assert wrong.status_code == 401
    assert deleted.status_code == 200
    assert client.get("/me/path").status_code == 401
    assert sign_in.status_code == 401


def test_each_learner_sees_only_their_own_path(curriculum, questions):
    site = site_for(Roadmap(curriculum, questions, llm=None))
    first, second = site.signed_in("a@example.com"), site.signed_in("b@example.com")

    path = confirmed_path(first)

    assert second.get("/me/path").json() is None
    assert first.get("/me/path").json()["id"] == path["id"]


# Decisions


def test_the_learners_own_decision_replaces_the_suggestion_and_asks_for_confirmation(
    curriculum, questions
):
    client = site_for(Roadmap(curriculum, questions, llm=None)).signed_in()
    confirmed_path(client)

    changed = client.post(
        "/me/path/choice", json={"module_id": ALGEBRA, "choice": "skip"}
    ).json()
    unprovable = client.post(
        "/me/path/choice",
        json={"module_id": "tracks/vision/capstone", "choice": "prove"},
    )
    unknown = client.post(
        "/me/path/choice", json={"module_id": "nowhere", "choice": "skip"}
    )

    assert item(changed, ALGEBRA)["choice"] == "skip"
    assert item(changed, ALGEBRA)["suggested"] == "study"
    assert changed["confirmed_at"] is None
    assert unprovable.status_code == 422
    assert unknown.status_code == 404


# Curriculum versions


def test_new_paths_use_the_newest_version_and_older_paths_keep_working(
    curriculum, questions
):
    old_roadmap = Roadmap(older(curriculum), questions, llm=None)
    site = site_for(Roadmap(curriculum, questions, llm=None), old_roadmap)
    new_learner, old_learner, retired_learner = (
        site.signed_in("new@example.com"),
        site.signed_in("old@example.com"),
        site.signed_in("retired@example.com"),
    )
    old_path = old_roadmap.build_path({"goal": "x"}, None).confirm()
    site.accounts.save_path(
        site.accounts.sign_in("old@example.com", PASSWORD)[0], old_path
    )
    site.accounts.save_path(
        site.accounts.sign_in("retired@example.com", PASSWORD)[0],
        old_path.model_copy(update={"curriculum_version": "retired"}),
    )

    new_path = confirmed_path(new_learner)
    done = old_learner.post("/me/path/done", json={"module_id": ALGEBRA})
    retired = retired_learner.post("/me/path/done", json={"module_id": ALGEBRA})

    assert new_path["curriculum_version"] == curriculum.version
    assert done.status_code == 200 and done.json()["curriculum_version"] == "older"
    assert retired.status_code == 409


# Checkpoints


def test_questions_are_sent_without_answers_and_with_options_shuffled_per_attempt(
    curriculum, questions
):
    client = site_for(
        Roadmap(curriculum, questions, llm=None), problem=PROBLEM
    ).learner()

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
    client = site_for(Roadmap(curriculum, questions, llm=None)).signed_in()
    confirmed_path(client, {TERMINAL: "prove"})

    failed = answer(client, attempt=0, right=2)

    assert failed["grade"]["score"] == 2 and not failed["grade"]["passed"]
    assert all(
        f["answer"] is None and f["explanation"] is None
        for f in failed["grade"]["feedback"]
    )
    assert failed["grade"]["review_topics"]
    after = failed["path"]
    assert after["blocking_module_id"] == TERMINAL
    assert ALGEBRA in after["locked_module_ids"]
    assert (
        item(after, TERMINAL)["choice"] == "study"
    )  # a failed "prove" becomes "study"
    locked = client.post("/me/path/done", json={"module_id": ALGEBRA})
    assert locked.status_code == 409

    passed = answer(client, attempt=1, right=5)

    assert passed["grade"]["passed"] and not passed["grade"]["effortless"]
    assert all(f["explanation"] == "Because." for f in passed["grade"]["feedback"])
    assert passed["path"]["locked_module_ids"] == []


def test_attempts_follow_the_stored_path_so_an_old_one_cannot_be_replayed(
    curriculum, questions
):
    client = site_for(Roadmap(curriculum, questions, llm=None)).signed_in()
    plan(client)

    unconfirmed = client.post(
        f"/me/attempts/{TERMINAL}",
        json={"attempt": 0, "answers": {f"q{n}": 1 for n in range(1, 6)}},
    )
    client.post("/me/path/confirm")
    answer(client, attempt=0, right=1)
    replayed = client.post(
        f"/me/attempts/{TERMINAL}",
        json={"attempt": 0, "answers": {f"q{n}": 1 for n in range(1, 6)}},
    )

    assert unconfirmed.status_code == 409
    assert replayed.status_code == 409
    assert item(client.get("/me/path").json(), TERMINAL)["progress"] == "failed"


def test_progress_cannot_be_changed_without_an_account(curriculum, questions):
    client = site_for(Roadmap(curriculum, questions, llm=None)).learner()
    plan(client)

    for request in (
        client.post(f"/me/attempts/{TERMINAL}", json={"attempt": 0, "answers": {}}),
        client.post("/me/path/done", json={"module_id": ALGEBRA}),
        client.post(f"/me/problems/{TERMINAL}/solved"),
    ):
        assert request.status_code == 401


def test_a_coding_problem_follows_the_questions_before_the_module_counts_as_passed(
    curriculum, questions
):
    client = site_for(
        Roadmap(curriculum, questions, llm=None), problem=PROBLEM
    ).signed_in()
    confirmed_path(client)
    too_early = client.post(f"/me/problems/{TERMINAL}/solved")

    after = answer(client, attempt=0, right=5)
    problem = client.get(f"/problems/{TERMINAL}").json()
    solved = client.post(f"/me/problems/{TERMINAL}/solved")

    assert too_early.status_code == 409
    assert after["grade"]["problem_pending"]
    assert item(after["path"], TERMINAL)["progress"] == "practice"
    assert "solution" not in problem and problem["tests"] == "assert double(2) == 4"
    assert item(solved.json(), TERMINAL)["progress"] == "passed"


def test_a_module_without_a_checkpoint_is_marked_done_and_suggestions_are_answered(
    curriculum, questions
):
    site = site_for(Roadmap(curriculum, questions, llm=None))
    client = site.signed_in("a@example.com")
    confirmed_path(client)
    account = site.accounts.sign_in("a@example.com", PASSWORD)[0]
    site.accounts.change_path(
        account,
        lambda path: path.with_proposals(
            [Proposal(module_id="tracks/notes", choice=Choice.SKIP, reason="Known.")]
        ),
    )

    done = client.post("/me/path/done", json={"module_id": ALGEBRA})
    with_checkpoint = client.post("/me/path/done", json={"module_id": TERMINAL})
    accepted = client.post("/me/path/accept", json={"module_id": "tracks/notes"})

    assert item(done.json(), ALGEBRA)["progress"] == "done"
    assert with_checkpoint.status_code == 409
    assert item(accepted.json(), "tracks/notes")["choice"] == "skip"
    assert accepted.json()["proposals"] == []


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
    client = site_for(Roadmap(curriculum, questions, llm)).signed_in()
    confirmed_path(client)
    answer(client, attempt=0, right=4)

    changed = client.post("/me/path/goal", json={"goal": "Speech recognition"}).json()

    choices = {item["module"]["id"]: item["choice"] for item in changed["items"]}
    assert choices[TERMINAL] == "study"  # started, so kept
    assert choices["tracks/vision/resources"] == "skip"
    assert changed["answers"]["goal"] == "Speech recognition"
    assert changed["confirmed_at"] is None
    assert "changed their goal to: Speech recognition" in llm.prompts[-1]


def test_without_a_model_the_goal_cannot_change_and_the_path_stays(
    curriculum, questions
):
    client = site_for(Roadmap(curriculum, questions, llm=None)).signed_in()
    path = confirmed_path(client)

    response = client.post("/me/path/goal", json={"goal": "Speech recognition"})

    assert response.status_code == 503
    assert client.get("/me/path").json()["confirmed_at"] == path["confirmed_at"]


# Shared progress and the report


def test_only_shared_paths_are_counted_and_the_report_needs_its_token(
    tmp_path: Path, curriculum, questions
):
    events = EventLog(tmp_path / "events.sqlite")
    site = site_for(
        Roadmap(curriculum, questions, llm=None),
        events=events,
        token="secret",  # nosec B106: a test token
    )
    private, shared = site.signed_in("a@example.com"), site.signed_in("b@example.com")
    confirmed_path(private)
    confirmed_path(shared)
    shared.post("/me/path/share", json={"share": True})

    answer(private, attempt=0, right=1)
    answer(shared, attempt=0, right=1)
    answer(shared, attempt=1, right=5)

    client = site.learner()
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


def test_reviewers_see_the_report_on_the_site_and_learners_do_not(
    tmp_path: Path, curriculum, questions
):
    site = site_for(
        Roadmap(curriculum, questions, llm=None),
        events=EventLog(tmp_path / "events.sqlite"),
        reviewers={"reviewer@example.com"},
    )
    learner = site.signed_in()
    confirmed_path(learner)
    learner.post("/me/path/share", json={"share": True})
    answer(learner, attempt=0, right=1)

    report = site.signed_in("reviewer@example.com").get("/review/report").json()

    assert report["paths"] == 1
    assert report["modules"][0]["title"]
    assert report["modules"][0]["failed_once"] == 1
    assert learner.get("/review/report").status_code == 403
    assert site.learner().get("/review/report").status_code in (401, 403)


def test_without_an_event_log_the_report_says_so(curriculum, questions):
    site = site_for(
        Roadmap(curriculum, questions, llm=None), reviewers={"reviewer@example.com"}
    )

    response = site.signed_in("reviewer@example.com").get("/review/report")

    assert response.status_code == 503


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


# The assistant in the path panel


def test_the_assistant_answers_from_the_learners_path_and_the_page_they_read(
    curriculum, questions
):
    llm = FakeLLM(
        study_all(
            curriculum, except_for={TERMINAL: (Choice.SKIP, "You use the shell daily.")}
        ),
        {
            "reply": "It is skipped because you use the shell daily.",
            "modules": [TERMINAL],
        },
    )
    client = site_for(Roadmap(curriculum, questions, llm)).signed_in()
    confirmed_path(client)

    response = client.post(
        "/me/chat",
        json={
            "question": "Why is the terminal module skipped?",
            "history": [
                {"speaker": "learner", "text": "Hi"},
                {"speaker": "assistant", "text": "Hello! Ask me about your path."},
            ],
            "module_id": TERMINAL,
        },
    )

    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["reply"] == "It is skipped because you use the shell daily."
    terminal = next(m for m in curriculum.modules if m.id == TERMINAL)
    assert reply["modules"] == [{"id": TERMINAL, "title": terminal.title}]
    prompt = llm.prompts[-1]
    assert f"[{TERMINAL}]" in prompt and "skip" in prompt
    assert "You use the shell daily." in prompt  # the planner's reason
    assert "# The module page they are reading now" in prompt
    assert "learner: Hi" in prompt
    assert prompt.rstrip().endswith("Why is the terminal module skipped?")


def test_module_ids_the_model_copies_into_the_reply_are_taken_out(
    curriculum, questions
):
    llm = FakeLLM(
        study_all(curriculum),
        {"reply": f"Next is Terminal [{TERMINAL}].", "modules": [TERMINAL]},
    )
    client = site_for(Roadmap(curriculum, questions, llm)).signed_in()
    confirmed_path(client)

    reply = client.post("/me/chat", json={"question": "What next?"}).json()

    assert reply["reply"] == "Next is Terminal."
    assert [module["id"] for module in reply["modules"]] == [TERMINAL]


def test_the_assistant_needs_an_account_a_path_and_a_model(curriculum, questions):
    question = {"question": "What next?"}
    with_model = site_for(
        Roadmap(curriculum, questions, FakeLLM(study_all(curriculum)))
    )
    assert with_model.learner().post("/me/chat", json=question).status_code == 401
    assert with_model.signed_in().post("/me/chat", json=question).status_code == 404

    without = site_for(Roadmap(curriculum, questions, llm=None)).signed_in()
    confirmed_path(without)
    assert without.post("/me/chat", json=question).status_code == 503


def test_an_answer_naming_a_module_the_path_lacks_is_not_shown(curriculum, questions):
    llm = FakeLLM(
        study_all(curriculum),
        {"reply": "Take Quantum Basics.", "modules": ["quantum/basics"]},
    )
    client = site_for(Roadmap(curriculum, questions, llm)).signed_in()
    confirmed_path(client)

    response = client.post("/me/chat", json={"question": "What should I add?"})

    assert response.status_code == 503


def test_questions_and_histories_are_bounded(curriculum, questions):
    client = site_for(
        Roadmap(curriculum, questions, FakeLLM(study_all(curriculum)))
    ).signed_in()
    confirmed_path(client)

    too_long = client.post("/me/chat", json={"question": "x" * 1001})
    too_many = client.post(
        "/me/chat",
        json={"question": "Hi", "history": [{"speaker": "learner", "text": "a"}] * 9},
    )
    empty = client.post("/me/chat", json={"question": "   "})

    assert {too_long.status_code, too_many.status_code, empty.status_code} == {422}


def test_the_assistant_sees_only_the_prerequisites_the_course_states(
    curriculum, questions
):
    llm = FakeLLM(study_all(curriculum), {"reply": "OpenCV basics.", "modules": []})
    client = site_for(Roadmap(curriculum, questions, llm)).signed_in()
    confirmed_path(client)

    client.post("/me/chat", json={"question": "What do I need for the capstone?"})

    prompt = llm.prompts[-1]
    assert (
        "Prerequisites, as the course states them: Python programming (intermediate level); "
        "Familiarity with NumPy arrays; OpenCV basics"
    ) in prompt
    assert prompt.count("Prerequisites, as the course states them") == 1
