from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Review(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    attempt_id: int
    tutor_id: int
    action: str
    original_total: int
    final_total: int | None
    original_decisions: tuple[dict[str, Any], ...]
    final_decisions: tuple[dict[str, Any], ...]
    original_feedback: tuple[str, ...]
    final_feedback: tuple[str, ...]
    reason: str
    created_at: datetime

