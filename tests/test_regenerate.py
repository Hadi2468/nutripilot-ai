from unittest.mock import patch


@patch("app.routers.regenerate.call_llm")
def test_regenerate_plan(mock_call_llm, client):
    mock_call_llm.return_value = (
        "Updated vegetarian diet plan."
    )

    payload = {
        "existing_plan": (
            "Breakfast: eggs. Lunch: chicken and rice."
        ),
        "modification_request": (
            "Replace animal protein with vegetarian protein."
        ),
    }

    response = client.post(
        "/v1/nutripilot/plan/regenerate",
        json=payload,
    )

    assert response.status_code == 200

    assert response.json() == {
        "type": "modified_plan",
        "data": "Updated vegetarian diet plan.",
    }

    mock_call_llm.assert_called_once()

    call_args = mock_call_llm.call_args.kwargs

    assert call_args["system_prompt"] == (
        "You are a dietitian who adjusts meal plans "
        "based on user needs."
    )

    assert (
        "Breakfast: eggs. Lunch: chicken and rice."
        in call_args["user_prompt"]
    )

    assert (
        "Replace animal protein with vegetarian protein."
        in call_args["user_prompt"]
    )


def test_regenerate_plan_invalid_payload(client):
    payload = {
        "existing_plan": "Breakfast: eggs.",
    }

    response = client.post(
        "/v1/nutripilot/plan/regenerate",
        json=payload,
    )

    assert response.status_code == 422