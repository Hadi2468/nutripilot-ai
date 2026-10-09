import pytest

from nutripilot.checks import (
    check_analysis,
    check_meal,
    check_plan,
    check_tips,
    macro_warnings,
    mentions,
)
from nutripilot.schemas import MealRequest, NutritionAnalysis, PlanRequest, Tips, WeeklyPlan
from tests.conftest import PLAN_REQUEST, meal, weekly_plan


@pytest.mark.parametrize(
    ("text", "term", "expected"),
    [
        ("Peanut butter toast", "peanuts", True),
        ("2 boiled eggs", "egg", True),
        ("1 egg omelette", "eggs", True),
        ("Tomato salad", "tomatoes", True),
        ("Mixed nuts", "nut", True),
        ("Peanut butter", "nut", False),  # whole words only
        ("Nutmeg latte", "nut", False),
        ("Grilled shellfish", "fish", False),
    ],
)
def test_mentions(text, term, expected):
    assert mentions(text, term) is expected


def plan_problems(**overrides):
    plan = WeeklyPlan.model_validate(weekly_plan(**overrides))
    return check_plan(plan, PlanRequest(**PLAN_REQUEST), tolerance=0.10)


def test_valid_plan_has_no_problems():
    assert plan_problems() == []


def test_calories_within_tolerance_pass_and_outside_fail():
    assert plan_problems(kcal_per_meal=455) == []  # 1820 kcal = -9%
    problems = plan_problems(kcal_per_meal=440)  # 1760 kcal = -12%
    assert len(problems) == 7 and "Day 1 totals 1760 kcal" in problems[0]


def test_missing_and_duplicate_days():
    data = weekly_plan()
    data["days"][6]["day"] = 1
    plan = WeeklyPlan.model_validate(data)
    problems = check_plan(plan, PlanRequest(**PLAN_REQUEST), 0.1)
    assert "exactly days 1-7" in problems[0]


def test_excluded_food_in_dish_or_ingredients():
    problems = plan_problems(dish="Mushroom risotto")
    assert len(problems) == 28  # 7 days x 4 meals
    assert problems[0] == "Day 1 Meal 0 contains excluded food 'mushrooms'"


def test_meal_checks():
    req = MealRequest(calories=500, allergies="shellfish")
    assert check_meal(meal_model(), req, 0.1) == []
    bad = meal_model(ingredients=["shellfish", "rice"], calories=800)
    problems = check_meal(bad, req, 0.1)
    assert "excluded food 'shellfish'" in problems[0] and "800 kcal" in problems[1]


def meal_model(**overrides):
    from nutripilot.schemas import Meal

    return Meal.model_validate(meal(**overrides))


def test_analysis_zero_calories_with_macros_is_a_problem():
    item = {"food": "x", "quantity": "1", "calories": 0, "protein_g": 10, "carbs_g": 0, "fat_g": 0}
    assert check_analysis(NutritionAnalysis.model_validate({"items": [item]}))


def test_tips_count():
    assert check_tips(Tips(tips=[])) == ["return exactly 5 tips, got 0"]


def test_macro_warnings_ignore_small_and_consistent_rows():
    assert macro_warnings([meal_model()]) == []  # 500 vs 502
    assert macro_warnings([meal_model(calories=30, protein_g=0, carbs_g=0, fat_g=0)]) == []
    assert len(macro_warnings([meal_model(calories=900)])) == 1
