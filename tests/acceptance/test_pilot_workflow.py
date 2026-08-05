from amath_bot.cli import main


def test_dry_run_day_exercises_pilot_flow(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(["simulate-day", "--date", "2026-08-05"])
    output = capsys.readouterr().out
    assert result == 0
    assert "assignment_selected=1" in output
    assert "provisional_review_required" in output
    assert "tutor_review=approved media_deleted=true" in output
