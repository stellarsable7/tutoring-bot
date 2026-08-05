from datetime import UTC, date, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.submissions.tables import AttemptRow
from amath_bot.telegram.progress import ProgressReporter


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def test_progress_uses_aggregate_learning_data(session: AsyncSession) -> None:
    session.add(TutorRow(telegram_id=100))
    student = StudentRow(
        telegram_id=200,
        tutor_telegram_id=100,
        display_name="Ada",
        syllabus_version="4049-2026",
        consented_at=datetime.now(UTC),
    )
    question = SourceQuestionRow(
        source_url="https://example.test/q",
        solution_url="https://example.test/s",
        provider="Example",
        school="Example Secondary",
        year=2024,
        paper="1",
        question_number="1",
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
    session.add(
        AttemptRow(
            assignment_id=assignment.id,
            status="reviewed",
            result_total=4,
            result_maximum=5,
            review_reasons=["low_recognition"],
        )
    )
    await session.commit()

    report = await ProgressReporter(session).for_student("Ada")
    text = report.render()
    assert "Completed: 1" in text
    assert "4/5" in text
    assert "A1.complete-square 80%" in text
    assert "low_recognition" in text
    assert "telegram" not in text.lower()
