import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    telegram_bot_token: str = ""
    owner_telegram_ids: str = ""
    ai_provider_api_key: str = ""
    frontend_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
app = FastAPI(title="BIZORA AI API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.frontend_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


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


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bizora-ai-api", "version": "0.2.0"}


@app.get("/api/config")
def public_config():
    return {
        "service": "BIZORA AI",
        "environment": settings.app_env,
        "ai_configured": bool(settings.ai_provider_api_key),
        "telegram_auth_configured": bool(settings.telegram_bot_token),
    }


@app.post("/api/auth/telegram")
def telegram_auth(x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data")):
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
    except ValueError:
        raise HTTPException(status_code=500, detail="Owner configuration is invalid")

    return {
        "authenticated": True,
        "user": {
            "id": int(user["id"]),
            "first_name": user.get("first_name", ""),
            "username": user.get("username"),
            "language_code": user.get("language_code"),
        },
        "role": "owner" if int(user["id"]) in owner_ids else "user",
        "auth_date": verified["auth_date"],
    }


@app.post("/api/chat/demo")
def demo_chat(request: DemoChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if settings.ai_provider_api_key:
        raise HTTPException(status_code=501, detail="AI provider integration is not implemented yet")
    return {
        "mode": "demo",
        "reply": (
            "BIZORA AI принял задачу. Сейчас включён демонстрационный режим — "
            "AI-провайдер ещё не подключён, поэтому я не буду выдавать шаблонный текст "
            "за результат настоящей нейросети. Следующий этап — подключение модели, "
            "лимитов и сохранения истории."
        ),
    }
