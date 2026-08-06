import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any, Protocol

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.reviews.service import ReviewService, ReviewUnavailable
from amath_bot.submissions.tables import AttemptMediaRow, AttemptRow
from amath_bot.telegram.tutor import TutorMessage, TutorReply


class InvalidReviewCallback(ValueError):
    pass


class ReviewNotifier(Protocol):
    async def finalized(self, attempt_id: int) -> bool: ...

    async def resubmission_requested(self, attempt_id: int) -> bool: ...


@dataclass(frozen=True)
class ReviewCard:
    attempt_id: int
    media_file_ids: tuple[str, ...]
    media_kinds: tuple[str, ...]
    transcription: tuple[str, ...]
    scheme_url: str
    proposed_total: int
    maximum: int
    decisions: tuple[dict[str, Any], ...]
    confidence: dict[str, float]
    review_reasons: tuple[str, ...]
    callback_token: str


class ReviewHandler:
    def __init__(
        self,
        *,
        tutor_telegram_id: int,
        session: AsyncSession,
        reviews: ReviewService,
        callback_secret: str,
        notifier: ReviewNotifier | None = None,
        callback_ttl_seconds: int = 900,
    ) -> None:
        if not callback_secret:
            raise ValueError("callback secret must not be empty")
        self._tutor_telegram_id = tutor_telegram_id
        self._session = session
        self._reviews = reviews
        self._secret = callback_secret.encode()
        self._notifier = notifier
        self._callback_ttl_seconds = callback_ttl_seconds

    async def next(
        self, message: TutorMessage | Message | CallbackQuery
    ) -> ReviewCard | TutorReply:
        if not self._is_tutor(message):
            return TutorReply("Tutor access required.")
        row = (
            await self._session.execute(
                select(AttemptRow, SourceQuestionRow.solution_url)
                .join(AssignmentRow, AssignmentRow.id == AttemptRow.assignment_id)
                .join(SourceQuestionRow, SourceQuestionRow.id == AssignmentRow.source_question_id)
                .where(AttemptRow.status == "flagged")
                .order_by(AttemptRow.created_at, AttemptRow.id)
                .limit(1)
            )
        ).first()
        if row is None:
            return TutorReply("No submissions are awaiting review.")
        attempt, scheme_url = row
        media_rows = tuple(
            await self._session.scalars(
                select(AttemptMediaRow)
                .where(AttemptMediaRow.attempt_id == attempt.id)
                .order_by(AttemptMediaRow.position)
            )
        )
        decisions = tuple(attempt.grade_decisions or [])
        transcription = tuple(
            str(line)
            for decision in decisions
            for line in decision.get("student_lines", [])
        )
        confidence = self._confidence(decisions)
        return ReviewCard(
            attempt_id=attempt.id,
            media_file_ids=tuple(item.telegram_file_id for item in media_rows),
            media_kinds=tuple(item.media_kind for item in media_rows),
            transcription=transcription,
            scheme_url=scheme_url,
            proposed_total=attempt.result_total or 0,
            maximum=attempt.result_maximum or 0,
            decisions=decisions,
            confidence=confidence,
            review_reasons=tuple(attempt.review_reasons or []),
            callback_token=self._sign(attempt.id),
        )

    async def approve(
        self, message: TutorMessage | Message | CallbackQuery, callback_token: str
    ) -> TutorReply:
        attempt_id = self._authorize(message, callback_token)
        await self._reviews.approve(attempt_id, tutor_id=self._tutor_telegram_id)
        notified = self._notifier is not None and await self._notifier.finalized(attempt_id)
        return TutorReply(
            "Mark approved and student notified."
            if notified
            else "Mark approved; student notification is pending."
        )

    async def override(
        self,
        message: TutorMessage | Message | CallbackQuery,
        callback_token: str,
        *,
        total: int,
        feedback: str,
        reason: str,
        forbidden_answers: frozenset[str] = frozenset(),
    ) -> TutorReply:
        attempt_id = self._authorize(message, callback_token)
        await self._reviews.override(
            attempt_id,
            tutor_id=self._tutor_telegram_id,
            total=total,
            feedback=feedback,
            reason=reason,
            forbidden_answers=forbidden_answers,
        )
        notified = self._notifier is not None and await self._notifier.finalized(attempt_id)
        return TutorReply(
            "Mark updated and student notified."
            if notified
            else "Mark updated; student notification is pending."
        )

    async def request_resubmission(
        self,
        message: TutorMessage | Message | CallbackQuery,
        callback_token: str,
        *,
        reason: str,
    ) -> TutorReply:
        attempt_id = self._authorize(message, callback_token)
        await self._reviews.request_resubmission(
            attempt_id, tutor_id=self._tutor_telegram_id, reason=reason
        )
        notified = self._notifier is not None and await self._notifier.resubmission_requested(
            attempt_id
        )
        return TutorReply(
            "Clearer upload requested from student."
            if notified
            else "Resubmission recorded; student notification is pending."
        )

    async def specify_mark(
        self,
        message: TutorMessage | Message,
        *,
        attempt_id: int,
        total: int,
        feedback: str,
    ) -> TutorReply:
        if not self._is_tutor(message):
            return TutorReply("Tutor access required.")
        await self._reviews.override(
            attempt_id,
            tutor_id=self._tutor_telegram_id,
            total=total,
            feedback=feedback,
            reason="Tutor specified the mark after local OCR review.",
        )
        notified = self._notifier is not None and await self._notifier.finalized(attempt_id)
        return TutorReply(
            "Mark saved and student notified."
            if notified
            else "Mark saved; student notification is pending."
        )

    def _authorize(self, message: TutorMessage | Message | CallbackQuery, token: str) -> int:
        if not self._is_tutor(message):
            raise InvalidReviewCallback("tutor access required")
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected = hmac.new(self._secret, encoded.encode(), hashlib.sha256).hexdigest()[:16]
            if not hmac.compare_digest(supplied_signature, expected):
                raise InvalidReviewCallback("invalid callback signature")
            payload = base64.urlsafe_b64decode(encoded + "==").decode()
            attempt_text, issued_text = payload.split(":", 1)
            if int(time.time()) - int(issued_text) > self._callback_ttl_seconds:
                raise InvalidReviewCallback("review callback expired")
            return int(attempt_text)
        except (ValueError, TypeError) as error:
            if isinstance(error, InvalidReviewCallback):
                raise
            raise InvalidReviewCallback("invalid review callback") from error

    def _sign(self, attempt_id: int) -> str:
        payload = f"{attempt_id}:{int(time.time())}".encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(self._secret, encoded.encode(), hashlib.sha256).hexdigest()[:16]
        return f"{encoded}.{signature}"

    def _is_tutor(self, message: TutorMessage | Message | CallbackQuery) -> bool:
        return message.from_user is not None and message.from_user.id == self._tutor_telegram_id

    @staticmethod
    def _confidence(decisions: tuple[dict[str, Any], ...]) -> dict[str, float]:
        values = [
            float(decision["provider_confidence"])
            for decision in decisions
            if "provider_confidence" in decision
        ]
        return {"provider": min(values, default=0.0)}


