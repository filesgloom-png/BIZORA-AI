import hashlib
import hmac
import json
import threading
import time
from urllib.parse import parse_qsl

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    telegram_bot_token: str = ""
    owner_telegram_ids: str = ""
    ai_provider_api_key: str = ""
    ai_provider_base_url: str = "https://api.openai.com/v1/chat/completions"
    ai_model: str = "gpt-4o-mini"
    user_hourly_ai_limit: int = 20
    owner_hourly_ai_limit: int = 200
    frontend_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
app = FastAPI(title="BIZORA AI API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.frontend_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


_ai_request_times: dict[int, list[float]] = {}
_ai_request_lock = threading.Lock()


def verify_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """Verify Telegram Mini App initData and return its parsed, trusted fields."""
    if not init_data or not bot_token:
        raise ValueError("Telegram initData and bot token are required")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
    except ValueError as exc:
        raise ValueError("Malformed Telegram initData") from exc

    if len(fields) != len(pairs):
        raise ValueError("Duplicate Telegram initData fields")

    received_hash = fields.pop("hash", None)
    if not received_hash or len(received_hash) != 64:
        raise ValueError("Missing or invalid Telegram hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Invalid Telegram signature")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Missing or invalid Telegram user data") from exc

    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > max_age_seconds:
        raise ValueError("Expired Telegram initData")
    if user_id <= 0:
        raise ValueError("Invalid Telegram user id")

    return {"user": user, "auth_date": auth_date}


def get_current_telegram_user(
    x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
) -> dict:
    """Reusable dependency for endpoints that require a verified Telegram user."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram authentication is not configured")
    try:
        verified = verify_telegram_init_data(x_telegram_init_data, settings.telegram_bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram initData") from exc

    user = verified["user"]
    try:
        owner_ids = {
            int(value.strip())
            for value in settings.owner_telegram_ids.split(",")
            if value.strip()
        }
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Owner configuration is invalid") from exc

    return {
        "id": int(user["id"]),
        "first_name": user.get("first_name", ""),
        "username": user.get("username"),
        "language_code": user.get("language_code"),
        "auth_date": verified["auth_date"],
        "role": "owner" if int(user["id"]) in owner_ids else "user",
    }


def require_owner(user: dict = Depends(get_current_telegram_user)) -> dict:
    """Reusable dependency that restricts an endpoint to configured owner IDs."""
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


def enforce_ai_rate_limit(user: dict) -> None:
    """Basic in-memory hourly guardrail; use shared persistent storage in production."""
    now = time.time()
    limit = settings.owner_hourly_ai_limit if user["role"] == "owner" else settings.user_hourly_ai_limit
    with _ai_request_lock:
        for user_id, timestamps in list(_ai_request_times.items()):
            recent = [stamp for stamp in timestamps if now - stamp < 3600]
            if recent:
                _ai_request_times[user_id] = recent
            else:
                _ai_request_times.pop(user_id, None)
        recent = _ai_request_times.setdefault(user["id"], [])
        if len(recent) >= max(1, limit):
            raise HTTPException(status_code=429, detail="Hourly AI request limit reached. Try again later.")
        recent.append(now)


def request_ai_reply(message: str) -> str:
    """Call an OpenAI-compatible chat-completions endpoint without exposing provider errors."""
    try:
        response = httpx.post(
            settings.ai_provider_base_url,
            headers={
                "Authorization": f"Bearer {settings.ai_provider_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Ты BIZORA AI — практичный бизнес-ассистент. Отвечай на языке пользователя, "
                            "структурированно, конкретно и честно. Если данных не хватает, уточняй."
                        ),
                    },
                    {"role": "user", "content": message},
                ],
                "temperature": 0.7,
                "max_tokens": 700,
            },
            timeout=30.0,
        )
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="AI provider is temporarily busy. Try again later.")
        response.raise_for_status()
        payload = response.json()
        reply = payload["choices"][0]["message"]["content"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Empty AI response")
        return reply.strip()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="AI provider timed out. Please try again.") from exc
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="AI provider request failed. Please try again later.") from exc


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bizora-ai-api", "version": "0.3.0"}


@app.get("/api/config")
def public_config():
    return {
        "service": "BIZORA AI",
        "environment": settings.app_env,
        "ai_configured": bool(settings.ai_provider_api_key),
        "telegram_auth_configured": bool(settings.telegram_bot_token),
    }


@app.post("/api/auth/telegram")
def telegram_auth(user: dict = Depends(get_current_telegram_user)):
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "first_name": user["first_name"],
            "username": user["username"],
            "language_code": user["language_code"],
        },
        "role": user["role"],
        "auth_date": user["auth_date"],
    }


@app.get("/api/me")
def current_user(user: dict = Depends(get_current_telegram_user)):
    return {"authenticated": True, "user": user}


@app.get("/api/owner")
def owner_dashboard(user: dict = Depends(require_owner)):
    return {"authorized": True, "role": "owner", "user_id": user["id"]}


@app.post("/api/chat/demo")
def demo_chat(request: DemoChatRequest, user: dict = Depends(get_current_telegram_user)):
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if not settings.ai_provider_api_key:
        return {
            "mode": "demo",
            "reply": (
                "BIZORA AI принял задачу. Сейчас включён демонстрационный режим — "
                "AI-провайдер ещё не подключён, поэтому я не буду выдавать шаблонный текст "
                "за результат настоящей нейросети. Добавь ключ провайдера в переменные окружения "
                "backend, чтобы включить настоящие ответы AI."
            ),
        }

    enforce_ai_rate_limit(user)
    reply = request_ai_reply(request.message.strip())
    return {"mode": "ai", "reply": reply, "model": settings.ai_model}
