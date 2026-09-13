import pytest
from fastapi.testclient import TestClient

from app.core.security import verify_token
from app.main import app


def override_verify_token():
    return "test-token"


@pytest.fixture
def client():
    app.dependency_overrides[verify_token] = override_verify_token

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()