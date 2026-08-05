from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from amath_bot.db import Base


class TutorRow(Base):
    __tablename__ = "tutors"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudentRow(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    tutor_telegram_id: Mapped[int] = mapped_column(ForeignKey("tutors.telegram_id"), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    syllabus_version: Mapped[str] = mapped_column(String(40), default="4049-2026")
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InviteRow(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(String(120), primary_key=True)
    tutor_telegram_id: Mapped[int] = mapped_column(ForeignKey("tutors.telegram_id"), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

