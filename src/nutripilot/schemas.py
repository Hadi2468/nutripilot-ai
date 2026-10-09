"""Request, LLM-output and response contracts shared by the service, API, CLI and dashboard.

LLM outputs are parsed into these models and then checked in code (see `checks.py`).
Totals are computed fields: the LLM gives per-item numbers, code does the arithmetic.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

Goal = Literal["weight loss", "maintenance", "muscle gain", "weight gain", "healthy eating"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]

ADULT_AGE = 18
# Below this, adult plans need medical supervision; we refuse instead of guessing.
MIN_ADULT_CALORIES = 1200

_TEXT = {"max_length": 300}


def split_terms(text: str | None) -> list[str]:
    """'peanuts, Shellfish;dairy' -> ['peanuts', 'shellfish', 'dairy']"""
    if not text:
        return []
    return [t.strip().lower() for t in text.replace(";", ",").split(",") if t.strip()]


class _Request(BaseModel):
    @field_validator("goal", "meal_type", mode="before", check_fields=False)
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class Restrictions(_Request):
    """Foods that must never appear in the output (checked in code, not just prompted)."""

    allergies: str | None = Field(None, description="Comma-separated, e.g. peanuts, shellfish")
    dislikes: str | None = Field(None, description="Comma-separated, e.g. mushrooms")

    @property
    def excluded_foods(self) -> list[str]:
        return split_terms(self.allergies) + split_terms(self.dislikes)


# ============================================================
# Requests
# ============================================================


class PlanRequest(Restrictions):
    """Profile for a seven-day plan. Bounds reject implausible or unsafe inputs."""

    meal_preference: str = Field(
        "any", min_length=1, max_length=60, description="Diet style or cuisine"
    )
    calories: int = Field(ge=1000, le=5000, description="Daily calorie target (kcal)")
    meal_count: int = Field(3, ge=1, le=6, description="Meals per day, snacks included")
    goal: Goal
    age: int = Field(ge=2, le=120)
    diseases: str | None = Field(None, description="Health conditions to respect", **_TEXT)
    preferred_foods: str | None = Field(None, **_TEXT)

    @model_validator(mode="after")
    def _check_safety(self) -> PlanRequest:
        if self.age < ADULT_AGE and self.goal == "weight loss":
            raise ValueError(
                "weight-loss plans are not generated for under-18s; "
                "choose 'healthy eating' and talk to a paediatrician"
            )
        if self.age >= ADULT_AGE and self.calories < MIN_ADULT_CALORIES:
            raise ValueError(
                f"adult plans below {MIN_ADULT_CALORIES} kcal/day need medical supervision"
            )
        return self


class MealRequest(Restrictions):
    meal_type: MealType = "lunch"
    calories: int = Field(ge=100, le=2000, description="Calorie target for this meal (kcal)")
    goal: Goal = "healthy eating"
    meal_preference: str = Field("any", min_length=1, max_length=60)


class FoodInput(BaseModel):
    food_items: str = Field(min_length=2, max_length=1000, description="Free text, with amounts")


class SubstituteRequest(Restrictions, FoodInput):
    goal: Goal = "healthy eating"


# ============================================================
# LLM outputs
# ============================================================


class Macros(BaseModel):
    calories: float = Field(ge=0, le=5000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=500)


class Meal(Macros):
    name: str = Field(description="Meal slot, e.g. Breakfast, Lunch, Snack")
    dish: str
    ingredients: list[str] = Field(min_length=1)


class DayPlan(BaseModel):
    day: int = Field(ge=1, le=7)
    meals: list[Meal] = Field(min_length=1)

    @computed_field
    @property
    def totals(self) -> Macros:
        return sum_macros(self.meals)


class WeeklyPlan(BaseModel):
    days: list[DayPlan]
    notes: list[str] = Field(default_factory=list, description="At most 3 short practical notes")


class RegenerateRequest(BaseModel):
    """The original profile is resent so the revised plan is held to the same checks."""

    profile: PlanRequest
    existing_plan: WeeklyPlan
    modification_request: str = Field(min_length=3, max_length=500)


class FoodItem(Macros):
    food: str
    quantity: str = Field(description="Amount assumed, e.g. '150 g' or '1 cup'")


class NutritionAnalysis(BaseModel):
    items: list[FoodItem] = Field(min_length=1)

    @computed_field
    @property
    def totals(self) -> Macros:
        return sum_macros(self.items)


class Substitution(BaseModel):
    original: str
    alternative: str
    why: str = Field(description="At most 20 words")


class Substitutions(BaseModel):
    substitutions: list[Substitution] = Field(min_length=1)


class Tip(BaseModel):
    tip: str = Field(description="One practical tip, at most 25 words")
    why: str = Field(description="Why it helps, at most 20 words")


class Tips(BaseModel):
    tips: list[Tip]


def sum_macros(rows: list[Macros]) -> Macros:
    return Macros(
        calories=round(sum(r.calories for r in rows), 1),
        protein_g=round(sum(r.protein_g for r in rows), 1),
        carbs_g=round(sum(r.carbs_g for r in rows), 1),
        fat_g=round(sum(r.fat_g for r in rows), 1),
    )


# ============================================================
# Response envelope
# ============================================================

T = TypeVar("T", bound=BaseModel)


class Meta(BaseModel):
    provider: str
    model: str
    prompt_version: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    repairs: int = 0  # extra LLM calls spent fixing failed checks


class Envelope(BaseModel, Generic[T]):
    type: str
    data: T
    warnings: list[str] = Field(default_factory=list)
    meta: Meta
    disclaimer: str
