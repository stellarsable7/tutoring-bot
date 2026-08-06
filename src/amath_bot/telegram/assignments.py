import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.people.tables import StudentRow


class AssignmentDelivery(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: int
    student_telegram_id: int
    student_display_name: str = "Student"
    tutor_telegram_id: int | None = None
    source_url: HttpUrl
    asset_path: str | None = None
    provider: str
    school: str
    year: int
    paper: str
    question_number: str
    marks: int
    scheduled_date: date


@dataclass(frozen=True)
class RenderedAssignment:
    chat_id: int
    text: str


class AssignmentRenderer:
    async def render(self, assignment: AssignmentDelivery) -> RenderedAssignment:
        estimated_minutes = max(1, round(assignment.marks * 1.5))
        text = (
            f"{assignment.scheduled_date.isoformat()} Question(s)\n\n"
            f"Paper {assignment.paper} · Question {assignment.question_number}\n"
            f"{assignment.marks} marks · about {estimated_minutes} minutes\n\n"
            f"{assignment.source_url}"
        )
        return RenderedAssignment(chat_id=assignment.student_telegram_id, text=text)


class TelegramSender(Protocol):
    async def send_message(self, chat_id: int, text: str) -> object: ...

    async def send_document(
        self, chat_id: int, document: FSInputFile, *, caption: str | None = None
    ) -> object: ...


class AssignmentDeliveryService:
    def __init__(
        self,
        session: AsyncSession,
        sender: TelegramSender,
        renderer: AssignmentRenderer | None = None,
    ) -> None:
        self._session = session
        self._sender = sender
        self._renderer = renderer or AssignmentRenderer()

    async def deliver_pending(self) -> int:
        result = await self._session.execute(
            select(AssignmentRow, StudentRow, SourceQuestionRow)
            .join(StudentRow, StudentRow.id == AssignmentRow.student_id)
            .join(SourceQuestionRow, SourceQuestionRow.id == AssignmentRow.source_question_id)
            .where(AssignmentRow.status == "pending")
            .order_by(AssignmentRow.id)
            .with_for_update(skip_locked=True)
        )
        rows = result.all()
        for assignment, _, _ in rows:
            assignment.status = "sending"
        await self._session.commit()

        delivered = 0
        for assignment, student, question in rows:
            payload = AssignmentDelivery(
                assignment_id=assignment.id,
                student_telegram_id=student.telegram_id,
                student_display_name=student.display_name,
                tutor_telegram_id=student.tutor_telegram_id,
                source_url=question.source_url,
                asset_path=question.asset_path,
                provider=question.provider,
                school=question.school,
                year=question.year,
                paper=question.paper,
                question_number=question.question_number,
                marks=question.marks,
                scheduled_date=assignment.scheduled_date,
            )
            rendered = await self._renderer.render(payload)
            try:
                if payload.asset_path:
                    await self._sender.send_document(
                        rendered.chat_id,
                        FSInputFile(
                            payload.asset_path,
                            filename=(
                                f"{payload.scheduled_date.isoformat()} Question(s).pdf"
                            ),
                        ),
                        caption=None,
                    )
                    if payload.tutor_telegram_id is not None:
                        safe_name = re.sub(
                            r"[^\w .'-]+", "_", payload.student_display_name, flags=re.UNICODE
                        ).strip() or "Student"
                        await self._sender.send_document(
                            payload.tutor_telegram_id,
                            FSInputFile(
                                payload.asset_path,
                                filename=(
                                    f"{safe_name}-{payload.scheduled_date.isoformat()}.pdf"
                                ),
                            ),
                            caption=None,
                        )
                else:
                    await self._sender.send_message(rendered.chat_id, rendered.text)
                    if payload.tutor_telegram_id is not None:
                        await self._sender.send_message(
                            payload.tutor_telegram_id,
                            f"{payload.student_display_name}-{payload.scheduled_date.isoformat()}\n"
                            f"{rendered.text}",
                        )
            except (TelegramAPIError, OSError):
                assignment.status = "pending"
                await self._session.commit()
                continue
            assignment.status = "delivered"
            assignment.delivery_time = datetime.now(UTC)
            await self._session.commit()
            delivered += 1
        return delivered
