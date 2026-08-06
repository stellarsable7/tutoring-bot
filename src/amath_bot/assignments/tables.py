from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from amath_bot.db import Base


class ScheduleRow(Base):
    __tablename__ = "schedules"

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), primary_key=True)
    weekdays: Mapped[list[int]] = mapped_column(JSON)
    hour: Mapped[int] = mapped_column(Integer)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    count: Mapped[int] = mapped_column(Integer, default=1)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Singapore")


class AssignmentRow(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "scheduled_date",
            "sequence_number",
            name="uq_assignment_daily_sequence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    source_question_id: Mapped[int] = mapped_column(ForeignKey("source_questions.id"))
    scheduled_date: Mapped[date] = mapped_column(Date)
    sequence_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    delivery_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    selection_reason: Mapped[str] = mapped_column(String(500))
