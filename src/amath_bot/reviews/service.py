from collections.abc import Set as AbstractSet
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.marking.feedback import validate_feedback
from amath_bot.reviews.models import Review
from amath_bot.reviews.tables import ReviewRow
from amath_bot.submissions.tables import AttemptRow


class ReviewUnavailable(ValueError):
    pass


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def approve(self, attempt_id: int, *, tutor_id: int, reason: str = "Approved") -> Review:
        attempt = await self._flagged(attempt_id)
        return await self._record(
            attempt,
            tutor_id=tutor_id,
            action="approve",
            final_total=attempt.result_total,
            final_feedback=tuple(attempt.feedback or []),
            final_decisions=tuple(attempt.grade_decisions or []),
            reason=reason,
        )

    async def override(
        self,
        attempt_id: int,
        *,
        tutor_id: int,
        total: int,
        feedback: str,
        reason: str,
        final_decisions: tuple[dict[str, Any], ...] | None = None,
        forbidden_answers: AbstractSet[str] = frozenset(),
    ) -> Review:
        attempt = await self._flagged(attempt_id)
        if attempt.result_maximum is None or not 0 <= total <= attempt.result_maximum:
            raise ValueError("override total is outside the published maximum")
        validate_feedback(feedback, forbidden=forbidden_answers)
        return await self._record(
            attempt,
            tutor_id=tutor_id,
            action="override",
            final_total=total,
            final_feedback=(feedback,),
            final_decisions=final_decisions or tuple(attempt.grade_decisions or []),
            reason=reason,
        )

    async def request_resubmission(
        self, attempt_id: int, *, tutor_id: int, reason: str
    ) -> Review:
        attempt = await self._flagged(attempt_id)
        return await self._record(
            attempt,
            tutor_id=tutor_id,
            action="request_resubmission",
            final_total=None,
            final_feedback=("Please submit a clearer image of your working.",),
            final_decisions=(),
            reason=reason,
        )

    async def _flagged(self, attempt_id: int) -> AttemptRow:
        attempt = await self._session.scalar(
            select(AttemptRow).where(AttemptRow.id == attempt_id).with_for_update()
        )
        if attempt is None or attempt.status != "flagged" or attempt.result_total is None:
            raise ReviewUnavailable("attempt is not awaiting tutor review")
        return attempt

    async def _record(
        self,
        attempt: AttemptRow,
        *,
        tutor_id: int,
        action: str,
        final_total: int | None,
        final_feedback: tuple[str, ...],
        final_decisions: tuple[dict[str, Any], ...],
        reason: str,
    ) -> Review:
        row = ReviewRow(
            attempt_id=attempt.id,
            tutor_id=tutor_id,
            action=action,
            original_total=attempt.result_total,
            final_total=final_total,
            original_decisions=list(attempt.grade_decisions or []),
            final_decisions=list(final_decisions),
            original_feedback=list(attempt.feedback or []),
            final_feedback=list(final_feedback),
            reason=reason,
        )
        self._session.add(row)
        attempt.status = "resubmission_requested" if action == "request_resubmission" else "reviewed"
        attempt.finalized_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        return Review.model_validate(row, from_attributes=True)

