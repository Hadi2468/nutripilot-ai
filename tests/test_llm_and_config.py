from types import SimpleNamespace

import httpx
import openai
import pytest

from nutripilot.aws_secrets import load_secret_into_env
from nutripilot.config import Settings
from nutripilot.llm import LLMError, LLMRateLimitError, OpenAICompatibleChat, build_chat_model
from nutripilot.prompts import plan_prompt
from nutripilot.schemas import PlanRequest
from tests.conftest import PLAN_REQUEST


class FakeCompletions:
    def __init__(self, exc: Exception | None = None):
        self.exc = exc
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
        )


def fake_client(exc=None):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(exc)))


def test_chat_model_requests_json_and_reports_usage():
    client = fake_client()
    chat = OpenAICompatibleChat(client, "groq", "openai/gpt-oss-20b", 0.3)
    result = chat.complete([{"role": "user", "content": "hi"}])

    assert result.content == '{"ok": true}' and result.prompt_tokens == 12
    sent = client.chat.completions.kwargs
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["model"] == "openai/gpt-oss-20b" and sent["temperature"] == 0.3


def _response(code: int) -> httpx.Response:
    return httpx.Response(code, request=httpx.Request("POST", "https://x"))


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (openai.RateLimitError("slow", response=_response(429), body=None), LLMRateLimitError),
        (openai.APIConnectionError(request=httpx.Request("POST", "https://x")), LLMError),
    ],
)
def test_provider_errors_are_wrapped(exc, expected):
    chat = OpenAICompatibleChat(fake_client(exc), "groq", "m", 0)
    with pytest.raises(expected):
        chat.complete([])


def test_provider_defaults_and_switching():
    groq = Settings(_env_file=None, GROQ_API_KEY="g")
    assert groq.resolved_model == "openai/gpt-oss-20b"
    assert groq.base_url == "https://api.groq.com/openai/v1"
    assert build_chat_model(groq).client.base_url.host == "api.groq.com"

    oai = Settings(_env_file=None, provider="openai", OPENAI_API_KEY="o", model="gpt-4.1-mini")
    chat = build_chat_model(oai)
    assert chat.model == "gpt-4.1-mini" and chat.client.base_url.host == "api.openai.com"


def test_missing_provider_key_is_reported():
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        build_chat_model(Settings(_env_file=None, provider="openai"))


def test_legacy_api_token_env_name_still_works(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "legacy")
    assert Settings(_env_file=None).api_token == "legacy"


def test_secret_is_exported_without_overriding(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "already-set")
    monkeypatch.delenv("NUTRIPILOT_API_TOKEN", raising=False)
    secret = '{"GROQ_API_KEY": "from-secret", "NUTRIPILOT_API_TOKEN": "tok", "EMPTY": ""}'
    client = SimpleNamespace(get_secret_value=lambda SecretId: {"SecretString": secret})

    assert load_secret_into_env("arn:aws:secretsmanager:x", client) == ["NUTRIPILOT_API_TOKEN"]
    assert Settings(_env_file=None).groq_api_key.get_secret_value() == "already-set"
    assert Settings(_env_file=None).api_token == "tok"


def test_secret_must_be_an_object():
    client = SimpleNamespace(get_secret_value=lambda SecretId: {"SecretString": "[1, 2]"})
    with pytest.raises(ValueError, match="JSON object"):
        load_secret_into_env("arn", client)


def test_plan_prompt_carries_rules_schema_and_audience():
    system, user = plan_prompt(
        PlanRequest(**PLAN_REQUEST | {"age": 70, "diseases": "hypertension"})
    )
    assert "JSON Schema" in system and '"meals"' in system
    assert (
        "Never include these foods or ingredients (allergies and dislikes): peanuts, mushrooms"
        in user
    )
    assert "older adult" in user and "hypertension" in user
