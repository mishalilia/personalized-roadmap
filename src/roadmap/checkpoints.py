"""Checkpoints: questions that check a learner understood a module, before the path moves on.

Questions are generated once per module and curriculum version, reviewed by a person and kept in
`checkpoints/`, rather than generated for each learner: every learner of a module gets the same reviewed
questions, and multiple-choice grading is ordinary code.

An attempt has four multiple-choice questions and, where the checkpoint has them, one open question: the
learner explains something in their own words, and a model marks which points of the question's rubric the
answer makes and what it states wrongly (OpenAnswerGrader). Whether that is enough is decided here, in code:
enough points, and nothing wrong. When no
model can mark it, the open question is left out of the attempt rather than holding the learner up.

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
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, StringConstraints, model_validator

from . import prompts
from .curriculum import Curriculum, Module
from .llm import LLMClient, LLMUnavailable, UnusableAnswer

QUESTIONS_PER_ATTEMPT = 5
PASS_MARK = 4  # correct answers out of QUESTIONS_PER_ATTEMPT
# Three attempts' worth, so a retake shows other questions. Correct answers are shown only after a pass, and
# the options are shuffled for each attempt, so a learner cannot pass by remembering earlier attempts.
GENERATED_QUESTIONS = 15
# Each topic's own pool: a learner who skips the module's other topics still gets other questions at a retake.
QUESTIONS_PER_TOPIC = 8
OPEN_PER_ATTEMPT = (
    1  # of the QUESTIONS_PER_ATTEMPT, when the checkpoint has open questions
)
OPEN_PER_TOPIC = (
    2  # open questions generated for each topic, so a retake asks another one
)
MAX_OPEN_ANSWER = 2000  # characters

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# A question that points at code ("this code prints...") must carry it: code of several lines, or a line of code
# in backticks, such as `x = f(2)`.
_POINTS_AT_CODE = re.compile(
    r"\b(this|the following) (code|snippet|script|program)\b", re.IGNORECASE
)
_INLINE_CODE = re.compile(r"`[^`]*[=(:][^`]*`")


def missing_code(text: str) -> bool:
    """True for a question that speaks of "this code" but shows none, so it cannot be answered."""
    return (
        bool(_POINTS_AT_CODE.search(text))
        and "\n" not in text
        and not _INLINE_CODE.search(text)
    )


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


class OpenQuestion(BaseModel):
    """A question the learner answers in their own words, marked against its rubric."""

    id: str = Field(description="Short and unique within the checkpoint, such as o1.")
    topic: Text = Field(description="The module topic the question checks.")
    text: Text = Field(
        description="The question. The learner explains how or why in two to five sentences."
    )
    rubric: list[Text] = Field(
        min_length=2,
        max_length=4,
        description="The points a full answer makes: each one idea that can be found in a learner's answer or not.",
    )
    required: int = Field(
        ge=1, description="How many of the rubric's points make the answer right."
    )
    model_answer: Text = Field(
        description="A full answer in three to five sentences, shown to the learner after a pass."
    )

    @model_validator(mode="after")
    def _attainable(self) -> OpenQuestion:
        if self.required > len(self.rubric):
            raise ValueError(
                f"Question {self.id} requires more points than its rubric has"
            )
        return self


class OpenVerdict(BaseModel):
    """What a model found in a learner's answer to an open question."""

    points_met: list[int] = Field(
        description="The numbers (from 1) of the rubric points the answer makes; empty when it makes none."
    )
    errors: list[Text] = Field(
        default=[],
        description="What the answer states that is wrong, one item each; not what it leaves out. Empty when "
        "it states nothing wrong.",
    )
    feedback: Text = Field(
        description="To the learner, one or two sentences: what the answer gets right and what it leaves out, "
        "without writing the full answer for them."
    )


