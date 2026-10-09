"""Application settings, loaded from environment variables and `.env`."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["groq", "openai"]

# Both providers speak the OpenAI Chat Completions protocol, so one client serves both.
BASE_URLS: dict[Provider, str | None] = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": None,  # the SDK default
}
DEFAULT_MODELS: dict[Provider, str] = {
    "groq": "openai/gpt-oss-20b",
    "openai": "gpt-4o-mini",
}


class Settings(BaseSettings):
    """App settings. Every field can be overridden with a `NUTRIPILOT_<FIELD>` env var;
    provider keys also accept their usual names (GROQ_API_KEY, OPENAI_API_KEY)."""

    model_config = SettingsConfigDict(env_prefix="NUTRIPILOT_", env_file=".env", extra="ignore")

    # LLM
    provider: Provider = "groq"
    model: str | None = None  # empty = the provider's default model
    temperature: float = Field(0.3, ge=0, le=2)
    # API Gateway cuts requests off at 30 s, so a single call must finish well before that.
    llm_timeout_s: float = 25.0
    llm_max_retries: int = Field(1, ge=0, le=5)
    groq_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("GROQ_API_KEY", "NUTRIPILOT_GROQ_API_KEY")
    )
    openai_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("OPENAI_API_KEY", "NUTRIPILOT_OPENAI_API_KEY")
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

    def provider_api_key(self) -> str | None:
        key = self.groq_api_key if self.provider == "groq" else self.openai_api_key
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
