import pytest
from pydantic import ValidationError

from nutripilot.schemas import (
    MealRequest,
    NutritionAnalysis,
    PlanRequest,
    SubstituteRequest,
    WeeklyPlan,
    split_terms,
)
from tests.conftest import PLAN_REQUEST, weekly_plan


def test_goal_is_case_insensitive():
    assert PlanRequest(**PLAN_REQUEST | {"goal": "  Muscle Gain "}).goal == "muscle gain"
    assert MealRequest(calories=400, meal_type="Breakfast").meal_type == "breakfast"


def test_excluded_foods_combine_allergies_and_dislikes():
    req = SubstituteRequest(food_items="chips", allergies="Peanuts; shellfish", dislikes="olives,")
    assert req.excluded_foods == ["peanuts", "shellfish", "olives"]
    assert split_terms(None) == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"age": 15}, "not generated for under-18s"),
        ({"calories": 1100}, "need medical supervision"),
    ],
)
def test_safety_rules(overrides, message):
    with pytest.raises(ValidationError, match=message):
        PlanRequest(**PLAN_REQUEST | overrides)


def test_children_can_get_healthy_eating_plans_below_the_adult_floor():
    req = PlanRequest(**PLAN_REQUEST | {"age": 8, "goal": "healthy eating", "calories": 1400})
    assert req.age == 8


def test_totals_are_computed_not_trusted():
    data = weekly_plan()
    data["days"][0]["totals"] = {"calories": 99999, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    plan = WeeklyPlan.model_validate(data)
    assert plan.days[0].totals.calories == 2000
    assert plan.model_dump()["days"][0]["totals"]["protein_g"] == 100


def test_analysis_requires_items():
    with pytest.raises(ValidationError):
        NutritionAnalysis(items=[])
