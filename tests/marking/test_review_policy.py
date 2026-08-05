import pytest

from amath_bot.marking.review_policy import ReviewReason, review_reasons


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"recognition": 0.89}, ReviewReason.LOW_RECOGNITION),
        ({"overall": 0.84}, ReviewReason.LOW_MARKING_CONFIDENCE),
        ({"symbolic_agreement": False}, ReviewReason.SYMBOLIC_DISAGREEMENT),
        ({"complete": False}, ReviewReason.INCOMPLETE_SUBMISSION),
        ({"alternative_method_without_coverage": True}, ReviewReason.UNSUPPORTED_METHOD),
    ],
)
def test_mandatory_review_conditions(overrides: dict[str, object], expected: ReviewReason) -> None:
    inputs: dict[str, object] = {
        "recognition": 0.95,
        "overall": 0.9,
        "symbolic_agreement": True,
        "complete": True,
        "alternative_method_without_coverage": False,
    }
    inputs.update(overrides)

    assert expected in review_reasons(**inputs)  # type: ignore[arg-type]


def test_high_confidence_covered_work_needs_no_review() -> None:
    assert review_reasons(
        recognition=0.95,
        overall=0.9,
        symbolic_agreement=True,
        complete=True,
        alternative_method_without_coverage=False,
    ) == ()
