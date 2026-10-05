from types import SimpleNamespace
from typing import cast

import httpx
import openai
import pytest
from helpers import ROOT
from pydantic_settings import SettingsConfigDict

from roadmap import Level, LevelAssessment, Settings
from roadmap.llm import LLMUnavailable, OpenAICompatibleClient, UnusableAnswer, connect

VALID_ANSWER = '{"level": "beginner", "evidence": ["Finished an intro course last month"], "confidence": "high"}'


class StubCompletions:
    """Stands in for `client.chat.completions`: one prepared reply per model name."""

    def __init__(self, replies: dict[str, str | Exception]) -> None:
        self._replies = replies
        self.requests: list[dict] = []

    def create(self, **request):
        self.requests.append(request)
        reply = self._replies[request["model"]]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


def client_answering(
    replies: dict[str, str | Exception],
) -> tuple[OpenAICompatibleClient, StubCompletions]:
    completions = StubCompletions(replies)
    stub = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    openai_client = cast(openai.OpenAI, stub)  # stands in for the real client
    return OpenAICompatibleClient(openai_client, models=list(replies)), completions


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
    for name in ("LLM_PROVIDER", "LLM_API_KEY_GROQ", "LLM_API_KEY_GOOGLE"):
        monkeypatch.delenv(name, raising=False)


def test_without_a_provider_the_first_one_with_a_key_is_used():
    client = connect(settings_with(llm_api_key_google=FAKE_KEY))

    assert client is not None
    assert client.models[0].startswith("gemini")


def test_the_chosen_provider_wins_over_the_order_in_the_config():
    client = connect(
        settings_with(
            llm_provider="google",
            llm_api_key_groq=FAKE_KEY,
            llm_api_key_google=FAKE_KEY,
        )
    )

    assert client is not None
    assert client.models[0].startswith("gemini")


def test_no_client_without_a_key_for_the_chosen_provider():
    assert connect(settings_with()) is None
    assert (
        connect(settings_with(llm_provider="google", llm_api_key_groq=FAKE_KEY)) is None
    )


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
