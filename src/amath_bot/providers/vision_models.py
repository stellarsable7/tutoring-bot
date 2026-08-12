from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class OCRLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: PositiveInt
    latex: str = Field(min_length=1)


class OCRResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lines: tuple[OCRLine, ...]
    uncertain_tokens: tuple[str, ...] = ()


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
    final_answer_correct: bool
    method_valid: bool
    overall_verdict: str = Field(pattern="^(correct|incorrect|partial)$")
    reasoning: str = Field(min_length=1)
    decisions: tuple[ProposedDecision, ...]
    feedback: tuple[str, ...]
    unclear: tuple[str, ...] = ()
