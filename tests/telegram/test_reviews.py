from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.reviews.service import ReviewService
from amath_bot.reviews.tables import ReviewRow
from amath_bot.submissions.tables import AttemptMediaRow, AttemptRow
from amath_bot.telegram.reviews import InvalidReviewCallback, ReviewCard, ReviewHandler


class FakeNotifier:
    def __init__(self) -> None:
        self.finalized_attempts: list[int] = []

    async def finalized(self, attempt_id: int) -> bool:
        self.finalized_attempts.append(attempt_id)
        return True

    async def resubmission_requested(self, attempt_id: int) -> bool:
        return True


@dataclass(frozen=True)
class FakeUser:
    id: int


@dataclass(frozen=True)
class FakeMessage:
    from_user: FakeUser


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def add_flagged_attempt(session: AsyncSession) -> AttemptRow:
    session.add(TutorRow(telegram_id=100))
    student = StudentRow(
        telegram_id=200,
        tutor_telegram_id=100,
        display_name="Ada",
        syllabus_version="4049-2026",
        consented_at=datetime.now(UTC),
    )
    question = SourceQuestionRow(
        source_url="https://questions.example/7",
        solution_url="https://private.example/scheme/7",
        provider="Example",
        school="Example Secondary",
        year=2024,
        paper="1",
        question_number="6",
        syllabus_version="4049-2026",
        objective_codes=["A1.complete-square"],
        marks=5,
        solution_kind="mark_scheme",
        marking_steps=[],
        tutor_validated=True,
        eligible=True,
    )
    session.add_all([student, question])
    await session.flush()
    assignment = AssignmentRow(
        student_id=student.id,
        source_question_id=question.id,
        scheduled_date=date(2026, 8, 5),
        sequence_number=1,
        status="delivered",
        selection_reason="test",
    )
    session.add(assignment)
    await session.flush()
    attempt = AttemptRow(
        assignment_id=assignment.id,
        status="flagged",
        result_total=4,
        result_maximum=5,
        feedback=["Line 2: method accepted."],
        grade_decisions=[{"scheme_step_code": "M1", "provider_confidence": 0.7}],
        review_reasons=["low_recognition"],
        media_expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(attempt)
    await session.flush()
    session.add(
        AttemptMediaRow(
            attempt_id=attempt.id,
            position=0,
            telegram_file_id="photo-1",
            mime_type="image/jpeg",
            media_kind="photo",
        )
    )
    await session.commit()
    await session.refresh(attempt)
    return attempt


async def test_tutor_approves_flagged_attempt(session: AsyncSession) -> None:
    attempt = await add_flagged_attempt(session)
    handler = ReviewHandler(
        tutor_telegram_id=100,
        session=session,
        reviews=ReviewService(session),
        callback_secret="test-secret",
    )
    message = FakeMessage(FakeUser(100))

    card = await handler.next(message)
    assert isinstance(card, ReviewCard)
    assert card.attempt_id == attempt.id
    assert card.media_file_ids == ("photo-1",)
    assert card.scheme_url.endswith("/scheme/7")
    assert len(f"review:resubmit:{card.callback_token}".encode()) <= 64
    result = await handler.approve(message, card.callback_token)

    assert result.text == "Mark approved; student notification is pending."
    await session.refresh(attempt)
    assert attempt.status == "reviewed"


async def test_successful_notifier_is_reported_truthfully(session: AsyncSession) -> None:
    attempt = await add_flagged_attempt(session)
    notifier = FakeNotifier()
    handler = ReviewHandler(
        tutor_telegram_id=100,
        session=session,
        reviews=ReviewService(session),
        callback_secret="test-secret",
        notifier=notifier,
    )
    message = FakeMessage(FakeUser(100))
    card = await handler.next(message)
    assert isinstance(card, ReviewCard)

    result = await handler.approve(message, card.callback_token)

    assert result.text == "Mark approved and student notified."
    assert notifier.finalized_attempts == [attempt.id]


async def test_tutor_specified_mark_uses_provider_neutral_audit_wording(
    session: AsyncSession,
) -> None:
    attempt = await add_flagged_attempt(session)
    handler = ReviewHandler(
        tutor_telegram_id=100,
        session=session,
        reviews=ReviewService(session),
        callback_secret="test-secret",
    )

    result = await handler.specify_mark(
        FakeMessage(FakeUser(100)), total=3, feedback="Tutor correction."
    )

    assert result.text == "Mark saved; student notification is pending."
    review = await session.scalar(select(ReviewRow).where(ReviewRow.attempt_id == attempt.id))
    assert review is not None
    assert review.reason == "Tutor specified the mark after AI review."
    assert "local" not in review.reason.lower()


async def test_tutor_can_requeue_flagged_attempt_for_fresh_vision_pass(
    session: AsyncSession,
) -> None:
    attempt = await add_flagged_attempt(session)
    attempt.marking_attempts = 4
    attempt.marking_last_error = "old error"
    await session.commit()
    handler = ReviewHandler(
        tutor_telegram_id=100,
        session=session,
        reviews=ReviewService(session),
        callback_secret="test-secret",
    )

    result = await handler.reread(FakeMessage(FakeUser(100)))

    assert result.text.startswith("Submission queued for a fresh OCR")
    await session.refresh(attempt)
    assert attempt.status == "queued"
    assert attempt.queued_at is not None
    assert attempt.marking_attempts == 0
    assert attempt.marking_last_error is None
    assert attempt.result_total is None
    assert attempt.result_maximum is None
    assert attempt.feedback is None
    assert attempt.grade_decisions is None
    assert attempt.review_reasons is None
    assert attempt.media_expires_at is None


async def test_student_cannot_requeue_flagged_attempt(session: AsyncSession) -> None:
    attempt = await add_flagged_attempt(session)
    handler = ReviewHandler(
        tutor_telegram_id=100,
        session=session,
        reviews=ReviewService(session),
        callback_secret="test-secret",
    )

    result = await handler.reread(FakeMessage(FakeUser(200)))

    assert result.text == "Tutor access required."
    await session.refresh(attempt)
    assert attempt.status == "flagged"


async def test_student_and_tampered_callbacks_are_rejected(session: AsyncSession) -> None:
    await add_flagged_attempt(session)
    handler = ReviewHandler(
        tutor_telegram_id=100,
        session=session,
        reviews=ReviewService(session),
        callback_secret="test-secret",
    )
    card = await handler.next(FakeMessage(FakeUser(100)))
    assert isinstance(card, ReviewCard)

    with pytest.raises(InvalidReviewCallback, match="tutor access"):
        await handler.approve(FakeMessage(FakeUser(200)), card.callback_token)
    with pytest.raises(InvalidReviewCallback, match="signature"):
        await handler.approve(FakeMessage(FakeUser(100)), card.callback_token + "bad")
