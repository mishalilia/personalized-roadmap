"""A model reviews a submitted project against its capstone's rubric; code decides whether it passes.

The model reads the project's files and says, for each rubric criterion, whether it is met, with evidence: a
file and a quote from it. Code then checks every quote against the files. A criterion counts as met only with
evidence that is really there, so a model that is mistaken, or a project that tries to talk the model into a
pass, cannot pass a criterion without the project showing it. The project passes when every criterion of the
rubric's passing level counts as met.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from . import prompts
from .curriculum import Module
from .llm import LLMClient, LLMUnavailable, UnusableAnswer
from .project_files import ProjectFiles

logger = logging.getLogger(__name__)

Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class Verdict(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    UNVERIFIED = "unverified"


class Evidence(BaseModel):
    file: Text = Field(description="A path from the list of files, exactly as listed.")
    quote: Text = Field(
        default="",
        description="A short quote copied exactly from the file; empty when the file's existence is the evidence.",
    )


class About(StrEnum):
    BEHAVIOUR = (
        "behaviour"  # how the project works when run: accuracy, timing, what it handles
    )
    ARTEFACT = "artefact"  # what the project contains: code structure, documentation, tests, a UI


class Criterion(BaseModel):
    name: Text = Field(description="The criterion as the rubric names it.")
    about: About = Field(
        description="behaviour: how the project works when run; artefact: what it contains."
    )
    verdict: Verdict
    evidence: list[Evidence] = Field(
        default=[], description="For a met criterion: where the files show it."
    )
    comment: Text = Field(description="One sentence: why this verdict.")


class Level(BaseModel):
    name: Text = Field(
        description="The rubric level, such as Sufficient, Good or Excellent."
    )
    passing: bool = Field(
        description="True for the level a project must reach to pass; exactly one level."
    )
    criteria: list[Criterion] = Field(min_length=1)


class ModelReview(BaseModel):
    levels: list[Level] = Field(
        min_length=1, description="Every level of the rubric, lowest first."
    )
    feedback: Text = Field(
        description="To the learner: what is good, and what to add or change to pass."
    )


class CheckedCriterion(Criterion):
    # The model said met, but its evidence is not in the files: the criterion does not count.
    evidence_missing: bool = False
    # A criterion about behaviour, met only on the author's word: no program output shows it.
    output_missing: bool = False
    votes: str | None = None  # how many of the reviews counted it, such as "2/3"

    @property
    def counts(self) -> bool:
        return (
            self.verdict is Verdict.MET
            and not self.evidence_missing
            and not self.output_missing
        )


class CheckedLevel(BaseModel):
    name: str
    passing: bool
    criteria: list[CheckedCriterion]

    @property
    def reached(self) -> bool:
        return all(criterion.counts for criterion in self.criteria)


class ProjectReview(BaseModel):
    """What the learner and the reviewers see."""

    passed: bool
    level: str | None  # the highest level whose every criterion counts, if any
    levels: list[CheckedLevel]
    feedback: str
    files_read: int
    files_listed: int
    source: str
    model: str | None = None
    runs: int = 1  # independent reviews combined
    outputs: list[str] = []  # the project's texts that its code produced


def _check(review: ModelReview) -> None:
    if sum(level.passing for level in review.levels) != 1:
        raise UnusableAnswer("Exactly one rubric level must be the passing one")


class ProjectReviewer:
    """`runs` independent reviews of the same project, at the same time; a criterion counts when most of them
    count it. One model answer can judge a borderline criterion either way; a learner should not pass or fail
    by that chance."""

    def __init__(
        self, llm: LLMClient, model_name: str | None = None, runs: int = 3
    ) -> None:
        self._llm = llm
        self._model_name = model_name
        self._runs = runs

    def review(self, module: Module, files: ProjectFiles) -> ProjectReview:
        """Raises LLMUnavailable when no model gives a usable answer."""
        prompt = (
            f"Capstone: {module.full_title}\n\n"
            f"<<<BRIEF>>>\n{module.project_brief or module.description}\n<<<END BRIEF>>>\n\n"
            f"The learner's project ({files.source}):\n{files.prompt()}"
        )

        def one() -> ProjectReview:
            answer = self._llm.ask(
                prompts.load("project_review"), prompt, ModelReview, check=_check
            )
            return judge(answer, files, self._model_name)

        if self._runs == 1:
            return one()
        reviews = []
        with ThreadPoolExecutor(max_workers=self._runs) as pool:
            for future in [pool.submit(one) for _ in range(self._runs)]:
                try:
                    reviews.append(future.result())
                except LLMUnavailable as error:
                    logger.warning("One review of the project failed: %s", error)
        if not reviews:
            raise LLMUnavailable("No review of the project succeeded")
        return combine(reviews)


def combine(reviews: list[ProjectReview]) -> ProjectReview:
    """One review from several: each criterion counts when more than half of the reviews count it, and shows
    the comment and evidence of a review that agrees. The feedback is that of a review with the same outcome.
    """

    def key(level: str, criterion: str) -> tuple[str, str]:
        return " ".join(level.casefold().split()), " ".join(
            criterion.casefold().split()
        )

    found = [
        {key(level.name, c.name): c for level in review.levels for c in level.criteria}
        for review in reviews
    ]
    levels = []
    for level in reviews[0].levels:
        criteria = []
        for criterion in level.criteria:
            versions = [
                each[key(level.name, criterion.name)]
                for each in found
                if key(level.name, criterion.name) in each
            ]
            votes = sum(version.counts for version in versions)
            counts = votes * 2 > len(reviews)
            agreeing = next(
                (version for version in versions if version.counts == counts),
                criterion,
            )
            criteria.append(
                agreeing.model_copy(update={"votes": f"{votes}/{len(reviews)}"})
            )
        levels.append(level.model_copy(update={"criteria": criteria}))
    passing = next(level for level in levels if level.passing)
    reached = None
    for level in levels:
        if not level.reached:
            break
        reached = level.name
    passed = passing.reached
    feedback = next(
        (review.feedback for review in reviews if review.passed == passed),
        reviews[0].feedback,
    )
    return reviews[0].model_copy(
        update={
            "passed": passed,
            "level": reached,
            "levels": levels,
            "feedback": feedback,
            "runs": len(reviews),
        }
    )


def judge(
    answer: ModelReview, files: ProjectFiles, model: str | None = None
) -> ProjectReview:
    """Checks the model's evidence against the files, and decides from what holds up."""
    levels = []
    for level in answer.levels:
        criteria = []
        for criterion in level.criteria:
            missing = criterion.verdict is Verdict.MET and not (
                criterion.evidence
                and all(
                    files.contains(item.file, item.quote) for item in criterion.evidence
                )
            )
            # How the project behaves counts only with what its code produced, not with what its author
            # wrote about it.
            output_missing = (
                criterion.verdict is Verdict.MET
                and criterion.about is About.BEHAVIOUR
                and not any(
                    item.file in files.outputs and files.contains(item.file, item.quote)
                    for item in criterion.evidence
                )
            )
            if missing:
                logger.info("Evidence for '%s' is not in the project", criterion.name)
            criteria.append(
                CheckedCriterion(
                    **criterion.model_dump(),
                    evidence_missing=missing,
                    output_missing=output_missing,
                )
            )
        levels.append(
            CheckedLevel(name=level.name, passing=level.passing, criteria=criteria)
        )
    passing = next(level for level in levels if level.passing)
    reached = None
    for level in levels:
        if not level.reached:
            break
        reached = level.name
    return ProjectReview(
        passed=passing.reached,
        level=reached,
        levels=levels,
        feedback=answer.feedback,
        files_read=len(files.texts),
        files_listed=len(files.tree),
        source=files.source,
        model=model,
        outputs=sorted(files.outputs),
    )
