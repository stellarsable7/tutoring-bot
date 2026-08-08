from pydantic import BaseModel, ConfigDict, Field


class OCRResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    complete: bool
    lines: tuple[str, ...]
    unclear: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)


class ProposedDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    part: str
    marks_awarded: int = Field(ge=0)
    maximum: int = Field(ge=1)
    scheme_evidence: str = Field(min_length=1)
    reason: str
    student_lines: tuple[str, ...]
    provider_confidence: float = Field(ge=0, le=1)


class ProposedGrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total: int = Field(ge=0)
    decisions: tuple[ProposedDecision, ...]
    feedback: tuple[str, ...]
    unclear: tuple[str, ...] = ()
