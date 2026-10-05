"""The entry point for interfaces: suggest a level, then build a path, falling back when no model answers."""

import logging

from .config import Settings
from .curriculum import Curriculum, Level
from .level import LevelAssessment, LevelAssessor
from .llm import LLMClient, LLMUnavailable, connect
from .onboarding import Answers, Question, load_questions
from .path import LearningPath, PathItem
from .planner import CourseOrderPlanner, LLMPlanner, Planner
from .source import CurriculumSource, load_curriculum

logger = logging.getLogger(__name__)


class Roadmap:
    def __init__(
        self, curriculum: Curriculum, questions: list[Question], llm: LLMClient | None
    ) -> None:
        self.curriculum = curriculum
        self.questions = questions
        self._assessor = LevelAssessor(llm, questions) if llm is not None else None
        self._planner: Planner | None = (
            LLMPlanner(llm, curriculum, questions) if llm is not None else None
        )
        self._fallback: Planner = CourseOrderPlanner(curriculum)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Roadmap":
        source = CurriculumSource.from_file(settings.curriculum_file)
        return cls(
            curriculum=load_curriculum(source, settings.curriculum_checkout),
            questions=load_questions(settings.questions_file),
            llm=connect(settings),
        )

    @property
    def personalization_available(self) -> bool:
        return self._planner is not None

    def assess_level(self, answers: Answers) -> LevelAssessment | None:
        """A suggested level, or None when no model is available and the learner has to choose one."""
        if self._assessor is None:
            return None
        try:
            return self._assessor.assess(answers)
        except LLMUnavailable as error:
            logger.warning("Level inference unavailable: %s", error)
            return None

    def build_path(
        self,
        answers: Answers,
        level: Level | None,
        assessment: LevelAssessment | None = None,
    ) -> LearningPath:
        """Plan for `level`, the learner's own choice, which may differ from the suggested `assessment`."""
        items = self._personal_plan(answers, level)
        return LearningPath(
            level=level,
            assessment=assessment,
            items=items if items is not None else self._fallback.plan(answers, level),
            personalization_unavailable=items is None,
            curriculum_version=self.curriculum.version,
            attribution=self.curriculum.attribution,
        )

    def _personal_plan(
        self, answers: Answers, level: Level | None
    ) -> list[PathItem] | None:
        if self._planner is None:
            return None
        try:
            return self._planner.plan(answers, level)
        except LLMUnavailable as error:
            logger.warning(
                "Personal planning unavailable, following the course order: %s", error
            )
            return None
