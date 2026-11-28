"""The entry point for interfaces: suggest a level, then build a path, falling back when no model answers."""

import logging
from collections.abc import Iterator

from .config import Settings
from .curriculum import Curriculum, Level
from .level import LevelAssessment, LevelAssessor
from .llm import LLMClient, LLMUnavailable, connect
from .onboarding import Answers, Question, load_questions
from .checkpoints import Grade
from .path import Choice, LearningPath, PathItem, Proposal
from .planner import CourseOrderPlanner, LLMPlanner, Plan, Planner
from .source import CurriculumSource, load_curriculum

logger = logging.getLogger(__name__)


class Roadmap:
    def __init__(
        self, curriculum: Curriculum, questions: list[Question], llm: LLMClient | None
    ) -> None:
        self.curriculum = curriculum
        self.questions = questions
        self.llm = llm  # also reviews submitted projects
        self._assessor = LevelAssessor(llm, questions) if llm is not None else None
        self._planner: Planner | None = (
            LLMPlanner(llm, curriculum, questions) if llm is not None else None
        )
        self._fallback: Planner = CourseOrderPlanner(curriculum)

    @classmethod
    def from_settings(cls, settings: Settings, version: str | None = None) -> "Roadmap":
        """A roadmap for one curriculum version: the newest in the config unless named."""
        source = CurriculumSource.from_file(settings.curriculum_file)
        return cls(
            curriculum=load_curriculum(
                source, source.version(version), settings.curricula_dir
            ),
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
        items, title = self._personal_plan(answers, level)
        return self._new_path(answers, level, assessment, items, title)

    def build_path_streaming(
        self,
        answers: Answers,
        level: Level | None,
        assessment: LevelAssessment | None = None,
    ) -> Iterator[PathItem | LearningPath]:
        """As `build_path`, with each module's decision as soon as the model has made it, then the path, last.
        When no model answers, the path follows the course order, as `build_path` does.
        """
        streaming = getattr(self._planner, "plan_streaming", None)
        if streaming is None:
            yield self.build_path(answers, level, assessment)
            return
        try:
            for event in streaming(answers, level):
                if isinstance(event, Plan):
                    yield self._new_path(
                        answers, level, assessment, event.items, event.title
                    )
                    return
                yield event
        except LLMUnavailable as error:
            logger.warning(
                "Personal planning unavailable, following the course order: %s", error
            )
        yield self._new_path(answers, level, assessment, None, None)

    def _new_path(
        self,
        answers: Answers,
        level: Level | None,
        assessment: LevelAssessment | None,
        items: list[PathItem] | None,
        title: str | None,
    ) -> LearningPath:
        return LearningPath(
            level=level,
            assessment=assessment,
            items=items if items is not None else self._fallback.plan(answers, level),
            personalization_unavailable=items is None,
            title=title,
            curriculum_version=self.curriculum.version,
            curriculum_site_version=self.curriculum.site_version,
            attribution=self.curriculum.attribution,
            answers=answers,
        )

    def after_checkpoint(
        self, path: LearningPath, module_id: str, grade: Grade, suggest: bool = True
    ) -> LearningPath:
        """The path with the learner's checkpoint result. After a checkpoint passed without a mistake at the
        first try, the model may suggest lightening the modules and topics that follow; after a failed one,
        it makes heavier at once those that build on the topics the learner got wrong. `suggest` False leaves
        the model out, as when the learner is over their quota."""
        path = path.with_checkpoint_result(
            module_id,
            grade.score,
            grade.total,
            grade.passed,
            grade.problem_pending,
            missed_topics=grade.review_topics,
        )
        if not suggest or not self.wants_suggestions(grade):
            return path
        return path.with_checkpoint_changes(
            self.suggestions_after(path, module_id, grade)
        )

    def wants_suggestions(self, grade: Grade) -> bool:
        """Whether a checkpoint result asks the model for changes to the rest of the path."""
        return self._planner is not None and (
            grade.effortless or (not grade.passed and bool(grade.review_topics))
        )

    def suggestions_after(
        self, path: LearningPath, module_id: str, grade: Grade
    ) -> list[Proposal]:
        """Lighter modules and topics after an easy pass, heavier after a failure. Slow: one model call over
        the whole course, so the API runs it after answering."""
        if grade.effortless:
            topics = list(dict.fromkeys(feedback.topic for feedback in grade.feedback))
            return self._proposals_after(path, module_id, topics, failed=False)
        return self._proposals_after(path, module_id, grade.review_topics, failed=True)

    def change_goal(self, path: LearningPath, goal: str) -> LearningPath:
        """The path replanned for a new goal, keeping what the learner has started. Raises
        LLMUnavailable when no model answers: without one, the path could only fall back to the whole
        course, which would undo the learner's own plan."""
        if self._planner is None:
            raise LLMUnavailable("No model is configured")
        started = [
            f"{item.module.full_title} ({item.progress})"
            for item in path.items
            if item.progress != "not_started"
        ]
        note = f"the learner changed their goal to: {goal}." + (
            f" They have already worked on: {'; '.join(started)}." if started else ""
        )
        answers = {**path.answers, "goal": goal}
        items, title = self._titled_plan(answers, path.level, note)
        return path.with_new_goal(goal, items, title)

    def _proposals_after(
        self, path: LearningPath, module_id: str, topics: list[str], failed: bool
    ) -> list[Proposal]:
        """The planner asked again with the checkpoint's result; what it would change in the modules after
        this one, as proposals for whole modules and for single topics."""
        if self._planner is None:
            return []
        title = path.item(module_id).module.full_title
        current = "; ".join(_decision(item) for item in path.items)
        if failed:
            note = (
                f"the learner failed the checkpoint of '{title}', getting wrong the questions on: "
                f"{'; '.join(topics)}. Their current decisions are: {current}. Return these decisions "
                "unchanged, except for a later module or topic that builds directly on these topics, which "
                "may now need more: to study instead of prove, or a topic studied in full instead of skimmed "
                "or skipped. A module that is skipped stays skipped. Keep everything else exactly as it is."
            )
        else:
            note = (
                f"the learner passed the checkpoint of '{title}' without a mistake at the first try, "
                f"answering questions on: {'; '.join(topics)}. Their current decisions are: {current}. "
                "Return these decisions unchanged, except for a later module that teaches these topics again "
                "or builds directly on them, which may now be lighter, as a whole or by skimming or skipping "
                "some of its topics."
            )
        try:
            items = self._planner.plan(path.answers, path.level, note)
        except LLMUnavailable as error:
            logger.warning("No suggestions after the checkpoint: %s", error)
            return []
        ids = [item.module.id for item in path.items]
        later = set(ids[ids.index(module_id) + 1 :])
        proposals = []
        for planned in items:
            if planned.module.id not in later:
                continue
            current_item = path.item(planned.module.id)
            if planned.choice is not current_item.choice:
                proposals.append(
                    Proposal(
                        module_id=planned.module.id,
                        choice=planned.choice,
                        reason=planned.reason,
                        after_failure=failed,
                    )
                )
                continue
            if planned.choice is not Choice.STUDY:
                continue
            reasons = {
                marked.topic: marked.reason
                for marked in [*planned.skim, *planned.skip_topics]
                if marked.reason
            }
            for topic in current_item.module.topics:
                old, new = current_item.topic_choice(topic.title), planned.topic_choice(
                    topic.title
                )
                if old is not new:
                    proposals.append(
                        Proposal(
                            module_id=planned.module.id,
                            topic=topic.title,
                            topic_choice=new,
                            reason=reasons.get(topic.title, planned.reason),
                            after_failure=failed,
                        )
                    )
        return proposals

    def _personal_plan(
        self, answers: Answers, level: Level | None
    ) -> tuple[list[PathItem] | None, str | None]:
        if self._planner is None:
            return None, None
        try:
            return self._titled_plan(answers, level)
        except LLMUnavailable as error:
            logger.warning(
                "Personal planning unavailable, following the course order: %s", error
            )
            return None, None

    def _titled_plan(
        self, answers: Answers, level: Level | None, progress: str | None = None
    ) -> tuple[list[PathItem], str | None]:
        """The planner's decisions, and a title when the planner gives one."""
        assert self._planner is not None  # nosec B101: callers check
        titled = getattr(self._planner, "plan_with_title", None)
        if titled is not None:
            return titled(answers, level, progress)
        return self._planner.plan(answers, level, progress), None


def _decision(item: PathItem) -> str:
    """A module's decision as the planner is told it, with the topics the learner skims or skips."""
    text = f"{item.module.id}: {item.choice}"
    parts = []
    if item.skimmed_topics:
        parts.append("skim " + ", ".join(sorted(item.skimmed_topics)))
    if item.skipped_topics:
        parts.append("skip " + ", ".join(sorted(item.skipped_topics)))
    return text + (f" ({'; '.join(parts)})" if parts else "")
