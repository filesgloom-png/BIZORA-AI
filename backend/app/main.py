from fastapi import FastAPI, HTTPException
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
app = FastAPI(title="BIZORA AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.frontend_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bizora-ai-api", "version": "0.1.0"}


@app.get("/api/config")
def public_config():
    return {
        "service": "BIZORA AI",
        "environment": settings.app_env,
        "ai_configured": bool(settings.ai_provider_api_key),
        "telegram_auth_configured": bool(settings.telegram_bot_token),
    }


@app.post("/api/chat/demo")
def demo_chat(request: DemoChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if settings.ai_provider_api_key:
        # Real provider integration will be added in the next milestone.
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
