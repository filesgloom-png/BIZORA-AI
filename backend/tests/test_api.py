from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_public_config_does_not_expose_secrets():
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert "telegram_auth_configured" in payload
    assert "ai_provider_api_key" not in payload
    assert "telegram_bot_token" not in payload


def test_demo_chat_returns_honest_placeholder():
    response = client.post("/api/chat/demo", json={"message": "Plan my business"})
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"
    assert "демонстрационном режиме" in response.json()["reply"]


def test_demo_chat_rejects_empty_message():
    response = client.post("/api/chat/demo", json={"message": "   "})
    assert response.status_code == 422