Judge = Callable[
    [OpenQuestion, str], "OpenVerdict | None"
]  # None: no model could mark the answer


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
    # The module's topic the problem practises, as one of its topic titles; the page links to it.
    topic: str | None = None
    # Plausible wrong solutions, each missing one requirement: the tests must reject every one of them, so
    # a learner cannot pass with half a solution. Never shown to learners.
    wrong_solutions: list[Text] = Field(
        default=[],
        description="Two or three plausible wrong solutions a learner might write, each missing one "
        "requirement of the prompt; the tests must fail every one.",
    )

    @model_validator(mode="after")
    def _python(self) -> CodingProblem:
        for name in ("starter_code", "tests", "solution"):
            try:
                ast.parse(getattr(self, name))
            except SyntaxError as error:
                raise ValueError(
                    f"The problem's {name} is not valid Python: {error}"
                ) from error
        for number, wrong in enumerate(self.wrong_solutions, start=1):
            try:
                ast.parse(wrong)
            except SyntaxError as error:
                raise ValueError(
                    f"Wrong solution {number} is not valid Python: {error}"
                ) from error
        return self


class Checkpoint(BaseModel):
    module_id: str
    curriculum_version: str
    status: Status = Status.DRAFT
    generated_by: str  # which model, or who, wrote the questions
    reviewed_by: str | None = None
    questions: list[CheckpointQuestion]
    # Explained in the learner's own words; one per attempt, marked by a model against its rubric.
    open_questions: list[OpenQuestion] = []
    # For modules that teach programming: solved after the questions, before the module counts as passed.
    problem: CodingProblem | None = None
    # More problems, each for another topic, so a learner who skips the first problem's topic gets one on a
    # topic they study.
    problems: list[CodingProblem] = []

    @model_validator(mode="after")
    def _enough_distinct_questions(self) -> Checkpoint:
        if len(self.questions) < QUESTIONS_PER_ATTEMPT:
            raise ValueError(
                f"A checkpoint needs at least {QUESTIONS_PER_ATTEMPT} questions"
            )
        ids = [question.id for question in (*self.questions, *self.open_questions)]
        if len(set(ids)) != len(ids):
            raise ValueError("Question ids repeat")
        return self

    def pool(self, skipped: frozenset[str] = frozenset()) -> list[CheckpointQuestion]:
        """The questions of the topics the learner does not skip, taken topic by topic in turn, so that an
        attempt spans the topics. With too few left for an attempt, the whole checkpoint.
        """
        kept = [
            question for question in self.questions if question.topic not in skipped
        ]
        if len(kept) < QUESTIONS_PER_ATTEMPT:
            kept = list(self.questions)
        by_topic: dict[str, list[CheckpointQuestion]] = {}
        for question in kept:
            by_topic.setdefault(question.topic, []).append(question)
        longest = max(len(questions) for questions in by_topic.values())
        return [
            questions[i]
            for i in range(longest)
            for questions in by_topic.values()
            if i < len(questions)
        ]

    @property
    def choice_count(self) -> int:
        """Multiple-choice questions per attempt: five, or four beside an open question."""
        return QUESTIONS_PER_ATTEMPT - (OPEN_PER_ATTEMPT if self.open_questions else 0)

    def questions_for_attempt(
        self, attempt: int, skipped: frozenset[str] = frozenset()
    ) -> list[CheckpointQuestion]:
        """The attempt's multiple-choice questions; the next attempt takes the next ones, round the pool."""
        pool = self.pool(skipped)
        count = self.choice_count
        start = (attempt * count) % len(pool)
        rotated = pool[start:] + pool[:start]
        return rotated[:count]

    def open_for_attempt(
        self, attempt: int, skipped: frozenset[str] = frozenset()
    ) -> OpenQuestion | None:
        """The attempt's open question, from the topics the learner does not skip, topic by topic in turn."""
        kept = [q for q in self.open_questions if q.topic not in skipped] or list(
            self.open_questions
        )
        if not kept:
            return None
        by_topic: dict[str, list[OpenQuestion]] = {}
        for question in kept:
            by_topic.setdefault(question.topic, []).append(question)
        longest = max(len(questions) for questions in by_topic.values())
        order = [
            qs[i] for i in range(longest) for qs in by_topic.values() if i < len(qs)
        ]
        return order[attempt % len(order)]

    def problem_for(
        self,
        skipped: frozenset[str] = frozenset(),
        skimmed: frozenset[str] = frozenset(),
    ) -> CodingProblem | None:
        """The coding problem for a learner: on a topic they study in full if there is one, else on one they
        skim; none when every problem is on a topic they skip."""
        candidates = [
            problem
            for problem in (self.problem, *self.problems)
            if problem is not None and (problem.topic or "") not in skipped
        ]
        return next(
            (problem for problem in candidates if (problem.topic or "") not in skimmed),
            candidates[0] if candidates else None,
        )

    def topic_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for question in self.questions:
            counts[question.topic] = counts.get(question.topic, 0) + 1
        return counts

    def order_of(self, attempt: int, question_id: str) -> list[int]:
        """The order the options of a question are shown in at this attempt: a fixed shuffle, so the
        learner sees the same order when they reload, and another one at the next attempt.
        """
        order = list(range(4))
        seed = f"{self.module_id}:{attempt}:{question_id}"
        random.Random(seed).shuffle(order)  # nosec B311: a display order, not a secret
        return order

    def asked(
        self, attempt: int, skipped: frozenset[str] = frozenset()
    ) -> list[AskedQuestion]:
        """The attempt's questions as the learner sees them: shuffled options, no answer; the open question
        last, with neither its rubric nor its model answer."""
        asked = [
            AskedQuestion(
                id=question.id,
                topic=question.topic,
                text=question.text,
                options=[
                    question.options[i] for i in self.order_of(attempt, question.id)
                ],
            )
            for question in self.questions_for_attempt(attempt, skipped)
        ]
        if (open_question := self.open_for_attempt(attempt, skipped)) is not None:
            asked.append(
                AskedQuestion(
                    id=open_question.id,
                    topic=open_question.topic,
                    text=open_question.text,
                    options=[],
                    kind="open",
                )
            )
        return asked

    def grade(
        self,
        attempt: int,
        answers: dict[str, int],
        skipped: frozenset[str] = frozenset(),
        open_answers: dict[str, str] | None = None,
        judge: Judge | None = None,
    ) -> Grade:
        """`answers` holds the position of each chosen option as shown; `open_answers` the text of the open
        question, which `judge` marks against its rubric. A failed attempt says which answers were wrong and
        what to review, but not the right answers. Without a judge, or when it cannot mark the answer, the open
        question is left out and one fewer right answer passes."""
        asked = self.questions_for_attempt(attempt, skipped)
        if set(answers) != {question.id for question in asked}:
            raise ValueError("Answer exactly the questions of this attempt")
        if any(not 0 <= shown <= 3 for shown in answers.values()):
            raise ValueError("Each answer is the position of one of four options")
        open_question = self.open_for_attempt(attempt, skipped)
        open_answers = open_answers or {}
        if set(open_answers) - ({open_question.id} if open_question else set()):
            raise ValueError("Answer exactly the questions of this attempt")
        correct = {
            question.id: self.order_of(attempt, question.id)[answers[question.id]]
            == question.answer
            for question in asked
        }
        open_feedback: list[QuestionFeedback] = []
        ungraded = 0
        if open_question is not None:
            text = open_answers.get(open_question.id, "").strip()[:MAX_OPEN_ANSWER]
            verdict = judge(open_question, text) if text and judge else None
            if text and verdict is None:
                ungraded = 1  # no model could mark it: left out of this attempt
            met = (
                sorted(
                    {
                        n
                        for n in verdict.points_met
                        if 1 <= n <= len(open_question.rubric)
                    }
                )
                if verdict
                else []
            )
            # Enough of the rubric, and nothing stated wrong: a confident wrong key idea does not pass on the rest.
            right = (
                verdict is not None
                and len(met) >= open_question.required
                and not verdict.errors
            )
            if not ungraded:
                correct[open_question.id] = right
            open_feedback.append(
                QuestionFeedback(
                    id=open_question.id,
                    topic=open_question.topic,
                    kind="open",
                    correct=right,
                    graded=not ungraded,
                    comment=(
                        verdict.feedback
                        if verdict
                        else (
                            "No answer."
                            if not text
                            else "Your answer could not be marked right now, so this attempt is graded without it."
                        )
                    ),
                )
            )
        score = sum(correct.values())
        passed = score >= PASS_MARK - ungraded
        for (
            item
        ) in (
            open_feedback
        ):  # the model answer, like the explanations, only after a pass
            if passed and open_question is not None:
                item.explanation = open_question.model_answer
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
        ] + open_feedback
        review = [item.topic for item in feedback if item.graded and not item.correct]
        return Grade(
            attempt=attempt,
            score=score,
            total=len(correct),
            passed=passed,
            # Every answer right at the first try: the learner may not need the modules that follow
            # in full either.
            effortless=attempt == 0 and score == len(correct) and not ungraded,
            review_topics=list(dict.fromkeys(review)),
            feedback=feedback,
            problem_pending=passed and self.problem_for(skipped) is not None,
        )


