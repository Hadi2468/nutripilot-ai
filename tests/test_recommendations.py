from unittest.mock import patch


@patch("app.routers.recommendations.call_llm")
def test_quick_recommendations(mock_call_llm, client):
    mock_call_llm.return_value = "Eat more vegetables."

    response = client.get(
        "/v1/nutripilot/recommendations"
    )

    assert response.status_code == 200
    assert response.json() == {
        "type": "tips",
        "data": "Eat more vegetables.",
    }

    mock_call_llm.assert_called_once_with(
        system_prompt="You are a health coach.",
        user_prompt="Give 5 quick healthy eating tips.",
    )


@patch("app.routers.recommendations.call_llm")
def test_quick_recommendations_llm_failure(mock_call_llm, client):
    mock_call_llm.side_effect = RuntimeError("LLM unavailable")

    response = client.get(
        "/v1/nutripilot/recommendations"
    )

    assert response.status_code == 500

    assert response.json() == {
        "detail": (
            "Internal server error. "
            "Please try again later."
        )
    }