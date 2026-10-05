"""Path planning: what a learner does with each module, and why. The course order is kept."""

import logging
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, Field

from . import prompts
from .curriculum import Curriculum, Level, Module
from .llm import LLMClient, UnusableAnswer
from .onboarding import Answers, Question, format_answers
from .path import Choice, PathItem, Reason

logger = logging.getLogger(__name__)


class Planner(Protocol):
    def plan(self, answers: Answers, level: Level | None) -> list[PathItem]: ...


class ModuleDecision(BaseModel):
    module_id: str = Field(description="The module's id exactly as given, such as m3.")
    choice: Choice
    reason: Reason = Field(
        description="One or two sentences to the learner, tied to their answers or goal."
    )


class PlanDecisions(BaseModel):
    decisions: list[ModuleDecision] = Field(
        description="Exactly one decision for every module."
    )


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

    def plan(self, answers: Answers, level: Level | None) -> list[PathItem]:
        response = self._llm.ask(
            prompts.load("path"),
            self._prompt(answers, level),
            PlanDecisions,
            check=self._check_every_module_decided,
        )
        decisions = {decision.module_id: decision for decision in response.decisions}
        if unknown := sorted(decisions.keys() - self._modules.keys()):
            logger.warning(
                "Ignored decisions for unknown modules: %s", ", ".join(unknown)
            )
        return [
            self._item(module, decisions[prompt_id])
            for prompt_id, module in self._modules.items()
        ]

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
        return PathItem.suggestion(module, decision.choice, decision.reason)

    def _prompt(self, answers: Answers, level: Level | None) -> str:
        outlines = [
            _outline(prompt_id, module) for prompt_id, module in self._modules.items()
        ]
        modules = yaml.safe_dump(
            outlines, sort_keys=False, allow_unicode=True, width=120
        )
        return (
            f"Learner's answers:\n\n{format_answers(self._questions, answers)}\n\n"
            f"Learner's level: {level or 'not assessed'}\n\n"
            f"Modules in course order:\n\n{modules}"
        )


def _outline(prompt_id: str, module: Module) -> dict[str, Any]:
    outline: dict[str, Any] = {
        "id": prompt_id,
        "title": module.full_title,
        "about": module.description,
        "resources": [
            f"{resource.title} ({resource.difficulty})" for resource in module.resources
        ],
    }
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

    def plan(self, answers: Answers, level: Level | None) -> list[PathItem]:
        return [
            PathItem.suggestion(module, Choice.STUDY, self.REASON)
            for module in self._curriculum.modules
        ]
