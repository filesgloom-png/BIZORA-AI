import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app.main import app, settings, verify_telegram_init_data

client = TestClient(app)
TEST_TOKEN = "test-bot-token"


def make_init_data(user_id: int = 123456, auth_date: int | None = None, token: str = TEST_TOKEN) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {"id": user_id, "first_name": "Test", "username": "test_user"},
            separators=(",", ":"),
        ),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


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
    assert "демонстрационный режим" in response.json()["reply"]


def test_demo_chat_rejects_empty_message():
    response = client.post("/api/chat/demo", json={"message": "   "})
    assert response.status_code == 422


def test_telegram_init_data_valid_signature():
    verified = verify_telegram_init_data(make_init_data(), TEST_TOKEN)
    assert verified["user"]["id"] == 123456


def test_telegram_init_data_rejects_tampering():
    init_data = make_init_data().replace("test_user", "attacker")
    with pytest.raises(ValueError, match="signature"):
        verify_telegram_init_data(init_data, TEST_TOKEN)


def test_telegram_init_data_rejects_expired_data():
    old_data = make_init_data(auth_date=int(time.time()) - 90000)
    with pytest.raises(ValueError, match="Expired"):
        verify_telegram_init_data(old_data, TEST_TOKEN)


def test_telegram_auth_returns_owner_role(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "owner_telegram_ids", "123456,987654")
    response = client.post(
        "/api/auth/telegram",
        headers={"X-Telegram-Init-Data": make_init_data(123456)},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"
    assert response.json()["authenticated"] is True


def test_telegram_auth_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    response = client.post(
        "/api/auth/telegram",
        headers={"X-Telegram-Init-Data": make_init_data().replace("test_user", "attacker")},
    )
    assert response.status_code == 401


def test_telegram_auth_requires_bot_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    response = client.post(
        "/api/auth/telegram",
        headers={"X-Telegram-Init-Data": make_init_data()},
    )
    assert response.status_code == 503