def create_review_router(handler: ReviewHandler) -> Router:
    router = Router(name="tutor-reviews")

    @router.message(Command("review"))
    async def next_review(message: Message) -> None:
        if message.from_user is None:
            return
        result = await handler.next(message)
        if isinstance(result, TutorReply):
            await message.answer(result.text)
            return
        for file_id, kind in zip(result.media_file_ids, result.media_kinds, strict=True):
            if kind == "pdf":
                await message.answer_document(file_id)
            else:
                await message.answer_photo(file_id)
        if result.transcription:
            transcription = "\n".join(result.transcription)
            await message.answer(f"OCR transcription:\n{transcription}"[:4000])
        reasons = ", ".join(result.review_reasons) or "unspecified"
        text = (
            f"Attempt {result.attempt_id}: {result.proposed_total}/{result.maximum}\n"
            f"Review reasons: {reasons}\nScheme: {result.scheme_url}\n"
            f"Media expires after the 24-hour review window."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Approve", callback_data=f"review:approve:{result.callback_token}"
                    ),
                    InlineKeyboardButton(
                        text="Request clearer upload",
                        callback_data=f"review:resubmit:{result.callback_token}",
                    ),
                ]
            ]
        )
        await message.answer(text, reply_markup=keyboard)

    @router.message(Command("mark"))
    async def specify_mark(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=3)
        if len(parts) < 4:
            await message.answer("Use: /mark ATTEMPT_ID SCORE feedback")
            return
        try:
            reply = await handler.specify_mark(
                message,
                attempt_id=int(parts[1]),
                total=int(parts[2]),
                feedback=parts[3],
            )
        except (ValueError, ReviewUnavailable) as error:
            await message.answer(f"Could not save that mark: {error}")
            return
        await message.answer(reply.text)

    @router.callback_query(F.data.startswith("review:approve:"))
    async def approve(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.data is None:
            return
        try:
            reply = await handler.approve(callback, callback.data.removeprefix("review:approve:"))
        except (InvalidReviewCallback, ReviewUnavailable) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer(reply.text, show_alert=True)

    @router.callback_query(F.data.startswith("review:resubmit:"))
    async def resubmit(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.data is None:
            return
        try:
            reply = await handler.request_resubmission(
                callback,
                callback.data.removeprefix("review:resubmit:"),
                reason="Tutor requested a clearer upload.",
            )
        except (InvalidReviewCallback, ReviewUnavailable) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer(reply.text, show_alert=True)

    return router


__all__ = [
    "InvalidReviewCallback",
    "ReviewCard",
    "ReviewHandler",
    "ReviewNotifier",
    "ReviewUnavailable",
    "create_review_router",
]
