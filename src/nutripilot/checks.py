"""Deterministic checks on parsed LLM output.

Each `check_*` returns a list of problems. A non-empty list sends the problems back to the
LLM for a repair; if problems remain after the repair budget, the request fails (502)
instead of returning an unsafe or wrong answer. `*_warnings` never block, they are only
reported to the client.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from nutripilot.schemas import (
    FoodItem,
    Macros,
    Meal,
    MealRequest,
    NutritionAnalysis,
    PlanRequest,
    Substitutions,
    Tips,
    WeeklyPlan,
)

TIP_COUNT = 5
# Atwater factors: kcal per gram of protein, carbohydrate and fat.
ATWATER = {"protein_g": 4, "carbs_g": 4, "fat_g": 9}
ATWATER_TOLERANCE = 0.25  # loose: fibre, alcohol and rounding all move the numbers


def _singulars(term: str) -> set[str]:
    forms = {term}
    if term.endswith("es"):
        forms.add(term[:-2])
    if term.endswith("s") and not term.endswith("ss"):
        forms.add(term[:-1])
    return forms


def mentions(text: str, term: str) -> bool:
    """Whole-word and case-insensitive, singular or plural: 'eggs' matches '1 egg' and
    'peanuts' matches 'peanut butter', but 'nut' does not match 'peanut'."""
    return any(
        re.search(rf"\b{re.escape(form)}(?:e?s)?\b", text, re.IGNORECASE)
        for form in _singulars(term)
    )


def _found_excluded(texts: Iterable[str], excluded: list[str]) -> list[str]:
    joined = " | ".join(texts)
    return [term for term in excluded if mentions(joined, term)]


def _calories_problem(label: str, actual: float, target: float, tolerance: float) -> str | None:
    if abs(actual - target) <= tolerance * target:
        return None
    return (
        f"{label} totals {actual:.0f} kcal but the target is {target:.0f} kcal "
        f"(allowed: ±{tolerance:.0%}); adjust portions"
    )


def _meal_texts(meal: Meal) -> list[str]:
    return [meal.dish, *meal.ingredients]


# ============================================================
# Plan and meal
# ============================================================


def check_plan(plan: WeeklyPlan, req: PlanRequest, tolerance: float) -> list[str]:
    problems: list[str] = []
    days = [d.day for d in plan.days]
    if sorted(days) != list(range(1, 8)):
        problems.append(f"the plan must have exactly days 1-7 once each, got {days}")

    for day in plan.days:
        label = f"Day {day.day}"
        if len(day.meals) != req.meal_count:
            problems.append(f"{label} has {len(day.meals)} meals, expected {req.meal_count}")
        if issue := _calories_problem(label, day.totals.calories, req.calories, tolerance):
            problems.append(issue)
        for meal in day.meals:
            for term in _found_excluded(_meal_texts(meal), req.excluded_foods):
                problems.append(f"{label} {meal.name} contains excluded food '{term}'")
    return problems


def check_meal(meal: Meal, req: MealRequest, tolerance: float) -> list[str]:
    problems = [
        f"the meal contains excluded food '{term}'"
        for term in _found_excluded(_meal_texts(meal), req.excluded_foods)
    ]
    if issue := _calories_problem("The meal", meal.calories, req.calories, tolerance):
        problems.append(issue)
    return problems


# ============================================================
# Analysis, substitutions, tips
# ============================================================


def check_analysis(analysis: NutritionAnalysis) -> list[str]:
    return [
        f"'{item.food}' has 0 kcal but non-zero macronutrients"
        for item in analysis.items
        if item.calories == 0 and (item.protein_g + item.carbs_g + item.fat_g) > 1
    ]


def check_substitutions(subs: Substitutions, excluded: list[str]) -> list[str]:
    return [
        f"the alternative '{s.alternative}' contains excluded food '{term}'"
        for s in subs.substitutions
        for term in _found_excluded([s.alternative], excluded)
    ]


def check_tips(tips: Tips) -> list[str]:
    if len(tips.tips) != TIP_COUNT:
        return [f"return exactly {TIP_COUNT} tips, got {len(tips.tips)}"]
    return []


# ============================================================
# Non-blocking warnings
# ============================================================


def atwater_calories(m: Macros) -> float:
    return sum(getattr(m, field) * kcal for field, kcal in ATWATER.items())


def macro_warnings(rows: Iterable[Meal | FoodItem]) -> list[str]:
    """Flag rows whose calories disagree with their macronutrients (LLM arithmetic slips)."""
    warnings = []
    for row in rows:
        expected = atwater_calories(row)
        if row.calories >= 50 and abs(expected - row.calories) > ATWATER_TOLERANCE * row.calories:
            name = row.dish if isinstance(row, Meal) else row.food
            warnings.append(
                f"'{name}': {row.calories:.0f} kcal stated, but its macronutrients add up "
                f"to ~{expected:.0f} kcal"
            )
    return warnings
