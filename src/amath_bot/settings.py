from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/amath_bot"
    timezone: str = "Asia/Singapore"
    telegram_bot_token: str | None = None
    tutor_telegram_id: int | None = None
    telegram_dry_run: bool = False

    model_config = SettingsConfigDict(env_prefix="AMATH_", env_file=".env")
