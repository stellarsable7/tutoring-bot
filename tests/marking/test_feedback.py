import pytest

from amath_bot.marking.feedback import UnsafeFeedback, render_feedback, validate_feedback
from amath_bot.marking.grader import MarkDecision


def test_feedback_rejects_answer_or_corrected_work() -> None:
    with pytest.raises(UnsafeFeedback):
        validate_feedback(
            "The correct answer is x = 2; replace line 3 with x = 2.",
            forbidden={"x = 2"},
        )


def test_feedback_renders_only_line_evidence_and_marks() -> None:
    decision = MarkDecision(
        scheme_step_code="M1",
        awarded=True,
        marks_awarded=1,
        student_line_indexes=(2,),
        reason="A valid factorisation method is shown.",
        provider_confidence=0.95,
    )

    text = render_feedback((decision,), marks_available={"M1": 1}, forbidden={"x=2"})

    assert text == "Line 2: A valid factorisation method is shown.; 1/1."
    assert "x=2" not in text
