"""Answers a learner's questions about their own path and the module they are reading.

The model sees the learner's path (every module, what the learner does with it and why, and how far they got)
and, when the learner is on a module's page, that module's outline. It cannot change the path: it says how
the learner can. The conversation stays in the learner's browser; each question brings the last few turns.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from . import prompts
from .checkpoints import PASS_MARK, QUESTIONS_PER_ATTEMPT, CodingProblem
from .curriculum import Module
from .llm import LLMClient, UnusableAnswer
from .path import Choice, LearningPath, PathItem, SkimTopic
from .submissions import MAX_ARCHIVE_BYTES, REVIEWS_PER_DAY, Submission

MAX_QUESTION = 1000
MAX_TURN = 2000
MAX_TURNS = 8  # earlier turns sent with a question
MAX_CODE = 6000
MAX_ERROR = 1000
MAX_PAGE_ERROR = 500
CHATS_PER_DAY = (
    40  # a question sends the path and a module's outline, a few thousand tokens
)

Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION)
]
Turn = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_TURN)]


class Speaker(StrEnum):
    LEARNER = "learner"
    ASSISTANT = "assistant"


class ChatTurn(BaseModel):
    speaker: Speaker
    text: Turn


class ChatRequest(BaseModel):
    question: Question
    history: list[ChatTurn] = Field(default=[], max_length=MAX_TURNS)
    # The module whose page the learner is reading, if any, and the heading of the part on their screen.
    module_id: str | None = None
    section: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None
    ) = None
    # The learner's code for the module's coding problem and the error its tests gave, when they ask about it.
    code: Annotated[str, StringConstraints(max_length=MAX_CODE)] | None = None
    error: Annotated[str, StringConstraints(max_length=MAX_ERROR)] | None = None
    # The last error message the site showed the learner, in the last minutes, such as a refused upload.
    page_error: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, max_length=MAX_PAGE_ERROR)
        ]
        | None
    ) = None


class ModelAnswer(BaseModel):
    """What the model returns."""

    reply: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)
    ]
    # Ids of the path's modules the reply is about, so the page can link to them.
    modules: list[str] = []


class ModuleLink(BaseModel):
    id: str
    title: str


class ChatReply(BaseModel):
    reply: str
    modules: list[ModuleLink]


class PathAssistant:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def answer(
        self,
        path: LearningPath,
        request: ChatRequest,
        problem: CodingProblem | None = None,
        submissions: list[Submission] | None = None,
    ) -> ChatReply:
        """`problem` is the coding problem of the page's module, when the learner sends their code for it;
        `submissions`, the learner's projects as their reviews left them."""
        items = {item.module.id: item for item in path.items}
        page = items.get(request.module_id) if request.module_id else None

        def check(answer: ModelAnswer) -> None:
            unknown = [
                module_id for module_id in answer.modules if module_id not in items
            ]
            if unknown:
                raise UnusableAnswer(
                    f"The answer names modules the path does not have: {unknown}"
                )

        answer = self._llm.ask(
            f"{prompts.load('chat')}\n\n{platform_guide()}",
            prompt(path, request, page, problem, submissions),
            ModelAnswer,
            check=check,
        )
        return ChatReply(
            reply=_without_ids(answer.reply, items),
            modules=[
                ModuleLink(id=module_id, title=items[module_id].module.title)
                for module_id in dict.fromkeys(answer.modules)
            ],
        )


def _without_ids(reply: str, items: dict[str, PathItem]) -> str:
    """Takes out module ids the model copied from the prompt, "[id]", which mean nothing to a learner;
    the modules it names are linked below the reply anyway."""
    for module_id in items:
        reply = reply.replace(f" [{module_id}]", "").replace(f"[{module_id}]", "")
    return reply


