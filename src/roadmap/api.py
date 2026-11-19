"""HTTP API over the core, for interfaces that run in a browser, such as a page on the curriculum site.

The model keys stay on this server. The browser asks for the questions, a suggested level and a path. A
learner who signs up keeps their path here (roadmap.accounts), and every change to it, their decisions,
progress, locks and checkpoint grading, goes through this API and the path's rules: a learner cannot unlock
a module by editing their path, and the browser never holds checkpoint answers.

New paths are planned for the newest curriculum version; a path planned for an older listed version keeps
working against that version, so learners keep their progress when the course moves on.

Run it with `uvicorn roadmap.api:app`. Settings come from the environment or `.env`, as for the rest of the
core: API_ALLOWED_ORIGINS lists the sites that may call it, API_REPORT_TOKEN opens the progress report,
API_ACCOUNTS_FILE is where accounts and their paths are kept, GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET turn
on sign-in with Google (roadmap.google).
"""

import hmac
import re
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, SecretStr, StringConstraints, ValidationError

from .accounts import (
    MAX_PASSWORD_LENGTH,
    SESSION_DAYS,
    Account,
    AccountError,
    AccountStore,
)
from .checkpoints import (
    PASS_MARK,
    CheckpointQuestion,
    QUESTIONS_PER_ATTEMPT,
    AskedQuestion,
    Checkpoint,
    CheckpointStore,
    Grade,
    Status,
)
from .config import Settings
from .curriculum import Level, Module
from .events import EventKind, EventLog, Report
from .google import FLOW_SECONDS, GoogleError, GoogleSignIn
from .level import LevelAssessment
from .llm import LLMClient, LLMUnavailable
from .onboarding import LearnerProfile, load_profiles
from .path import Choice, LearningPath, PathItem, PathStateError, Progress, TopicChoice
from .path_chat import CHATS_PER_DAY, ChatReply, ChatRequest, PathAssistant
from .project_files import (
    ProjectError,
    ProjectFiles,
    github_repository,
    read_archive,
    read_github,
)
from .project_review import ProjectReview, ProjectReviewer
from .question_reports import QuestionReport, QuestionReportIn, QuestionReportStore
from .service import Roadmap
from .submissions import (
    MAX_ARCHIVE_BYTES,
    MAX_NOTE_LENGTH,
    Status as SubmissionStatus,
    Submission,
    SubmissionError,
    SubmissionStore,
    check_link,
    safe_file_name,
    REVIEWS_PER_DAY,
)
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


class ReviewedQuestion(BaseModel):
    """A question of an attempt the learner passed, as they saw it, with the right option and why."""

    id: str
    topic: str
    text: str
    options: list[str]
    answer: int  # the position of the right option, as shown
    explanation: str


class ProblemOut(BaseModel):
    """A coding problem without its reference solution."""

    module_id: str
    title: str
    prompt: str
    starter_code: str
    tests: str
    packages: list[str]
    topic: str | None = None  # the module's topic it practises
    topic_anchor: str | None = None  # that topic's heading id on the module page, when it has one


class ReportedQuestion(QuestionReport):
    """A report as reviewers see it: with the question in full, its answer key and explanation."""

    module_title: str
    question: CheckpointQuestion | None  # None when the checkpoint no longer has this question


class ResolveRequest(BaseModel):
    resolved: bool


class AttemptRequest(BaseModel):
    attempt: int = Field(ge=0)
    answers: dict[str, int]  # question id -> position of the chosen option, as shown


class AttemptResponse(BaseModel):
    grade: Grade
    path: LearningPath


class ModuleAction(BaseModel):
    module_id: str
    topic: str | None = None  # for accepting or declining a suggestion about one of the module's topics


class ChoiceRequest(BaseModel):
    module_id: str
    choice: Choice


class TopicRequest(BaseModel):
    module_id: str
    topic: str
    choice: TopicChoice


class ShareRequest(BaseModel):
    share: bool


class GoalRequest(BaseModel):
    goal: Goal


class Credentials(BaseModel):
    email: Annotated[str, StringConstraints(max_length=254)]
    password: Annotated[str, StringConstraints(max_length=MAX_PASSWORD_LENGTH)]
    # A path planned before signing in, to keep as the account's path.
    draft_id: str | None = None


