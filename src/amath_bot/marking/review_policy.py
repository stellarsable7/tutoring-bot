from enum import StrEnum


class ReviewReason(StrEnum):
    LOW_RECOGNITION = "low_recognition"
    LOW_MARKING_CONFIDENCE = "low_marking_confidence"
    SYMBOLIC_DISAGREEMENT = "symbolic_disagreement"
    INCOMPLETE_SUBMISSION = "incomplete_submission"
    UNSUPPORTED_METHOD = "unsupported_method"


def review_reasons(
    *,
    recognition: float,
    overall: float,
    symbolic_agreement: bool,
    complete: bool,
    alternative_method_without_coverage: bool,
) -> tuple[ReviewReason, ...]:
    reasons: list[ReviewReason] = []
    if recognition < 0.90:
        reasons.append(ReviewReason.LOW_RECOGNITION)
    if overall < 0.85:
        reasons.append(ReviewReason.LOW_MARKING_CONFIDENCE)
    if not symbolic_agreement:
        reasons.append(ReviewReason.SYMBOLIC_DISAGREEMENT)
    if not complete:
        reasons.append(ReviewReason.INCOMPLETE_SUBMISSION)
    if alternative_method_without_coverage:
        reasons.append(ReviewReason.UNSUPPORTED_METHOD)
    return tuple(reasons)
