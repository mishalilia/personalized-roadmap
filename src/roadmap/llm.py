"""Structured answers from a chat model served through an OpenAI-compatible API (Groq, Gemini, local servers)."""

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

import openai
from pydantic import BaseModel, Field, ValidationError

from .config import Settings, read_yaml

logger = logging.getLogger(__name__)

Response = TypeVar("Response", bound=BaseModel)


class LLMUnavailable(Exception):
    """No configured model returned a usable answer."""


class UnusableAnswer(Exception):
    """An answer that fits the response schema but not the request, such as an incomplete plan."""


class LLMClient(Protocol):
    def ask(
        self,
        instructions: str,
        prompt: str,
        response_model: type[Response],
        check: Callable[[Response], None] | None = None,
    ) -> Response:
        """The model's answer. `check` raises UnusableAnswer to reject it, as a schema mismatch does."""
        ...


class Provider(BaseModel):
    base_url: str
    models: list[str] = Field(min_length=1)  # in the order they are tried


def load_providers(path: Path) -> dict[str, Provider]:
    return {
        name: Provider.model_validate(provider)
        for name, provider in read_yaml(path).items()
    }


class OpenAICompatibleClient:
    """Tries each model in turn until one answers with JSON that fits the response model.

    Free-tier quotas are counted per model, so a second, smaller model is the first fallback.
    """

    def __init__(self, client: openai.OpenAI, models: list[str]) -> None:
        self._client = client
        self.models = models

    @classmethod
    def connect(cls, api_key: str, provider: Provider) -> "OpenAICompatibleClient":
        client = openai.OpenAI(
            api_key=api_key, base_url=provider.base_url, max_retries=1, timeout=60
        )
        return cls(client, provider.models)

    def ask(
        self,
        instructions: str,
        prompt: str,
        response_model: type[Response],
        check: Callable[[Response], None] | None = None,
    ) -> Response:
        schema = json.dumps(response_model.model_json_schema())
        system = f"{instructions}\n\nReply with one JSON object that follows this JSON Schema:\n{schema}"
        for model in self.models:
            try:
                answer = self._ask_model(model, system, prompt, response_model)
                if check is not None:
                    check(answer)
                return answer
            except (openai.OpenAIError, ValidationError, UnusableAnswer) as error:
                logger.warning("Model %s gave no usable answer: %s", model, error)
        raise LLMUnavailable(f"No usable answer from {', '.join(self.models)}")

    def _ask_model(
        self, model: str, system: str, prompt: str, response_model: type[Response]
    ) -> Response:
        started = time.monotonic()
        completion = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        if completion.usage is not None:
            logger.info(
                "%s answered in %.1f s using %d prompt and %d completion tokens",
                model,
                time.monotonic() - started,
                completion.usage.prompt_tokens,
                completion.usage.completion_tokens,
            )
        return response_model.model_validate_json(
            completion.choices[0].message.content or ""
        )


def connect(settings: Settings) -> OpenAICompatibleClient | None:
    """A client for LLM_PROVIDER, or else for the first provider in config/llm.yaml that has a key."""
    providers = load_providers(settings.llm_file)
    keys = settings.llm_api_keys
    name = settings.llm_provider or next(
        (name for name in providers if name in keys), None
    )
    if name is None:
        logger.warning("No model key in .env: paths will follow the course order")
        return None
    if name not in providers:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{name}'; config/llm.yaml has: {', '.join(providers)}"
        )
    if name not in keys:
        logger.warning(
            "No key for %s (LLM_API_KEY_%s): paths will follow the course order",
            name,
            name.upper(),
        )
        return None
    logger.info("Using %s: %s", name, ", ".join(providers[name].models))
    return OpenAICompatibleClient.connect(
        keys[name].get_secret_value(), providers[name]
    )
