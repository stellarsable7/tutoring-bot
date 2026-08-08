from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, NonNegativeInt, PositiveInt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.people.tables import StudentRow
from amath_bot.submissions.tables import AttemptRow


class MarkingPipelineError(RuntimeError):
    pass


class MarkingConfigurationError(MarkingPipelineError):
    """A safe operator-actionable provider configuration failure."""


class MarkingOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total: NonNegativeInt
    maximum: PositiveInt
    feedback: tuple[str, ...]
    review_reasons: tuple[str, ...]
    decisions: tuple[dict[str, Any], ...] = ()


class AttemptPipeline(Protocol):
    async def mark(self, attempt_id: int) -> MarkingOutcome: ...


class StudentNotifier(Protocol):
    async def send_message(self, chat_id: int, text: str) -> object: ...


class AttemptMediaLifecycle(Protocol):
    async def delete_attempt_media(self, attempt_id: int) -> None: ...


class MarkAttemptJob:
    def __init__(
        self,
        session: AsyncSession,
        *,
        pipeline: AttemptPipeline,
        notifier: StudentNotifier,
        media: AttemptMediaLifecycle,
    ) -> None:
        self._session = session
        self._pipeline = pipeline
        self._notifier = notifier
        self._media = media

    async def run_pending(self) -> int:
        attempts = tuple(
            await self._session.scalars(
                select(AttemptRow)
                .where(AttemptRow.status == "queued")
                .order_by(AttemptRow.id)
                .with_for_update(skip_locked=True)
            )
        )
        processed = 0
        for attempt in attempts:
            attempt.status = "processing"
            await self._session.commit()
            try:
                outcome = await self._pipeline.mark(attempt.id)
            except MarkingPipelineError:
                attempt.status = "queued"
                await self._session.commit()
                continue
            if outcome.total > outcome.maximum:
                attempt.status = "queued"
                await self._session.commit()
                raise MarkingPipelineError("marking total exceeds maximum")
            now = datetime.now(UTC)
            attempt.result_total = outcome.total
            attempt.result_maximum = outcome.maximum
            attempt.feedback = list(outcome.feedback)
            attempt.grade_decisions = list(outcome.decisions)
            attempt.review_reasons = list(outcome.review_reasons)
            if outcome.review_reasons:
                attempt.status = "flagged"
                attempt.media_expires_at = now + timedelta(hours=24)
            else:
                attempt.status = "marked"
                attempt.finalized_at = now
            await self._session.commit()
            processed += 1

        await self._finalize_media()
        await self._notify_students()
        return processed

    async def _finalize_media(self) -> None:
        attempts = tuple(
            await self._session.scalars(
                select(AttemptRow).where(
                    AttemptRow.status == "marked", AttemptRow.media_deleted_at.is_(None)
                )
            )
        )
        for attempt in attempts:
            await self._media.delete_attempt_media(attempt.id)
            attempt.media_deleted_at = datetime.now(UTC)
            await self._session.commit()

    async def _notify_students(self) -> None:
        rows = await self._session.execute(
            select(AttemptRow, StudentRow)
            .join(AssignmentRow, AssignmentRow.id == AttemptRow.assignment_id)
            .join(StudentRow, StudentRow.id == AssignmentRow.student_id)
            .where(AttemptRow.status == "marked", AttemptRow.notified_at.is_(None))
            .order_by(AttemptRow.id)
        )
        for attempt, student in rows:
            feedback = "\n".join(attempt.feedback or [])
            text = f"Mark finalized: {attempt.result_total}/{attempt.result_maximum}\n\n{feedback}"
            try:
                await self._notifier.send_message(student.telegram_id, text)
            except OSError:
                continue
            attempt.notified_at = datetime.now(UTC)
            await self._session.commit()
