import re
from collections.abc import Mapping
from collections.abc import Set as AbstractSet

from amath_bot.marking.grader import MarkDecision


class UnsafeFeedback(ValueError):
    pass


_CORRECTION_PHRASES = (
    "correct answer",
    "the answer is",
    "should be",
    "replace line",
    "instead write",
    "model solution",
)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def validate_feedback(text: str, *, forbidden: AbstractSet[str]) -> str:
    lowered = text.casefold()
    if any(phrase in lowered for phrase in _CORRECTION_PHRASES):
        raise UnsafeFeedback("feedback contains corrected working or an answer phrase")
    normalised = _normalise(text)
    for answer in forbidden:
        candidate = _normalise(answer)
        if candidate and candidate in normalised:
            raise UnsafeFeedback("feedback contains a published expected expression")
    return text


def render_feedback(
    decisions: tuple[MarkDecision, ...],
    *,
    marks_available: Mapping[str, int],
    forbidden: AbstractSet[str],
) -> str:
    lines: list[str] = []
    for decision in decisions:
        available = marks_available.get(decision.scheme_step_code)
        if available is None:
            raise UnsafeFeedback("feedback decision is not in the published scheme")
        evidence = ", ".join(str(index) for index in decision.student_line_indexes)
        label = f"Line {evidence}" if len(decision.student_line_indexes) == 1 else f"Lines {evidence}"
        lines.append(f"{label}: {decision.reason}; {decision.marks_awarded}/{available}.")
    return validate_feedback("\n".join(lines), forbidden=forbidden)
