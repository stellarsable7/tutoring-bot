from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/amath_bot"
    timezone: str = "Asia/Singapore"
    telegram_bot_token: str | None = None
    tutor_telegram_id: int | None = None
    review_callback_secret: str | None = None
    telegram_dry_run: bool = False
    openrouter_api_key: str | None = None
    openrouter_url: str = "https://openrouter.ai/api/v1"
    gemini_api_key: str | None = None
    gemini_url: str = "https://generativelanguage.googleapis.com/v1beta"
    document_ai_project_id: str | None = None
    document_ai_location: str = "us"
    document_ai_processor_id: str | None = None
    google_service_account_json: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="AMATH_",
        env_file=".env",
        extra="ignore",
    )
