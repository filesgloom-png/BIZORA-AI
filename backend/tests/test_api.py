import hashlib
import hmac
import json
import time
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app, settings, verify_telegram_init_data
from app.database import ConversationRecord, MessageRecord, ProjectRecord, SessionLocal, UsageEvent, UserRecord, WorkspaceRecord, initialize_database

client = TestClient(app)
initialize_database()
TEST_TOKEN = "test-bot-token"


@pytest.fixture(autouse=True)
def clear_test_database():
    initialize_database()
    with SessionLocal() as db:
        db.query(UsageEvent).delete()
        db.query(MessageRecord).delete()
        db.query(ConversationRecord).delete()
        db.query(ProjectRecord).delete()
        db.query(WorkspaceRecord).delete()
        db.query(MessageRecord).delete()
        db.query(ConversationRecord).delete()
        db.query(ProjectRecord).delete()
        db.query(WorkspaceRecord).delete()
        db.query(UserRecord).delete()
        db.commit()


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


def test_chat_persists_conversation_and_messages(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "")
    headers = {"X-Telegram-Init-Data": make_init_data(616161)}
    first = client.post("/api/chat/demo", json={"message": "First task"}, headers=headers)
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    second = client.post("/api/chat/demo", json={"message": "Follow-up task", "conversation_id": conversation_id}, headers=headers)
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id
    listing = client.get("/api/conversations", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()["conversations"]) == 1
    history = client.get(f"/api/conversations/{conversation_id}/messages", headers=headers)
    assert history.status_code == 200
    assert [item["role"] for item in history.json()["messages"]] == ["user", "assistant", "user", "assistant"]


def test_user_cannot_read_another_users_conversation(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "")
    owner_headers = {"X-Telegram-Init-Data": make_init_data(717171)}
    other_headers = {"X-Telegram-Init-Data": make_init_data(818181)}
    created = client.post("/api/chat/demo", json={"message": "Private conversation"}, headers=owner_headers)
    conversation_id = created.json()["conversation_id"]
    response = client.get(f"/api/conversations/{conversation_id}/messages", headers=other_headers)
    assert response.status_code == 404


def test_ai_provider_receives_persisted_conversation_context(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "server-side-test-key")
    captured = {}

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"choices": [{"message": {"content": "Follow-up answer"}}]}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(main_module.httpx, "post", fake_post)
    headers = {"X-Telegram-Init-Data": make_init_data(929292)}
    first = client.post("/api/chat/demo", json={"message": "My product is coffee"}, headers=headers)
    conversation_id = first.json()["conversation_id"]
    second = client.post("/api/chat/demo", json={"message": "Write a slogan for it", "conversation_id": conversation_id}, headers=headers)
    assert second.status_code == 200
    sent = captured["json"]["messages"]
    assert sent[0]["role"] == "system"
    assert any(item["role"] == "user" and item["content"] == "My product is coffee" for item in sent)
    assert sent[-1] == {"role": "user", "content": "Write a slogan for it"}


def test_database_supports_large_telegram_ids(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "")
    telegram_id = 4_500_000_000
    headers = {"X-Telegram-Init-Data": make_init_data(telegram_id)}
    response = client.post("/api/chat/demo", json={"message": "Large ID test"}, headers=headers)
    assert response.status_code == 200
    listing = client.get("/api/conversations", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["conversations"][0]["id"] == response.json()["conversation_id"]



@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL concurrency integration test runs in CI's PostgreSQL service",
)
def test_postgres_quota_lock_serializes_concurrent_requests(monkeypatch):
    from fastapi import HTTPException
    from app.database import check_and_record_usage

    user_id = 3_838_383
    user = {"id": user_id, "first_name": "Quota test", "role": "user"}
    with SessionLocal() as setup:
        existing = setup.get(UserRecord, user_id)
        if existing is None:
            setup.add(UserRecord(telegram_id=user_id, first_name="Quota test", role="user"))
            setup.commit()

    first = SessionLocal()
    second_started = threading.Event()

    try:
        check_and_record_usage(first, user, 1)
        second_done = threading.Event()

        def second_request():
            second_started.set()
            try:
                with SessionLocal() as second:
                    check_and_record_usage(second, user, 1)
                    second.commit()
                    return "allowed"
            except HTTPException as exc:
                return exc.status_code
            finally:
                second_done.set()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(second_request)
            assert second_started.wait(timeout=2)
            # The second transaction must wait on the same user's row lock.
            assert not second_done.wait(timeout=0.25)
            first.commit()
            assert future.result(timeout=5) == 429
    finally:
        first.rollback()
        first.close()
        with SessionLocal() as cleanup:
            cleanup.query(UsageEvent).filter(UsageEvent.telegram_id == user_id).delete()
            cleanup.query(UserRecord).filter(UserRecord.telegram_id == user_id).delete()
            cleanup.commit()



