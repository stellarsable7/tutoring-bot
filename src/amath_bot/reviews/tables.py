from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from amath_bot.db import Base


class ReviewRow(Base):
    __tablename__ = "marking_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("submission_attempts.id"), index=True)
    tutor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tutors.telegram_id"))
    action: Mapped[str] = mapped_column(String(40))
    original_total: Mapped[int] = mapped_column(Integer)
    final_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    final_decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    original_feedback: Mapped[list[str]] = mapped_column(JSON)
    final_feedback: Mapped[list[str]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
