import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, NonNegativeInt, PositiveInt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.people.tables import StudentRow
from amath_bot.submissions.tables import AttemptRow

logger = logging.getLogger(__name__)
PROCESSING_LEASE = timedelta(minutes=5)


def retry_delay(failed_attempt: int) -> timedelta:
    if failed_attempt < 1:
        raise ValueError("failed_attempt must be at least 1")
    seconds = {1: 3, 2: 10, 3: 30, 4: 30}.get(failed_attempt, 60)
    return timedelta(seconds=seconds)


class MarkingPipelineError(RuntimeError):
    def __init__(
        self, message: str, *, retry_status: str = "queued", retryable: bool = True
    ) -> None:
        super().__init__(message)
        self.diagnostic = message[:500]
        self.retry_status = retry_status
        self.retryable = retryable


class OCRValidationError(MarkingPipelineError):
    def __init__(self, validation_error: str, raw_response: str) -> None:
        super().__init__(
            f"OCR validation failed: {validation_error}",
            retry_status="ocr_validation_failed",
            retryable=False,
        )
        self.validation_error = validation_error
        self.raw_response = raw_response


class RateLimitError(MarkingPipelineError):
    """A transient provider rate limit eligible for exponential backoff."""


class MarkingValidationError(MarkingPipelineError):
    """A deterministic provider-output validation failure."""

    def __init__(
        self, message: str, *, retry_status: str = "marking_validation_failed"
    ) -> None:
        super().__init__(message, retry_status=retry_status, retryable=False)


class MarkingConfigurationError(MarkingPipelineError):
    """A safe operator-actionable provider configuration failure."""

    def __init__(self, message: str, *, retry_status: str = "configuration_failed") -> None:
        super().__init__(message, retry_status=retry_status, retryable=False)


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
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session = session
        self._pipeline = pipeline
        self._notifier = notifier
        self._media = media
        self._now = now

    async def _claim_next(self, now: datetime) -> AttemptRow | None:
        attempt = await self._session.scalar(
            select(AttemptRow)
            .where(
                AttemptRow.status.in_(("queued", "transcribed", "transcribing", "grading")),
                (AttemptRow.marking_retry_at.is_(None)) | (AttemptRow.marking_retry_at <= now),
            )
            .order_by(AttemptRow.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if attempt is None:
            return None
        attempt.status = (
            "grading" if attempt.status in ("transcribed", "grading") else "transcribing"
        )
        attempt.marking_retry_at = now + PROCESSING_LEASE
        await self._session.commit()
        return attempt

    async def _persist_failure(
        self,
        attempt: AttemptRow,
        error: MarkingPipelineError,
        *,
        retry_at: datetime | None = None,
    ) -> None:
        attempt.status = error.retry_status
        attempt.marking_attempts += 1
        attempt.marking_last_error = error.diagnostic
        if isinstance(error, OCRValidationError):
            attempt.ocr_raw_response = error.raw_response
            attempt.ocr_validation_error = error.validation_error
        if not error.retryable:
            attempt.marking_retry_at = None
        elif retry_at is not None:
            attempt.marking_retry_at = retry_at
        elif isinstance(error, RateLimitError):
            base = min(3 * (2 ** (attempt.marking_attempts - 1)), 300)
            attempt.marking_retry_at = self._now() + timedelta(
                seconds=base + random.uniform(0, base * 0.25)
            )
        else:
            attempt.marking_retry_at = self._now() + retry_delay(attempt.marking_attempts)
        await self._session.commit()

    async def run_pending(self) -> int:
        processed = 0
        while attempt := await self._claim_next(self._now()):
            try:
                outcome = await self._pipeline.mark(attempt.id)
                if outcome.total > outcome.maximum:
                    raise MarkingPipelineError("marking total exceeds maximum")
            except MarkingConfigurationError as error:
                logger.warning(
                    "Marking configuration failure; automatic retry disabled: %s",
                    error.diagnostic,
                )
                await self._persist_failure(attempt, error)
                continue
            except MarkingPipelineError as error:
                await self._persist_failure(attempt, error)
                continue
            now = self._now()
            attempt.result_total = outcome.total
            attempt.result_maximum = outcome.maximum
            attempt.feedback = list(outcome.feedback)
            attempt.grade_decisions = list(outcome.decisions)
            attempt.review_reasons = list(outcome.review_reasons)
            attempt.marking_retry_at = None
            attempt.marking_last_error = None
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
            attempt.media_deleted_at = self._now()
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
            attempt.notified_at = self._now()
            await self._session.commit()
