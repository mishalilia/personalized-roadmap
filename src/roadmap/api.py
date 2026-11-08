"""HTTP API over the core, for interfaces that run in a browser, such as a page on the curriculum site.

The model keys stay on this server. The browser asks for the questions, a suggested level and a path. A
learner who signs up keeps their path here (roadmap.accounts), and every change to it, their decisions,
progress, locks and checkpoint grading, goes through this API and the path's rules: a learner cannot unlock
a module by editing their path, and the browser never holds checkpoint answers.

New paths are planned for the newest curriculum version; a path planned for an older listed version keeps
working against that version, so learners keep their progress when the course moves on.

Run it with `uvicorn roadmap.api:app`. Settings come from the environment or `.env`, as for the rest of the
core: API_ALLOWED_ORIGINS lists the sites that may call it, API_REPORT_TOKEN opens the progress report,
API_ACCOUNTS_FILE is where accounts and their paths are kept.
"""

import hmac
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from .accounts import (
    MAX_PASSWORD_LENGTH,
    SESSION_DAYS,
    Account,
    AccountError,
    AccountStore,
)
from .checkpoints import (
    PASS_MARK,
    QUESTIONS_PER_ATTEMPT,
    AskedQuestion,
    Checkpoint,
    CheckpointStore,
    Grade,
    Status,
)
from .config import Settings
from .curriculum import Level
from .events import EventKind, EventLog, Report
from .level import LevelAssessment
from .llm import LLMUnavailable
from .onboarding import LearnerProfile, load_profiles
from .path import Choice, LearningPath, PathStateError, Progress
from .service import Roadmap
from .source import CurriculumSource

logger = logging.getLogger(__name__)

MAX_ANSWER_LENGTH = 2000  # characters; a long answer costs quota and says no more

Answer = Annotated[str, StringConstraints(max_length=MAX_ANSWER_LENGTH)]
Goal = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=MAX_ANSWER_LENGTH
    ),
]


@dataclass(frozen=True)
class Edition:
    """One curriculum version as the API serves it: its roadmap and its checkpoints."""

    roadmap: Roadmap
    checkpoints: dict[str, Checkpoint]

    @property
    def version(self) -> str:
        return self.roadmap.curriculum.version


class QuestionOut(BaseModel):
    id: str
    text: str
    placeholder: str


class CurriculumInfo(BaseModel):
    version: str  # the pinned commit
    # The curriculum site's name for the version, such as "current" or "2026-10-06", so that a page on the
    # site can link a path's modules to the pages the planner saw.
    site_version: str | None
    title: str
    licence: str


class QuestionsResponse(BaseModel):
    questions: list[QuestionOut]
    curriculum: CurriculumInfo  # the version new paths are planned for
    versions: list[CurriculumInfo]  # every version whose paths the API still serves
    personalization_available: bool


class LevelRequest(BaseModel):
    answers: dict[str, Answer]


class LevelResponse(BaseModel):
    # None when no model answered; the learner then chooses a level themselves.
    assessment: LevelAssessment | None


class PathRequest(BaseModel):
    answers: dict[str, Answer]
    level: Level | None = Field(
        description="The level the learner chose, which may differ from the suggested one."
    )
    assessment: LevelAssessment | None = Field(
        default=None, description="The suggestion from /level, kept in the path."
    )


class CheckpointSummary(BaseModel):
    status: Status
    questions_per_attempt: int = QUESTIONS_PER_ATTEMPT
    pass_mark: int = PASS_MARK
    has_problem: bool = False


class CheckpointOut(BaseModel):
    module_id: str
    status: Status
    attempt: int
    pass_mark: int
    questions: list[AskedQuestion]


class ProblemOut(BaseModel):
    """A coding problem without its reference solution."""

    module_id: str
    title: str
    prompt: str
    starter_code: str
    tests: str
    packages: list[str]


class AttemptRequest(BaseModel):
    attempt: int = Field(ge=0)
    answers: dict[str, int]  # question id -> position of the chosen option, as shown


class AttemptResponse(BaseModel):
    grade: Grade
    path: LearningPath


class ModuleAction(BaseModel):
    module_id: str


class ChoiceRequest(BaseModel):
    module_id: str
    choice: Choice


class ShareRequest(BaseModel):
    share: bool


class GoalRequest(BaseModel):
    goal: Goal


