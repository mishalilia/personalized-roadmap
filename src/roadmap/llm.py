"""Structured answers from a chat model served through an OpenAI-compatible API (Groq, Gemini, local servers)."""

import json
import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, NamedTuple, Protocol, TypeVar

import openai
from pydantic import BaseModel, Field, ValidationError

from .config import Settings, read_yaml

logger = logging.getLogger(__name__)

Response = TypeVar("Response", bound=BaseModel)
Item = TypeVar("Item", bound=BaseModel)


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
    # How long the models think before they answer, where the provider has the setting (OpenAI: none, low,
    # medium, high). Thinking is most of the time a path takes: measured on 27 November 2026, about 2,900 of
    # gpt-6-luna's 4,100 completion tokens for a path.
    reasoning_effort: str | None = None


class Route(NamedTuple):
    """One model to ask: the provider's client, the model, and the request's own settings."""

    client: openai.OpenAI
    model: str
    options: Mapping[str, Any] = MappingProxyType({})


def load_providers(path: Path) -> dict[str, Provider]:
    return {
        name: Provider.model_validate(provider)
        for name, provider in read_yaml(path).items()
    }


class OpenAICompatibleClient:
    """Tries each model in turn until one answers with JSON that fits the response model.

    The models may sit with different providers: when the paid one is down or out of credit, the free ones
    follow. Free-tier quotas are counted per model, so a second, smaller model is a fallback too.
    """

    def __init__(self, routes: list[Route]) -> None:
        self._routes = routes  # in the order they are tried

    @property
    def models(self) -> list[str]:
        return [route.model for route in self._routes]

    @classmethod
    def connect(cls, api_key: str, provider: Provider) -> "OpenAICompatibleClient":
        client = _openai_client(api_key, provider)
        options = (
            {"reasoning_effort": provider.reasoning_effort}
            if provider.reasoning_effort
            else {}
        )
        return cls([Route(client, model, options) for model in provider.models])

    @classmethod
    def chain(cls, clients: list["OpenAICompatibleClient"]) -> "OpenAICompatibleClient":
        """One client that tries every model of the first, then of the next, and so on."""
        return cls([route for client in clients for route in client._routes])

    def ask(
        self,
        instructions: str,
        prompt: str,
        response_model: type[Response],
        check: Callable[[Response], None] | None = None,
    ) -> Response:
        system = _system(instructions, response_model)
        for route in self._routes:
            try:
                answer = self._ask_model(route, system, prompt, response_model)
                if check is not None:
                    check(answer)
                return answer
            except (openai.OpenAIError, ValidationError, UnusableAnswer) as error:
                logger.warning("Model %s gave no usable answer: %s", route.model, error)
        raise LLMUnavailable(f"No usable answer from {', '.join(self.models)}")

    def ask_streaming(
        self,
        instructions: str,
        prompt: str,
        response_model: type[Response],
        items: str,
        item_model: type[Item],
        key: str,
        check: Callable[[Response], None] | None = None,
    ) -> Iterator[Item | Response]:
        """The answer as the model writes it: each element of its `items` list as soon as it is complete, then
        the whole answer, last.

        When a model fails part way, the next one is asked and the elements already given are kept: the next
        model's elements with the same `key` are left out, so nothing given is taken back.
        """
        system = _system(instructions, response_model)
        given: dict[Any, dict[str, Any]] = {}
        for route in self._routes:
            parser = ItemsParser(items)
            try:
                for chunk in self._stream_model(route, system, prompt):
                    for element in parser.feed(chunk):
                        name = element.get(key)
                        if name is None or name in given:
                            continue
                        try:
                            item = item_model.model_validate(element)
                        except ValidationError:
                            continue  # left for the check of the whole answer
                        given[name] = element
                        yield item
                answer = response_model.model_validate(
                    _with_given(json.loads(parser.text), items, key, given)
                )
                if check is not None:
                    check(answer)
                yield answer
                return
            except (
                openai.OpenAIError,
                ValidationError,
                UnusableAnswer,
                json.JSONDecodeError,
            ) as error:
                logger.warning("Model %s gave no usable answer: %s", route.model, error)
        raise LLMUnavailable(f"No usable answer from {', '.join(self.models)}")

    @staticmethod
    def _ask_model(
        route: Route,
        system: str,
        prompt: str,
        response_model: type[Response],
    ) -> Response:
        started = time.monotonic()
        completion = route.client.chat.completions.create(
            model=route.model,
            messages=_messages(system, prompt),
            response_format={"type": "json_object"},
            **route.options,
        )
        if completion.usage is not None:
            _log_usage(route.model, started, completion.usage)
        return response_model.model_validate_json(
            completion.choices[0].message.content or ""
        )

    @staticmethod
    def _stream_model(route: Route, system: str, prompt: str) -> Iterator[str]:
        """The answer's text in pieces as the model writes it. A provider that cannot stream a JSON answer
        gives it in one piece."""
        started = time.monotonic()
        request = {
            "model": route.model,
            "messages": _messages(system, prompt),
            "response_format": {"type": "json_object"},
            **route.options,
        }
        try:
            stream = route.client.chat.completions.create(
                **request, stream=True, stream_options={"include_usage": True}
            )
        except openai.BadRequestError as error:
            logger.info(
                "%s does not stream this request (%s); asking at once",
                route.model,
                error,
            )
            completion = route.client.chat.completions.create(**request)
            if completion.usage is not None:
                _log_usage(route.model, started, completion.usage)
            yield completion.choices[0].message.content or ""
            return
        first = None
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                if first is None:
                    first = time.monotonic() - started
                yield chunk.choices[0].delta.content
            if getattr(chunk, "usage", None) is not None:
                _log_usage(route.model, started, chunk.usage, first)


