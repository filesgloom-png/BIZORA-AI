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
    database_url: str = "sqlite:///./bizora.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
