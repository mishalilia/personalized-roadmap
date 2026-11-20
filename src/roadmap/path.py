"""The generated path. Its JSON form is what every interface reads, and what a learner keeps.

The planner only suggests. The learner can change any decision and confirms the path before using it.

Once the learner works through the path, it also keeps their progress. A failed checkpoint locks the modules
after it until the learner passes it; it also turns "prove" into "study", since the learner could not prove
the module. A checkpoint passed without a mistake at the first try may bring suggestions to lighten the
modules that follow; the learner accepts or declines each.
"""

import re
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
    SUBMITTED = "submitted"  # a project, waiting for a reviewer
    RETURNED = "returned"  # a project the reviewer sent back with a comment; does not lock what follows


class TopicChoice(StrEnum):
    """How the learner takes a topic of a module they study."""

    STUDY = "study"
    SKIM = "skim"  # go through it quickly; the checkpoint still asks about it
    SKIP = "skip"  # leave it out; the checkpoint does not ask about it


# The same for a topic of a module the learner studies.
TOPIC_WEIGHT = {TopicChoice.STUDY: 2, TopicChoice.SKIM: 1, TopicChoice.SKIP: 0}


def same_topic(first: str, second: str) -> bool:
    """Whether two titles name the same topic: "1. Readable Python" and "Readable Python" do."""

    def bare(title: str) -> str:
        return re.sub(r"^\d+\.\s*", "", title).strip().lower()

    return bare(first) == bare(second)


class SkimTopic(BaseModel):
    """A topic of a module to study that the learner's answers show they know: they can go through it quickly.
    The module's checkpoint still asks about it."""

    topic: str  # one of the module's topic titles
    reason: Reason
    chosen: bool = False  # the learner marked it, rather than the planner


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
    # The topics of the wrong answers in the last attempt, so the assistant can say what to review.
    missed_topics: list[str] = []
    # Why the path changed this module on its own, after a checkpoint.
    adjustment: str | None = None
    # For a module to study: topics the learner can skim, by the planner.
    skim: list[SkimTopic] = []
    # For a module to study: topics the learner leaves out, so its checkpoint does not ask about them.
    skip_topics: list[SkimTopic] = []
    # Topics the learner marked as finished, in the module's order: their own tally, which neither unlocks nor
    # passes anything; the checkpoint still decides whether the module is passed.
    finished_topics: list[str] = []

    @model_validator(mode="after")
    def _prove_only_with_a_checklist(self) -> "PathItem":
        proving = Choice.PROVE in (self.suggested, self.choice)
        if proving and not self.module.can_be_proved:
            raise ValueError(f"'{self.module.id}' has no checklist to prove it with")
        return self

    @classmethod
    def suggestion(
        cls,
        module: Module,
        choice: Choice,
        reason: str,
        skim: list[SkimTopic] | None = None,
        skip_topics: list[SkimTopic] | None = None,
    ) -> "PathItem":
        return cls(
            module=module,
            suggested=choice,
            reason=reason,
            choice=choice,
            skim=skim or [],
            skip_topics=skip_topics or [],
        )

    @property
    def skipped_topics(self) -> frozenset[str]:
        """The topics the checkpoint leaves out: only for a module studied; a module proved is checked whole."""
        if self.choice is not Choice.STUDY:
            return frozenset()
        return frozenset(marked.topic for marked in self.skip_topics)

    @property
    def skimmed_topics(self) -> frozenset[str]:
        if self.choice is not Choice.STUDY:
            return frozenset()
        return frozenset(marked.topic for marked in self.skim)

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

    def topic_choice(self, topic: str) -> TopicChoice:
        """How the learner takes a topic of this module: in full, skimmed, or left out."""
        if topic in self.skipped_topics:
            return TopicChoice.SKIP
        if topic in self.skimmed_topics:
            return TopicChoice.SKIM
        return TopicChoice.STUDY

    def chosen(self, choice: Choice) -> "PathItem":
        """This item with the learner's own choice; validated again, since not every module can be proved."""
        return PathItem.model_validate({**self.model_dump(), "choice": choice})