class Credentials(BaseModel):
    email: Annotated[str, StringConstraints(max_length=254)]
    password: Annotated[str, StringConstraints(max_length=MAX_PASSWORD_LENGTH)]
    # A path planned before signing in, to keep as the account's path.
    draft_id: str | None = None


class PasswordRequest(BaseModel):
    password: Annotated[str, StringConstraints(max_length=MAX_PASSWORD_LENGTH)]


class AccountOut(BaseModel):
    email: str


class SessionResponse(BaseModel):
    account: AccountOut | None
    path: LearningPath | None = None


class PlannedPath(BaseModel):
    path: LearningPath
    # Set when the learner is not signed in: the path is kept for a day under this id, for them to sign up
    # or in and keep it.
    draft_id: str | None = None


class RateLimiter:
    """At most `limit` calls per client in any `window` seconds. In memory: one server process."""

    def __init__(
        self, limit: int, window: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = self._clock()
        with self._lock:
            calls = self._calls[client]
            while calls and now - calls[0] >= self._window:
                calls.popleft()
            if len(calls) >= self._limit:
                return False
            calls.append(now)
            return True


SESSION_COOKIE = "roadmap_session"


def create_app(
    editions: list[Edition],
    allowed_origins: list[str],
    limiter: RateLimiter,
    events: EventLog | None = None,
    report_token: str | None = None,
    profiles: list[LearnerProfile] | None = None,
    accounts: AccountStore | None = None,
    sign_in_limiter: RateLimiter | None = None,
    secure_cookies: bool = True,
) -> FastAPI:
    """`editions` newest first: new paths use the first. `profiles` are invented learners a demo can
    start from. `accounts` keeps learners' accounts and paths; in memory unless given.
    """
    newest = editions[0]
    by_version = {edition.version: edition for edition in editions}
    store = accounts or AccountStore(Path(":memory:"))
    sign_ins = sign_in_limiter or RateLimiter(10, 600)
    app = FastAPI(
        title="Personalized Roadmap API",
        description="Suggested levels and personal paths through the HumbleBeeAI Open Curriculum.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,  # the session cookie
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def same_site_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """A browser names the page that sent a request. Requests that change something are refused from
        any other site, so that another site cannot act with a learner's session."""
        origin = request.headers.get("origin")
        if (
            request.method == "POST"
            and origin is not None
            and origin not in allowed_origins
        ):
            return JSONResponse(
                {"detail": "Requests from this site are not allowed."}, 403
            )
        return await call_next(request)

    question_ids = {question.id for question in newest.roadmap.questions}

    def info(edition: Edition) -> CurriculumInfo:
        curriculum = edition.roadmap.curriculum
        return CurriculumInfo(
            version=curriculum.version,
            site_version=curriculum.site_version,
            title=curriculum.attribution.title,
            licence=curriculum.attribution.licence,
        )

    def check_answers(answers: dict[str, str]) -> dict[str, str]:
        if unknown := sorted(answers.keys() - question_ids):
            raise HTTPException(422, f"Unknown questions: {', '.join(unknown)}")
        if not any(answer.strip() for answer in answers.values()):
            raise HTTPException(422, "Answer at least one question.")
        return answers

    def client_of(request: Request) -> str:
        """Behind a reverse proxy, run uvicorn with --proxy-headers so that the client is the learner,
        not the proxy."""
        return request.client.host if request.client else "unknown"

    def within_quota(request: Request) -> None:
        """Model calls share a quota, so each client gets a share of it."""
        if not limiter.allow(client_of(request)):
            raise HTTPException(429, "Too many requests. Try again later.")

    def account_of(request: Request) -> Account | None:
        return store.account_for(request.cookies.get(SESSION_COOKIE))

    def signed_in(request: Request) -> Account:
        account = account_of(request)
        if account is None:
            raise HTTPException(401, "Sign in to keep a path and track your progress.")
        return account

    def start_session(response: Response, token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_DAYS * 24 * 3600,
            httponly=True,  # page scripts never see it
            secure=secure_cookies,
            samesite="lax",
        )

    def end_session(response: Response) -> None:
        response.delete_cookie(
            SESSION_COOKIE, httponly=True, secure=secure_cookies, samesite="lax"
        )

    def edition_of(path: LearningPath) -> Edition:
        if path.curriculum_version not in by_version:
            raise HTTPException(
                409,
                "This path was planned for a curriculum version that is no longer served. "
                "Plan a new one.",
            )
        return by_version[path.curriculum_version]

    def edition_named(version: str | None) -> Edition:
        if version is None:
            return newest
        for edition in editions:
            if version in (edition.version, edition.roadmap.curriculum.site_version):
                return edition
        raise HTTPException(404, f"Unknown curriculum version '{version}'")

    def checkpoint_of(edition: Edition, module_id: str) -> Checkpoint:
        if module_id not in edition.checkpoints:
            raise HTTPException(404, f"No checkpoint for '{module_id}'")
        return edition.checkpoints[module_id]

    def change(
        account: Account, action: Callable[[LearningPath], LearningPath]
    ) -> LearningPath:
        """Applies a change to the learner's stored path; the path's rules become HTTP errors."""
        try:
            return store.change_path(account, action)
        except LookupError as error:
            raise HTTPException(404, str(error.args[0])) from error
        except PathStateError as error:
            raise HTTPException(409, str(error)) from error
        except ValidationError as error:
            raise HTTPException(422, error.errors()[0]["msg"]) from error

    def record(
        path: LearningPath, kind: EventKind, module_id: str | None = None
    ) -> None:
        if events is not None:
            events.record(path, kind, module_id)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/questions")
    def questions() -> QuestionsResponse:
        return QuestionsResponse(
            questions=[
                QuestionOut(
                    id=question.id, text=question.text, placeholder=question.placeholder
                )
                for question in newest.roadmap.questions
            ],
            curriculum=info(newest),
            versions=[info(edition) for edition in editions],
            personalization_available=newest.roadmap.personalization_available,
        )

    @app.get("/profiles")
    def example_profiles() -> list[LearnerProfile]:
        """Invented example learners, not real people, whose answers a demo can start from."""
        return profiles or []

    # Accounts

    @app.get("/auth/session")
    def session(request: Request) -> SessionResponse:
        """Who is signed in, and their path."""
        account = account_of(request)
        if account is None:
            return SessionResponse(account=None)
        return SessionResponse(
            account=AccountOut(email=account.email), path=store.path_of(account)
        )

    def signed_in_response(
        response: Response, account: Account, token: str, draft_id: str | None
    ) -> SessionResponse:
        start_session(response, token)
        path = store.claim_draft(account, draft_id) if draft_id else None
        return SessionResponse(
            account=AccountOut(email=account.email),
            path=path or store.path_of(account),
        )

    def limit_sign_ins(request: Request) -> None:
        if not sign_ins.allow(client_of(request)):
            raise HTTPException(429, "Too many attempts. Try again in a few minutes.")

    @app.post("/auth/sign-up", dependencies=[Depends(limit_sign_ins)])
    def sign_up(body: Credentials, response: Response) -> SessionResponse:
        try:
            account, token = store.sign_up(body.email, body.password)
        except AccountError as error:
            raise HTTPException(422, str(error)) from error
        return signed_in_response(response, account, token, body.draft_id)

    @app.post("/auth/sign-in", dependencies=[Depends(limit_sign_ins)])
    def sign_in(body: Credentials, response: Response) -> SessionResponse:
        try:
            account, token = store.sign_in(body.email, body.password)
        except AccountError as error:
            raise HTTPException(401, str(error)) from error
        return signed_in_response(response, account, token, body.draft_id)

    @app.post("/auth/sign-out")
    def sign_out(request: Request, response: Response) -> SessionResponse:
        if token := request.cookies.get(SESSION_COOKIE):
            store.sign_out(token)
        end_session(response)
        return SessionResponse(account=None)

    @app.post("/auth/delete", dependencies=[Depends(limit_sign_ins)])
    def delete_account(
        body: PasswordRequest, request: Request, response: Response
    ) -> SessionResponse:
        """Deletes the account and its path. Shared progress events hold no account, so they stay."""
        account = signed_in(request)
        try:
            store.delete(account, body.password)
        except AccountError as error:
            raise HTTPException(401, str(error)) from error
        end_session(response)
        return SessionResponse(account=None)

    # Planning

    @app.post("/level", dependencies=[Depends(within_quota)])
    def level(body: LevelRequest) -> LevelResponse:
        return LevelResponse(
            assessment=newest.roadmap.assess_level(check_answers(body.answers))
        )

    @app.post("/path", dependencies=[Depends(within_quota)])
    def path(body: PathRequest, request: Request) -> PlannedPath:
        """Plans a path. A signed-in learner's path replaces the one they had; otherwise it is kept as a
        draft until they sign up or in."""
        planned = newest.roadmap.build_path(
            check_answers(body.answers), body.level, body.assessment
        )
        account = account_of(request)
        if account is None:
            return PlannedPath(path=planned, draft_id=store.keep_draft(planned))
        with store.changing_path(account):
            store.save_path(account, planned)
        return PlannedPath(path=planned)

    @app.get("/drafts/{draft_id}")
    def draft(draft_id: str) -> LearningPath:
        found = store.draft(draft_id)
        if found is None:
            raise HTTPException(404, "This draft has expired. Plan your path again.")
        return found

    # The signed-in learner's path

    @app.get("/me/path")
    def my_path(request: Request) -> LearningPath | None:
        return store.path_of(signed_in(request))

    @app.post("/me/path/reset")
    def reset(request: Request) -> None:
        account = signed_in(request)
        with store.changing_path(account):
            store.save_path(account, None)

    @app.post("/me/path/choice")
    def choose(body: ChoiceRequest, request: Request) -> LearningPath:
        """The learner's own decision for a module; the path asks for a new confirmation."""
        return change(
            signed_in(request),
            lambda path: path.with_choice(body.module_id, body.choice),
        )

    @app.post("/me/path/confirm")
    def confirm(request: Request) -> LearningPath:
        """The learner approves the path; if they share their progress, its modules are counted."""

        def confirmed(path: LearningPath) -> LearningPath:
            edition_of(path)
            return path.confirm()

        result = change(signed_in(request), confirmed)
        if events is not None:
            events.record_included(result)
        return result

    @app.post("/me/path/share")
    def share(body: ShareRequest, request: Request) -> LearningPath:
        """Counting starts from the modules of the confirmed path, so turning sharing on counts them."""
        result = change(
            signed_in(request),
            lambda path: path.model_copy(update={"share_progress": body.share}),
        )
        if body.share and result.confirmed and events is not None:
            events.record_included(result)
        return result

    @app.post("/me/path/goal", dependencies=[Depends(within_quota)])
    def goal(body: GoalRequest, request: Request) -> LearningPath:
        """The path replanned for a new goal; started modules keep their progress. The learner confirms
        it again."""

        def replanned(path: LearningPath) -> LearningPath:
            try:
                return edition_of(path).roadmap.change_goal(path, body.goal)
            except LLMUnavailable as error:
                raise HTTPException(
                    503,
                    "Replanning is unavailable right now. Your path has not changed.",
                ) from error

        result = change(signed_in(request), replanned)
        record(result, EventKind.GOAL_CHANGED)
        return result

    @app.post("/me/attempts/{module_id:path}")
    def attempt(
        module_id: str, body: AttemptRequest, request: Request
    ) -> AttemptResponse:
        """Grades an attempt against the stored path: locked modules, a "prove" turned into "study", or
        suggestions after a checkpoint passed without a mistake."""
        grades: list[Grade] = []

        def graded(path: LearningPath) -> LearningPath:
            edition = edition_of(path)
            found = checkpoint_of(edition, module_id)
            # The questions of an attempt follow from its number, which the stored path keeps.
            if body.attempt != path.item(module_id).attempts:
                raise HTTPException(
                    409, "This attempt does not follow your last one. Reload the page."
                )
            try:
                grade = found.grade(body.attempt, body.answers)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            if grade.effortless:
                within_quota(request)  # suggestions after it ask the model
            grades.append(grade)
            return edition.roadmap.after_checkpoint(path, module_id, grade)

        updated = change(signed_in(request), graded)
        record(
            updated,
            {
                Progress.FAILED: EventKind.FAILED,
                Progress.PRACTICE: EventKind.PRACTICE,
                Progress.PASSED: EventKind.FINISHED,
            }[updated.item(module_id).progress],
            module_id,
        )
        return AttemptResponse(grade=grades[0], path=updated)

    @app.post("/me/problems/{module_id:path}/solved")
    def solved(module_id: str, request: Request) -> LearningPath:
        """The learner's code passed the problem's tests in their browser. The server cannot run the
        learner's code safely, so it takes the browser's word for this one step; the questions before it
        are graded here."""

        def solved_in(path: LearningPath) -> LearningPath:
            if checkpoint_of(edition_of(path), module_id).problem is None:
                raise HTTPException(404, f"No coding problem for '{module_id}'")
            return path.with_problem_solved(module_id)

        updated = change(signed_in(request), solved_in)
        record(updated, EventKind.FINISHED, module_id)
        return updated

    @app.post("/me/path/done")
    def done(body: ModuleAction, request: Request) -> LearningPath:
        """Marks a module without a checkpoint as done."""

        def marked(path: LearningPath) -> LearningPath:
            if body.module_id in edition_of(path).checkpoints:
                raise HTTPException(
                    409, "This module has a checkpoint: pass it instead."
                )
            return path.marked_done(body.module_id)

        updated = change(signed_in(request), marked)
        record(updated, EventKind.FINISHED, body.module_id)
        return updated

    @app.post("/me/path/accept")
    def accept(body: ModuleAction, request: Request) -> LearningPath:
        return change(signed_in(request), lambda path: path.accept(body.module_id))

    @app.post("/me/path/decline")
    def decline(body: ModuleAction, request: Request) -> LearningPath:
        return change(signed_in(request), lambda path: path.decline(body.module_id))

    # Checkpoints

    @app.get("/checkpoints")
    def checkpoint_list(version: str | None = None) -> dict[str, CheckpointSummary]:
        """The modules of a curriculum version (the newest unless named) that have a checkpoint."""
        return {
            module_id: CheckpointSummary(
                status=checkpoint.status, has_problem=checkpoint.problem is not None
            )
            for module_id, checkpoint in edition_named(version).checkpoints.items()
        }

    @app.get("/checkpoints/{module_id:path}")
    def checkpoint(
        module_id: str, attempt: int = 0, version: str | None = None
    ) -> CheckpointOut:
        found = checkpoint_of(edition_named(version), module_id)
        return CheckpointOut(
            module_id=module_id,
            status=found.status,
            attempt=attempt,
            pass_mark=PASS_MARK,
            questions=found.asked(attempt),
        )

    @app.get("/problems/{module_id:path}")
    def problem(module_id: str, version: str | None = None) -> ProblemOut:
        found = checkpoint_of(edition_named(version), module_id).problem
        if found is None:
            raise HTTPException(404, f"No coding problem for '{module_id}'")
        return ProblemOut(
            module_id=module_id,
            title=found.title,
            prompt=found.prompt,
            starter_code=found.starter_code,
            tests=found.tests,
            packages=found.packages,
        )

    @app.get("/report")
    def report(
        version: str | None = None, authorization: str | None = Header(default=None)
    ) -> Report:
        """Where learners who share their progress stop, per module. Needs API_REPORT_TOKEN."""
        expected = f"Bearer {report_token}" if report_token else None
        if (
            events is None
            or expected is None
            or not hmac.compare_digest(authorization or "", expected)
        ):
            raise HTTPException(403, "The report needs the report token.")
        edition = edition_named(version)
        order = [module.id for module in edition.roadmap.curriculum.modules]
        return events.report(edition.version, order)

    return app


class ApiSettings(Settings):
    # Comma-separated origins allowed to call the API from a browser.
    api_allowed_origins: str = "http://localhost:3000"
    api_rate_limit: int = 20  # model-calling requests per client per window
    api_rate_window: int = 3600  # seconds
    api_report_token: str | None = None  # opens GET /report; no report without it
    # Accounts and their paths; data/accounts.sqlite unless set.
    api_accounts_file: Path | None = None
    # Send the session cookie over HTTPS only. Turn off only to try the API over plain HTTP.
    api_cookie_secure: bool = True

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.api_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def accounts_file(self) -> Path:
        return self.api_accounts_file or self.data_dir / "accounts.sqlite"


def load_editions(settings: Settings) -> list[Edition]:
    source = CurriculumSource.from_file(settings.curriculum_file)
    editions = []
    for version in source.versions:
        roadmap = Roadmap.from_settings(settings, version.name)
        store = CheckpointStore(settings.checkpoints_dir / version.name)
        editions.append(Edition(roadmap, store.all_for(roadmap.curriculum)))
    return editions


@lru_cache(maxsize=1)
def _app() -> FastAPI:
    settings = ApiSettings()
    return create_app(
        editions=load_editions(settings),
        allowed_origins=settings.allowed_origins,
        limiter=RateLimiter(settings.api_rate_limit, settings.api_rate_window),
        events=EventLog(settings.events_file),
        report_token=settings.api_report_token,
        profiles=load_profiles(settings.profiles_file),
        accounts=AccountStore(settings.accounts_file),
        secure_cookies=settings.api_cookie_secure,
    )


def __getattr__(name: str) -> FastAPI:
    """`roadmap.api:app` builds the app on first use, so importing this module reads no settings."""
    if name == "app":
        return _app()
    raise AttributeError(name)
