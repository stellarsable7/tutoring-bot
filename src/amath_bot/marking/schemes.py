from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, HttpUrl, PositiveInt, model_validator


class MarkingStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    mark_type: Literal["M", "A", "B", "FT"]
    marks: PositiveInt
    expected_latex: str
    guidance: str
    dependencies: tuple[str, ...] = ()


class PublishedScheme(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_url: HttpUrl
    total_marks: PositiveInt
    steps: tuple[MarkingStep, ...]

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        if sum(step.marks for step in self.steps) != self.total_marks:
            raise ValueError("scheme step marks must equal total marks")
        seen: set[str] = set()
        for step in self.steps:
            if step.code in seen:
                raise ValueError(f"duplicate scheme step: {step.code}")
            unknown = set(step.dependencies).difference(seen)
            if unknown:
                raise ValueError(
                    f"step {step.code} depends on unknown or later steps: {sorted(unknown)}"
                )
            seen.add(step.code)
        return self

