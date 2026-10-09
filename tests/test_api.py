import pytest

from nutripilot.llm import LLMError, LLMRateLimitError
from tests.conftest import PLAN_REQUEST, FakeLLM, meal, weekly_plan

P = "/v1/nutripilot"


class FailingLLM(FakeLLM):
    def __init__(self, exc: Exception):
        super().__init__("{}")
        self.exc = exc

    def complete(self, messages):
        raise self.exc


def test_health_is_open_even_with_auth(make_client):
    with make_client(FakeLLM(), api_token="s3cret") as client:
        for path in ("/", "/health"):
            body = client.get(path).json()
            assert body["status"] == "ok" and body["version"]


def test_plan_returns_checked_structured_plan(make_client):
    with make_client(FakeLLM(weekly_plan())) as client:
        body = client.post(f"{P}/plan", json=PLAN_REQUEST).json()

    assert body["type"] == "weekly_plan"
    assert [d["day"] for d in body["data"]["days"]] == list(range(1, 8))
    assert body["data"]["days"][0]["totals"]["calories"] == 2000  # computed in code
    assert body["meta"] | {"latency_ms": 0} == {
        "provider": "fake",
        "model": "fake-model",
        "prompt_version": "2.0",
        "latency_ms": 0,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "repairs": 0,
    }
    assert "not medical advice" in body["disclaimer"]


def test_regenerate_round_trips_the_plan(make_client):
    with make_client(FakeLLM(weekly_plan())) as client:
        plan = client.post(f"{P}/plan", json=PLAN_REQUEST).json()["data"]
        body = client.post(
            f"{P}/plan/regenerate",
            json={
                "profile": PLAN_REQUEST,
                "existing_plan": plan,
                "modification_request": "No rice",
            },
        ).json()
    assert body["type"] == "modified_plan" and len(body["data"]["days"]) == 7


def test_meal_analysis_substitute_and_tips(make_client):
    llm = FakeLLM(
        meal(),
        {
            "items": [
                {
                    "food": "rice",
                    "quantity": "1 cup",
                    **{k: meal()[k] for k in ("calories", "protein_g", "carbs_g", "fat_g")},
                }
            ]
        },
        {
            "substitutions": [
                {"original": "soda", "alternative": "sparkling water", "why": "No sugar"}
            ]
        },
        {"tips": [{"tip": f"Tip {i}", "why": "Because"} for i in range(5)]},
    )
    with make_client(llm) as client:
        assert client.post(f"{P}/meal", json={"calories": 500}).json()["type"] == "single_meal"
        analysis = client.post(f"{P}/analysis", json={"food_items": "1 cup rice"}).json()
        assert analysis["data"]["totals"]["calories"] == 500
        subs = client.post(f"{P}/substitute", json={"food_items": "soda"}).json()
        assert subs["data"]["substitutions"][0]["alternative"] == "sparkling water"
        tips = client.get(f"{P}/recommendations", params={"goal": "muscle gain"}).json()
        assert len(tips["data"]["tips"]) == 5
    assert "Goal: muscle gain" in llm.calls[-1][1]["content"]


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/plan", PLAN_REQUEST | {"calories": 900}),  # out of bounds
        ("/plan", PLAN_REQUEST | {"calories": 1100}),  # below the adult floor
        ("/plan", PLAN_REQUEST | {"age": 12}),  # weight loss for a child
        ("/plan", PLAN_REQUEST | {"goal": "bulk forever"}),
        ("/plan", {"calories": 2000}),
        ("/meal", {"calories": 50}),
        ("/analysis", {}),
        ("/substitute", {"food_items": ""}),
    ],
)
def test_invalid_requests_return_422(make_client, path, payload):
    with make_client(FakeLLM()) as client:
        assert client.post(f"{P}{path}", json=payload).status_code == 422


def test_output_failing_checks_returns_502_with_problems(make_client):
    with make_client(FakeLLM(weekly_plan(meals_per_day=2))) as client:
        response = client.post(f"{P}/plan", json=PLAN_REQUEST)
    assert response.status_code == 502
    assert any("expected 4" in p for p in response.json()["problems"])


@pytest.mark.parametrize(
    ("exc", "code"),
    [(LLMRateLimitError("slow down"), 429), (LLMError("down"), 503)],
)
def test_llm_errors_are_mapped(make_client, exc, code):
    with make_client(FailingLLM(exc)) as client:
        assert client.get(f"{P}/recommendations").status_code == code


def test_bearer_token_is_enforced_when_configured(make_client):
    tips = {"tips": [{"tip": "t", "why": "w"}] * 5}
    with make_client(FakeLLM(tips), api_token="s3cret") as client:
        assert client.get(f"{P}/recommendations").status_code == 401
        bad = {"Authorization": "Bearer wrong"}
        assert client.get(f"{P}/recommendations", headers=bad).status_code == 401
        good = {"Authorization": "Bearer s3cret"}
        assert client.get(f"{P}/recommendations", headers=good).status_code == 200


def test_auth_required_without_token_fails_closed(make_client):
    with make_client(FakeLLM(), auth_required=True, api_token=None) as client:
        assert client.get(f"{P}/recommendations").status_code == 503


def test_service_is_built_lazily_and_missing_key_is_503(settings):
    from fastapi.testclient import TestClient

    from nutripilot.api import create_app

    app = create_app(settings=settings)  # no service, no GROQ_API_KEY in test settings
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get(f"{P}/recommendations").status_code == 503


def _http_api_event(path: str, stage: str) -> dict:
    return {
        "version": "2.0",
        "routeKey": "ANY /{proxy+}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "abc.execute-api.us-east-1.amazonaws.com"},
        "requestContext": {
            "http": {"method": "GET", "path": path, "protocol": "HTTP/1.1", "sourceIp": "1.2.3.4"},
            "stage": stage,
        },
        "isBase64Encoded": False,
    }


def test_lambda_handler_strips_the_stage(monkeypatch):
    import importlib

    import nutripilot.api as api

    monkeypatch.setenv("NUTRIPILOT_BASE_PATH", "/prod")
    reloaded = importlib.reload(api)
    try:
        response = reloaded.handler(_http_api_event("/prod/health", "prod"), None)
        assert response["statusCode"] == 200 and '"status":"ok"' in response["body"]
    finally:
        monkeypatch.delenv("NUTRIPILOT_BASE_PATH")
        importlib.reload(api)
