"""The generated path. Its JSON form is what every interface reads, and what a learner keeps.

The planner only suggests. The learner can change any decision and confirms the path before using it.

Once the learner works through the path, it also keeps their progress. A failed checkpoint locks the modules
after it until the learner passes it; it also turns "prove" into "study", since the learner could not prove
the module. A checkpoint passed without a mistake at the first try may bring suggestions to lighten the
modules that follow; the learner accepts or declines each.
"""

from datetime import UTC, datetime
from uuid import uuid4
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from .curriculum import Attribution, Level, Module
from .level import LevelAssessment
from .onboarding import Answers

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


# How much each choice asks of the learner; a suggestion after a checkpoint may only lighten a module.
WEIGHT = {Choice.STUDY: 2, Choice.PROVE: 1, Choice.SKIP: 0}


class Progress(StrEnum):
    NOT_STARTED = "not_started"
    DONE = "done"  # the learner marked a module without a checkpoint as done
    # The questions are passed and the module's coding problem is next; does not lock what follows.
    PRACTICE = "practice"
    PASSED = "passed"
    FAILED = "failed"  # until the learner passes the checkpoint on a later attempt


class PathItem(BaseModel):
    module: Module
    # The planner's suggestion and why.
    suggested: Choice
    reason: Reason
    # What the learner will do: the suggestion, unless they changed it.
    choice: Choice
    progress: Progress = Progress.NOT_STARTED
    attempts: int = 0  # checkpoint attempts so far
    last_score: str | None = None  # such as "4/5"
    # Why the path changed this module on its own, after a checkpoint.
    adjustment: str | None = None

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

    @property
    def finished(self) -> bool:
        return self.progress in (Progress.DONE, Progress.PASSED)

    def chosen(self, choice: Choice) -> "PathItem":
        """This item with the learner's own choice; validated again, since not every module can be proved."""
        return PathItem.model_validate({**self.model_dump(), "choice": choice})


class Proposal(BaseModel):
    """A lighter choice for a module, suggested after a checkpoint; the learner accepts or declines it."""

    module_id: str
    choice: Choice
    reason: Reason


class TimeEstimate(BaseModel):
    """Hours for the path and for the whole course, from the modules that state an estimate."""

    path_low: float
    path_high: float
    course_low: float
    course_high: float
    # Included modules with no estimate: the path's hours leave them out.
    modules_without_estimate: int


