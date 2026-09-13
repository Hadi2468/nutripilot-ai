from unittest.mock import patch


@patch("app.routers.analysis.call_llm")
def test_analyze_food(mock_call_llm, client):
    mock_call_llm.return_value = (
        "Calories: 500, Protein: 35g, Carbs: 45g, Fat: 15g."
    )

    payload = {
        "food_items": "grilled chicken, brown rice, broccoli",
    }

    response = client.post(
        "/v1/nutripilot/analysis",
        json=payload,
    )

    assert response.status_code == 200

    assert response.json() == {
        "type": "analysis",
        "data": "Calories: 500, Protein: 35g, Carbs: 45g, Fat: 15g.",
    }

    mock_call_llm.assert_called_once_with(
        system_prompt=(
            "You are a nutrition expert. "
            "Provide calories, protein, carbohydrates, and fats."
        ),
        user_prompt=(
            "Analyze the nutritional value of: "
            "grilled chicken, brown rice, broccoli"
        ),
    )


def test_analyze_food_invalid_payload(client):
    response = client.post(
        "/v1/nutripilot/analysis",
        json={},
    )

    assert response.status_code == 422