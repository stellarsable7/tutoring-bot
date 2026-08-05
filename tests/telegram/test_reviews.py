from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.reviews.service import ReviewService
from amath_bot.submissions.tables import AttemptMediaRow, AttemptRow
from amath_bot.telegram.reviews import InvalidReviewCallback, ReviewCard, ReviewHandler


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
    result = await handler.approve(message, card.callback_token)

    assert result.text == "Mark approved and student notified."
    await session.refresh(attempt)
    assert attempt.status == "reviewed"


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
