"""Checkpoints: questions that check a learner understood a module, before the path moves on.

Questions are generated once per module and curriculum version, reviewed by a person and kept in
`checkpoints/`, rather than generated for each learner: a checkpoint then costs no model call, every learner
of a module gets the same reviewed questions, and grading is ordinary code.

The source has little text of its own (Q-004), so the model writes questions about what the module says it
teaches: its topics and stated outcomes, its checklist and the authors' notes on each resource. Nothing is
copied from the linked third-party material.
"""

from __future__ import annotations

import ast
import importlib.util
import random
import re
import subprocess  # nosec B404: only runs a reviewer's own checkpoint files, see verify_problem
import sys
import tempfile
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
# Three attempts' worth, so a retake shows other questions. Correct answers are shown only after a pass, and
# the options are shuffled for each attempt, so a learner cannot pass by remembering earlier attempts.
GENERATED_QUESTIONS = 15

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_NUMBERING = re.compile(r"^\s*\d+[.)]\s*")

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


class CodingProblem(BaseModel):
    """A short programming task. The learner's code runs in their browser (Pyodide) against `tests`."""

    title: Text
    prompt: Text = Field(
        description="What to write, in Markdown, with an example call."
    )
    starter_code: Text = Field(
        description="A function signature and a docstring, no solution."
    )
    tests: Text = Field(
        description="Plain Python asserts that call the learner's function; no test framework."
    )
    solution: Text = Field(description="A reference solution that passes the tests.")
    # Pyodide packages the code needs, such as numpy; standard library only when empty.
    packages: list[str] = []

    @model_validator(mode="after")
    def _python(self) -> CodingProblem:
        for name in ("starter_code", "tests", "solution"):
            try:
                ast.parse(getattr(self, name))
            except SyntaxError as error:
                raise ValueError(
                    f"The problem's {name} is not valid Python: {error}"
                ) from error
        return self


class Checkpoint(BaseModel):
    module_id: str
    curriculum_version: str
    status: Status = Status.DRAFT
    generated_by: str  # which model, or who, wrote the questions
    reviewed_by: str | None = None
    questions: list[CheckpointQuestion]
    # For modules that teach programming: solved after the questions, before the module counts as passed.
    problem: CodingProblem | None = None

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

    def order_of(self, attempt: int, question_id: str) -> list[int]:
        """The order the options of a question are shown in at this attempt: a fixed shuffle, so the
        learner sees the same order when they reload, and another one at the next attempt.
        """
        order = list(range(4))
        seed = f"{self.module_id}:{attempt}:{question_id}"
        random.Random(seed).shuffle(order)  # nosec B311: a display order, not a secret
        return order

    def asked(self, attempt: int) -> list[AskedQuestion]:
        """The attempt's questions as the learner sees them: shuffled options, no answer."""
        return [
            AskedQuestion(
                id=question.id,
                topic=question.topic,
                text=question.text,
                options=[
                    question.options[i] for i in self.order_of(attempt, question.id)
                ],
            )
            for question in self.questions_for_attempt(attempt)
        ]

    def grade(self, attempt: int, answers: dict[str, int]) -> Grade:
        """`answers` holds the position of each chosen option as shown. A failed attempt says which
        answers were wrong and what to review, but not the right answers."""
        asked = self.questions_for_attempt(attempt)
        if set(answers) != {question.id for question in asked}:
            raise ValueError("Answer exactly the questions of this attempt")
        if any(not 0 <= shown <= 3 for shown in answers.values()):
            raise ValueError("Each answer is the position of one of four options")
        correct = {
            question.id: self.order_of(attempt, question.id)[answers[question.id]]
            == question.answer
            for question in asked
        }
        score = sum(correct.values())
        passed = score >= PASS_MARK
        feedback = [
            QuestionFeedback(
                id=question.id,
                topic=question.topic,
                correct=correct[question.id],
                answer=(
                    self.order_of(attempt, question.id).index(question.answer)
                    if passed
                    else None
                ),
                explanation=question.explanation if passed else None,
            )
            for question in asked
        ]
        review = [question.topic for question in asked if not correct[question.id]]
        return Grade(
            attempt=attempt,
            score=score,
            total=len(asked),
            passed=passed,
            # Every answer right at the first try: the learner may not need the modules that follow
            # in full either.
            effortless=attempt == 0 and score == len(asked),
            review_topics=list(dict.fromkeys(review)),
            feedback=feedback,
            problem_pending=passed and self.problem is not None,
        )


