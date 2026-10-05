"""The generated path. Its JSON form is what every interface reads.

The planner only suggests. The learner can change any decision and confirms the path before using it.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from .curriculum import Attribution, Level, Module
from .level import LevelAssessment

CHANGES_NOTICE = (
    "Arranged as a personal path: modules are listed in course order and marked to "
    "study, to prove or to skip, each with a reason. Linked resources remain under their "
    "own licences."
)

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Choice(StrEnum):
    """What a learner does with a module."""

    STUDY = "study"
    PROVE = "prove"  # work through its checklist instead; study it only if that fails
    SKIP = "skip"


class PathItem(BaseModel):
    module: Module
    # The planner's suggestion and why.
    suggested: Choice
    reason: Reason
    # What the learner will do: the suggestion, unless they changed it.
    choice: Choice

    @model_validator(mode="after")
    def _prove_only_with_a_checklist(self) -> "PathItem":
        proving = Choice.PROVE in (self.suggested, self.choice)
        if proving and not self.module.can_be_proved:
            raise ValueError(f"'{self.module.id}' has no checklist to prove it with")
        return self

    @classmethod
    def suggestion(cls, module: Module, choice: Choice, reason: str) -> "PathItem":
        return cls(module=module, suggested=choice, reason=reason, choice=choice)

    @property
    def included(self) -> bool:
        """Whether the module stays in the path, to study or to prove."""
        return self.choice is not Choice.SKIP

    @property
    def changed_by_learner(self) -> bool:
        return self.choice is not self.suggested

    def chosen(self, choice: Choice) -> "PathItem":
        """This item with the learner's own choice."""
        return PathItem(
            module=self.module,
            suggested=self.suggested,
            reason=self.reason,
            choice=choice,
        )


class LearningPath(BaseModel):
    # The level the path was planned for, after any correction by the learner.
    level: Level | None
    assessment: LevelAssessment | None  # what the model suggested, if it was asked
    items: list[PathItem]  # every module of the course, in course order
    personalization_unavailable: bool
    curriculum_version: str
    attribution: Attribution
    changes: str = CHANGES_NOTICE
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # When the learner approved the path; any later change clears it.
    confirmed_at: datetime | None = None

    @property
    def included(self) -> list[PathItem]:
        return [item for item in self.items if item.included]

    @property
    def skipped(self) -> list[PathItem]:
        return [item for item in self.items if not item.included]

    @property
    def confirmed(self) -> bool:
        return self.confirmed_at is not None

    def count(self, choice: Choice) -> int:
        return sum(item.choice is choice for item in self.items)

    def with_choice(self, module_id: str, choice: Choice) -> "LearningPath":
        """A copy in which the learner's choice for the module replaces the planner's."""
        if module_id not in {item.module.id for item in self.items}:
            raise KeyError(f"The path has no module '{module_id}'")
        items = [
            item.chosen(choice) if item.module.id == module_id else item
            for item in self.items
        ]
        return self.model_copy(update={"items": items, "confirmed_at": None})

    def confirm(self) -> "LearningPath":
        return self.model_copy(update={"confirmed_at": datetime.now(UTC)})


def path_difference(first: LearningPath, second: LearningPath) -> float:
    """Share of the modules either path keeps that the two treat differently.

    0 when the paths are equal, 1 when they have nothing in common. A module proved in one
    path and studied in the other counts as different. Both paths cover the same course.
    """
    if [item.module.id for item in first.items] != [
        item.module.id for item in second.items
    ]:
        raise ValueError("The paths cover different courses")
    choices = [
        (a.choice, b.choice) for a, b in zip(first.items, second.items, strict=True)
    ]
    kept = [pair for pair in choices if pair != (Choice.SKIP, Choice.SKIP)]
    return sum(a is not b for a, b in kept) / len(kept) if kept else 0.0
