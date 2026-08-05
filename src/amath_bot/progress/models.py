from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class MasteryState(BaseModel):
    model_config = ConfigDict(frozen=True)

    mastery: float = Field(ge=0, le=1)
    remediation_required: bool
    question_mode: str
    review_dates: tuple[date, ...] = ()
    updated: bool = True
