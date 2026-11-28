from types import SimpleNamespace
from typing import cast

import httpx
import openai
import pytest
from helpers import ROOT
from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict

from roadmap import Level, LevelAssessment, Settings
from roadmap.llm import (
    ItemsParser,
    LLMUnavailable,
    OpenAICompatibleClient,
    Route,
    UnusableAnswer,
    connect,
)

VALID_ANSWER = '{"level": "beginner", "evidence": ["Finished an intro course last month"], "confidence": "high"}'


class StubCompletions:
    """Stands in for `client.chat.completions`: one prepared reply per model name."""

    def __init__(self, replies: dict[str, str | list | Exception]) -> None:
        self._replies = replies
        self.requests: list[dict] = []

    def create(self, **request):
        self.requests.append(request)
        reply = self._replies[request["model"]]
        if isinstance(reply, Exception):
            raise reply
        if request.get("stream"):
            return self._stream(reply)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )

    def _stream(self, reply: str | list):
        """A reply in pieces of five characters; an exception in a list is raised where it stands."""
        pieces = reply if isinstance(reply, list) else [reply]
        self.sent = 0
        for piece in pieces:
            if isinstance(piece, Exception):
                raise piece
            for at in range(0, len(piece), 5):
                self.sent += 1
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=piece[at : at + 5])
                        )
                    ],
                    usage=None,
                )
        yield SimpleNamespace(
            choices=[], usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        )


def client_answering(
    replies: dict[str, str | list | Exception],
) -> tuple[OpenAICompatibleClient, StubCompletions]:
    completions = StubCompletions(replies)
    stub = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    openai_client = cast(openai.OpenAI, stub)  # stands in for the real client
    return (
        OpenAICompatibleClient([Route(openai_client, model) for model in replies]),
        completions,
    )


def test_asks_for_json_that_follows_the_response_schema():
    client, completions = client_answering({"main": VALID_ANSWER})

    assessment = client.ask("Assess the level.", "Q: ...\nA: ...", LevelAssessment)

    assert assessment.level == Level.BEGINNER
    [request] = completions.requests
    assert request["response_format"] == {"type": "json_object"}
    system_message = request["messages"][0]["content"]
    assert system_message.startswith("Assess the level.")
    assert '"evidence"' in system_message


def test_falls_back_to_the_next_model_when_one_is_unreachable():
    unreachable = openai.APIConnectionError(
        request=httpx.Request("POST", "https://llm.example")
    )
    client, completions = client_answering(
        {"main": unreachable, "fallback": VALID_ANSWER}
    )

    assert client.ask("Assess the level.", "", LevelAssessment).level == Level.BEGINNER
    assert [request["model"] for request in completions.requests] == [
        "main",
        "fallback",
    ]


def test_falls_back_when_the_answer_does_not_fit_the_schema():
    client, _ = client_answering(
        {"main": '{"level": "expert"}', "fallback": VALID_ANSWER}
    )

    assert client.ask("Assess the level.", "", LevelAssessment).level == Level.BEGINNER


def test_raises_when_no_model_gives_a_usable_answer():
    client, _ = client_answering({"main": "not JSON", "fallback": "{}"})

    with pytest.raises(LLMUnavailable):
        client.ask("Assess the level.", "", LevelAssessment)


FAKE_KEY = "not-a-real-key"  # pragma: allowlist secret


class SettingsWithoutDotenv(Settings):
    """Settings that ignore the developer's .env file, so these tests do not depend on it."""

    model_config = SettingsConfigDict(
        env_file=None, env_ignore_empty=True, extra="ignore"
    )


def settings_with(**values) -> Settings:
    return SettingsWithoutDotenv(config_dir=ROOT / "config", **values)


