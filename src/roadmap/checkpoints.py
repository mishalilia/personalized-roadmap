"""Checkpoints: questions that check a learner understood a module, before the path moves on.

Questions are generated once per module and curriculum version, reviewed by a person and kept in
`checkpoints/`, rather than generated for each learner: a checkpoint then costs no model call, every learner
of a module gets the same reviewed questions, and grading is ordinary code.

The source has little text of its own (Q-004), so the model writes questions about what the module says it
teaches: its topics and stated outcomes, its checklist and the authors' notes on each resource. Nothing is
copied from the linked third-party material.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, StringConstraints, model_validator

from . import prompts
from .curriculum import Curriculum, Module
from .llm import LLMClient, UnusableAnswer

QUESTIONS_PER_ATTEMPT = 5
PASS_MARK = 4  # correct answers out of QUESTIONS_PER_ATTEMPT
GENERATED_QUESTIONS = 10  # two attempts' worth, so a retake shows other questions

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Status(StrEnum):
    DRAFT = "draft"  # generated, not yet checked by a person
    REVIEWED = "reviewed"  # a person who knows the topic checked every question


class CheckpointQuestion(BaseModel):
    id: str = Field(description="Short and unique within the checkpoint, such as q1.")
    topic: Text = Field(description="The module topic the question checks.")
    text: Text = Field(
        description="The question. It asks the learner to apply an idea."
    )
    options: list[Text] = Field(
        min_length=4, max_length=4, description="Four answers, exactly one correct."
    )
    answer: int = Field(ge=0, le=3, description="Index of the correct option.")
    explanation: Text = Field(
        description="Why the correct option is right, in one or two sentences."
    )

    @model_validator(mode="after")
    def _distinct_options(self) -> CheckpointQuestion:
        if len({option.casefold() for option in self.options}) != len(self.options):
            raise ValueError(f"Question {self.id} repeats an option")
        return self


class Checkpoint(BaseModel):
    module_id: str
    curriculum_version: str
    status: Status = Status.DRAFT
    generated_by: str  # which model, or who, wrote the questions
    reviewed_by: str | None = None
    questions: list[CheckpointQuestion]

    @model_validator(mode="after")
    def _enough_distinct_questions(self) -> Checkpoint:
        if len(self.questions) < QUESTIONS_PER_ATTEMPT:
            raise ValueError(
                f"A checkpoint needs at least {QUESTIONS_PER_ATTEMPT} questions"
            )
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("Question ids repeat")
        return self

    def questions_for_attempt(self, attempt: int) -> list[CheckpointQuestion]:
        """Five questions per attempt; the next attempt takes the next five, round the list."""
        start = (attempt * QUESTIONS_PER_ATTEMPT) % len(self.questions)
        rotated = self.questions[start:] + self.questions[:start]
        return rotated[:QUESTIONS_PER_ATTEMPT]

    def grade(self, attempt: int, answers: dict[str, int]) -> Grade:
        asked = self.questions_for_attempt(attempt)
        if set(answers) != {question.id for question in asked}:
            raise ValueError("Answer exactly the questions of this attempt")
        feedback = [
            QuestionFeedback(
                id=question.id,
                correct=answers[question.id] == question.answer,
                answer=question.answer,
                explanation=question.explanation,
            )
            for question in asked
        ]
        score = sum(item.correct for item in feedback)
        return Grade(
            attempt=attempt,
            score=score,
            total=len(asked),
            passed=score >= PASS_MARK,
            # Every answer right at the first try: the learner may not need the modules that follow
            # in full either.
            effortless=attempt == 0 and score == len(asked),
            feedback=feedback,
        )


class QuestionFeedback(BaseModel):
    id: str
    correct: bool
    answer: int
    explanation: str


class Grade(BaseModel):
    attempt: int
    score: int
    total: int
    passed: bool
    effortless: bool
    feedback: list[QuestionFeedback]


class CheckpointStore:
    """Checkpoints as YAML files under one directory, one per module: `<module id>.yaml`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, module_id: str) -> Path:
        return self._directory / f"{module_id}.yaml"

    def load(self, module_id: str) -> Checkpoint | None:
        file = self.path_for(module_id)
        if not file.is_file():
            return None
        return Checkpoint.model_validate(yaml.safe_load(file.read_text("utf-8")))

    def save(self, checkpoint: Checkpoint) -> Path:
        file = self.path_for(checkpoint.module_id)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(
            yaml.safe_dump(
                checkpoint.model_dump(mode="json"),
                sort_keys=False,
                allow_unicode=True,
                width=110,
            ),
            encoding="utf-8",
        )
        return file

    def all_for(self, curriculum: Curriculum) -> dict[str, Checkpoint]:
        """The checkpoints of the curriculum's modules, for the curriculum's version only."""
        checkpoints = {}
        for module in curriculum.modules:
            checkpoint = self.load(module.id)
            if (
                checkpoint is not None
                and checkpoint.curriculum_version == curriculum.version
            ):
                checkpoints[module.id] = checkpoint
        return checkpoints


class GeneratedQuestions(BaseModel):
    questions: list[CheckpointQuestion] = Field(
        description=f"Exactly {GENERATED_QUESTIONS} questions."
    )


class CheckpointGenerator:
    def __init__(self, llm: LLMClient, model_name: str) -> None:
        self._llm = llm
        self._model_name = model_name

    def generate(self, module: Module, curriculum_version: str) -> Checkpoint:
        response = self._llm.ask(
            prompts.load("checkpoint"),
            module_brief(module),
            GeneratedQuestions,
            check=_check_generated,
        )
        questions = [
            question.model_copy(update={"id": f"q{number}"})
            for number, question in enumerate(response.questions, start=1)
        ]
        return Checkpoint(
            module_id=module.id,
            curriculum_version=curriculum_version,
            generated_by=self._model_name,
            questions=questions,
        )


def _check_generated(response: GeneratedQuestions) -> None:
    if len(response.questions) != GENERATED_QUESTIONS:
        raise UnusableAnswer(
            f"{len(response.questions)} questions instead of {GENERATED_QUESTIONS}"
        )
    texts = {question.text.casefold() for question in response.questions}
    if len(texts) != len(response.questions):
        raise UnusableAnswer("Questions repeat")


def module_brief(module: Module) -> str:
    """What the module says it teaches, for the model to write questions about."""
    outline = {
        "module": module.full_title,
        "about": module.description,
        "topics": [
            {"title": topic.title, "outcomes": topic.outcomes}
            for topic in module.topics
        ],
        "resources": [
            {
                "title": resource.title,
                "difficulty": resource.difficulty.value,
                "authors_note": resource.note,
            }
            for resource in module.resources
        ],
        # Link text only: the model writes about the subject, not about linked pages.
        "checklist": [_LINK.sub(r"\1", item) for item in module.checklist],
    }
    return yaml.safe_dump(outline, sort_keys=False, allow_unicode=True, width=120)