class Proposal(BaseModel):
    """A change to a module the learner has not started, suggested after a checkpoint; the learner accepts or
    declines it. Lighter after a checkpoint passed without a mistake, heavier after a failed one. It changes
    either the module's choice or, for a module the learner studies, how they take one of its topics."""

    module_id: str
    choice: Choice | None = None  # the module's new choice; None for a topic
    reason: Reason
    topic: str | None = None  # one of the module's topic titles
    topic_choice: TopicChoice | None = None
    after_failure: bool = False  # heavier, after a failed checkpoint; otherwise lighter

    @model_validator(mode="after")
    def _a_module_or_a_topic(self) -> "Proposal":
        for_topic = self.topic is not None and self.topic_choice is not None and self.choice is None
        for_module = self.choice is not None and self.topic is None and self.topic_choice is None
        if for_topic == for_module:
            raise ValueError("A proposal changes either the module's choice or one of its topics")
        return self

    def concerns(self, module_id: str, topic: str | None) -> bool:
        return self.module_id == module_id and self.topic == topic


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
    # A short name for the path, after the learner's goal, written by the planner; None without a model.
    title: str | None = None
    proposals: list[Proposal] = []
    # Set while the model works out suggestions after a checkpoint, as "module id:attempts", so that they land
    # only if the learner has not taken that checkpoint again meanwhile.
    suggestions_pending: str | None = None
    # Anonymous progress events (see roadmap.events) count this path; on unless the learner turns it off.
    share_progress: bool = True

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
        current = self.item(module_id)
        if choice is not current.choice and current.progress in (Progress.PASSED, Progress.DONE):
            raise PathStateError("This module is finished: its decision no longer changes")
        items = [
            item.chosen(choice) if item.module.id == module_id else item
            for item in self.items
        ]
        proposals = [p for p in self.proposals if p.module_id != module_id]
        return self.model_copy(
            update={"items": items, "confirmed_at": None, "proposals": proposals}
        )

    def with_topic(self, module_id: str, topic: str, choice: TopicChoice) -> "LearningPath":
        """The learner's own decision for a topic of a module they study: study it in full, skim it, or skip
        it, which leaves it out of the checkpoint. The path stays confirmed: the learner decided it."""
        item = self.item(module_id)
        order = [candidate.title for candidate in item.module.topics]
        if topic not in order:
            raise KeyError(f"'{module_id}' has no topic '{topic}'")
        if item.choice is not Choice.STUDY:
            raise PathStateError("Only a module you study has topics to skim or skip")
        if item.module.is_project:
            raise PathStateError("A project is done in full: its parts cannot be skimmed or skipped")
        if item.progress in (Progress.PASSED, Progress.DONE):
            raise PathStateError("This module is finished")
        skipped = {marked.topic for marked in item.skip_topics} - {topic}
        if choice is TopicChoice.SKIP and len(skipped) + 1 >= len(order):
            raise PathStateError("To leave out every topic, skip the module instead")

        def kept(marks: list[SkimTopic], wanted: bool, reason: str) -> list[SkimTopic]:
            others = [marked for marked in marks if marked.topic != topic]
            if wanted:
                already = next((marked for marked in marks if marked.topic == topic), None)
                others.append(already or SkimTopic(topic=topic, reason=reason, chosen=True))
            return sorted(others, key=lambda marked: order.index(marked.topic))

        return self._replace(
            item.model_copy(
                update={
                    "skim": kept(item.skim, choice is TopicChoice.SKIM, "You chose to skim it."),
                    "skip_topics": kept(
                        item.skip_topics, choice is TopicChoice.SKIP, "You chose to skip it."
                    ),
                    # A topic left out is not one to finish.
                    "finished_topics": [
                        t for t in item.finished_topics if not (t == topic and choice is TopicChoice.SKIP)
                    ],
                }
            )
        )

    def with_topic_finished(self, module_id: str, topic: str, finished: bool) -> "LearningPath":
        """The learner marks a topic of a module they study as finished, or takes the mark back. It is their own
        tally of where they are in the module; the module is still passed by its checkpoint."""
        item = self._check_open(module_id)
        order = [candidate.title for candidate in item.module.topics]
        if topic not in order:
            raise KeyError(f"'{module_id}' has no topic '{topic}'")
        if item.choice is not Choice.STUDY or item.module.is_project:
            raise PathStateError("Only the topics of a module you study can be marked as finished")
        if finished and topic in item.skipped_topics:
            raise PathStateError("This topic is skipped: study it to mark it as finished")
        done = (set(item.finished_topics) | {topic}) if finished else (set(item.finished_topics) - {topic})
        return self._replace(
            item.model_copy(update={"finished_topics": [t for t in order if t in done]})
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
            part = share[item.choice]
            if item.choice is Choice.STUDY and item.module.topics:
                # A skipped topic takes no time, a skimmed one about half.
                left_out = len(item.skipped_topics) + 0.5 * len(item.skimmed_topics - item.skipped_topics)
                part *= 1 - left_out / len(item.module.topics)
            path_low += hours.low * part
            path_high += hours.high * part
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
        missed_topics: list[str] | None = None,
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
            "missed_topics": list(missed_topics or []),
        }
        if not passed and item.choice is Choice.PROVE:
            # The path changes the decision, not the learner: it becomes the suggestion too, so the module
            # is not shown as the learner's own choice.
            update["choice"] = Choice.STUDY
            update["suggested"] = Choice.STUDY
            update["adjustment"] = (
                f"Changed to study: the checkpoint showed gaps ({score}/{total}). "
                "Study the module, then take the checkpoint again."
            )
        if not passed:
            # A topic the learner skimmed and then got wrong is one to study in full.
            relearn = [
                marked
                for marked in item.skim
                if any(same_topic(marked.topic, missed) for missed in missed_topics or [])
            ]
            if relearn:
                update["skim"] = [marked for marked in item.skim if marked not in relearn]
                topics = ", ".join(marked.topic for marked in relearn)
                update["adjustment"] = (
                    update.get("adjustment", "") + f" Changed to study in full: {topics}, which you skimmed"
                    " and got wrong in the checkpoint."
                ).strip()
        elif passed and item.adjustment and item.adjustment.startswith("Changed to study"):
            # The advice to study and try again is done with; say how it ended.
            update["adjustment"] = (
                "Changed to study after the checkpoint showed gaps; "
                f"passed on attempt {item.attempts + 1} ({score}/{total})."
            )
        # Suggestions from an earlier checkpoint go once this one is taken: the new result supersedes them.
        proposals = [] if not passed else [p for p in self.proposals if p.module_id != module_id]
        return self._replace(item.model_copy(update=update), proposals=proposals)

    def with_problem_solved(self, module_id: str) -> "LearningPath":
        """The learner's code passed the module's coding problem, after its questions."""
        item = self._check_open(module_id)
        if item.progress is not Progress.PRACTICE:
            raise PathStateError(f"Pass the questions of '{module_id}' first")
        return self._replace(item.model_copy(update={"progress": Progress.PASSED}))

    def with_new_goal(
        self, goal: str, items: list[PathItem], title: str | None = None
    ) -> "LearningPath":
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
                "title": title,
                "proposals": [],
                "confirmed_at": None,
            }
        )

    def marked_done(self, module_id: str) -> "LearningPath":
        """The learner finished a module that has no checkpoint."""
        item = self._check_open(module_id)
        if item.module.is_project:
            raise PathStateError("Submit the project for review instead")
        return self._replace(item.model_copy(update={"progress": Progress.DONE}))

    def with_submission(self, module_id: str) -> "LearningPath":
        """The learner submitted the module's project; it waits for a reviewer."""
        item = self._check_open(module_id)
        if not item.module.is_project:
            raise PathStateError(f"'{module_id}' has no project to submit")
        if item.progress is Progress.DONE:
            raise PathStateError("This project has already been accepted")
        return self._replace(
            item.model_copy(update={"progress": Progress.SUBMITTED, "adjustment": None})
        )

    def with_review(
        self, module_id: str, accepted: bool, comment: str
    ) -> "LearningPath":
        """A reviewer accepted the project, which finishes the module, or sent it back with a comment. A person
        may decide otherwise than the model did, so a decision can follow an earlier one.
        """
        item = self.item(module_id)
        if item.progress not in (Progress.SUBMITTED, Progress.RETURNED, Progress.DONE):
            raise PathStateError("This project has not been submitted")
        progress = Progress.DONE if accepted else Progress.RETURNED
        note = f"Reviewer: {comment}" if comment else None
        return self._replace(
            item.model_copy(update={"progress": progress, "adjustment": note})
        )

    def with_proposals(self, proposals: list["Proposal"]) -> "LearningPath":
        """Keeps only proposals for modules the learner has not started that go the proposal's way: lighter
        after an easy pass, heavier after a failure, and never bringing back a module the path skips. A lighter one never touches a locked module; a heavier one
        may, since it is locked by the failure that brought the proposal. A topic proposal is kept only for a
        module to study, and not when the same module's choice is proposed to change."""
        kept: list[Proposal] = []
        moved = {p.module_id for p in proposals if p.topic is None}
        for proposal in proposals:
            try:
                item = self.item(proposal.module_id)
            except KeyError:
                continue
            if item.progress is not Progress.NOT_STARTED:
                continue
            if not proposal.after_failure and proposal.module_id in self.locked_module_ids:
                continue
            if proposal.topic is None:
                assert proposal.choice is not None  # nosec B101: checked by the model
                old, new = WEIGHT[item.choice], WEIGHT[proposal.choice]
                if proposal.choice is Choice.PROVE and not item.module.can_be_proved:
                    continue
                # A module the path skips stays skipped after a failure: it was left out for the learner's
                # goal, and a gap elsewhere does not change the goal. Only what the path keeps gets heavier.
                if proposal.after_failure and item.choice is Choice.SKIP:
                    continue
            else:
                assert proposal.topic_choice is not None  # nosec B101: checked by the model
                titles = [t.title for t in item.module.topics]
                if (
                    proposal.module_id in moved
                    or item.choice is not Choice.STUDY
                    or item.module.is_project
                    or proposal.topic not in titles
                ):
                    continue
                old = TOPIC_WEIGHT[item.topic_choice(proposal.topic)]
                new = TOPIC_WEIGHT[proposal.topic_choice]
            if (new > old) if proposal.after_failure else (new < old):
                kept.append(proposal)
        return self.model_copy(update={"proposals": kept})

    def with_suggestions(self, key: str, proposals: list["Proposal"]) -> "LearningPath":
        """The suggestions worked out after the checkpoint `key` names; ignored if the path has moved on."""
        if self.suggestions_pending != key:
            return self
        return self.with_proposals(proposals).model_copy(update={"suggestions_pending": None})

    def _proposal(self, module_id: str, topic: str | None) -> "Proposal":
        proposal = next((p for p in self.proposals if p.concerns(module_id, topic)), None)
        if proposal is None:
            raise PathStateError(f"No suggestion for '{module_id}'" + (f", topic '{topic}'" if topic else ""))
        return proposal

    def accept(self, module_id: str, topic: str | None = None) -> "LearningPath":
        """The learner takes the suggestion; their acceptance is their approval, so the path stays
        confirmed."""
        proposal = self._proposal(module_id, topic)
        rest = [p for p in self.proposals if p is not proposal]
        note = f"You accepted a suggestion after a checkpoint: {proposal.reason}"
        if proposal.topic is not None:
            assert proposal.topic_choice is not None  # nosec B101: checked by the model
            changed = self.with_topic(module_id, proposal.topic, proposal.topic_choice)
            item = changed.item(module_id).model_copy(update={"adjustment": note})
            return changed._replace(item, proposals=rest)
        assert proposal.choice is not None  # nosec B101: checked by the model
        item = self.item(module_id).model_copy(update={"choice": proposal.choice, "adjustment": note})
        return self._replace(item, proposals=rest)

    def decline(self, module_id: str, topic: str | None = None) -> "LearningPath":
        proposal = self._proposal(module_id, topic)
        return self.model_copy(update={"proposals": [p for p in self.proposals if p is not proposal]})


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
