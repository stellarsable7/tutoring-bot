from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CandidateQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: int
    objective_codes: tuple[str, ...]
    difficulty_band: int
    overdue_review: bool = False
    near_transfer: bool = False


class Assignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    student_id: int
    source_question_id: int
    scheduled_date: date
    sequence_number: int
    status: str
    delivery_time: datetime | None
    selection_reason: str
