"""Path planning: what a learner does with each module, and why. The course order is kept."""

import logging
import re
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, Field

from . import prompts
from .curriculum import Curriculum, Level, Module
from .llm import LLMClient, UnusableAnswer
from .onboarding import Answers, Question, format_answers
from .path import Choice, PathItem, Reason, SkimTopic

logger = logging.getLogger(__name__)


class Planner(Protocol):
    def plan(
        self, answers: Answers, level: Level | None, progress: str | None = None
    ) -> list[PathItem]: ...


class SkimSuggestion(BaseModel):
    topic: str = Field(
        description="One of the module's topic titles, exactly as given."
    )
    reason: Reason = Field(
        description="One short sentence tied to the learner's answers."
    )


class ModuleDecision(BaseModel):
    module_id: str = Field(description="The module's id exactly as given, such as m3.")
    choice: Choice
    reason: Reason = Field(
        description="One or two sentences to the learner, tied to their answers or goal."
    )
    skim: list[SkimSuggestion] = Field(
        default=[],
        description="For a module to study only: topics the learner knows but should refresh. Empty otherwise.",
    )
    skip_topics: list[SkimSuggestion] = Field(
        default=[],
        description="For a module to study only: topics the learner's answers show they already know, which "
        "the checkpoint then leaves out. Empty otherwise.",
    )


def _topics_for(
    module: Module, decision: ModuleDecision
) -> tuple[list[SkimTopic], list[SkimTopic]]:
    """The topics to skim and to skip, as the module's own titles: only for a module to study, never a topic
    the module does not have, and at least one topic left to study in full; else the module would be one to
    prove or skip."""
    if decision.choice is not Choice.STUDY or module.is_project:
        return [], []

    def key(title: str) -> str:
        return re.sub(r"^\d+\.\s*", "", title).strip().casefold()

    titles = {key(topic.title): topic.title for topic in module.topics}
    marked: set[str] = set()

    def found(suggestions: list[SkimSuggestion]) -> list[SkimTopic]:
        kept = []
        for suggestion in suggestions:
            title = titles.get(key(suggestion.topic))
            if title and title not in marked:
                marked.add(title)
                kept.append(SkimTopic(topic=title, reason=suggestion.reason))
        return kept

    skip = found(decision.skip_topics)
    if len(skip) >= len(titles):
        skip = []
        marked.clear()
    skim = found(decision.skim)
    if len(marked) >= len(titles):
        skim = []  # leaves nothing to study in full: keep only what is skipped
    return skim, skip


class PlanDecisions(BaseModel):
    decisions: list[ModuleDecision] = Field(
        description="Exactly one decision for every module."
    )
    title: str | None = Field(
        default=None,
        description="The learner's goal as a title for their path, in two to six plain words, "
        "such as 'Computer vision research'.",
    )


MAX_TITLE = 60


def clean_title(title: str | None) -> str | None:
    """The model's title, on one line and short; None when it gave none."""
    if not title:
        return None
    title = " ".join(title.split()).strip(" .\"'")
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE].rsplit(" ", 1)[0]
    return title or None


def prompt_ids(modules: list[Module]) -> dict[str, Module]:
    """Short ids (m1, m2, ...) the model sees instead of module ids.

    Models copy short ids reliably, while a long id that does not match the title tends to
    get "corrected".
    """
    return {f"m{number}": module for number, module in enumerate(modules, start=1)}


class LLMPlanner:
    """The model judges each module; code keeps the course order and checks every decision."""

    NO_CHECKLIST = (
        "Kept for study: the planner suggested proving this module, "
        "but it has no checklist to prove it with."
    )

    def __init__(
        self, llm: LLMClient, curriculum: Curriculum, questions: list[Question]
    ) -> None:
        self._llm = llm
        self._modules = prompt_ids(curriculum.modules)
        self._questions = questions

    def plan(
        self, answers: Answers, level: Level | None, progress: str | None = None
    ) -> list[PathItem]:
        """`progress` says what the learner has shown since onboarding, such as a checkpoint passed."""
        return self.plan_with_title(answers, level, progress)[0]

    def plan_with_title(
        self, answers: Answers, level: Level | None, progress: str | None = None
    ) -> tuple[list[PathItem], str | None]:
        """The plan and a short title for the path, named after the learner's goal."""
        response = self._llm.ask(
            prompts.load("path"),
            self._prompt(answers, level, progress),
            PlanDecisions,
            check=self._check_every_module_decided,
        )
        decisions = {decision.module_id: decision for decision in response.decisions}
        if unknown := sorted(decisions.keys() - self._modules.keys()):
            logger.warning(
                "Ignored decisions for unknown modules: %s", ", ".join(unknown)
            )
        items = [
            self._item(module, decisions[prompt_id])
            for prompt_id, module in self._modules.items()
        ]
        return items, clean_title(response.title)

    def _check_every_module_decided(self, response: PlanDecisions) -> None:
        """A plan that leaves modules out is rejected, so the next model is asked instead."""
        decided = {decision.module_id for decision in response.decisions}
        if missing := sorted(self._modules.keys() - decided):
            ids = ", ".join(self._modules[prompt_id].id for prompt_id in missing)
            raise UnusableAnswer(f"No decision for {ids}")

    def _item(self, module: Module, decision: ModuleDecision) -> PathItem:
        if decision.choice is Choice.PROVE and not module.can_be_proved:
            logger.warning(
                "The model suggested proving %s, which has no checklist", module.id
            )
            return PathItem.suggestion(module, Choice.STUDY, self.NO_CHECKLIST)
        skim, skip = _topics_for(module, decision)
        return PathItem.suggestion(module, decision.choice, decision.reason, skim, skip)

    def _prompt(
        self, answers: Answers, level: Level | None, progress: str | None = None
    ) -> str:
        outlines = [
            _outline(prompt_id, module) for prompt_id, module in self._modules.items()
        ]
        modules = yaml.safe_dump(
            outlines, sort_keys=False, allow_unicode=True, width=120
        )
        return (
            f"Learner's answers:\n\n{format_answers(self._questions, answers)}\n\n"
            f"Learner's level: {level or 'not assessed'}\n\n"
            + (f"Since then: {progress}\n\n" if progress else "")
            + f"Modules in course order:\n\n{modules}"
        )


def _outline(prompt_id: str, module: Module) -> dict[str, Any]:
    outline: dict[str, Any] = {
        "id": prompt_id,
        "title": module.full_title,
        "about": module.description,
        "resources": [
            (
                f"{resource.title} ({resource.difficulty})"
                if resource.difficulty
                else resource.title
            )
            for resource in module.resources
        ],
    }
    if module.topics:
        outline["topics"] = [topic.title for topic in module.topics]
    if module.prerequisites:
        outline["prerequisites"] = module.prerequisites
    if module.checklist:
        outline["checklist"] = module.checklist
    return outline


class CourseOrderPlanner:
    """The fallback when no model answers: the course as written, every module to study."""

    REASON = (
        "Included because personalization is unavailable right now, "
        "so the path follows the course as written."
    )

    def __init__(self, curriculum: Curriculum) -> None:
        self._curriculum = curriculum

    def plan(
        self, answers: Answers, level: Level | None, progress: str | None = None
    ) -> list[PathItem]:
        return [
            PathItem.suggestion(module, Choice.STUDY, self.REASON)
            for module in self._curriculum.modules
        ]
