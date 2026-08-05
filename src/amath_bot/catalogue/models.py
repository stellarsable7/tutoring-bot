from enum import StrEnum

from pydantic import BaseModel, ConfigDict, HttpUrl, PositiveInt


class SolutionKind(StrEnum):
    FINAL_ANSWER = "final_answer"
    WORKED_SOLUTION = "worked_solution"
    MARK_SCHEME = "mark_scheme"


class SourceQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_url: HttpUrl
    solution_url: HttpUrl | None
    provider: str
    school: str
    year: PositiveInt
    paper: str
    question_number: str
    syllabus_version: str
    objective_codes: tuple[str, ...]
    marks: PositiveInt
    solution_kind: SolutionKind | None
    tutor_validated: bool = False
