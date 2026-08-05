from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from amath_bot.db import Base


class SourceQuestionRow(Base):
    __tablename__ = "source_questions"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "school",
            "year",
            "paper",
            "question_number",
            name="uq_source_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    solution_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    provider: Mapped[str] = mapped_column(String(120))
    school: Mapped[str] = mapped_column(String(240))
    year: Mapped[int] = mapped_column(Integer)
    paper: Mapped[str] = mapped_column(String(40))
    question_number: Mapped[str] = mapped_column(String(40))
    syllabus_version: Mapped[str] = mapped_column(String(40), index=True)
    objective_codes: Mapped[list[str]] = mapped_column(JSON)
    marks: Mapped[int] = mapped_column(Integer)
    solution_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    marking_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tutor_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
