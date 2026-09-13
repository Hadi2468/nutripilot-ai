from unittest.mock import patch


@patch("app.routers.substitute.call_llm")
def test_substitute_food(mock_call_llm, client):
    mock_call_llm.return_value = (
        "Replace white rice with brown rice or quinoa."
    )

    payload = {
        "food_items": "white rice, french fries",
    }

    response = client.post(
        "/v1/nutripilot/substitute",
        json=payload,
    )

    assert response.status_code == 200

    assert response.json() == {
        "type": "substitution",
        "data": "Replace white rice with brown rice or quinoa.",
    }

    mock_call_llm.assert_called_once_with(
        system_prompt=(
            "You are a nutritionist suggesting "
            "healthy food substitutions."
        ),
        user_prompt=(
            "Suggest healthy alternatives for: "
            "white rice, french fries"
        ),
    )


def test_substitute_food_invalid_payload(client):
    response = client.post(
        "/v1/nutripilot/substitute",
        json={},
    )

    assert response.status_code == 422