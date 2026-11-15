"""HTTP API over the core, for interfaces that run in a browser, such as a page on the curriculum site.

The model keys stay on this server. The browser asks for the questions, a suggested level and a path; it
changes decisions itself, since that is only an edit of the path JSON. Everything with a rule behind it,
progress, locks and checkpoint grading, happens here, so the browser never holds checkpoint answers.

New paths are planned for the newest curriculum version; a path planned for an older listed version keeps
working against that version, so learners keep their progress when the course moves on.

Run it with `uvicorn roadmap.api:app`. Settings come from the environment or `.env`, as for the rest of the
core: API_ALLOWED_ORIGINS lists the sites that may call it, API_REPORT_TOKEN opens the progress report.
"""

import hmac
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, TypeVar

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StringConstraints

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
from .path import LearningPath, PathStateError, Progress
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
T = TypeVar("T")


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
    path: LearningPath
    attempt: int = Field(ge=0)
    answers: dict[str, int]  # question id -> position of the chosen option, as shown


class AttemptResponse(BaseModel):
    grade: Grade
    path: LearningPath


class PathAction(BaseModel):
    path: LearningPath
    module_id: str


class PathBody(BaseModel):
    path: LearningPath


class GoalRequest(BaseModel):
    path: LearningPath
    goal: Goal


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


def create_app(
    editions: list[Edition],
    allowed_origins: list[str],
    limiter: RateLimiter,
    events: EventLog | None = None,
    report_token: str | None = None,
    profiles: list[LearnerProfile] | None = None,
) -> FastAPI:
    """`editions` newest first: new paths use the first. `profiles` are invented learners a demo can
    start from."""
    newest = editions[0]
    by_version = {edition.version: edition for edition in editions}
    app = FastAPI(
        title="Personalized Roadmap API",
        description="Suggested levels and personal paths through the HumbleBeeAI Open Curriculum.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
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

    def within_quota(request: Request) -> None:
        """Model calls share a free-tier quota, so each client gets a share of it. Behind a reverse
        proxy, run uvicorn with --proxy-headers so that the client is the learner, not the proxy.
        """
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(429, "Too many requests. Try again later.")

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

    def act(action: Callable[[], T]) -> T:
        try:
            return action()
        except PathStateError as error:
            raise HTTPException(409, str(error)) from error
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

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

    @app.post("/level", dependencies=[Depends(within_quota)])
    def level(body: LevelRequest) -> LevelResponse:
        return LevelResponse(
            assessment=newest.roadmap.assess_level(check_answers(body.answers))
        )

    @app.post("/path", dependencies=[Depends(within_quota)])
    def path(body: PathRequest) -> LearningPath:
        return newest.roadmap.build_path(
            check_answers(body.answers), body.level, body.assessment
        )

    @app.post("/path/confirm")
    def confirm(body: PathBody) -> LearningPath:
        """The learner approves the path; if they share their progress, its modules are counted."""
        edition_of(body.path)
        confirmed = body.path.confirm()
        if events is not None:
            events.record_included(confirmed)
        return confirmed

    @app.post("/path/goal", dependencies=[Depends(within_quota)])
    def goal(body: GoalRequest) -> LearningPath:
        """The path replanned for a new goal; started modules keep their progress. The learner confirms
        it again."""
        edition = edition_of(body.path)
        try:
            changed = edition.roadmap.change_goal(body.path, body.goal)
        except LLMUnavailable as error:
            raise HTTPException(
                503, "Replanning is unavailable right now. Your path has not changed."
            ) from error
        record(changed, EventKind.GOAL_CHANGED)
        return changed

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

    @app.post("/attempts/{module_id:path}")
    def attempt(
        module_id: str, body: AttemptRequest, request: Request
    ) -> AttemptResponse:
        """Grades an attempt and returns the path with its result: locked modules, a "prove" turned
        into "study", or suggestions after a checkpoint passed without a mistake."""
        edition = edition_of(body.path)
        found = checkpoint_of(edition, module_id)
        # The questions of an attempt follow from its number, so the path decides which attempt this is.
        if body.attempt != act(lambda: body.path.item(module_id)).attempts:
            raise HTTPException(
                409, "This attempt does not follow the path's last one."
            )
        try:
            grade = found.grade(body.attempt, body.answers)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if grade.effortless:
            within_quota(request)  # suggestions after it ask the model
        updated = act(
            lambda: edition.roadmap.after_checkpoint(body.path, module_id, grade)
        )
        progress = updated.item(module_id).progress
        record(
            updated,
            {
                Progress.FAILED: EventKind.FAILED,
                Progress.PRACTICE: EventKind.PRACTICE,
                Progress.PASSED: EventKind.FINISHED,
            }[progress],
            module_id,
        )
        return AttemptResponse(grade=grade, path=updated)

    @app.post("/problems/{module_id:path}/solved")
    def solved(module_id: str, body: PathBody) -> LearningPath:
        """The learner's code passed the problem's tests in their browser. The server cannot run the
        learner's code safely, so it takes the browser's word: like the lock, this holds in the interface,
        not against a learner who edits their path."""
        if checkpoint_of(edition_of(body.path), module_id).problem is None:
            raise HTTPException(404, f"No coding problem for '{module_id}'")
        updated = act(lambda: body.path.with_problem_solved(module_id))
        record(updated, EventKind.FINISHED, module_id)
        return updated

    @app.post("/path/done")
    def done(body: PathAction) -> LearningPath:
        """Marks a module without a checkpoint as done."""
        if body.module_id in edition_of(body.path).checkpoints:
            raise HTTPException(409, "This module has a checkpoint: pass it instead.")
        updated = act(lambda: body.path.marked_done(body.module_id))
        record(updated, EventKind.FINISHED, body.module_id)
        return updated

    @app.post("/path/accept")
    def accept(body: PathAction) -> LearningPath:
        edition_of(body.path)
        return act(lambda: body.path.accept(body.module_id))

    @app.post("/path/decline")
    def decline(body: PathAction) -> LearningPath:
        edition_of(body.path)
        return act(lambda: body.path.decline(body.module_id))

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

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.api_allowed_origins.split(",")
            if origin.strip()
        ]


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
    )


def __getattr__(name: str) -> FastAPI:
    """`roadmap.api:app` builds the app on first use, so importing this module reads no settings."""
    if name == "app":
        return _app()
    raise AttributeError(name)
