from amath_bot.app import health
from amath_bot.settings import Settings


def test_health_reports_ok() -> None:
    assert health() == {"status": "ok", "service": "amath-bot"}


def test_settings_ignore_compose_only_environment_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=compose-only\nAMATH_TIMEZONE=Asia/Singapore\n")

    settings = Settings(_env_file=env_file)

    assert settings.timezone == "Asia/Singapore"
