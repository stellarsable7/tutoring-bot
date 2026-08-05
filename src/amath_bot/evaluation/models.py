from pydantic import BaseModel, ConfigDict, Field


class LabelledCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    consent_provenance: str = Field(min_length=1)
    category: str
    expected_transcription: str
    actual_transcription: str
    tutor_total: int = Field(ge=0)
    predicted_total: int = Field(ge=0)
    expected_flags: frozenset[str] = frozenset()
    predicted_flags: frozenset[str] = frozenset()
    feedback: str = ""
    forbidden_answers: frozenset[str] = frozenset()


class CategoryReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    cases: int
    exact_agreement: float
    transcription_errors: int


class EvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    cases: int
    exact_agreement: float
    within_one_mark: float
    transcription_errors: int
    missed_material_ambiguities: int
    answer_leaks: int
    by_category: dict[str, CategoryReport]

    @property
    def launch_ready(self) -> bool:
        return (
            self.cases > 0
            and self.exact_agreement >= 0.90
            and self.within_one_mark >= 0.95
            and self.missed_material_ambiguities == 0
            and self.answer_leaks == 0
        )