class AskedQuestion(BaseModel):
    """A checkpoint question without its answer: grading happens on the server, not in the browser."""

    id: str
    topic: str
    text: str
    options: list[str]  # none for an open question
    kind: Literal["choice", "open"] = "choice"


class QuestionFeedback(BaseModel):
    id: str
    topic: str
    correct: bool
    kind: Literal["choice", "open"] = "choice"
    graded: bool = (
        True  # False: an open answer no model could mark, left out of the score
    )
    # Shown only after a pass: the position of the right option as the learner saw it, and why (for an open
    # question, a full answer).
    answer: int | None = None
    explanation: str | None = None
    comment: str | None = (
        None  # an open answer: what it gets right and what it leaves out
    )


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
    """Runs the reference solution against the tests in a separate Python, then each wrong solution, which
    the tests must reject. None if all is as it should be, else what is not. For a reviewer checking a
    checkpoint on their own machine: the code comes from the checkpoint file, so run it only on files you
    have read."""
    if missing := [
        name for name in problem.packages if importlib.util.find_spec(name) is None
    ]:
        return f"needs {', '.join(missing)}: pip install {' '.join(missing)}"
    if error := _run_tests(problem.solution, problem.tests, timeout):
        return error
    for number, wrong in enumerate(problem.wrong_solutions, start=1):
        if _run_tests(wrong, problem.tests, timeout) is None:
            return f"wrong solution {number} passes the tests, so they miss a requirement:\n{wrong}"
    return None


