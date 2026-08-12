from sqlalchemy import CheckConstraint

from amath_bot.submissions.tables import AttemptRow


def test_marking_retry_columns_match_persistence_contract() -> None:
    table = AttemptRow.__table__

    attempts = table.c.marking_attempts
    assert attempts.nullable is False
    assert attempts.default is not None
    assert attempts.default.arg == 0
    assert attempts.server_default is not None
    assert str(attempts.server_default.arg) == "0"

    retry_at = table.c.marking_retry_at
    assert retry_at.nullable is True
    assert retry_at.type.timezone is True
    assert {
        index.name
        for index in table.indexes
        if index.columns.contains_column(retry_at)
    } == {
        "ix_submission_attempts_marking_retry_at"
    }

    last_error = table.c.marking_last_error
    assert last_error.nullable is True
    assert last_error.type.length == 500


def test_marking_attempts_has_named_nonnegative_constraint() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in AttemptRow.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert constraints["ck_submission_attempts_marking_attempts_nonnegative"] == (
        "marking_attempts >= 0"
    )


def test_ocr_stage_columns_are_persisted() -> None:
    table = AttemptRow.__table__

    assert table.c.ocr_transcription.nullable is True
    assert table.c.ocr_unclear.nullable is True
    assert table.c.ocr_confidence.nullable is True
    assert table.c.ocr_complete.nullable is True
