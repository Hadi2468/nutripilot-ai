"""Shared fixtures. Everything runs offline: no API keys, no network, no cost."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nutripilot.api import create_app
from nutripilot.config import Settings
from nutripilot.llm import Completion, Message
from nutripilot.service import NutriPilotService


class FakeLLM:
    """Stands in for the provider. Returns scripted replies in order (the last one repeats)
    and records every message list it receives."""

    provider = "fake"
    model = "fake-model"

    def __init__(self, *replies: Any):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.calls: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> Completion:
        self.calls.append([dict(m) for m in messages])
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        return Completion(content=reply, prompt_tokens=100, completion_tokens=50)


def meal(name: str = "Lunch", calories: float = 500, **overrides: Any) -> dict[str, Any]:
    # 25 g protein, 60 g carbs, 18 g fat -> 502 kcal by Atwater factors
    base = {
        "name": name,
        "dish": "Lentil curry with rice",
        "ingredients": ["red lentils", "basmati rice", "spinach"],
        "calories": calories,
        "protein_g": 25,
        "carbs_g": 60,
        "fat_g": 18,
    }
    return base | overrides


def weekly_plan(meals_per_day: int = 4, kcal_per_meal: float = 500, **meal_overrides) -> dict:
    return {
        "days": [
            {
                "day": d,
                "meals": [
                    meal(f"Meal {i}", kcal_per_meal, **meal_overrides) for i in range(meals_per_day)
                ],
            }
            for d in range(1, 8)
        ],
        "notes": ["Drink water with meals."],
    }


PLAN_REQUEST = {
    "meal_preference": "vegetarian",
    "calories": 2000,
    "meal_count": 4,
    "goal": "Weight loss",
    "age": 45,
    "allergies": "peanuts",
    "dislikes": "mushrooms",
}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    # Importing the app runs load_dotenv(), which may export a developer's real keys and
    # token; tests must behave the same on every machine and in CI.
    for name in (
        "API_TOKEN",
        "ANTHROPIC_API_KEY",
        "API_URL",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "NUTRIPILOT_API_TOKEN",
        "NUTRIPILOT_API_URL",
        "NUTRIPILOT_PROVIDER",
        "NUTRIPILOT_MODEL",
        "NUTRIPILOT_SECRET_ARN",
        "NUTRIPILOT_AUTH_REQUIRED",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: tests must not depend on the developer's local .env
    return Settings(_env_file=None, max_repairs=1, calorie_tolerance=0.10)


@pytest.fixture
def make_client(settings):
    def _make(llm: FakeLLM, **overrides: Any) -> TestClient:
        s = settings.model_copy(update=overrides)
        return TestClient(create_app(service=NutriPilotService(llm, s), settings=s))

    return _make
