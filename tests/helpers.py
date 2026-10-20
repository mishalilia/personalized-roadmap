from collections.abc import Callable
from pathlib import Path
from typing import Any

from roadmap import Choice, Curriculum
from roadmap.llm import LLMUnavailable, Response, UnusableAnswer
from roadmap.planner import prompt_ids

ROOT = Path(__file__).parents[1]
FIXTURE_DOCS = Path(__file__).parent / "fixtures" / "docs"
SITE_URL = "https://site.example/docs"


class FakeLLM:
    """A one-model client with prepared answers, given in turn. Records every prompt.

    An answer that is an exception is raised; an answer the check rejects makes the model
    unavailable, as it does in the real client once no model is left to try.
    """

    def __init__(self, *responses: dict[str, Any] | Exception) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def ask(
        self,
        instructions: str,
        prompt: str,
        response_model: type[Response],
        check: Callable[[Response], None] | None = None,
    ) -> Response:
        self.prompts.append(prompt)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        answer = response_model.model_validate(response)
        if check is not None:
            try:
                check(answer)
            except UnusableAnswer as error:
                raise LLMUnavailable(
                    "The only model gave an unusable answer"
                ) from error
        return answer


def planner_response(
    curriculum: Curriculum, decisions: dict[str, tuple[Choice, str]]
) -> dict[str, Any]:
    """The planner's answer as the model gives it, from (choice, reason) by module id.

    The model sees short ids (m1, m2, ...) instead of module ids, so the answer uses those.
    """
    prompt_id_of = {
        module.id: prompt_id
        for prompt_id, module in prompt_ids(curriculum.modules).items()
    }
    return {
        "decisions": [
            {"module_id": prompt_id_of[module_id], "choice": choice, "reason": reason}
            for module_id, (choice, reason) in decisions.items()
        ]
    }


def study_all(
    curriculum: Curriculum, except_for: dict[str, tuple[Choice, str]] | None = None
) -> dict[str, Any]:
    """A complete plan: every module to study, except the given (choice, reason) by module id."""
    decisions = {
        module.id: (Choice.STUDY, "Needed for your goal.")
        for module in curriculum.modules
    }
    return planner_response(curriculum, decisions | (except_for or {}))
