from app.services.validators import (
    parse_nutrition_analysis_output,
    validate_nutrition_analysis_output,
    validate_weekly_plan_output,
)

def test_weekly_plan_valid():
    output = """
    Day 1: Breakfast, Lunch, Dinner
    Day 2: Breakfast, Lunch, Dinner
    Day 3: Breakfast, Lunch, Dinner
    Day 4: Breakfast, Lunch, Dinner
    Day 5: Breakfast, Lunch, Dinner
    Day 6: Breakfast, Lunch, Dinner
    Day 7: Breakfast, Lunch, Dinner
    """

    assert validate_weekly_plan_output(output) is True


def test_weekly_plan_missing_day():
    output = """
    Day 1: Breakfast, Lunch, Dinner
    Day 2: Breakfast, Lunch, Dinner
    Day 3: Breakfast, Lunch, Dinner
    Day 4: Breakfast, Lunch, Dinner
    Day 5: Breakfast, Lunch, Dinner
    Day 6: Breakfast, Lunch, Dinner
    """

    assert validate_weekly_plan_output(output) is False


def test_weekly_plan_empty_output():
    assert validate_weekly_plan_output("") is False


def test_weekly_plan_whitespace_only():
    assert validate_weekly_plan_output("   ") is False

def test_nutrition_analysis_valid():
    output = """
    Calories: 520 kcal
    Protein: 35 g
    Carbohydrates: 48 g
    Fat: 18 g
    """

    assert validate_nutrition_analysis_output(output) is True


def test_nutrition_analysis_missing_required_term():
    output = """
    Calories: 520 kcal
    Protein: 35 g
    Fat: 18 g
    """

    assert validate_nutrition_analysis_output(output) is False


def test_nutrition_analysis_empty_output():
    assert validate_nutrition_analysis_output("") is False


def test_parse_nutrition_analysis_valid_json():
    output = """
    {
        "calories": 520,
        "protein": 35,
        "carbohydrates": 48,
        "fat": 18
    }
    """

    result = parse_nutrition_analysis_output(output)

    assert result is not None
    assert result.calories == 520
    assert result.protein == 35
    assert result.carbohydrates == 48
    assert result.fat == 18


def test_parse_nutrition_analysis_invalid_json():
    output = """
    calories: 520
    protein: 35
    """

    result = parse_nutrition_analysis_output(output)

    assert result is None


def test_parse_nutrition_analysis_missing_field():
    output = """
    {
        "calories": 520,
        "protein": 35,
        "fat": 18
    }
    """

    result = parse_nutrition_analysis_output(output)

    assert result is None