def _run_tests(solution: str, tests: str, timeout: float) -> str | None:
    """None if `tests` pass against `solution`, else the end of the error."""
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "check.py"
        script.write_text(f"{solution}\n\n{tests}\n", encoding="utf-8")
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


class GeneratedProblem(BaseModel):
    problem: CodingProblem


class TopicProblem(BaseModel):
    problem: CodingProblem | None = Field(
        default=None,
        description="The problem, or null when the topic cannot be practised by writing a Python function.",
    )


class TopicQuestions(BaseModel):
    questions: list[CheckpointQuestion]


class GeneratedOpenQuestions(BaseModel):
    questions: list[OpenQuestion]


class OpenAnswerGrader:
    """Marks an open answer against its question's rubric with a model. The answer is data: it is shown to the
    model inside tags, and what comes back is only the numbers of the rubric points it makes, which code
    checks; whether that is enough to count is decided by the question's `required`, not by the model.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def __call__(self, question: OpenQuestion, answer: str) -> OpenVerdict | None:
        rubric = "\n".join(
            f"{number}. {point}"
            for number, point in enumerate(question.rubric, start=1)
        )
        # The learner cannot close the tag early and write instructions after it.
        answer = answer[:MAX_OPEN_ANSWER].replace("</answer>", "")
        prompt = (
            f"Topic: {question.topic}\nQuestion: {question.text}\n\nRubric:\n{rubric}\n\n"
            f"<answer>\n{answer}\n</answer>"
        )

        def check(verdict: OpenVerdict) -> None:
            if any(not 1 <= n <= len(question.rubric) for n in verdict.points_met):
                raise UnusableAnswer(
                    f"Rubric points are numbered 1 to {len(question.rubric)}"
                )

        try:
            return self._llm.ask(
                prompts.load("open_grade"), prompt, OpenVerdict, check=check
            )
        except LLMUnavailable:
            return None


PROBLEM_TRIES = (
    3  # a problem whose checks fail is asked for again, this many times in all
)


class CheckpointGenerator:
    def __init__(self, llm: LLMClient, model_name: str) -> None:
        self._llm = llm
        self._model_name = model_name

    def generate_problem(self, module: Module, existing: Checkpoint) -> Checkpoint:
        """The checkpoint with a new coding problem and its questions as they were, for a problem whose
        tests turned out too weak. Raises UnusableAnswer when no try gives a problem that passes the checks.
        """
        last: Exception | None = None
        for _ in range(PROBLEM_TRIES):
            try:
                response = self._llm.ask(
                    prompts.load("problem"),
                    module_brief(module),
                    GeneratedProblem,
                    check=lambda found: _check_problem(found.problem, module),
                )
            except LLMUnavailable as error:
                last = error
                continue
            return existing.model_copy(
                update={
                    "problem": _with_module_topic(response.problem, module),
                    "status": Status.DRAFT,
                    "reviewed_by": None,
                }
            )
        raise UnusableAnswer(f"No usable problem for {module.id}: {last}")

    def topic_questions(
        self, module: Module, topic: str, count: int, existing: Checkpoint
    ) -> list[CheckpointQuestion]:
        """`count` new questions on one topic of the module, unlike the checkpoint's questions, with ids
        that follow theirs. Raises LLMUnavailable without a usable answer."""
        asked = [q.text for q in existing.questions if q.topic == topic]
        prompt = (
            f"{module_brief(module)}\nTopic: {topic}\nWrite {count} new questions on this topic only."
            + (
                "\nIts questions so far, not to repeat:\n"
                + "\n".join(f"- {text}" for text in asked)
                if asked
                else ""
            )
        )
        known = {q.text.casefold() for q in existing.questions}
        titles = [t.title for t in module.topics]

        def check(response: TopicQuestions) -> None:
            if any(_module_topic(q.topic, titles) != topic for q in response.questions):
                raise UnusableAnswer(f"Every question must be on {topic}")
            if any(missing_code(q.text) for q in response.questions):
                raise UnusableAnswer(
                    "A question speaks of code it does not show; put the code in the question"
                )

        response = self._llm.ask(
            prompts.load("topic_questions"), prompt, TopicQuestions, check=check
        )
        # A question that repeats one already there is left out; the caller asks again for what is missing.
        fresh: list[CheckpointQuestion] = []
        for question in response.questions:
            if question.text.casefold() not in known:
                known.add(question.text.casefold())
                fresh.append(question)
        numbers = [
            int(q.id[1:]) for q in existing.questions if re.fullmatch(r"q\d+", q.id)
        ]
        start = max(numbers, default=0) + 1
        return [
            q.model_copy(update={"id": f"q{start + i}", "topic": topic})
            for i, q in enumerate(fresh[:count])
        ]

    def topic_problem(self, module: Module, topic: str) -> CodingProblem | None:
        """A coding problem on one topic, checked like any other; None when the model says the topic cannot
        be practised in code. Raises UnusableAnswer when no try passes the checks."""
        last: Exception | None = None
        for _ in range(PROBLEM_TRIES):
            try:
                response = self._llm.ask(
                    prompts.load("problem") + "\n\n" + prompts.load("topic_problem"),
                    f"{module_brief(module)}\nTopic: {topic}",
                    TopicProblem,
                    check=lambda found: _check_topic_problem(
                        found.problem, module, topic
                    ),
                )
            except LLMUnavailable as error:
                last = error
                continue
            if response.problem is None:
                return None
            return response.problem.model_copy(update={"topic": topic})
        raise UnusableAnswer(f"No usable problem on {topic}: {last}")

    def open_questions(
        self, module: Module, existing: Checkpoint
    ) -> list[OpenQuestion]:
        """OPEN_PER_TOPIC open questions on each of the module's topics (on the module as a whole when it has
        none), with ids o1, o2, ... Raises LLMUnavailable without a usable answer."""
        titles = [topic.title for topic in module.topics] or [module.full_title]
        prompt = (
            f"{module_brief(module)}\nWrite {OPEN_PER_TOPIC} open questions on each of these topics, giving the "
            "topic exactly as written:\n" + "\n".join(f"- {title}" for title in titles)
        )

        def topic_of(question: OpenQuestion) -> str | None:
            return _module_topic(question.topic, titles)

        def check(response: GeneratedOpenQuestions) -> None:
            if unknown := {q.topic for q in response.questions if topic_of(q) is None}:
                raise UnusableAnswer(
                    f"Topics the module does not have: {', '.join(sorted(unknown))}"
                )
            counts = {title: 0 for title in titles}
            for question in response.questions:
                counts[topic_of(question) or ""] += 1
            if short := [title for title, n in counts.items() if n < OPEN_PER_TOPIC]:
                raise UnusableAnswer(
                    f"{OPEN_PER_TOPIC} questions are needed on: {', '.join(short)}"
                )
            if any(missing_code(q.text) for q in response.questions):
                raise UnusableAnswer(
                    "A question speaks of code it does not show; put the code in the question"
                )

        response = self._llm.ask(
            prompts.load("open_questions"), prompt, GeneratedOpenQuestions, check=check
        )
        kept: list[OpenQuestion] = []
        for title in titles:
            on_topic = [q for q in response.questions if topic_of(q) == title][
                :OPEN_PER_TOPIC
            ]
            kept += [q.model_copy(update={"topic": title}) for q in on_topic]
        return [
            q.model_copy(update={"id": f"o{number}"})
            for number, q in enumerate(kept, start=1)
        ]

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
            problem=(
                _with_module_topic(response.problem, module)
                if response.problem
                else None
            ),
        )


def _check_generated(response: GeneratedQuestions, module: Module) -> None:
    if len(response.questions) != GENERATED_QUESTIONS:
        raise UnusableAnswer(
            f"{len(response.questions)} questions instead of {GENERATED_QUESTIONS}"
        )
    texts = {question.text.casefold() for question in response.questions}
    if len(texts) != len(response.questions):
        raise UnusableAnswer("Questions repeat")
    if any(missing_code(question.text) for question in response.questions):
        raise UnusableAnswer(
            "A question speaks of code it does not show; put the code in the question"
        )
    # A failed attempt sends the learner back to these topics, so they must be the module's own.
    titles = [topic.title for topic in module.topics]
    unknown = {
        q.topic for q in response.questions if _module_topic(q.topic, titles) is None
    }
    if titles and unknown:
        raise UnusableAnswer(
            f"Topics the module does not have: {', '.join(sorted(unknown))}"
        )
    if response.problem is not None:
        _check_problem(response.problem, module)


def _check_problem(problem: CodingProblem, module: Module) -> None:
    """A problem is kept only if its reference solution passes, it comes with wrong solutions, and its
    tests reject each of them."""
    if len(problem.wrong_solutions) < 2:
        raise UnusableAnswer(
            "The problem needs at least two wrong solutions to check its tests"
        )
    if error := verify_problem(problem):
        raise UnusableAnswer(f"The problem does not check out: {error}")
    titles = [topic.title for topic in module.topics]
    if titles and problem.topic and _module_topic(problem.topic, titles) is None:
        raise UnusableAnswer(
            f"The problem's topic is not the module's: {problem.topic}"
        )


def _check_topic_problem(
    problem: CodingProblem | None, module: Module, topic: str
) -> None:
    if problem is None:
        return
    _check_problem(problem, module)
    titles = [t.title for t in module.topics]
    if _module_topic(problem.topic or "", titles) != topic:
        raise UnusableAnswer(f"The problem must practise {topic}, not {problem.topic}")


def _with_module_topic(problem: CodingProblem, module: Module) -> CodingProblem:
    titles = [topic.title for topic in module.topics]
    found = _module_topic(problem.topic, titles) if problem.topic else None
    return problem.model_copy(update={"topic": found or problem.topic})


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
