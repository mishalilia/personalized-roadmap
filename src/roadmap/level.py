"""Level inference: a suggestion with the evidence behind it, which the learner can correct."""

from enum import StrEnum

from pydantic import BaseModel, Field

from . import prompts
from .curriculum import Level
from .llm import LLMClient
from .onboarding import Answers, Question, format_answers


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LevelAssessment(BaseModel):
    level: Level
    evidence: list[str] = Field(
        min_length=1,
        description="Points from the learner's answers that support the level, one per item.",
    )
    confidence: Confidence


class LevelAssessor:
    def __init__(self, llm: LLMClient, questions: list[Question]) -> None:
        self._llm = llm
        self._questions = questions

    def assess(self, answers: Answers) -> LevelAssessment:
        return self._llm.ask(
            prompts.load("level"),
            format_answers(self._questions, answers),
            LevelAssessment,
        )