class AskedQuestion(BaseModel):
    """A checkpoint question without its answer: grading happens on the server, not in the browser."""

    id: str
    topic: str
    text: str
    options: list[str]


class QuestionFeedback(BaseModel):
    id: str
    topic: str
    correct: bool
    # Shown only after a pass: the position of the right option as the learner saw it, and why.
    answer: int | None = None
    explanation: str | None = None


class Grade(BaseModel):
    attempt: int
    score: int
    total: int
    passed: bool
    effortless: bool
    feedback: list[QuestionFeedback]
    review_topics: list[str] = []  # the topics of the wrong answers, in order
    problem_pending: bool = False  # passed, and the coding problem is next


def verify_problem(problem: CodingProblem, timeout: float = 20) -> str | None:
    """Runs the reference solution against the tests in a separate Python; None if they pass, else the
    error. For a reviewer checking a checkpoint on their own machine: the code comes from the checkpoint
    file, so run it only on files you have read."""
    if missing := [
        name for name in problem.packages if importlib.util.find_spec(name) is None
    ]:
        return f"needs {', '.join(missing)}: pip install {' '.join(missing)}"
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "check.py"
        script.write_text(f"{problem.solution}\n\n{problem.tests}\n", encoding="utf-8")
        try:
            result = subprocess.run(  # nosec B603: our own interpreter, isolated mode, no shell
                [sys.executable, "-I", str(script)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=directory,
            )
        except subprocess.TimeoutExpired:
            return f"timed out after {timeout:.0f} s"
    return None if result.returncode == 0 else result.stderr.strip()[-600:]


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
        text = yaml.safe_dump(
            checkpoint.model_dump(mode="json"),
            sort_keys=False,
            allow_unicode=True,
            width=110,
        )
        # The curriculum version is a commit hash, which the secret scanner in pre-commit takes for a key.
        version_line = f"curriculum_version: {checkpoint.curriculum_version}\n"
        text = text.replace(
            version_line,
            version_line.rstrip("\n") + "  # pragma: allowlist secret\n",
            1,
        )
        file.write_text(text, encoding="utf-8")
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
    problem: CodingProblem | None = Field(
        default=None,
        description="One coding problem if the module teaches programming; null otherwise.",
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
            check=lambda response: _check_generated(response, module),
        )
        titles = [topic.title for topic in module.topics]
        questions = [
            question.model_copy(
                update={
                    "id": f"q{number}",
                    "topic": _module_topic(question.topic, titles) or question.topic,
                }
            )
            for number, question in enumerate(response.questions, start=1)
        ]
        return Checkpoint(
            module_id=module.id,
            curriculum_version=curriculum_version,
            generated_by=self._model_name,
            questions=questions,
            problem=response.problem,
        )


def _check_generated(response: GeneratedQuestions, module: Module) -> None:
    if len(response.questions) != GENERATED_QUESTIONS:
        raise UnusableAnswer(
            f"{len(response.questions)} questions instead of {GENERATED_QUESTIONS}"
        )
    texts = {question.text.casefold() for question in response.questions}
    if len(texts) != len(response.questions):
        raise UnusableAnswer("Questions repeat")
    # A failed attempt sends the learner back to these topics, so they must be the module's own.
    titles = [topic.title for topic in module.topics]
    unknown = {
        q.topic for q in response.questions if _module_topic(q.topic, titles) is None
    }
    if titles and unknown:
        raise UnusableAnswer(
            f"Topics the module does not have: {', '.join(sorted(unknown))}"
        )


def _module_topic(topic: str, titles: list[str]) -> str | None:
    """The module's own title for a topic the model named, which may leave out the heading's number, as
    "Collaboration and handover" for "4. Collaboration and handover"."""

    def key(title: str) -> str:
        return _NUMBERING.sub("", title).strip().casefold()

    return next((title for title in titles if key(title) == key(topic)), None)


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
                "difficulty": (
                    resource.difficulty.value if resource.difficulty else None
                ),
                "authors_note": resource.note,
            }
            for resource in module.resources
        ],
        # Link text only: the model writes about the subject, not about linked pages.
        "checklist": [_LINK.sub(r"\1", item) for item in module.checklist],
    }
    return yaml.safe_dump(outline, sort_keys=False, allow_unicode=True, width=120)
