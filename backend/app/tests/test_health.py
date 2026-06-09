from fastapi.testclient import TestClient

from app.main import app
from app.services.model_gateway import runtime_config


def test_health_returns_ok():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_model_health_reports_mock_fallbacks(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    client = TestClient(app)

    response = client.get("/api/health/models")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["llm"]["provider"] == "mock"
    assert data["embedding"]["provider"] == "mock"
