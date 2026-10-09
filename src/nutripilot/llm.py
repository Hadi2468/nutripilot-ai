"""Chat model adapter. Groq and OpenAI both speak the OpenAI Chat Completions protocol, so
one small client covers both; the service depends only on the `ChatModel` protocol, which
is how the tests run offline with a scripted fake."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import openai

from nutripilot.config import Settings

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
    def __init__(self, client: Any, provider: str, model: str, temperature: float):
        self.client = client
        self.provider = provider
        self.model = model
        self.temperature = temperature

    def complete(self, messages: list[Message]) -> Completion:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                # JSON mode: supported by both providers; the schema itself is in the prompt
                # and the result is validated with Pydantic.
                response_format={"type": "json_object"},
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError("The LLM provider is rate limiting requests") from exc
        except openai.OpenAIError as exc:
            logger.warning("LLM call failed: %s", exc.__class__.__name__)
            raise LLMError("The LLM provider is unavailable") from exc

        usage = response.usage
        return Completion(
            content=response.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


def build_chat_model(settings: Settings) -> OpenAICompatibleChat:
    api_key = settings.provider_api_key()
    if not api_key:
        env = "GROQ_API_KEY" if settings.provider == "groq" else "OPENAI_API_KEY"
        raise LLMError(f"{env} is not configured for provider '{settings.provider}'")
    client = openai.OpenAI(
        api_key=api_key,
        base_url=settings.base_url,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )
    return OpenAICompatibleChat(
        client, settings.provider, settings.resolved_model, settings.temperature
    )
