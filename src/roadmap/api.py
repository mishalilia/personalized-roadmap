"""HTTP API over the core, for interfaces that run in a browser, such as a page on the curriculum site.

The model keys stay on this server. The browser asks for the questions, a suggested level and a path; it
changes decisions and confirms the path itself, since that is only an edit of the path JSON.

Run it with `uvicorn roadmap.api:app`. Settings come from the environment or `.env`, as for the rest of
the core; API_ALLOWED_ORIGINS lists the sites that may call it.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StringConstraints

from .checkpoints import (
    PASS_MARK,
    QUESTIONS_PER_ATTEMPT,
    Checkpoint,
    CheckpointStore,
    Grade,
    Status,
)
from .config import Settings
from .curriculum import Level
from .level import LevelAssessment
from .path import LearningPath, PathStateError
from .service import Roadmap
from .source import CurriculumSource

logger = logging.getLogger(__name__)

MAX_ANSWER_LENGTH = 2000  # characters; a long answer costs quota and says no more

Answer = Annotated[str, StringConstraints(max_length=MAX_ANSWER_LENGTH)]


class QuestionOut(BaseModel):
    id: str
    text: str
    placeholder: str


class CurriculumInfo(BaseModel):
    version: str  # the pinned commit
    # The version of the curriculum site with the same content, such as "2026-10-06", so that a page
    # on the site can tell whether a path was planned for the pages it shows.
    site_version: str | None
    title: str
    licence: str


class QuestionsResponse(BaseModel):
    questions: list[QuestionOut]
    curriculum: CurriculumInfo
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


class AskedQuestion(BaseModel):
    """A checkpoint question without its answer: grading happens here, not in the browser."""

    id: str
    topic: str
    text: str
    options: list[str]


class CheckpointOut(BaseModel):
    module_id: str
    status: Status
    attempt: int
    pass_mark: int
    questions: list[AskedQuestion]


class AttemptRequest(BaseModel):
    path: LearningPath
    attempt: int = Field(ge=0)
    answers: dict[str, int]


class AttemptResponse(BaseModel):
    grade: Grade
    path: LearningPath


class PathAction(BaseModel):
    path: LearningPath
    module_id: str


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
    roadmap: Roadmap,
    source: CurriculumSource,
    allowed_origins: list[str],
    limiter: RateLimiter,
    checkpoints: dict[str, Checkpoint] | None = None,
) -> FastAPI:
    checkpoints = checkpoints or {}
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
    question_ids = {question.id for question in roadmap.questions}

    def check_answers(answers: dict[str, str]) -> dict[str, str]:
        if unknown := sorted(answers.keys() - question_ids):
            raise HTTPException(422, f"Unknown questions: {', '.join(unknown)}")
        if not any(answer.strip() for answer in answers.values()):
            raise HTTPException(422, "Answer at least one question.")
        return answers

    def within_quota(request: Request) -> None:
        """Model calls share a free-tier quota, so each client gets a share of it."""
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(429, "Too many requests. Try again later.")

    def check_path(path: LearningPath) -> LearningPath:
        if path.curriculum_version != roadmap.curriculum.version:
            raise HTTPException(
                409,
                "This path was planned for another curriculum version. Plan a new one.",
            )
        return path

    def checkpoint_of(module_id: str) -> Checkpoint:
        if module_id not in checkpoints:
            raise HTTPException(404, f"No checkpoint for '{module_id}'")
        return checkpoints[module_id]

    def act(action):  # type: ignore[no-untyped-def]
        try:
            return action()
        except PathStateError as error:
            raise HTTPException(409, str(error)) from error
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

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
                for question in roadmap.questions
            ],
            curriculum=CurriculumInfo(
                version=source.version,
                site_version=source.site_version,
                title=source.attribution.title,
                licence=source.attribution.licence,
            ),
            personalization_available=roadmap.personalization_available,
        )

    @app.post("/level", dependencies=[Depends(within_quota)])
    def level(body: LevelRequest) -> LevelResponse:
        return LevelResponse(
            assessment=roadmap.assess_level(check_answers(body.answers))
        )

    @app.post("/path", dependencies=[Depends(within_quota)])
    def path(body: PathRequest) -> LearningPath:
        return roadmap.build_path(
            check_answers(body.answers), body.level, body.assessment
        )

    @app.get("/checkpoints")
    def checkpoint_list() -> dict[str, CheckpointSummary]:
        """The modules that have a checkpoint."""
        return {
            module_id: CheckpointSummary(status=checkpoint.status)
            for module_id, checkpoint in checkpoints.items()
        }

    @app.get("/checkpoints/{module_id:path}")
    def checkpoint(module_id: str, attempt: int = 0) -> CheckpointOut:
        found = checkpoint_of(module_id)
        return CheckpointOut(
            module_id=module_id,
            status=found.status,
            attempt=attempt,
            pass_mark=PASS_MARK,
            questions=[
                AskedQuestion(
                    id=question.id,
                    topic=question.topic,
                    text=question.text,
                    options=question.options,
                )
                for question in found.questions_for_attempt(attempt)
            ],
        )

    @app.post("/attempts/{module_id:path}")
    def attempt(
        module_id: str, body: AttemptRequest, request: Request
    ) -> AttemptResponse:
        """Grades an attempt and returns the path with its result: locked modules, a "prove" turned
        into "study", or suggestions after a checkpoint passed without a mistake."""
        path = check_path(body.path)
        found = checkpoint_of(module_id)
        # The questions of an attempt follow from its number, so the path decides which attempt this is.
        if body.attempt != act(lambda: path.item(module_id)).attempts:
            raise HTTPException(
                409, "This attempt does not follow the path's last one."
            )
        try:
            grade = found.grade(body.attempt, body.answers)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if grade.effortless:
            within_quota(request)  # suggestions after it ask the model
        updated = act(lambda: roadmap.after_checkpoint(path, module_id, grade))
        return AttemptResponse(grade=grade, path=updated)

    @app.post("/path/done")
    def done(body: PathAction) -> LearningPath:
        """Marks a module without a checkpoint as done."""
        if body.module_id in checkpoints:
            raise HTTPException(409, "This module has a checkpoint: pass it instead.")
        return act(lambda: check_path(body.path).marked_done(body.module_id))

    @app.post("/path/accept")
    def accept(body: PathAction) -> LearningPath:
        return act(lambda: check_path(body.path).accept(body.module_id))

    @app.post("/path/decline")
    def decline(body: PathAction) -> LearningPath:
        return act(lambda: check_path(body.path).decline(body.module_id))

    return app


class ApiSettings(Settings):
    # Comma-separated origins allowed to call the API from a browser.
    api_allowed_origins: str = "http://localhost:3000"
    api_rate_limit: int = 20  # model-calling requests per client per window
    api_rate_window: int = 3600  # seconds

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.api_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache(maxsize=1)
def _app() -> FastAPI:
    settings = ApiSettings()
    roadmap = Roadmap.from_settings(settings)
    return create_app(
        roadmap=roadmap,
        source=CurriculumSource.from_file(settings.curriculum_file),
        allowed_origins=settings.allowed_origins,
        limiter=RateLimiter(settings.api_rate_limit, settings.api_rate_window),
        checkpoints=CheckpointStore(settings.checkpoints_dir).all_for(
            roadmap.curriculum
        ),
    )


def __getattr__(name: str) -> FastAPI:
    """`roadmap.api:app` builds the app on first use, so importing this module reads no settings."""
    if name == "app":
        return _app()
    raise AttributeError(name)