@pytest.fixture(autouse=True)
def no_llm_environment(monkeypatch):
    for name in (
        "LLM_PROVIDER",
        "LLM_API_KEY_OPENAI",
        "LLM_API_KEY_GROQ",
        "LLM_API_KEY_GOOGLE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_without_a_provider_the_first_one_with_a_key_is_used():
    client = connect(settings_with(llm_api_key_google=FAKE_KEY))

    assert client is not None
    assert client.models[0].startswith("gemini")


def test_openai_comes_first_then_the_free_providers():
    client = connect(
        settings_with(
            llm_api_key_openai=FAKE_KEY,
            llm_api_key_groq=FAKE_KEY,
            llm_api_key_google=FAKE_KEY,
        )
    )

    assert client is not None
    assert client.models == [
        "gpt-6-luna",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "openai/gpt-oss-120b",
    ]


def test_only_providers_with_a_key_are_asked():
    client = connect(
        settings_with(llm_api_key_openai=FAKE_KEY, llm_api_key_groq=FAKE_KEY)
    )

    assert client is not None
    assert client.models == ["gpt-6-luna", "openai/gpt-oss-120b"]


def test_the_chosen_provider_goes_first():
    client = connect(
        settings_with(
            llm_provider="groq",
            llm_api_key_openai=FAKE_KEY,
            llm_api_key_groq=FAKE_KEY,
        )
    )

    assert client is not None
    assert client.models == ["openai/gpt-oss-120b", "gpt-6-luna"]


def test_without_a_key_for_the_chosen_provider_the_others_are_asked():
    client = connect(settings_with(llm_provider="google", llm_api_key_groq=FAKE_KEY))

    assert client is not None
    assert client.models == ["openai/gpt-oss-120b"]


def test_no_client_without_any_key():
    assert connect(settings_with()) is None
    assert connect(settings_with(llm_provider="google")) is None


def test_a_failing_provider_hands_over_to_the_next_one():
    out_of_credit = openai.RateLimitError(
        "insufficient_quota",
        response=httpx.Response(
            429, request=httpx.Request("POST", "https://paid.example")
        ),
        body=None,
    )
    paid, paid_calls = client_answering({"gpt-6-luna": out_of_credit})
    free, free_calls = client_answering({"gemini-3.5-flash-lite": VALID_ANSWER})

    assessment = OpenAICompatibleClient.chain([paid, free]).ask(
        "Assess the level.", "", LevelAssessment
    )

    assert assessment.level == Level.BEGINNER
    assert [r["model"] for r in paid_calls.requests] == ["gpt-6-luna"]
    assert [r["model"] for r in free_calls.requests] == ["gemini-3.5-flash-lite"]


def test_an_unknown_provider_is_an_error():
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        connect(settings_with(llm_provider="nonexistent", llm_api_key_groq=FAKE_KEY))


def test_an_answer_the_check_rejects_goes_to_the_next_model():
    client, completions = client_answering(
        {"main": VALID_ANSWER, "fallback": VALID_ANSWER}
    )
    answers = iter([False, True])

    def accept_second(answer: LevelAssessment) -> None:
        if not next(answers):
            raise UnusableAnswer("incomplete")

    client.ask("Assess the level.", "", LevelAssessment, check=accept_second)

    assert [request["model"] for request in completions.requests] == [
        "main",
        "fallback",
    ]


class Entry(BaseModel):
    id: str
    text: str


class Entries(BaseModel):
    entries: list[Entry]
    note: str = ""


ENTRIES = '{"entries": [{"id": "a", "text": "First {with a brace}"}, {"id": "b", "text": "Second"}], "note": "Done"}'


def stream(client: OpenAICompatibleClient, check=None) -> list:
    return list(
        client.ask_streaming("List them.", "", Entries, "entries", Entry, "id", check)
    )


def test_a_streamed_answer_gives_each_element_as_soon_as_it_is_written():
    client, completions = client_answering({"main": ENTRIES})
    events = client.ask_streaming("List them.", "", Entries, "entries", Entry, "id")

    first = next(events)
    sent_for_first = completions.sent
    rest = list(events)

    assert first == Entry(id="a", text="First {with a brace}")
    assert (
        sent_for_first < len(ENTRIES) // 5
    )  # before the rest of the answer was written
    assert rest[0] == Entry(id="b", text="Second")
    assert rest[1] == Entries.model_validate_json(ENTRIES)
    assert completions.requests[0]["stream"] is True


def test_a_model_failing_part_way_hands_over_and_what_was_given_stays():
    broken = openai.APIConnectionError(
        request=httpx.Request("POST", "https://llm.example")
    )
    client, _ = client_answering(
        {
            "main": [
                '{"entries": [{"id": "a", "text": "From main"}, {"id": "b", "te',
                broken,
            ],
            "fallback": '{"entries": [{"id": "a", "text": "From fallback"}, {"id": "b", "text": "B"}]}',
        }
    )

    events = stream(client)

    assert events[:2] == [Entry(id="a", text="From main"), Entry(id="b", text="B")]
    assert [entry.text for entry in events[2].entries] == ["From main", "B"]


def test_a_streamed_answer_the_check_rejects_goes_to_the_next_model():
    def needs_three(answer: Entries) -> None:
        if len(answer.entries) < 3:
            raise UnusableAnswer("Too few")

    three = '{"entries": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}, {"id": "c", "text": "C"}]}'
    client, _ = client_answering({"main": ENTRIES, "fallback": three})

    events = stream(client, needs_three)

    assert [event.id for event in events[:-1]] == ["a", "b", "c"]
    assert events[-1].entries[0].text == "First {with a brace}"  # given first, kept


def test_a_provider_that_cannot_stream_answers_at_once():
    refused = openai.BadRequestError(
        "streaming is not supported",
        response=httpx.Response(
            400, request=httpx.Request("POST", "https://llm.example")
        ),
        body=None,
    )

    class NoStreaming(StubCompletions):
        def create(self, **request):
            if request.get("stream"):
                self.requests.append(request)
                raise refused
            return super().create(**request)

    completions = NoStreaming({"main": ENTRIES})
    stub = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client = OpenAICompatibleClient([Route(cast(openai.OpenAI, stub), "main")])

    events = stream(client)

    assert [event.id for event in events[:-1]] == ["a", "b"]
    assert [request.get("stream") for request in completions.requests] == [True, None]


def test_without_any_usable_stream_the_models_are_unavailable():
    client, _ = client_answering(
        {"main": "not JSON", "fallback": '{"entries": "none"}'}
    )

    with pytest.raises(LLMUnavailable):
        stream(client)


def test_the_parser_finds_elements_across_pieces_and_ignores_brackets_in_text():
    parser = ItemsParser("entries")
    text = '{"entries": [{"id": "a", "text": "x ] } \\" y"}, {"id": "b", "text": "[z]"}], "note": "{}"}'
    found = [
        element
        for at in range(0, len(text), 3)
        for element in parser.feed(text[at : at + 3])
    ]

    assert [element["id"] for element in found] == ["a", "b"]
    assert found[0]["text"] == 'x ] } " y'


def test_the_providers_reasoning_effort_goes_with_every_request():
    from roadmap.llm import Provider

    provider = Provider(
        base_url="https://llm.example/v1", models=["one"], reasoning_effort="low"
    )
    client = OpenAICompatibleClient.connect(FAKE_KEY, provider)
    completions = StubCompletions({"one": VALID_ANSWER})
    stub = cast(
        openai.OpenAI, SimpleNamespace(chat=SimpleNamespace(completions=completions))
    )
    client = OpenAICompatibleClient(
        [route._replace(client=stub) for route in client._routes]
    )

    client.ask("Assess the level.", "", LevelAssessment)

    assert completions.requests[0]["reasoning_effort"] == "low"


def test_the_openai_models_think_little_and_the_others_keep_their_default():
    from roadmap.llm import load_providers

    providers = load_providers(ROOT / "config" / "llm.yaml")

    assert providers["openai"].reasoning_effort == "low"
    assert providers["google"].reasoning_effort is None
    assert providers["groq"].reasoning_effort is None
