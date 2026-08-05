from pydantic import BaseModel, ConfigDict


class CandidateQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: int
    objective_codes: tuple[str, ...]
    difficulty_band: int
    overdue_review: bool = False
    near_transfer: bool = False

