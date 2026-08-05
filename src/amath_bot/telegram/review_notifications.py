from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.people.tables import StudentRow
from amath_bot.reviews.tables import ReviewRow
from amath_bot.submissions.tables import AttemptRow


class TelegramReviewNotifier:
    def __init__(self, session: AsyncSession, bot: Bot) -> None:
        self._session = session
        self._bot = bot

    async def finalized(self, attempt_id: int) -> bool:
        row = (
            await self._session.execute(
                select(AttemptRow, ReviewRow, StudentRow)
                .join(AssignmentRow, AssignmentRow.id == AttemptRow.assignment_id)
                .join(StudentRow, StudentRow.id == AssignmentRow.student_id)
                .join(ReviewRow, ReviewRow.attempt_id == AttemptRow.id)
                .where(AttemptRow.id == attempt_id)
                .order_by(ReviewRow.created_at.desc(), ReviewRow.id.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return False
        attempt, review, student = row
        feedback = "\n".join(review.final_feedback)
        text = f"Mark finalized: {review.final_total}/{attempt.result_maximum}"
        if feedback:
            text += f"\n\n{feedback}"
        return await self._send(attempt, student.telegram_id, text)

    async def resubmission_requested(self, attempt_id: int) -> bool:
        row = (
            await self._session.execute(
                select(AttemptRow, StudentRow)
                .join(AssignmentRow, AssignmentRow.id == AttemptRow.assignment_id)
                .join(StudentRow, StudentRow.id == AssignmentRow.student_id)
                .where(AttemptRow.id == attempt_id)
            )
        ).first()
        if row is None:
            return False
        attempt, student = row
        return await self._send(
            attempt,
            student.telegram_id,
            "Please submit a clearer image of your working.",
        )

    async def _send(self, attempt: AttemptRow, telegram_id: int, text: str) -> bool:
        try:
            await self._bot.send_message(telegram_id, text)
        except (TelegramAPIError, OSError):
            return False
        attempt.notified_at = datetime.now(UTC)
        await self._session.commit()
        return True
