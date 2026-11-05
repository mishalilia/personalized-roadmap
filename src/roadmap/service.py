"""The entry point for interfaces: suggest a level, then build a path, falling back when no model answers."""

import logging

from .config import Settings
from .curriculum import Curriculum, Level
from .level import LevelAssessment, LevelAssessor
from .llm import LLMClient, LLMUnavailable, connect
from .onboarding import Answers, Question, load_questions
from .checkpoints import Grade
from .path import LearningPath, PathItem, Proposal
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
            answers=answers,
        )

    def after_checkpoint(
        self, path: LearningPath, module_id: str, grade: Grade
    ) -> LearningPath:
        """The path with the learner's checkpoint result. After a checkpoint passed without a mistake
        at the first try, the model may suggest lightening the modules that follow."""
        path = path.with_checkpoint_result(
            module_id, grade.score, grade.total, grade.passed
        )
        if not grade.effortless:
            return path
        return path.with_proposals(self._lighter_after(path, module_id))

    def _lighter_after(self, path: LearningPath, module_id: str) -> list[Proposal]:
        if self._planner is None:
            return []
        title = path.item(module_id).module.full_title
        note = f"the learner passed the checkpoint of '{title}' without a mistake at the first try."
        try:
            items = self._planner.plan(path.answers, path.level, note)
        except LLMUnavailable as error:
            logger.warning("No suggestions after the checkpoint: %s", error)
            return []
        ids = [item.module.id for item in path.items]
        later = set(ids[ids.index(module_id) + 1 :])
        return [
            Proposal(module_id=item.module.id, choice=item.choice, reason=item.reason)
            for item in items
            if item.module.id in later
        ]

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