def prompt(
    path: LearningPath,
    request: ChatRequest,
    page: PathItem | None,
    problem: CodingProblem | None = None,
    submissions: list[Submission] | None = None,
) -> str:
    parts = [
        "# The learner",
        *_learner(path),
        "",
        "# Their path, in course order",
        *map(_item, path.items),
    ]
    if page is not None:
        parts += ["", "# The module page they are reading now", *_outline(page.module)]
        if request.section:
            parts.append(f"The part of the page on their screen: {request.section}")
    if problem is not None and request.code is not None:
        parts += [
            "",
            "# The module's coding problem, and the learner's code as it is now",
            f"Problem: {problem.title}",
            problem.prompt,
            "Tests:",
            problem.tests,
            "Their code:",
            request.code,
            f"Their last run of the tests: {request.error or 'not run yet'}",
        ]
    for submission in submissions or []:
        parts += ["", *_submission(submission)]
    if request.page_error:
        parts += [
            "",
            "# An error message the site showed them in the last minutes",
            request.page_error,
        ]
    if request.history:
        parts += ["", "# The conversation so far"]
        parts += [
            f"{turn.speaker.value}: {turn.text}"
            for turn in request.history[-MAX_TURNS:]
        ]
    parts += ["", "# Their question", request.question]
    return "\n".join(parts)


def _learner(path: LearningPath) -> list[str]:
    lines = [
        f"Level the path was planned for: {path.level.value if path.level else 'not given'}"
    ]
    lines += [f"{key}: {value}" for key, value in path.answers.items() if value.strip()]
    return lines


def _item(item: PathItem) -> str:
    module = item.module
    line = f"- [{module.id}] {module.full_title}: {item.choice.value}"
    if item.choice != item.suggested:
        line += f" (the learner chose it; the planner suggested {item.suggested.value})"
    line += f"; progress: {item.progress.value}"
    if item.attempts:
        line += f"; checkpoint attempts: {item.attempts}, last score {item.last_score}"
        if item.missed_topics:
            line += f"; topics of the wrong answers last time: {', '.join(item.missed_topics)}"
    if module.hours:
        line += f"; about {module.hours.low:g}-{module.hours.high:g} h"
    if module.prerequisites:
        stated = "; ".join(module.prerequisites)
        line += f"\n  Prerequisites, as the course states them: {stated}"
    line += f"\n  Why: {item.adjustment or item.reason}"
    if item.skim and item.choice is Choice.STUDY:
        skims = "; ".join(_marked(skim) for skim in item.skim)
        line += f"\n  Topics they can skim, though the checkpoint still asks about them: {skims}"
    if item.skip_topics and item.choice is Choice.STUDY:
        skips = "; ".join(_marked(skip) for skip in item.skip_topics)
        line += f"\n  Topics they skip; the checkpoint leaves them out: {skips}"
    return line


def _outline(module: Module) -> list[str]:
    lines = [f"[{module.id}] {module.full_title}"]
    if module.description:
        lines.append(module.description)
    for topic in module.topics:
        lines.append(f"## {topic.title}")
        lines += [f"- {outcome}" for outcome in topic.outcomes]
    if module.checklist:
        lines.append("What finishes the module:")
        lines += [f"- {line}" for line in module.checklist]
    if module.resources:
        lines.append("The course's resources for it:")
        lines += [
            f"- {resource.title} ({resource.type}): {resource.note}"
            for resource in module.resources
        ]
    return lines


def _submission(submission: Submission) -> list[str]:
    """A handed-in project as the learner sees it: its state, and for a review, what the passing level is missing."""
    handed = ", ".join(
        part
        for part in (
            f"link {submission.link}" if submission.link else "",
            f"archive {submission.file_name}" if submission.file_name else "",
        )
        if part
    )
    lines = [
        f"# Their project for {submission.module_title}",
        f"Handed in {submission.submitted_at:%Y-%m-%d}: {handed or 'nothing attached'}",
        f"State: {_STATE[submission.status.value]}",
    ]
    if submission.reviewed_by and submission.reviewed_by != "model":
        lines.append("Decided by a course reviewer, not the model.")
    if submission.review_comment:
        lines.append(f"Feedback: {submission.review_comment}")
    review = submission.ai_review
    if review is not None:
        lines.append(
            f"The review read {review.files_read} of the {review.files_listed} files in the project."
        )
        passing = next((level for level in review.levels if level.passing), None)
        for criterion in passing.criteria if passing else []:
            if criterion.counts:
                continue
            if criterion.evidence_missing:
                why = "not counted: the quoted evidence is not in their files"
            elif criterion.output_missing:
                why = "not counted: only their own words show it, no output of their program"
            else:
                why = {
                    "not_met": "not met",
                    "unverified": "not shown by any program output",
                }.get(criterion.verdict.value, criterion.verdict.value)
            lines.append(
                f"- Missing to pass: {criterion.name} ({why}): {criterion.comment}"
            )
    return lines


