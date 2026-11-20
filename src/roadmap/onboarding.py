"""Onboarding: the questions a learner answers, and invented example learners for demos and tests.

Most questions are answered by choosing (`single`: one option, `multiple`: any number), each with optional
details in the learner's own words; a short code question (`check`) has one right option, which the browser is
never told; the goal is written freely (`text`). What reaches the model is text: the chosen options, whether
the code question was answered right, and the learner's own words (`answer_texts`). Paths keep that text.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import read_yaml

Answers = dict[str, str]  # question id -> the learner's answer as text, as the model and the path see it


class Option(BaseModel):
    id: str
    label: str


class Question(BaseModel):
    id: str
    text: str
    kind: Literal["text", "single", "multiple", "check"] = "text"
    # For a text question its hint; for a choice question the hint of the optional details.
    placeholder: str = ""
    options: list[Option] = []
    code: str = ""  # check: the code the question is about
    correct: str | None = Field(default=None, exclude=True)  # check: the right option; stays on the server

    def option(self, option_id: str) -> Option:
        for option in self.options:
            if option.id == option_id:
                return option
        raise ValueError(f"'{option_id}' is not an option of question '{self.id}'.")


class ChoiceAnswer(BaseModel):
    choices: list[str] = []
    details: str = ""


Answer = str | ChoiceAnswer
RawAnswers = dict[str, Answer]  # as the browser sends them


class LearnerProfile(BaseModel):
    """An invented learner, not a real person."""

    id: str
    title: str
    answers: RawAnswers


def load_questions(path: Path) -> list[Question]:
    return [Question.model_validate(item) for item in read_yaml(path)["questions"]]


def load_profiles(path: Path) -> list[LearnerProfile]:
    return [LearnerProfile.model_validate(item) for item in read_yaml(path)["profiles"]]


def answer_text(question: Question, answer: Answer) -> str:
    """The answer as text for the model; "" for no answer. Raises ValueError for an option the question has not,
    or more than one where one is asked for."""
    if question.kind == "text":
        return (answer if isinstance(answer, str) else answer.details).strip()
    if isinstance(answer, str):  # an answer written before the question had options
        answer = ChoiceAnswer(details=answer)
    if question.kind != "multiple" and len(answer.choices) > 1:
        raise ValueError(f"Choose one option for question '{question.id}'.")
    chosen = [question.option(choice) for choice in dict.fromkeys(answer.choices)]
    parts = []
    if chosen and question.kind == "check":
        right = question.option(question.correct) if question.correct else None
        verdict = (
            "right" if right and chosen[0].id == right.id
            else f"wrong; the right answer is {right.label}" if right
            else "not graded"
        )
        parts.append(f"Picked: {chosen[0].label} ({verdict}).")
    elif chosen:
        parts.append(f"Chose: {'; '.join(option.label for option in chosen)}.")
    if details := answer.details.strip():
        parts.append(f"In their own words: {details}")
    return " ".join(parts)


def answer_texts(questions: list[Question], answers: RawAnswers) -> Answers:
    """Every answer as text, for the model and the path. Raises ValueError for an unknown question or option."""
    by_id = {question.id: question for question in questions}
    if unknown := sorted(answers.keys() - by_id.keys()):
        raise ValueError(f"Unknown questions: {', '.join(unknown)}")
    return {key: answer_text(by_id[key], answer) for key, answer in answers.items()}


def format_answers(questions: list[Question], answers: Answers) -> str:
    """Questions and answers as plain text for a prompt."""

    def asked(question: Question) -> str:
        if question.kind == "check":
            options = "; ".join(option.label for option in question.options)
            return f"{question.text} (a code question)\n```python\n{question.code}\n```\nOptions: {options}"
        return question.text

    return "\n\n".join(
        f"Q: {asked(question)}\nA: {answers.get(question.id, '').strip() or '(no answer)'}"
        for question in questions
    )