def _system(instructions: str, response_model: type[BaseModel]) -> str:
    schema = json.dumps(response_model.model_json_schema())
    return f"{instructions}\n\nReply with one JSON object that follows this JSON Schema:\n{schema}"


def _messages(system: str, prompt: str) -> list[Any]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


def _log_usage(
    model: str, started: float, usage: Any, first: float | None = None
) -> None:
    logger.info(
        "%s answered in %.1f s%s using %d prompt and %d completion tokens",
        model,
        time.monotonic() - started,
        f" (first words after {first:.1f} s)" if first is not None else "",
        usage.prompt_tokens,
        usage.completion_tokens,
    )


def _with_given(
    answer: Any, items: str, key: str, given: dict[Any, dict[str, Any]]
) -> Any:
    """The answer with the elements already given in place of its own for the same key."""
    if (
        not given
        or not isinstance(answer, dict)
        or not isinstance(answer.get(items), list)
    ):
        return answer
    own = [
        element
        for element in answer[items]
        if not (isinstance(element, dict) and element.get(key) in given)
    ]
    return {**answer, items: [*given.values(), *own]}


class ItemsParser:
    """Finds the finished elements of one list in a JSON object that is still being written, such as
    {"decisions": [{...}, {...}, ...: each element once its closing brace arrives."""

    def __init__(self, items: str) -> None:
        self.text = ""
        self._start = re.compile(rf'"{re.escape(items)}"\s*:\s*\[')
        self._at: int | None = None  # where scanning goes on, once the list has begun
        self._depth = 0  # inside the list: 0 between elements
        self._in_string = False
        self._escaped = False
        self._element = 0  # where the current element began
        self._done = False

    def feed(self, chunk: str) -> list[dict[str, Any]]:
        self.text += chunk
        if self._done:
            return []
        if self._at is None:
            found = self._start.search(self.text)
            if found is None:
                return []
            self._at = found.end()
        elements = []
        text = self.text
        for at in range(self._at, len(text)):
            char = text[at]
            if self._in_string:
                if self._escaped:
                    self._escaped = False
                elif char == "\\":
                    self._escaped = True
                elif char == '"':
                    self._in_string = False
                continue
            if char == '"':
                self._in_string = True
            elif char in "{[":
                if self._depth == 0:
                    self._element = at
                self._depth += 1
            elif char in "}]":
                if self._depth == 0:  # the list ends
                    self._done = True
                    self._at = at + 1
                    return elements
                self._depth -= 1
                if self._depth == 0 and char == "}":
                    try:
                        element = json.loads(text[self._element : at + 1])
                    except json.JSONDecodeError:
                        element = None
                    if isinstance(element, dict):
                        elements.append(element)
        self._at = len(text)
        return elements


def _openai_client(api_key: str, provider: Provider) -> openai.OpenAI:
    return openai.OpenAI(
        api_key=api_key, base_url=provider.base_url, max_retries=1, timeout=60
    )


def connect(settings: Settings) -> OpenAICompatibleClient | None:
    """A client for every provider with a key, in the order of config/llm.yaml; LLM_PROVIDER goes first.

    When one provider gives no usable answer, the next one is asked; when none does, callers fall back to
    the course order.
    """
    providers = load_providers(settings.llm_file)
    keys = settings.llm_api_keys
    chosen = settings.llm_provider
    if chosen is not None and chosen not in providers:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{chosen}'; config/llm.yaml has: {', '.join(providers)}"
        )
    if chosen is not None and chosen not in keys:
        logger.warning("No key for %s (LLM_API_KEY_%s)", chosen, chosen.upper())
    order = sorted(providers, key=lambda name: name != chosen)
    with_keys = [name for name in order if name in keys]
    if not with_keys:
        logger.warning("No model key in .env: paths will follow the course order")
        return None
    clients = [
        OpenAICompatibleClient.connect(keys[name].get_secret_value(), providers[name])
        for name in with_keys
    ]
    client = OpenAICompatibleClient.chain(clients)
    logger.info("Using %s", " → ".join(client.models))
    return client
