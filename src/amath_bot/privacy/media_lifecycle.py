from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.submissions.tables import AttemptRow


class AttemptMediaDeleter(Protocol):
    async def delete_attempt_media(self, attempt_id: int) -> None: ...


class DeletionFailureCounter(Protocol):
    def increment(self) -> None: ...


class MediaLifecycle:
    MAX_RETRY_SECONDS = 3600

    def __init__(
        self,
        session: AsyncSession,
        *,
        deleter: AttemptMediaDeleter,
        failures: DeletionFailureCounter | None = None,
    ) -> None:
        self._session = session
        self._deleter = deleter
        self._failures = failures

    async def expire(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        rows = tuple(
            await self._session.scalars(
                select(AttemptRow)
                .where(
                    AttemptRow.media_deleted_at.is_(None),
                    or_(
                        AttemptRow.status.in_(("marked", "reviewed", "resubmission_requested")),
                        AttemptRow.media_expires_at <= current,
                    ),
                    or_(
                        AttemptRow.media_delete_retry_at.is_(None),
                        AttemptRow.media_delete_retry_at <= current,
                    ),
                )
                .order_by(AttemptRow.id)
                .with_for_update(skip_locked=True)
            )
        )
        deleted = 0
        for attempt in rows:
            if attempt.status == "flagged" and self._is_expired(attempt, current):
                attempt.status = "unresolved"
                attempt.finalized_at = current
            try:
                await self._deleter.delete_attempt_media(attempt.id)
            except OSError as error:
                attempt.media_delete_attempts += 1
                delay = min(2 ** (attempt.media_delete_attempts - 1) * 60, self.MAX_RETRY_SECONDS)
                attempt.media_delete_retry_at = current + timedelta(seconds=delay)
                attempt.media_delete_error = type(error).__name__
                if self._failures is not None:
                    self._failures.increment()
            else:
                attempt.media_deleted_at = current
                attempt.media_delete_retry_at = None
                attempt.media_delete_error = None
                deleted += 1
            await self._session.commit()
        return deleted

    async def get(self, attempt_id: int) -> AttemptRow | None:
        return await self._session.get(AttemptRow, attempt_id)

    @staticmethod
    def _is_expired(attempt: AttemptRow, now: datetime) -> bool:
        expires = attempt.media_expires_at
        if expires is None:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires <= now
