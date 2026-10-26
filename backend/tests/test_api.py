import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
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


def test_demo_chat_returns_honest_placeholder(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "")
    response = client.post(
        "/api/chat/demo",
        json={"message": "Plan my business"},
        headers={"X-Telegram-Init-Data": make_init_data()},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"
    assert "демонстрационный режим" in response.json()["reply"]


def test_demo_chat_rejects_empty_message(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    response = client.post(
        "/api/chat/demo",
        json={"message": "   "},
        headers={"X-Telegram-Init-Data": make_init_data()},
    )
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


def test_protected_me_rejects_missing_init_data(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    response = client.get("/api/me")
    assert response.status_code == 401


def test_protected_me_accepts_verified_user(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "owner_telegram_ids", "987654")
    response = client.get(
        "/api/me",
        headers={"X-Telegram-Init-Data": make_init_data(123456)},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"


def test_owner_endpoint_rejects_regular_user(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "owner_telegram_ids", "987654")
    response = client.get(
        "/api/owner",
        headers={"X-Telegram-Init-Data": make_init_data(123456)},
    )
    assert response.status_code == 403


def test_owner_endpoint_accepts_configured_owner(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "owner_telegram_ids", "123456,987654")
    response = client.get(
        "/api/owner",
        headers={"X-Telegram-Init-Data": make_init_data(123456)},
    )
    assert response.status_code == 200
    assert response.json()["authorized"] is True
    assert response.json()["user_id"] == 123456


def test_demo_chat_rejects_missing_telegram_auth(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    response = client.post("/api/chat/demo", json={"message": "Plan my business"})
    assert response.status_code == 401


def test_ai_provider_returns_real_reply_and_uses_server_key(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "server-side-test-key")
    monkeypatch.setattr(settings, "ai_model", "test-model")
    main_module._ai_request_times.clear()

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "  Here is a plan.  "}}]}

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(main_module.httpx, "post", fake_post)
    response = client.post(
        "/api/chat/demo",
        json={"message": "Plan my business"},
        headers={"X-Telegram-Init-Data": make_init_data()},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "ai"
    assert response.json()["reply"] == "Here is a plan."
    assert captured["headers"]["Authorization"] == "Bearer server-side-test-key"
    assert captured["json"]["model"] == "test-model"


def test_ai_provider_rate_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "server-side-test-key")
    monkeypatch.setattr(settings, "user_hourly_ai_limit", 1)
    main_module._ai_request_times.clear()

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Answer"}}]}

    monkeypatch.setattr(main_module.httpx, "post", lambda *args, **kwargs: FakeResponse())
    headers = {"X-Telegram-Init-Data": make_init_data(444444)}
    first = client.post("/api/chat/demo", json={"message": "First"}, headers=headers)
    second = client.post("/api/chat/demo", json={"message": "Second"}, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 429


def test_ai_provider_failure_is_reported_without_leaking_details(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "server-side-test-key")
    main_module._ai_request_times.clear()

    class FakeResponse:
        status_code = 500

        def raise_for_status(self):
            raise main_module.httpx.HTTPStatusError(
                "private provider detail",
                request=main_module.httpx.Request("POST", "https://example.test"),
                response=main_module.httpx.Response(500),
            )

    monkeypatch.setattr(main_module.httpx, "post", lambda *args, **kwargs: FakeResponse())
    response = client.post(
        "/api/chat/demo",
        json={"message": "Plan my business"},
        headers={"X-Telegram-Init-Data": make_init_data(555555)},
    )
    assert response.status_code == 502
    assert "private provider detail" not in response.text
