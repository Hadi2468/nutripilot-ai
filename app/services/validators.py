import json

from pydantic import ValidationError

from app.models.schemas import NutritionAnalysis


def validate_weekly_plan_output(text: str) -> bool:
    """
    Validate that the LLM output looks like a seven-day meal plan.
    """

    if not text or not text.strip():
        return False

    required_days = [
        "Day 1",
        "Day 2",
        "Day 3",
        "Day 4",
        "Day 5",
        "Day 6",
        "Day 7",
    ]

    return all(day in text for day in required_days)


def validate_nutrition_analysis_output(text: str) -> bool:
    """
    Validate that the nutrition analysis contains key nutrient information.
    """

    if not text or not text.strip():
        return False

    normalized_text = text.lower()

    required_terms = [
        "calories",
        "protein",
        "carbohydrates",
        "fat",
    ]

    return all(term in normalized_text for term in required_terms)


def parse_nutrition_analysis_output(text: str) -> NutritionAnalysis | None:
    """
    Parse and validate structured nutrition analysis output from the LLM.
    """

    if not text or not text.strip():
        return None

    try:
        data = json.loads(text)
        return NutritionAnalysis.model_validate(data)

    except (json.JSONDecodeError, ValidationError, TypeError):
        return None