_STATE = {
    "reviewing": "the model is reviewing it now; it takes up to a minute",
    "submitted": "waiting for a person: the automatic review was unavailable",
    "accepted": "accepted; the module is finished",
    "returned": "sent back: the passing level is not reached yet",
}


def platform_guide() -> str:
    """How the site works, for questions about the site itself, from the same numbers the site uses."""
    return f"""# How the site works (answer questions about the site from this; it is all you know about it)

Signing in: with an email and a password, or with Google where the site offers it. The site has no password
reset yet. "Too many attempts. Try again in a few minutes." means too many sign-ins in a short time: wait.
The account menu has Sign out and Delete account (deletes the path, progress and handed-in projects).

The path panel: the "My path" button opens it, on any page. Its tabs are Path and Ask (this assistant). Under
the path are its settings: Change your goal (plans the modules not started again),
"Count my progress in course statistics" (on by default; anonymous), and Start over (deletes the path and its
progress). "This draft has expired. Plan your path again." means a path planned before signing in was not
kept: plan it again.

Checkpoints: {QUESTIONS_PER_ATTEMPT} questions; {PASS_MARK} right answers pass. Each new attempt has other
questions. Any question can be reported with "Report this question" and a reason; a course reviewer reads the
reports. After a pass, "Review the checkpoint questions" shows them with the right answers. A module without a
checkpoint is finished with "Mark as done".

Coding problems: after the checkpoint's questions, where the module has one. The code runs in the learner's
browser and is not sent anywhere. Python loads from the internet the first time, which takes a few seconds;
"Python could not be loaded in this browser." means it could not be downloaded: check the connection, reload
the page, or try another browser. Each test shows a check mark or a cross after a run. The module counts as
finished when every test passes.

Capstone projects: hand in a link, a .zip or .tar.gz archive of at most {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB,
or both, with an optional note. A new submission replaces the last; up to {REVIEWS_PER_DAY} a day.
- The review reads an attached archive, or else a public GitHub repository from its main link, such as
  https://github.com/name/project (not a link to a folder or a file in it). Other links are kept for a person
  but cannot be reviewed: the project comes back at once asking for an archive or a GitHub link. A private
  repository cannot be read: make it public or attach an archive.
- Leave out data, models, virtual environments and node_modules: they are not read, and they make the archive
  too big. A repository over 20 MB cannot be read: attach an archive of the code instead.
- The review takes up to a minute; the learner can leave the page. It grades the project against the
  capstone's rubric, criterion by criterion: Met, Not met, or Not shown.
- It does not run the code. How the project works counts only with what the code produced: a notebook with its
  outputs kept, or logs and results files the code wrote. Numbers written by hand in a README do not count
  ("only your own words show it"). "The evidence is not in your files" means a quote could not be found.
- A course reviewer can decide otherwise than the model. When the automatic review is unavailable, the
  project waits for a person. A project sent back can be fixed and handed in again.

The assistant answers {CHATS_PER_DAY} questions a day.

"The personal path service cannot be reached right now." means the site's server or the connection is down:
try again later. For a problem this guide does not cover, say plainly that you do not know the cause, suggest
reloading the page or signing in again, and do not invent settings, buttons or contacts."""


def _marked(marked: SkimTopic) -> str:
    return f"{marked.topic} ({marked.reason})" if marked.reason else marked.topic
