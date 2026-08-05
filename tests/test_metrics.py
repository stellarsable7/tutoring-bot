import pytest

from amath_bot.metrics import MetricRegistry


def test_metrics_never_include_identity_or_transcription() -> None:
    registry = MetricRegistry()
    registry.increment()
    payload = registry.render()
    assert "telegram_id" not in payload
    assert "transcription" not in payload
    assert "submission_media_deletion_failures_total 1" in payload


def test_unapproved_metric_or_negative_value_is_rejected() -> None:
    registry = MetricRegistry()
    with pytest.raises(ValueError):
        registry.increment("student_telegram_id")
    with pytest.raises(ValueError):
        registry.increment(amount=-1)
