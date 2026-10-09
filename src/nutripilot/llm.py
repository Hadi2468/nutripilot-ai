"""Chat model adapters. Groq, OpenAI and the Meta Llama API speak the OpenAI Chat Completions
protocol, so one small client covers them; Claude goes through the Anthropic SDK. The
service depends only on the `ChatModel` protocol, which is how the tests run offline with a
scripted fake."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
import openai

from nutripilot.config import (
    BASE_URLS,
    DEFAULT_MODELS,
    KEY_ENV_NAMES,
    Provider,
    Settings,
    find_spec,
)

logger = logging.getLogger(__name__)

Message = dict[str, str]


class LLMError(Exception):
    """The provider failed or is not configured (HTTP 503)."""


class LLMRateLimitError(LLMError):
    """The provider is rate limiting us (HTTP 429)."""


@dataclass
class Completion:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatModel(Protocol):
    provider: str
    model: str

    def complete(self, messages: list[Message]) -> Completion: ...


class OpenAICompatibleChat:
    def __init__(self, client: Any, provider: str, model: str, temperature: float | None):
        self.client = client
        self.provider = provider
        self.model = model
        self.temperature = temperature

    def complete(self, messages: list[Message]) -> Completion:
        try:
            sampling = {} if self.temperature is None else {"temperature": self.temperature}
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                # JSON mode: supported by every provider here; the schema itself is in the
                # prompt and the result is validated with Pydantic.
                response_format={"type": "json_object"},
                **sampling,
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError("The LLM provider is rate limiting requests") from exc
        except openai.OpenAIError as exc:
            logger.warning("LLM call failed: %s: %s", exc.__class__.__name__, exc)
            raise LLMError("The LLM provider is unavailable") from exc

        usage = response.usage
        return Completion(
            content=response.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class AnthropicChat:
    """Claude via the Anthropic Messages API.

    Claude 5.5 models think adaptively and reject sampling parameters, so depth is set
    with `effort` instead of `temperature`. JSON comes from the schema in the system
    prompt; the service validates and repairs it like any other provider's output.
    """

    # Opus re-runs a request it declines on a fallback model (server side); Haiku has none.
    FALLBACK_MODELS = frozenset({"claude-opus-5-5"})
    MAX_TOKENS = 16000  # room for adaptive thinking plus a full seven-day plan

    def __init__(self, client: Any, model: str, effort: str):
        self.client = client
        self.provider = "anthropic"
        self.model = model
        self.effort = effort

    def complete(self, messages: list[Message]) -> Completion:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.MAX_TOKENS,
            "system": system,
            "messages": turns,
            "output_config": {"effort": self.effort},
        }
        if self.model in self.FALLBACK_MODELS:
            request |= {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            response = self.client.beta.messages.create(**request)
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError("The LLM provider is rate limiting requests") from exc
        except anthropic.APIError as exc:
            logger.warning("LLM call failed: %s: %s", exc.__class__.__name__, exc)
            raise LLMError("The LLM provider is unavailable") from exc

        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request")
        return Completion(
            content="".join(b.text for b in response.content if b.type == "text"),
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )


def build_chat_model(
    settings: Settings, provider: Provider | None = None, model: str | None = None
) -> ChatModel:
    """The configured default model, or a specific catalog model chosen per request."""
    provider = provider or settings.provider
    model = model or (settings.resolved_model if provider == settings.provider else None)
    api_key = settings.provider_api_key(provider)
    if not api_key:
        raise LLMError(f"{KEY_ENV_NAMES[provider]} is not configured for provider '{provider}'")

    if provider == "anthropic":
        client = anthropic.Anthropic(
            api_key=api_key, timeout=settings.llm_timeout_s, max_retries=settings.llm_max_retries
        )
        return AnthropicChat(client, model or DEFAULT_MODELS[provider], settings.claude_effort)

    client = openai.OpenAI(
        api_key=api_key,
        base_url=BASE_URLS[provider],
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )
    model = model or DEFAULT_MODELS[provider]
    spec = find_spec(provider, model)
    temperature = None if spec and not spec.temperature else settings.temperature
    return OpenAICompatibleChat(client, provider, model, temperature)
