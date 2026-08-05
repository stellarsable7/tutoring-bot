from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Invite(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    tutor_telegram_id: int
    used_at: datetime | None = None


class Student(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    telegram_id: int
    display_name: str
    syllabus_version: str
    consented_at: datetime
    paused: bool

