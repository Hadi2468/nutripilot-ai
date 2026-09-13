from unittest.mock import patch

@patch("app.routers.plan.call_llm")
def test_generate_diet_plan(mock_call_llm, client):

    valid_plan = """
    Day 1: Breakfast, Lunch, Dinner
    Day 2: Breakfast, Lunch, Dinner
    Day 3: Breakfast, Lunch, Dinner
    Day 4: Breakfast, Lunch, Dinner
    Day 5: Breakfast, Lunch, Dinner
    Day 6: Breakfast, Lunch, Dinner
    Day 7: Breakfast, Lunch, Dinner
    """

    mock_call_llm.return_value = valid_plan

    payload = {
        "meal_preference": "Indian",
        "calories": 2000,
        "meal_count": 3,
        "diseases": None,
        "goal": "Weight loss",
        "age": 35,
        "dislikes": "Mushrooms",
        "preferred_foods": "Chicken, rice",
    }

    response = client.post(
        "/v1/nutripilot/plan",
        json=payload,
    )

    assert response.status_code == 200

    assert response.json() == {
        "type": "weekly_plan",
        "data": valid_plan,
    }

    mock_call_llm.assert_called_once()

    call_args = mock_call_llm.call_args.kwargs

    assert call_args["system_prompt"] == (
        "You are an expert Indian dietitian. "
        "Create practical homemade meal plans."
    )

    assert "Meal preference: Indian" in call_args["user_prompt"]
    assert "Daily calories: 2000" in call_args["user_prompt"]
    assert "Meals per day: 3" in call_args["user_prompt"]
    assert "Goal: Weight loss" in call_args["user_prompt"]
    assert "Age: 35" in call_args["user_prompt"]
    assert "Dislikes: Mushrooms" in call_args["user_prompt"]
    assert "Preferred foods: Chicken, rice" in call_args["user_prompt"]


def test_generate_diet_plan_invalid_payload(client):
    payload = {
        "meal_preference": "Indian",
        "calories": 2000,
    }

    response = client.post(
        "/v1/nutripilot/plan",
        json=payload,
    )

    assert response.status_code == 422


@patch("app.routers.plan.call_llm")
def test_generate_diet_plan_invalid_llm_output(mock_call_llm, client):
    mock_call_llm.return_value = """
Day 1: Breakfast, Lunch, Dinner
Day 2: Breakfast, Lunch, Dinner
Day 3: Breakfast, Lunch, Dinner
"""

    payload = {
        "meal_preference": "Indian",
        "calories": 2000,
        "meal_count": 3,
        "diseases": None,
        "goal": "Weight loss",
        "age": 35,
        "dislikes": None,
        "preferred_foods": None,
    }

    response = client.post(
        "/v1/nutripilot/plan",
        json=payload,
    )

    assert response.status_code == 502

    assert response.json() == {
        "detail": "The AI generated an invalid weekly plan."
    }