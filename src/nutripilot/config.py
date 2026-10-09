"""Application settings, loaded from environment variables and `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["groq", "openai", "anthropic", "meta"]
Platform = Literal["groq", "direct"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Groq, OpenAI and the Meta Llama API speak the OpenAI Chat Completions protocol, so one
# client serves all three; Anthropic (Claude) uses its own SDK.
BASE_URLS: dict[Provider, str | None] = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": None,  # the SDK default
    "anthropic": None,
    "meta": "https://api.llama.com/compat/v1/",
}
KEY_ENV_NAMES: dict[Provider, str] = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "meta": "LLAMA_API_KEY",
}


@dataclass(frozen=True)
class ModelSpec:
    provider: Provider
    model: str
    family: str  # who made the model: OpenAI, Claude, Llama
    label: str
    temperature: bool = True  # reasoning models such as GPT-5.5 only accept the default

    @property
    def platform(self) -> Platform:
        """Groq (fast inference of open models) or the model maker's own API."""
        return "groq" if self.provider == "groq" else "direct"


# The models a client may pick per request. The first model of each provider is its default.
# Groq only serves open-weight models, so Claude is available on the direct platform only.
CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec("groq", "openai/gpt-oss-20b", "OpenAI", "GPT-OSS 20B"),
    ModelSpec("groq", "openai/gpt-oss-120b", "OpenAI", "GPT-OSS 120B"),
    ModelSpec("groq", "llama-3.1-8b-instant", "Llama", "Llama 3.1 8B"),
    ModelSpec("groq", "llama-3.3-70b-versatile", "Llama", "Llama 3.3 70B"),
    ModelSpec("groq", "meta-llama/llama-4-scout-17b-16e-instruct", "Llama", "Llama 4 Scout"),
    ModelSpec("openai", "gpt-4o-mini", "OpenAI", "GPT-4o mini"),
    ModelSpec("openai", "gpt-5.4-mini", "OpenAI", "GPT-5.4 mini"),
    ModelSpec("openai", "gpt-5.5", "OpenAI", "GPT-5.5", temperature=False),
    ModelSpec("anthropic", "claude-opus-5-5", "Claude", "Claude Opus 5.5"),
    ModelSpec("anthropic", "claude-sonnet-5-5", "Claude", "Claude Sonnet 5.5"),
    ModelSpec("anthropic", "claude-haiku-5-5", "Claude", "Claude Haiku 5.5"),
    ModelSpec("meta", "Llama-3.3-70B-Instruct", "Llama", "Llama 3.3 70B"),
    ModelSpec("meta", "Llama-4-Scout-17B-16E-Instruct-FP8", "Llama", "Llama 4 Scout"),
    ModelSpec("meta", "Llama-4-Maverick-17B-128E-Instruct-FP8", "Llama", "Llama 4 Maverick"),
)
MODEL_CATALOG: dict[Provider, dict[str, ModelSpec]] = {}
for _spec in CATALOG:
    MODEL_CATALOG.setdefault(_spec.provider, {})[_spec.model] = _spec
DEFAULT_MODELS: dict[Provider, str] = {p: next(iter(m)) for p, m in MODEL_CATALOG.items()}


def find_spec(provider: Provider, model: str) -> ModelSpec | None:
    return MODEL_CATALOG.get(provider, {}).get(model)


def provider_of(model: str) -> Provider | None:
    """The provider of a catalog model ID (IDs are unique across providers)."""
    return next((s.provider for s in CATALOG if s.model == model), None)


class Settings(BaseSettings):
    """App settings. Every field can be overridden with a `NUTRIPILOT_<FIELD>` env var;
    provider keys also accept their usual names (GROQ_API_KEY, OPENAI_API_KEY,
    ANTHROPIC_API_KEY, LLAMA_API_KEY)."""

    model_config = SettingsConfigDict(env_prefix="NUTRIPILOT_", env_file=".env", extra="ignore")

    # LLM (defaults; clients can pick another catalog model per request)
    provider: Provider = "groq"
    model: str | None = None  # empty = the provider's default model
    temperature: float = Field(0.3, ge=0, le=2)  # where supported; Claude uses effort
    claude_effort: Effort = "medium"
    # Per LLM call. Claude thinks before answering, so a seven-day plan can take a while;
    # the SAM template lowers this to fit API Gateway's 30 s limit.
    llm_timeout_s: float = 90.0
    llm_max_retries: int = Field(1, ge=0, le=5)
    groq_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("GROQ_API_KEY", "NUTRIPILOT_GROQ_API_KEY")
    )
    openai_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("OPENAI_API_KEY", "NUTRIPILOT_OPENAI_API_KEY")
    )
    anthropic_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "NUTRIPILOT_ANTHROPIC_API_KEY")
    )
    llama_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("LLAMA_API_KEY", "NUTRIPILOT_LLAMA_API_KEY")
    )

    # Output validation
    max_repairs: int = Field(1, ge=0, le=3)  # extra LLM calls allowed to fix a failed check
    calorie_tolerance: float = Field(0.10, gt=0, le=0.5)  # allowed relative calorie error

    # Serving
    api_token: str | None = Field(
        None, validation_alias=AliasChoices("NUTRIPILOT_API_TOKEN", "API_TOKEN")
    )
    # Fail closed: when true and no token is configured, protected routes return 503.
    auth_required: bool = False
    api_url: str = Field(
        "http://localhost:8000", validation_alias=AliasChoices("NUTRIPILOT_API_URL", "API_URL")
    )

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS[self.provider]

    @property
    def base_url(self) -> str | None:
        return BASE_URLS[self.provider]

    def provider_api_key(self, provider: Provider | None = None) -> str | None:
        key = {
            "groq": self.groq_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "meta": self.llama_api_key,
        }[provider or self.provider]
        return key.get_secret_value() if key else None


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    # On Lambda, secrets come from Secrets Manager instead of plain environment variables.
    secret_arn = os.getenv("NUTRIPILOT_SECRET_ARN")
    if secret_arn:
        from nutripilot.aws_secrets import load_secret_into_env

        load_secret_into_env(secret_arn)
    return Settings()
