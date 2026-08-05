from datetime import date

from amath_bot.progress.service import ProgressService


def test_recent_failure_lowers_mastery_and_schedules_near_transfer() -> None:
    state = ProgressService().update(previous=0.70, score_ratio=0.20, confidence=0.95)
    assert state.mastery < 0.70
    assert state.remediation_required is True
    assert state.question_mode == "near_transfer_remediation"


def test_unresolved_attempt_does_not_change_mastery() -> None:
    state = ProgressService().update(
        previous=0.6, score_ratio=0.1, confidence=0.9, resolved=False
    )
    assert state.mastery == 0.6
    assert state.updated is False


def test_success_schedules_spaced_reviews() -> None:
    state = ProgressService().update(
        previous=0.8,
        score_ratio=1,
        confidence=1,
        attempted_on=date(2026, 8, 5),
    )
    assert state.review_dates == (
        date(2026, 8, 8),
        date(2026, 8, 12),
        date(2026, 8, 26),
    )
