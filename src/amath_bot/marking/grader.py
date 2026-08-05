from collections.abc import Mapping
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amath_bot.marking.schemes import PublishedScheme
from amath_bot.marking.transcription import Transcription
from amath_bot.providers.reasoning import ReasoningMarker

ConfidenceValue = Annotated[float, Field(ge=0, le=1)]


class InvalidGrade(ValueError):
    pass


class MarkDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme_step_code: str
    awarded: bool
    marks_awarded: int = Field(ge=0)
    student_line_indexes: tuple[int, ...]
    reason: str
    provider_confidence: ConfidenceValue


class _ProviderGrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total: int = Field(ge=0)
    decisions: tuple[MarkDecision, ...]


class GradeConfidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    recognition: ConfidenceValue
    scheme_match: ConfidenceValue
    symbolic_agreement: ConfidenceValue
    provider: ConfidenceValue
    overall: ConfidenceValue


class GradeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    decisions: tuple[MarkDecision, ...]
    confidence: GradeConfidence


class Grader:
    def __init__(self, marker: ReasoningMarker) -> None:
        self._marker = marker

    async def grade(
        self,
        transcription: Transcription,
        scheme: PublishedScheme,
        *,
        symbolic_checks: Mapping[str, bool],
    ) -> GradeResult:
        raw = await self._marker.mark(transcription, scheme, symbolic_checks)
        try:
            proposed = _ProviderGrade.model_validate(raw)
        except ValidationError as error:
            raise InvalidGrade("provider returned an invalid grade schema") from error

        steps = {step.code: step for step in scheme.steps}
        decision_codes = [decision.scheme_step_code for decision in proposed.decisions]
        if len(decision_codes) != len(set(decision_codes)):
            raise InvalidGrade("provider returned duplicate scheme decisions")
        if set(decision_codes) != set(steps):
            raise InvalidGrade("every decision must refer to exactly one published scheme step")

        valid_lines = {
            line.index
            for page in transcription.pages
            for line in page.lines
            if not line.crossed_out
        }
        decisions_by_code = {
            decision.scheme_step_code: decision for decision in proposed.decisions
        }
        canonical_decisions = tuple(decisions_by_code[step.code] for step in scheme.steps)
        awarded_codes: set[str] = set()
        for decision in canonical_decisions:
            step = steps[decision.scheme_step_code]
            if decision.marks_awarded > step.marks:
                raise InvalidGrade(f"marks exceed published step {step.code}")
            if decision.awarded:
                if decision.marks_awarded < 1 or not decision.student_line_indexes:
                    raise InvalidGrade("awarded marks require marks and student-line evidence")
                if not set(decision.student_line_indexes).issubset(valid_lines):
                    raise InvalidGrade("decision cites an unknown or crossed-out student line")
                if step.mark_type != "FT" and not set(step.dependencies).issubset(awarded_codes):
                    raise InvalidGrade("awarded step has unmet published dependencies")
                awarded_codes.add(step.code)
            elif decision.marks_awarded != 0:
                raise InvalidGrade("unawarded steps must award zero marks")

        calculated_total = sum(decision.marks_awarded for decision in canonical_decisions)
        if proposed.total != calculated_total or calculated_total > scheme.total_marks:
            raise InvalidGrade("provider total is inconsistent with the published scheme")

        recognition_values = [
            line.confidence
            for page in transcription.pages
            for line in page.lines
            if not line.crossed_out
        ]
        recognition = min(recognition_values, default=0.0)
        symbolic = (
            sum(1 for agrees in symbolic_checks.values() if agrees) / len(symbolic_checks)
            if symbolic_checks
            else 1.0
        )
        provider = min(
            (decision.provider_confidence for decision in canonical_decisions), default=0.0
        )
        scheme_match = 1.0
        confidence = GradeConfidence(
            recognition=recognition,
            scheme_match=scheme_match,
            symbolic_agreement=symbolic,
            provider=provider,
            overall=min(recognition, scheme_match, symbolic, provider),
        )
        return GradeResult(
            total=calculated_total,
            decisions=canonical_decisions,
            confidence=confidence,
        )
