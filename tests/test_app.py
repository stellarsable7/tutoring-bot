import pytest

from amath_bot import app
from amath_bot.app import health
from amath_bot.settings import Settings


def test_health_reports_ok() -> None:
    assert health() == {"status": "ok", "service": "amath-bot"}


def test_settings_ignore_compose_only_environment_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=compose-only\nAMATH_TIMEZONE=Asia/Singapore\n")

    settings = Settings(_env_file=env_file)

    assert settings.timezone == "Asia/Singapore"


def test_settings_default_to_openrouter_api() -> None:
    settings = Settings(_env_file=None)

    assert settings.openrouter_api_key is None
    assert settings.openrouter_url == "https://openrouter.ai/api/v1"
    assert settings.gemini_api_key is None
    assert settings.gemini_url == "https://generativelanguage.googleapis.com/v1beta"


def test_settings_do_not_expose_removed_ollama_or_interval_fields() -> None:
    settings = Settings(_env_file=None)

    assert not hasattr(settings, "ollama_url")
    assert not hasattr(settings, "ollama_vision_model")
    assert not hasattr(settings, "marking_interval_seconds")


def polling_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "telegram_bot_token": "telegram-token",
        "tutor_telegram_id": 123,
        "review_callback_secret": "callback-secret",
        "openrouter_api_key": "openrouter-key",
        "gemini_api_key": "gemini-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_polling_settings_reject_missing_openrouter_api_key() -> None:
    settings = polling_settings(openrouter_api_key=None)

    with pytest.raises(ValueError, match="AMATH_OPENROUTER_API_KEY"):
        app.validate_polling_settings(settings)


def test_polling_settings_reject_whitespace_openrouter_api_key() -> None:
    settings = polling_settings(openrouter_api_key="   \t")

    with pytest.raises(ValueError, match="AMATH_OPENROUTER_API_KEY"):
        app.validate_polling_settings(settings)


def test_polling_settings_accept_valid_openrouter_api_key() -> None:
    app.validate_polling_settings(polling_settings())


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_polling_settings_reject_missing_gemini_key(api_key: str | None) -> None:
    with pytest.raises(ValueError, match="AMATH_GEMINI_API_KEY"):
        app.validate_polling_settings(polling_settings(gemini_api_key=api_key))


def test_main_dry_run_does_not_require_openrouter_api_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        _env_file=None,
        telegram_dry_run=True,
        openrouter_api_key=None,
    )
    monkeypatch.setattr(app, "Settings", lambda: settings)
    monkeypatch.setattr(
        app,
        "run_polling",
        lambda _settings: pytest.fail("dry-run must not enter polling"),
    )

    assert app.main() == 0