class LearningPath(BaseModel):
    # A random id, so anonymous progress events of one path can be told apart; nothing about the learner.
    id: str | None = Field(default_factory=lambda: uuid4().hex)
    # The level the path was planned for, after any correction by the learner.
    level: Level | None
    assessment: LevelAssessment | None  # what the model suggested, if it was asked
    items: list[PathItem]  # every module of the course, in course order
    personalization_unavailable: bool
    curriculum_version: str
    # The curriculum site's name for that version, such as "current", so a page can link to its modules.
    curriculum_site_version: str | None = None
    attribution: Attribution
    changes: str = CHANGES_NOTICE
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # When the learner approved the path; any later change clears it.
    confirmed_at: datetime | None = None
    # The onboarding answers, so the rest of the path can be planned again after a checkpoint.
    answers: Answers = {}
    proposals: list[Proposal] = []
    # The learner chose to share anonymous progress events (see roadmap.events). Off unless they turn it on.
    share_progress: bool = False

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
        proposals = [p for p in self.proposals if p.module_id != module_id]
        return self.model_copy(
            update={"items": items, "confirmed_at": None, "proposals": proposals}
        )

    def confirm(self) -> "LearningPath":
        return self.model_copy(update={"confirmed_at": datetime.now(UTC)})

    @computed_field  # type: ignore[prop-decorator]
    @property
    def time_estimate(self) -> TimeEstimate:
        """A module to prove counts as a fifth of its hours: the learner works through its checklist."""
        share = {Choice.STUDY: 1.0, Choice.PROVE: 0.2, Choice.SKIP: 0.0}
        path_low = path_high = course_low = course_high = 0.0
        unknown = 0
        for item in self.items:
            hours = item.module.hours
            if hours is None:
                unknown += item.included
                continue
            course_low += hours.low
            course_high += hours.high
            path_low += hours.low * share[item.choice]
            path_high += hours.high * share[item.choice]
        return TimeEstimate(
            path_low=round(path_low),
            path_high=round(path_high),
            course_low=round(course_low),
            course_high=round(course_high),
            modules_without_estimate=unknown,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def locked_module_ids(self) -> list[str]:
        """The modules after the first failed checkpoint, until the learner passes it."""
        for index, item in enumerate(self.items):
            if item.included and item.progress is Progress.FAILED:
                return [later.module.id for later in self.items[index + 1 :]]
        return []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def blocking_module_id(self) -> str | None:
        """The failed module that locks the rest, if any."""
        locked = self.locked_module_ids
        if not locked:
            return None
        position = [item.module.id for item in self.items].index(locked[0])
        return self.items[position - 1].module.id

    def item(self, module_id: str) -> PathItem:
        for item in self.items:
            if item.module.id == module_id:
                return item
        raise KeyError(f"The path has no module '{module_id}'")

    def _replace(self, item: PathItem, **update: Any) -> "LearningPath":
        items = [item if old.module.id == item.module.id else old for old in self.items]
        return self.model_copy(update={"items": items, **update})

    def _check_open(self, module_id: str) -> PathItem:
        item = self.item(module_id)
        if not self.confirmed:
            raise PathStateError("Confirm the path before working through it")
        if module_id in self.locked_module_ids:
            raise PathStateError(
                f"'{module_id}' is locked until the checkpoint of "
                f"'{self.blocking_module_id}' is passed"
            )
        if not item.included:
            raise PathStateError(f"'{module_id}' is skipped in this path")
        return item

    def with_checkpoint_result(
        self,
        module_id: str,
        score: int,
        total: int,
        passed: bool,
        problem_pending: bool = False,
    ) -> "LearningPath":
        """The path after a checkpoint attempt. A failed "prove" becomes "study"; the path stays
        confirmed, since the rule is the one the learner saw when they confirmed it. Passed questions
        with a coding problem still to solve leave the module in practice."""
        item = self._check_open(module_id)
        if passed:
            progress = Progress.PRACTICE if problem_pending else Progress.PASSED
        else:
            progress = Progress.FAILED
        update: dict[str, Any] = {
            "attempts": item.attempts + 1,
            "last_score": f"{score}/{total}",
            "progress": progress,
        }
        if not passed and item.choice is Choice.PROVE:
            update["choice"] = Choice.STUDY
            update["adjustment"] = (
                f"Changed to study: the checkpoint showed gaps ({score}/{total}). "
                "Study the module, then take the checkpoint again."
            )
        proposals = [p for p in self.proposals if p.module_id != module_id]
        return self._replace(item.model_copy(update=update), proposals=proposals)

    def with_problem_solved(self, module_id: str) -> "LearningPath":
        """The learner's code passed the module's coding problem, after its questions."""
        item = self._check_open(module_id)
        if item.progress is not Progress.PRACTICE:
            raise PathStateError(f"Pass the questions of '{module_id}' first")
        return self._replace(item.model_copy(update={"progress": Progress.PASSED}))

    def with_new_goal(self, goal: str, items: list[PathItem]) -> "LearningPath":
        """The path for a new goal: `items` are the planner's new decisions. Modules the learner has
        started keep their decision and progress; the rest take the new decision. The learner confirms
        the path again, since the planner changed it."""
        planned = {item.module.id: item for item in items}
        kept = [
            (
                old
                if old.progress is not Progress.NOT_STARTED
                or old.module.id not in planned
                else planned[old.module.id]
            )
            for old in self.items
        ]
        return self.model_copy(
            update={
                "items": kept,
                "answers": {**self.answers, "goal": goal},
                "proposals": [],
                "confirmed_at": None,
            }
        )

    def marked_done(self, module_id: str) -> "LearningPath":
        """The learner finished a module that has no checkpoint."""
        item = self._check_open(module_id)
        return self._replace(item.model_copy(update={"progress": Progress.DONE}))

    def with_proposals(self, proposals: list["Proposal"]) -> "LearningPath":
        """Keeps only proposals that lighten a module the learner has not started."""
        kept = []
        for proposal in proposals:
            item = self.item(proposal.module_id)
            lighter = WEIGHT[proposal.choice] < WEIGHT[item.choice]
            provable = proposal.choice is not Choice.PROVE or item.module.can_be_proved
            if (
                lighter
                and provable
                and item.progress is Progress.NOT_STARTED
                and proposal.module_id not in self.locked_module_ids
            ):
                kept.append(proposal)
        return self.model_copy(update={"proposals": kept})

    def accept(self, module_id: str) -> "LearningPath":
        """The learner takes the suggestion; their acceptance is their approval, so the path stays
        confirmed."""
        proposal = next((p for p in self.proposals if p.module_id == module_id), None)
        if proposal is None:
            raise PathStateError(f"No suggestion for '{module_id}'")
        item = self.item(module_id).model_copy(
            update={
                "choice": proposal.choice,
                "adjustment": f"You accepted a suggestion after a checkpoint: {proposal.reason}",
            }
        )
        rest = [p for p in self.proposals if p.module_id != module_id]
        return self._replace(item, proposals=rest)

    def decline(self, module_id: str) -> "LearningPath":
        rest = [p for p in self.proposals if p.module_id != module_id]
        return self.model_copy(update={"proposals": rest})


class PathStateError(ValueError):
    """An action the path does not allow in its current state."""


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
