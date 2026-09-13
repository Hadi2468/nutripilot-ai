from unittest.mock import patch


@patch("app.routers.meal.call_llm")
def test_suggest_meal(mock_call_llm, client):
    mock_call_llm.return_value = "Grilled chicken with vegetables."

    payload = {
        "meal_preference": "Indian",
        "calories": 600,
        "meal_count": 3,
        "diseases": None,
        "goal": "Weight loss",
        "age": 35,
        "dislikes": None,
        "preferred_foods": None,
    }

    response = client.post(
        "/v1/nutripilot/meal",
        json=payload,
    )

    assert response.status_code == 200

    assert response.json() == {
        "type": "single_meal",
        "data": "Grilled chicken with vegetables.",
    }

    mock_call_llm.assert_called_once_with(
        system_prompt="You are a diet expert.",
        user_prompt=(
            "Suggest one healthy meal for Weight loss "
            "within 600 calories."
        ),
    )


def test_suggest_meal_invalid_payload(client):
    payload = {
        "goal": "Weight loss",
        "calories": 600,
    }

    response = client.post(
        "/v1/nutripilot/meal",
        json=payload,
    )

    assert response.status_code == 422