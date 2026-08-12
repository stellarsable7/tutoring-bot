import re

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

_PROSE = re.compile(
    r"(?:error|should|transcrib|written|original|similar|unclear|ambiguous|note|guess)",
    re.IGNORECASE,
)


class OCRLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: PositiveInt
    latex: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_math_only(self) -> "OCRLine":
        value = self.latex.strip()
        if "$$" in value or "\\text" in value or "\n" in value or _PROSE.search(value):
            raise ValueError("OCR line contains commentary instead of mathematical LaTeX")
        depth = 0
        for character in value:
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth < 0:
                    raise ValueError("OCR line contains unbalanced LaTeX braces")
        if depth:
            raise ValueError("OCR line contains unbalanced LaTeX braces")
        return self


class OCRUncertainToken(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    line_id: PositiveInt
    token: str = Field(min_length=1)
    alternatives: tuple[str, ...]


class OCRResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lines: tuple[OCRLine, ...]
    uncertain_tokens: tuple[OCRUncertainToken, ...] = ()

    @model_validator(mode="after")
    def consecutive_line_ids(self) -> "OCRResult":
        if [line.id for line in self.lines] != list(range(1, len(self.lines) + 1)):
            raise ValueError("OCR line IDs must be consecutive starting at 1")
        line_ids = {line.id for line in self.lines}
        if any(item.line_id not in line_ids for item in self.uncertain_tokens):
            raise ValueError("uncertain token references an unknown OCR line")
        return self


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
