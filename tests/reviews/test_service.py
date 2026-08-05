from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.marking.feedback import UnsafeFeedback
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.reviews.service import ReviewService
from amath_bot.submissions.tables import AttemptRow


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def flagged_attempt(session: AsyncSession) -> AttemptRow:
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
        provider="Holy Grail",
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
        feedback=["Line 2: Method accepted; 1/1."],
        grade_decisions=[{"scheme_step_code": "M1", "marks_awarded": 1}],
        review_reasons=["low_recognition"],
        media_expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return attempt


async def test_override_preserves_original_grade(session: AsyncSession) -> None:
    attempt = await flagged_attempt(session)
    review = await ReviewService(session).override(
        attempt.id,
        tutor_id=100,
        total=3,
        feedback="Line 2: Method mark not earned.",
        reason="Tutor checked the written method.",
    )

    assert review.original_total == 4
    assert review.final_total == 3
    assert review.tutor_id == 100
    assert review.original_decisions[0]["scheme_step_code"] == "M1"


async def test_tutor_feedback_is_checked_for_answer_leaks(session: AsyncSession) -> None:
    attempt = await flagged_attempt(session)

    with pytest.raises(UnsafeFeedback):
        await ReviewService(session).override(
            attempt.id,
            tutor_id=100,
            total=3,
            feedback="The correct answer is x=2.",
            reason="Edited",
            forbidden_answers={"x=2"},
        )