class DeleteRequest(BaseModel):
    # The password, or for an account made with Google, which has none, its email address.
    confirmation: Annotated[str, StringConstraints(max_length=MAX_PASSWORD_LENGTH)]


class AccountOut(BaseModel):
    email: str
    has_password: bool = True  # False for an account made with Google
    reviewer: bool = False  # may review submitted projects


class ReviewRequest(BaseModel):
    accept: bool
    comment: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=MAX_NOTE_LENGTH)
    ] = ""


class Providers(BaseModel):
    """The ways to sign in this API offers, besides an email and a password."""

    google: bool


class SessionResponse(BaseModel):
    account: AccountOut | None
    path: LearningPath | None = None


class PublicLink(BaseModel):
    token: str | None  # None while the learner has no public link


class ProvenModule(BaseModel):
    """A module on a learner's public page, and how it was finished."""

    title: str
    url: str
    # checkpoint: questions graded by the server, and the coding problem where there is one;
    # questions: the questions passed, the coding problem not yet; project: accepted by a reviewer;
    # marked_done: a module without a checkpoint, on the learner's own word.
    how: Literal["checkpoint", "questions", "project", "marked_done"]
    score: str | None = None  # the passing attempt's score, such as "4/5"
    attempts: int = 0


class PublicProgress(BaseModel):
    """What a learner's public link shows: their path's goal and level and what they finished. Never their
    email, their answers or their reasons."""

    title: str | None
    level: Level | None
    modules_in_path: int
    finished: list[ProvenModule]
    curriculum: CurriculumInfo
    attribution_url: str


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
GOOGLE_STATE_COOKIE = "roadmap_google_state"


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
    google: GoogleSignIn | None = None,
    submissions: SubmissionStore | None = None,
    reviewers: set[str] | None = None,
    github: httpx.Client | None = None,
    github_token: str | None = None,
    review_runs: int = 3,
    question_reports: QuestionReportStore | None = None,
) -> FastAPI:
    """`editions` newest first: new paths use the first. `profiles` are invented learners a demo can
    start from. `accounts` keeps learners' accounts and paths; in memory unless given.
    """
    newest = editions[0]
    by_version = {edition.version: edition for edition in editions}
    store = accounts or AccountStore(Path(":memory:"))

    def with_current_modules(path: LearningPath) -> LearningPath:
        """The path's modules as the course is read now, for a version this API serves."""
        edition = by_version.get(path.curriculum_version)
        if edition is None:
            return path
        modules = {module.id: module for module in edition.roadmap.curriculum.modules}
        return path.model_copy(
            update={
                "items": [
                    _settled(item.model_copy(update={"module": modules.get(item.module.id, item.module)}))
                    for item in path.items
                ]
            }
        )

    store.refresh_paths_with(with_current_modules)
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

    @app.middleware("http")
    async def bounded_uploads(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """A project upload is refused by its declared size, before any of it is read or kept on disk."""
        if request.method == "POST" and request.url.path.startswith("/me/submissions/"):
            declared = request.headers.get("content-length", "")
            if not declared.isdigit():
                return JSONResponse({"detail": "Send the size of the upload."}, 411)
            if (
                int(declared) > MAX_ARCHIVE_BYTES + 64 * 1024
            ):  # the archive and the form around it
                return JSONResponse(
                    {
                        "detail": f"The archive is over {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB."
                    },
                    413,
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

    reviewer_emails = {email.strip().lower() for email in reviewers or set()}

    def account_out(account: Account) -> AccountOut:
        return AccountOut(
            email=account.email,
            has_password=account.has_password,
            reviewer=account.email in reviewer_emails,
        )

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
            account=account_out(account),
            path=store.path_of(account),
        )

    def signed_in_response(
        response: Response, account: Account, token: str, draft_id: str | None
    ) -> SessionResponse:
        start_session(response, token)
        path = store.claim_draft(account, draft_id) if draft_id else None
        return SessionResponse(
            account=account_out(account),
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
        body: DeleteRequest, request: Request, response: Response
    ) -> SessionResponse:
        """Deletes the account and its path. Shared progress events hold no account, so they stay."""
        account = signed_in(request)
        try:
            store.delete(account, body.confirmation)
        except AccountError as error:
            raise HTTPException(401, str(error)) from error
        if submissions is not None:
            submissions.delete_for(account.id)
        end_session(response)
        return SessionResponse(account=None)

    @app.get("/auth/providers")
    def providers() -> Providers:
        return Providers(google=google is not None)

    def page_on_site(address: str) -> bool:
        return any(
            address == origin or address.startswith(f"{origin}/")
            for origin in allowed_origins
        )

    @app.get("/auth/google", dependencies=[Depends(limit_sign_ins)])
    def google_start(return_to: str, draft_id: str | None = None) -> RedirectResponse:
        """Sends the learner to Google. They come back to `return_to`, a page of the site, signed in."""
        if google is None:
            raise HTTPException(404, "Sign-in with Google is not set up.")
        if not page_on_site(return_to):
            raise HTTPException(422, "Sign-in can only return to the course site.")
        address, state = google.start(return_to, draft_id)
        redirect = RedirectResponse(address, status_code=303)
        redirect.set_cookie(
            GOOGLE_STATE_COOKIE,
            state,
            max_age=FLOW_SECONDS,
            httponly=True,
            secure=secure_cookies,
            samesite="lax",  # sent when Google sends the learner back: a top-level navigation
        )
        return redirect

    @app.get("/auth/google/callback")
    def google_callback(
        request: Request,
        state: str = "",
        code: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        """Google sends the learner back here. Signs them in and returns them to the page they came from,
        or to it with `#sign-in-error=<reason>` if they cancelled or Google did not confirm who they are.
        """
        if google is None:
            raise HTTPException(404, "Sign-in with Google is not set up.")
        cookie = request.cookies.get(GOOGLE_STATE_COOKIE, "")
        flow = (
            google.flow(state) if state and hmac.compare_digest(state, cookie) else None
        )
        if flow is None:
            raise HTTPException(
                400,
                "This sign-in has expired or was started elsewhere. Start it again.",
            )

        def back(fragment: str = "") -> RedirectResponse:
            redirect = RedirectResponse(
                f"{flow.return_to.split('#')[0]}{fragment}", status_code=303
            )
            redirect.delete_cookie(
                GOOGLE_STATE_COOKIE,
                httponly=True,
                secure=secure_cookies,
                samesite="lax",
            )
            return redirect

        if error or not code:
            return back("#sign-in-error=cancelled")
        try:
            identity = google.identity(code, flow)
            account, token = store.sign_in_with_google(identity.subject, identity.email)
        except (GoogleError, AccountError) as failure:
            logger.warning("Sign-in with Google failed: %s", failure)
            return back("#sign-in-error=google")
        redirect = back()
        start_session(redirect, token)
        if flow.draft_id:
            store.claim_draft(account, flow.draft_id)
        return redirect

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

    @app.post("/me/path/topic")
    def choose_topic(body: TopicRequest, request: Request) -> LearningPath:
        """The learner studies a topic of a module in full, skims it, or skips it out of the checkpoint."""
        return change(
            signed_in(request),
            lambda path: path.with_topic(body.module_id, body.topic, body.choice),
        )

    def topics_of(request: Request, module_id: str) -> tuple[frozenset[str], frozenset[str]]:
        """The topics the signed-in learner skips and skims in a module; none for anyone else."""
        account = account_of(request)
        path = store.path_of(account) if account else None
        item = next((i for i in path.items if i.module.id == module_id), None) if path else None
        if item is None:
            return frozenset(), frozenset()
        return item.skipped_topics, item.skimmed_topics

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

    # A public link to the learner's progress

    @app.get("/me/public-link")
    def my_public_link(request: Request) -> PublicLink:
        return PublicLink(token=store.public_link_of(signed_in(request)))

    @app.post("/me/public-link")
    def new_public_link(request: Request) -> PublicLink:
        """A new link; an earlier one stops working."""
        return PublicLink(token=store.make_public_link(signed_in(request)))

    @app.post("/me/public-link/remove")
    def remove_public_link(request: Request) -> PublicLink:
        store.remove_public_link(signed_in(request))
        return PublicLink(token=None)

    @app.get("/public/{token}")
    def public_progress(token: str) -> PublicProgress:
        """The read-only page behind a learner's public link."""
        account = store.account_by_public_link(token) if len(token) <= 64 else None
        path = store.path_of(account) if account else None
        if path is None:
            raise HTTPException(404, "This link does not exist or its owner removed it.")
        edition = edition_of(path)
        finished = []
        for item in path.items:
            if item.progress == Progress.DONE:
                how = "marked_done"
            elif item.progress == Progress.PRACTICE:
                how = "questions"
            elif item.progress == Progress.PASSED:
                how = "project" if item.module.is_project else "checkpoint"
            else:
                continue
            finished.append(
                ProvenModule(
                    title=item.module.full_title,
                    url=item.module.url,
                    how=how,
                    score=None if how in ("project", "marked_done") else item.last_score,
                    attempts=item.attempts,
                )
            )
        return PublicProgress(
            title=path.title,
            level=path.level,
            modules_in_path=len(path.included),
            finished=finished,
            curriculum=info(edition),
            attribution_url=path.attribution.url,
        )

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
        module_id: str, body: AttemptRequest, request: Request, background: BackgroundTasks
    ) -> AttemptResponse:
        """Grades an attempt against the stored path: locked modules, a "prove" turned into "study", skimmed
        topics answered wrong turned into study. Suggestions for the rest of the path, after an easy pass or a
        failure, take a model call over the whole course, so they are worked out after the answer: the path
        says so meanwhile, and the page asks for it again."""
        grades: list[Grade] = []
        later: list[tuple[Roadmap, LearningPath, str]] = []

        def graded(path: LearningPath) -> LearningPath:
            edition = edition_of(path)
            found = checkpoint_of(edition, module_id)
            # The questions of an attempt follow from its number, which the stored path keeps.
            if body.attempt != path.item(module_id).attempts:
                raise HTTPException(
                    409, "This attempt does not follow your last one. Reload the page."
                )
            try:
                grade = found.grade(
                    body.attempt, body.answers, path.item(module_id).skipped_topics
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            # Suggestions after an easy pass or a failure ask the model; over the quota the result still
            # counts, without them.
            suggest = True
            if grade.effortless or not grade.passed:
                try:
                    within_quota(request)
                except HTTPException:
                    suggest = False
            grades.append(grade)
            result = edition.roadmap.after_checkpoint(path, module_id, grade, suggest=False)
            if suggest and edition.roadmap.wants_suggestions(grade):
                key = f"{module_id}:{result.item(module_id).attempts}"
                result = result.model_copy(update={"suggestions_pending": key})
                later.append((edition.roadmap, result, key))
            return result

        account = signed_in(request)
        updated = change(account, graded)
        for roadmap, snapshot, key in later:
            background.add_task(suggest_later, account, roadmap, snapshot, module_id, grades[0], key)
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

    def suggest_later(
        account: Account, roadmap: Roadmap, snapshot: LearningPath, module_id: str, grade: Grade, key: str
    ) -> None:
        try:
            proposals = roadmap.suggestions_after(snapshot, module_id, grade)
        except Exception:  # the result is already saved; without suggestions the path stays as it is
            logger.exception("Suggestions after the checkpoint of %s failed", module_id)
            proposals = []
        try:
            store.change_path(account, lambda path: path.with_suggestions(key, proposals))
        except LookupError:
            pass  # the learner started over meanwhile

    @app.post("/me/problems/{module_id:path}/solved")
    def solved(module_id: str, request: Request) -> LearningPath:
        """The learner's code passed the problem's tests in their browser. The server cannot run the
        learner's code safely, so it takes the browser's word for this one step; the questions before it
        are graded here."""

        def solved_in(path: LearningPath) -> LearningPath:
            item = path.item(module_id)
            if checkpoint_of(edition_of(path), module_id).problem_for(item.skipped_topics) is None:
                raise HTTPException(404, f"No coding problem for '{module_id}'")
            return path.with_problem_solved(module_id)

        updated = change(signed_in(request), solved_in)
        record(updated, EventKind.FINISHED, module_id)
        return updated

    # The assistant in the path panel

    # A question sends the path and a module's outline, a few thousand tokens, so each learner gets a share.
    chats = RateLimiter(CHATS_PER_DAY, 24 * 3600)

    @app.post("/me/chat")
    def chat(body: ChatRequest, request: Request) -> ChatReply:
        """Answers the learner's question about their path, or the module page they are reading."""
        account = signed_in(request)
        path = store.path_of(account)
        if path is None:
            raise HTTPException(404, "Plan your path first; then ask about it.")
        llm = edition_of(path).roadmap.llm
        if llm is None:
            raise HTTPException(503, "The assistant is not available right now.")
        if not chats.allow(account.id):
            raise HTTPException(
                429, f"You have asked {CHATS_PER_DAY} questions today. Ask again tomorrow."
            )
        # Code for the page's coding problem: the problem goes with it, never its reference solution.
        problem = None
        if body.code is not None and body.module_id is not None:
            checkpoint = edition_of(path).checkpoints.get(body.module_id)
            item = next((i for i in path.items if i.module.id == body.module_id), None)
            problem = (
                checkpoint.problem_for(item.skipped_topics, item.skimmed_topics)
                if checkpoint and item
                else None
            )
        # Their projects as the review left them, so the assistant can say why one came back.
        handed_in = []
        if submissions is not None:
            for item in path.items:
                if item.module.is_project and (
                    item.module.id == body.module_id
                    or item.progress in (Progress.SUBMITTED, Progress.RETURNED)
                ):
                    found = submissions.for_module(account.id, item.module.id)
                    if found is not None:
                        handed_in.append(found)
        try:
            return PathAssistant(llm).answer(path, body, problem, handed_in)
        except LLMUnavailable as error:
            logger.warning("No answer for a question: %s", error)
            raise HTTPException(
                503, "The assistant cannot answer right now. Try again in a minute."
            ) from error

    # Projects

    uploads = RateLimiter(20, 3600)
    # A review reads up to about 30 000 tokens of the project, so each learner gets a few a day.
    ai_reviews = RateLimiter(REVIEWS_PER_DAY, 24 * 3600)
    github_client = github or httpx.Client(timeout=30)

    def submission_store() -> SubmissionStore:
        if submissions is None:
            raise HTTPException(404, "Project submissions are not set up.")
        return submissions

    def reviewer(request: Request) -> Account:
        account = signed_in(request)
        if account.email not in reviewer_emails:
            raise HTTPException(403, "Only reviewers can do this.")
        return account

    # Reports of checkpoint questions

    reports = question_reports or QuestionReportStore(Path(":memory:"))
    report_limit = RateLimiter(30, 24 * 3600)

    @app.post("/me/checkpoints/{module_id:path}/reports")
    def report_question(
        module_id: str, body: QuestionReportIn, request: Request
    ) -> QuestionReport:
        """A learner says a question of a checkpoint in their path looks wrong; reviewers check it."""
        account = signed_in(request)
        if not report_limit.allow(account.id):
            raise HTTPException(429, "Too many reports today. Try again tomorrow.")
        path = store.path_of(account)
        if path is None or all(item.module.id != module_id for item in path.items):
            raise HTTPException(404, f"'{module_id}' is not in your path")
        checkpoint = checkpoint_of(edition_of(path), module_id)
        if all(question.id != body.question_id for question in checkpoint.questions):
            raise HTTPException(404, "No such question in this checkpoint.")
        return reports.add(account.id, module_id, path.curriculum_version, body)

    @app.get("/review/question-reports")
    def question_reports_list(request: Request) -> list[ReportedQuestion]:
        """Open reports first, each with the question as the checkpoint has it now."""
        reviewer(request)
        found = []
        for report in reports.listed():
            edition = by_version.get(report.curriculum_version)
            checkpoint = edition.checkpoints.get(report.module_id) if edition else None
            question = next(
                (q for q in checkpoint.questions if q.id == report.question_id), None
            ) if checkpoint else None
            module = (
                next((m for m in edition.roadmap.curriculum.modules if m.id == report.module_id), None)
                if edition
                else None
            )
            found.append(
                ReportedQuestion(
                    **report.model_dump(),
                    module_title=module.full_title if module else report.module_id,
                    question=question,
                )
            )
        return found

    @app.post("/review/question-reports/{report_id}")
    def resolve_report(report_id: str, body: ResolveRequest, request: Request) -> None:
        reviewer(request)
        if not reports.set_resolved(report_id, body.resolved):
            raise HTTPException(404, "No such report.")

    @app.post("/me/submissions/{module_id:path}")
    def submit(
        module_id: str,
        request: Request,
        background: BackgroundTasks,
        link: Annotated[str | None, Form()] = None,
        note: Annotated[str, Form(max_length=MAX_NOTE_LENGTH)] = "",
        archive: Annotated[UploadFile | None, File()] = None,
    ) -> Submission:
        """Hands in the module's project: a link, an archive, or both. A new submission replaces the last. A
        model reviews it right after this answers; the learner's page asks for the result.
        """
        found = submission_store()
        account = signed_in(request)
        if not uploads.allow(account.id) or not ai_reviews.allow(account.id):
            raise HTTPException(
                429, f"You can submit a project {REVIEWS_PER_DAY} times a day. Try again tomorrow."
            )
        try:
            checked_link = check_link(link)
            if checked_link is None and archive is None:
                raise SubmissionError(
                    "Give a link to your project, attach an archive, or both."
                )
            path = store.path_of(account)
            if path is None:
                raise HTTPException(404, "You have no path yet.")
            # Checks the path's rules before anything is kept.
            path.with_submission(module_id)
            stored = None
            if archive is not None:
                name, size = found.keep_archive(archive.file)
                stored = (name, size, safe_file_name(archive.filename))
        except SubmissionError as error:
            raise HTTPException(422, str(error)) from error
        except PathStateError as error:
            raise HTTPException(409, str(error)) from error
        except KeyError as error:
            raise HTTPException(404, str(error.args[0])) from error
        change(account, lambda current: current.with_submission(module_id))
        item = path.item(module_id)
        submission = found.submit(
            account_id=account.id,
            email=account.email,
            module_id=module_id,
            module_title=item.module.full_title,
            curriculum_version=path.curriculum_version,
            link=checked_link,
            note=note.strip(),
            archive=stored,
        )
        edition = edition_of(path)
        if edition.roadmap.llm is None:
            return submission  # waits for a person
        found.set_status(submission.id, SubmissionStatus.REVIEWING)
        module = next(
            (m for m in edition.roadmap.curriculum.modules if m.id == module_id),
            item.module,
        )
        background.add_task(
            review_by_model, submission.id, account, module, edition.roadmap.llm
        )
        return found.get(submission.id) or submission

    def project_files(submission: Submission) -> ProjectFiles:
        archive = submission_store().archive_of(submission.id)
        if archive is not None and archive.is_file():
            return read_archive(archive.read_bytes())
        if repository := github_repository(submission.link):
            return read_github(*repository, github_client, github_token)
        raise ProjectError(
            "The review reads an archive or a public GitHub repository. Attach an archive of your code, "
            "or give the repository's GitHub link."
        )

    def review_by_model(
        submission_id: str, account: Account, module: Module, llm: LLMClient
    ) -> None:
        """Runs after the submission is answered. The project is read, the model grades it, code checks the
        model's evidence and decides; the learner's path follows. Without a usable answer from any model, the
        submission waits for a person."""
        found = submission_store()
        submission = found.get(submission_id)
        if submission is None:
            return
        try:
            files = project_files(submission)
        except ProjectError as error:
            decide(submission, account, False, str(error), "model")
            return
        try:
            result = ProjectReviewer(llm, runs=review_runs).review(module, files)
        except LLMUnavailable as error:
            logger.warning("No review of %s by a model: %s", submission_id, error)
            found.set_status(submission_id, SubmissionStatus.SUBMITTED)
            return
        except (
            Exception
        ):  # noqa: BLE001 - a background task: nobody else would see the error
            logger.exception("The review of %s failed", submission_id)
            found.set_status(submission_id, SubmissionStatus.SUBMITTED)
            return
        decide(submission, account, result.passed, result.feedback, "model", result)

    def decide(
        submission: Submission,
        learner: Account,
        accept: bool,
        comment: str,
        by: str,
        result: ProjectReview | None = None,
    ) -> Submission:
        reviewed = submission_store().review(
            submission.id, accept, comment, by, ai_review=result
        )
        try:
            updated = store.change_path(
                learner,
                lambda path: path.with_review(submission.module_id, accept, comment),
            )
            if accept:
                record(updated, EventKind.FINISHED, submission.module_id)
        except (LookupError, PathStateError, KeyError) as error:
            # The learner started over or changed the module: the review stands on its own.
            logger.info(
                "Review of %s not applied to the path: %s", submission.id, error
            )
        return reviewed

    @app.get("/me/submissions/{module_id:path}")
    def my_submission(module_id: str, request: Request) -> Submission | None:
        return submission_store().for_module(signed_in(request).id, module_id)

    @app.get("/submissions/{submission_id}/archive")
    def submission_archive(submission_id: str, request: Request) -> FileResponse:
        """The archive, as a download, for its learner and for reviewers only."""
        found = submission_store()
        account = signed_in(request)
        submission = found.get(submission_id)
        allowed = submission is not None and (
            submission.account_id == account.id or account.email in reviewer_emails
        )
        archive = found.archive_of(submission_id) if allowed else None
        if submission is None or archive is None or not archive.is_file():
            raise HTTPException(404, "No such archive.")
        return FileResponse(
            archive,
            media_type="application/octet-stream",  # downloaded, never shown in the browser
            filename=submission.file_name or "project",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/review/submissions")
    def review_queue(request: Request) -> dict[str, list[Submission]]:
        """Projects no model could review, then the latest decisions, the model's included, which a person
        may change."""
        reviewer(request)
        found = submission_store()
        return {"waiting": found.waiting(), "reviewed": found.recent()}

    @app.post("/review/submissions/{submission_id}")
    def review(submission_id: str, body: ReviewRequest, request: Request) -> Submission:
        """Accepts a project, which finishes the learner's module, or sends it back with a comment."""
        person = reviewer(request)
        submission = submission_store().get(submission_id)
        if submission is None:
            raise HTTPException(404, "No such submission.")
        if not body.accept and not body.comment:
            raise HTTPException(422, "Say what to change when you send a project back.")
        learner = store.account_by_id(submission.account_id)
        if learner is None:
            raise HTTPException(404, "The learner's account no longer exists.")
        try:
            return decide(submission, learner, body.accept, body.comment, person.email)
        except SubmissionError as error:
            raise HTTPException(409, str(error)) from error

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
        return change(signed_in(request), lambda path: path.accept(body.module_id, body.topic))

    @app.post("/me/path/decline")
    def decline(body: ModuleAction, request: Request) -> LearningPath:
        return change(signed_in(request), lambda path: path.decline(body.module_id, body.topic))

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

    @app.get("/me/checkpoints/{module_id:path}/passed")
    def passed_questions(module_id: str, request: Request) -> list[ReviewedQuestion]:
        """The questions of the attempt that passed, with their answers, to look back at while solving the
        coding problem or after. Only once the learner passed: before, the answers stay hidden."""
        path = store.path_of(signed_in(request))
        if path is None:
            raise HTTPException(404, "You have no path yet.")
        item = next((i for i in path.items if i.module.id == module_id), None)
        if item is None or item.progress not in (Progress.PRACTICE, Progress.PASSED) or not item.attempts:
            raise HTTPException(409, "Pass this checkpoint first.")
        checkpoint = checkpoint_of(edition_of(path), module_id)
        attempt = item.attempts - 1
        reviewed = []
        for question in checkpoint.questions_for_attempt(attempt, item.skipped_topics):
            order = checkpoint.order_of(attempt, question.id)
            reviewed.append(
                ReviewedQuestion(
                    id=question.id,
                    topic=question.topic,
                    text=question.text,
                    options=[question.options[i] for i in order],
                    answer=order.index(question.answer),
                    explanation=question.explanation,
                )
            )
        return reviewed

    @app.get("/checkpoints/{module_id:path}")
    def checkpoint(
        module_id: str, request: Request, attempt: int = 0, version: str | None = None
    ) -> CheckpointOut:
        """The attempt's questions; for a signed-in learner, from the topics they do not skip."""
        found = checkpoint_of(edition_named(version), module_id)
        skipped, _ = topics_of(request, module_id)
        return CheckpointOut(
            module_id=module_id,
            status=found.status,
            attempt=attempt,
            pass_mark=PASS_MARK,
            questions=found.asked(attempt, skipped),
        )

    @app.get("/problems/{module_id:path}")
    def problem(module_id: str, request: Request, version: str | None = None) -> ProblemOut:
        """The coding problem; for a signed-in learner, on a topic they study."""
        edition = edition_named(version)
        found = checkpoint_of(edition, module_id).problem_for(*topics_of(request, module_id))
        if found is None:
            raise HTTPException(404, f"No coding problem for '{module_id}'")
        module = next(
            (m for m in edition.roadmap.curriculum.modules if m.id == module_id), None
        )
        topic = next(
            (
                t
                for t in (module.topics if module else [])
                if found.topic and _bare(t.title) == _bare(found.topic)
            ),
            None,
        )
        return ProblemOut(
            module_id=module_id,
            title=found.title,
            prompt=found.prompt,
            starter_code=found.starter_code,
            tests=found.tests,
            packages=found.packages,
            topic=topic.title if topic else None,
            topic_anchor=topic.anchor if topic else None,
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
        return course_report(version)

    @app.get("/review/report")
    def reviewer_report(request: Request, version: str | None = None) -> Report:
        """The same report for the course team: reviewers see it on the site without the token."""
        reviewer(request)
        if events is None:
            raise HTTPException(503, "Progress events are not recorded on this server.")
        return course_report(version)

    def course_report(version: str | None) -> Report:
        assert events is not None  # nosec B101: both callers check
        edition = edition_named(version)
        modules = edition.roadmap.curriculum.modules
        report = events.report(edition.version, [module.id for module in modules])
        titles = {module.id: module.full_title for module in modules}
        return report.model_copy(
            update={
                "modules": [
                    row.model_copy(update={"title": titles[row.module_id]})
                    for row in report.modules
                ]
            }
        )

    return app


def _bare(title: str) -> str:
    """A topic title without its heading number, for matching "1. Readable Python" to "Readable Python"."""
    return re.sub(r"^\d+\.\s*", "", title).strip().lower()


def _settled(item: PathItem) -> PathItem:
    """A module the path changed to study after a failed checkpoint, stored before such a change counted as
    the path's suggestion and before a later pass updated its note."""
    if not (item.adjustment and item.adjustment.startswith("Changed to study:")):
        return item
    update: dict[str, object] = {"suggested": Choice.STUDY}
    if item.progress in (Progress.PASSED, Progress.PRACTICE):
        update["adjustment"] = (
            "Changed to study after the checkpoint showed gaps; "
            f"passed on attempt {item.attempts} ({item.last_score})."
        )
    return item.model_copy(update=update)


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
    # Sign-in with Google (roadmap.google); off unless both are set.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    # The API's own address, as learners' browsers reach it; Google sends them back to it.
    api_public_url: str = "http://localhost:8000"
    # Accounts that may review submitted projects, comma-separated emails.
    api_reviewer_emails: str = ""
    # Archives learners submit with their projects; data/uploads unless set.
    api_uploads_dir: Path | None = None
    # Optional: raises GitHub's limit on reading public repositories for reviews (60 an hour without it).
    github_token: SecretStr | None = None

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

    @property
    def uploads_dir(self) -> Path:
        return self.api_uploads_dir or self.data_dir / "uploads"

    @property
    def reviewers(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.api_reviewer_emails.split(",")
            if email.strip()
        }

    @property
    def google(self) -> GoogleSignIn | None:
        if not (self.google_client_id and self.google_client_secret):
            return None
        return GoogleSignIn(
            self.google_client_id,
            self.google_client_secret.get_secret_value(),
            f"{self.api_public_url.rstrip('/')}/auth/google/callback",
        )


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
        google=settings.google,
        submissions=SubmissionStore(settings.accounts_file, settings.uploads_dir),
        reviewers=settings.reviewers,
        question_reports=QuestionReportStore(settings.accounts_file),
        github_token=(
            settings.github_token.get_secret_value() if settings.github_token else None
        ),
    )


def __getattr__(name: str) -> FastAPI:
    """`roadmap.api:app` builds the app on first use, so importing this module reads no settings."""
    if name == "app":
        return _app()
    raise AttributeError(name)
