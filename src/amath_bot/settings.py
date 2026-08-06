from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/amath_bot"
    timezone: str = "Asia/Singapore"
    telegram_bot_token: str | None = None
    tutor_telegram_id: int | None = None
    review_callback_secret: str | None = None
    telegram_dry_run: bool = False
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_vision_model: str = "qwen3-vl:4b-instruct"
    marking_interval_seconds: int = 20

    model_config = SettingsConfigDict(
        env_prefix="AMATH_",
        env_file=".env",
        extra="ignore",
    )