def test_workspace_and_project_crud_is_persisted_and_owner_scoped(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    owner_headers = {"X-Telegram-Init-Data": make_init_data(232323)}
    other_headers = {"X-Telegram-Init-Data": make_init_data(343434)}

    created = client.post(
        "/api/workspaces",
        json={"name": "  Coffee launch  ", "description": "Go-to-market plan"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    workspace = created.json()["workspace"]
    assert workspace["name"] == "Coffee launch"

    workspace_list = client.get("/api/workspaces", headers=owner_headers)
    assert workspace_list.status_code == 200
    assert workspace_list.json()["workspaces"][0]["id"] == workspace["id"]

    project_response = client.post(
        f"/api/workspaces/{workspace['id']}/projects",
        json={"title": "  Brand campaign ", "description": "First launch"},
        headers=owner_headers,
    )
    assert project_response.status_code == 201
    project = project_response.json()["project"]
    assert project["title"] == "Brand campaign"
    assert project["workspace_id"] == workspace["id"]

    listed = client.get(f"/api/workspaces/{workspace['id']}/projects", headers=owner_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["projects"]] == [project["id"]]
    assert client.get("/api/projects", headers=owner_headers).json()["projects"][0]["id"] == project["id"]

    assert client.get("/api/workspaces", headers=other_headers).json()["workspaces"] == []
    forbidden = client.get(f"/api/workspaces/{workspace['id']}/projects", headers=other_headers)
    assert forbidden.status_code == 404
    cannot_create = client.post(
        f"/api/workspaces/{workspace['id']}/projects",
        json={"title": "Should not leak"},
        headers=other_headers,
    )
    assert cannot_create.status_code == 404


def test_project_chat_context_is_persisted_and_owner_scoped(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "ai_provider_api_key", "")
    owner_headers = {"X-Telegram-Init-Data": make_init_data(454545)}
    other_headers = {"X-Telegram-Init-Data": make_init_data(565656)}

    workspace_response = client.post(
        "/api/workspaces", json={"name": "Product"}, headers=owner_headers
    )
    workspace_id = workspace_response.json()["workspace"]["id"]
    project_response = client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"title": "Launch plan"}, headers=owner_headers,
    )
    project_id = project_response.json()["project"]["id"]

    chat = client.post(
        "/api/chat/demo",
        json={"message": "Keep this launch context", "project_id": project_id},
        headers=owner_headers,
    )
    assert chat.status_code == 200
    conversation_id = chat.json()["conversation_id"]
    assert chat.json()["project_id"] == project_id

    project_conversations = client.get(
        f"/api/projects/{project_id}/conversations", headers=owner_headers
    )
    assert project_conversations.status_code == 200
    assert [item["id"] for item in project_conversations.json()["conversations"]] == [conversation_id]
    assert project_conversations.json()["conversations"][0]["project_id"] == project_id

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=owner_headers
    )
    assert messages.status_code == 200
    assert messages.json()["messages"][0]["content"] == "Keep this launch context"

    # A different account cannot list or attach conversations to this project.
    assert client.get(
        f"/api/projects/{project_id}/conversations", headers=other_headers
    ).status_code == 404
    assert client.post(
        "/api/chat/demo",
        json={"message": "Attempt to use someone else's project", "project_id": project_id},
        headers=other_headers,
    ).status_code == 404

    # A conversation cannot be reused under a different project context.
    second_project = client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"title": "Separate launch"}, headers=owner_headers,
    ).json()["project"]
    mismatch = client.post(
        "/api/chat/demo",
        json={"message": "Mix contexts", "conversation_id": conversation_id, "project_id": second_project["id"]},
        headers=owner_headers,
    )
    assert mismatch.status_code == 404

    # Unscoped history remains separate from project-specific history.
    global_chat = client.post(
        "/api/chat/demo", json={"message": "General question"}, headers=owner_headers
    )
    assert global_chat.status_code == 200
    assert global_chat.json()["project_id"] is None
    assert [item["id"] for item in client.get(
        f"/api/projects/{project_id}/conversations", headers=owner_headers
    ).json()["conversations"]] == [conversation_id]
