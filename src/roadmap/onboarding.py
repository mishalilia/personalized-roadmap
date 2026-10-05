"""Onboarding: the open questions a learner answers, and invented example learners for demos and tests."""

from pathlib import Path

from pydantic import BaseModel

from .config import read_yaml

Answers = dict[str, str]  # question id -> the learner's answer


class Question(BaseModel):
    id: str
    text: str
    placeholder: str = ""


class LearnerProfile(BaseModel):
    """An invented learner, not a real person."""

    id: str
    title: str
    answers: Answers


def load_questions(path: Path) -> list[Question]:
    return [Question.model_validate(item) for item in read_yaml(path)["questions"]]


def load_profiles(path: Path) -> list[LearnerProfile]:
    return [LearnerProfile.model_validate(item) for item in read_yaml(path)["profiles"]]


def format_answers(questions: list[Question], answers: Answers) -> str:
    """Questions and answers as plain text for a prompt."""
    return "\n\n".join(
        f"Q: {question.text}\nA: {answers.get(question.id, '').strip() or '(no answer)'}"
        for question in questions
    )
