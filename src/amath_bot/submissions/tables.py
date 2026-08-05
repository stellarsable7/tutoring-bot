from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from amath_bot.db import Base


class AttemptRow(Base):
    __tablename__ = "submission_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_maximum: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    grade_decisions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    review_reasons: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    media_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    media_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    media_delete_attempts: Mapped[int] = mapped_column(Integer, default=0)
    media_delete_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    media_delete_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttemptMediaRow(Base):
    __tablename__ = "submission_media"
    __table_args__ = (
        UniqueConstraint("attempt_id", "position", name="uq_submission_media_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("submission_attempts.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    telegram_file_id: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120))
    media_kind: Mapped[str] = mapped_column(String(20))
