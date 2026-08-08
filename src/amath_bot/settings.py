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

    model_config = SettingsConfigDict(
        env_prefix="AMATH_",
        env_file=".env",
        extra="ignore",
    )
