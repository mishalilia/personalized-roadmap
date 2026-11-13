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
from .curriculum import Module
from .llm import LLMClient, UnusableAnswer
from .path import LearningPath, PathItem

MAX_QUESTION = 1000
MAX_TURN = 2000
MAX_TURNS = 8  # earlier turns sent with a question

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
    # The module whose page the learner is reading, if any.
    module_id: str | None = None


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

    def answer(self, path: LearningPath, request: ChatRequest) -> ChatReply:
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
            prompts.load("chat"), prompt(path, request, page), ModelAnswer, check=check
        )
        return ChatReply(
            reply=answer.reply,
            modules=[
                ModuleLink(id=module_id, title=items[module_id].module.title)
                for module_id in dict.fromkeys(answer.modules)
            ],
        )


def prompt(path: LearningPath, request: ChatRequest, page: PathItem | None) -> str:
    parts = [
        "# The learner",
        *_learner(path),
        "",
        "# Their path, in course order",
        *map(_item, path.items),
    ]
    if page is not None:
        parts += ["", "# The module page they are reading now", *_outline(page.module)]
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
    lines.append(
        "Path confirmed: yes, they are working through it"
        if path.confirmed_at
        else "Path confirmed: not yet, they are still reviewing it"
    )
    return lines


def _item(item: PathItem) -> str:
    module = item.module
    line = f"- [{module.id}] {module.full_title}: {item.choice.value}"
    if item.choice != item.suggested:
        line += f" (the learner chose it; the planner suggested {item.suggested.value})"
    line += f"; progress: {item.progress.value}"
    if item.attempts:
        line += f"; checkpoint attempts: {item.attempts}, last score {item.last_score}"
    if module.hours:
        line += f"; about {module.hours.low:g}-{module.hours.high:g} h"
    if module.prerequisites:
        stated = "; ".join(module.prerequisites)
        line += f"\n  Prerequisites, as the course states them: {stated}"
    line += f"\n  Why: {item.adjustment or item.reason}"
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
