from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from amath_bot.db import Base


class AttemptRow(Base):
    __tablename__ = "submission_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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

