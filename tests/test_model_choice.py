"""Claude adapter and per-request model choice."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from nutripilot.config import Settings
from nutripilot.llm import (
    AnthropicChat,
    LLMError,
    LLMRateLimitError,
    OpenAICompatibleChat,
    build_chat_model,
)
from tests.conftest import FakeLLM

P = "/v1/nutripilot"
TIPS = {"tips": [{"tip": "t", "why": "w"}] * 5}


# ============================================================
# Anthropic adapter
# ============================================================


class FakeMessages:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return self.response


def claude_response(stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text='{"tips": '),
            SimpleNamespace(type="text", text="[]}"),
        ],
        usage=SimpleNamespace(input_tokens=40, output_tokens=7),
    )


def fake_anthropic(**kw):
    messages = FakeMessages(**kw)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


MESSAGES = [
    {"role": "system", "content": "Return JSON."},
    {"role": "user", "content": "Tips please"},
    {"role": "assistant", "content": "{}"},
    {"role": "user", "content": "Fix it"},
]


def test_claude_request_shape_and_text_extraction():
    client, messages = fake_anthropic(response=claude_response())
    result = AnthropicChat(client, "claude-haiku-5-5", "medium").complete(MESSAGES)

    assert result.content == '{"tips": []}'  # thinking blocks skipped, text joined
    assert (result.prompt_tokens, result.completion_tokens) == (40, 7)
    sent = messages.kwargs
    assert sent["system"] == "Return JSON."
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    assert sent["output_config"] == {"effort": "medium"}
    assert "temperature" not in sent  # Claude 5.5 models reject sampling parameters
    assert "fallbacks" not in sent  # Haiku has no server-side fallback


def test_claude_opus_opts_into_server_side_fallback():
    client, messages = fake_anthropic(response=claude_response())
    AnthropicChat(client, "claude-opus-5-5", "medium").complete(MESSAGES)
    assert messages.kwargs["fallbacks"] == "default"
    assert messages.kwargs["betas"] == ["server-side-fallback-2026-07-01"]


def test_claude_refusal_is_an_llm_error():
    client, _ = fake_anthropic(response=claude_response(stop_reason="refusal"))
    with pytest.raises(LLMError, match="declined"):
        AnthropicChat(client, "claude-opus-5-5", "medium").complete(MESSAGES)


def _response(code: int) -> httpx2.Response:
    return httpx2.Response(code, request=httpx2.Request("POST", "https://x"))


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (anthropic.RateLimitError("slow", response=_response(429), body=None), LLMRateLimitError),
        (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")), LLMError),
    ],
)
def test_claude_errors_are_wrapped(exc, expected):
    client, _ = fake_anthropic(exc=exc)
    with pytest.raises(expected):
        AnthropicChat(client, "claude-haiku-5-5", "low").complete(MESSAGES)


def test_build_chat_model_per_provider():
    s = Settings(_env_file=None, GROQ_API_KEY="g", ANTHROPIC_API_KEY="a", claude_effort="low")
    default = build_chat_model(s)
    assert isinstance(default, OpenAICompatibleChat) and default.model == "openai/gpt-oss-20b"

    claude = build_chat_model(s, "anthropic")
    assert isinstance(claude, AnthropicChat)
    assert (claude.model, claude.effort) == ("claude-opus-5-5", "low")
    assert build_chat_model(s, "anthropic", "claude-haiku-5-5").model == "claude-haiku-5-5"

    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        build_chat_model(s, "openai")


# ============================================================
# Per-request model choice through the API
# ============================================================


@pytest.fixture
def choice_client(settings):
    from fastapi.testclient import TestClient

    from nutripilot.api import create_app

    built: list[tuple[str, str]] = []

    def builder(provider, model):
        built.append((provider, model))
        llm = FakeLLM(TIPS)
        llm.provider, llm.model = provider, model
        return llm

    s = settings.model_copy(
        update={"groq_api_key": SecretStr("g"), "anthropic_api_key": SecretStr("a")}
    )
    client = TestClient(create_app(settings=s, model_builder=builder))
    return client, built


def test_models_endpoint_reports_availability(choice_client):
    client, _ = choice_client
    body = client.get(f"{P}/models").json()
    assert body["default"] == {"provider": "groq", "model": "openai/gpt-oss-20b"}
    available = {m["model"]: m["available"] for m in body["models"]}
    assert available["claude-haiku-5-5"] and available["openai/gpt-oss-120b"]
    assert not available["gpt-4o-mini"]  # no OPENAI_API_KEY


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ("groq", "openai/gpt-oss-20b")),
        ({"provider": "anthropic"}, ("anthropic", "claude-opus-5-5")),
        ({"model": "claude-haiku-5-5"}, ("anthropic", "claude-haiku-5-5")),
        (
            {"provider": "groq", "model": "llama-3.3-70b-versatile"},
            ("groq", "llama-3.3-70b-versatile"),
        ),
    ],
)
def test_request_picks_the_model(choice_client, params, expected):
    client, _ = choice_client
    meta = client.get(f"{P}/recommendations", params=params).json()["meta"]
    assert (meta["provider"], meta["model"]) == expected


def test_models_are_built_once_and_reused(choice_client):
    client, built = choice_client
    for _ in range(3):
        client.get(f"{P}/recommendations", params={"model": "claude-haiku-5-5"})
    assert built == [("anthropic", "claude-haiku-5-5")]


@pytest.mark.parametrize(
    "params",
    [
        {"model": "gpt-99"},
        {"provider": "groq", "model": "claude-haiku-5-5"},
        {"provider": "mistral"},
    ],
)
def test_unknown_or_mismatched_models_are_422(choice_client, params):
    client, built = choice_client
    assert client.get(f"{P}/recommendations", params=params).status_code == 422
    assert built == []


def test_cli_provider_and_model_flags(monkeypatch, capsys):
    import nutripilot.cli as cli

    seen = {}

    def fake_build(settings, provider, model):
        seen.update(provider=provider, model=model)
        llm = FakeLLM(TIPS)
        llm.provider, llm.model = provider, model
        return llm

    monkeypatch.setattr(cli, "build_chat_model", fake_build)
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    assert cli.main(["--model", "claude-haiku-5-5", "tips"]) == 0
    assert seen == {"provider": "anthropic", "model": "claude-haiku-5-5"}
    assert "claude-haiku-5-5" in capsys.readouterr().out
