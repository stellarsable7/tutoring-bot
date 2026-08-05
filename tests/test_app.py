from amath_bot.app import health


def test_health_reports_ok() -> None:
    assert health() == {"status": "ok", "service": "amath-bot"}
