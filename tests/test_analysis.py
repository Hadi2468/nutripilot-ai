from unittest.mock import patch


@patch("app.routers.analysis.call_llm")
def test_analyze_food(mock_call_llm, client):
    mock_call_llm.return_value = """
    {
        "calories": 500,
        "protein": 35,
        "carbohydrates": 45,
        "fat": 15
    }
    """

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
        "data": {
            "calories": 500.0,
            "protein": 35.0,
            "carbohydrates": 45.0,
            "fat": 15.0,
        },
    }

    mock_call_llm.assert_called_once_with(
        system_prompt=(
            "You are a nutrition expert. "
            "Provide calories, protein, carbohydrates, and fats."
        ),
        user_prompt=(
            "Analyze the nutritional value of the following foods and "
            "return ONLY valid JSON with these numeric fields: "
            "calories, protein, carbohydrates, fat. "
            "Do not include markdown, explanations, or code fences.\n\n"
            "Food items: grilled chicken, brown rice, broccoli"
        ),
    )


def test_analyze_food_invalid_payload(client):
    response = client.post(
        "/v1/nutripilot/analysis",
        json={},
    )

    assert response.status_code == 422


@patch("app.routers.analysis.call_llm")
def test_analyze_food_invalid_llm_output(mock_call_llm, client):
    mock_call_llm.return_value = (
        "This meal contains approximately 500 calories."
    )

    payload = {
        "food_items": "grilled chicken, brown rice, broccoli",
    }

    response = client.post(
        "/v1/nutripilot/analysis",
        json=payload,
    )

    assert response.status_code == 502

    assert response.json() == {
        "detail": "The AI generated an invalid nutrition analysis."
    }