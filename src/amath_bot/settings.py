from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/amath_bot"
    timezone: str = "Asia/Singapore"

    model_config = SettingsConfigDict(env_prefix="AMATH_", env_file=".env")
