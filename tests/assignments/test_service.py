from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.service import AssignmentService
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def enrolled_student(session: AsyncSession) -> StudentRow:
    session.add(TutorRow(telegram_id=100))
    student = StudentRow(
        telegram_id=200,
        tutor_telegram_id=100,
        display_name="Ada",
        syllabus_version="4049-2026",
        consented_at=datetime.now(UTC),
    )
    session.add(student)
    session.add(
        SourceQuestionRow(
            source_url="https://grail.moe/question.pdf",
            solution_url="https://grail.moe/answer.pdf",
            provider="Holy Grail",
            school="Example Secondary",
            year=2024,
            paper="1",
            question_number="6",
            syllabus_version="4049-2026",
            objective_codes=["A1.complete-square"],
            marks=5,
            solution_kind="worked_solution",
            marking_steps=[],
            tutor_validated=True,
            eligible=True,
        )
    )
    await session.commit()
    await session.refresh(student)
    return student


async def test_due_schedule_creates_one_assignment_by_default(session: AsyncSession) -> None:
    student = await enrolled_student(session)
    service = AssignmentService(session)
    await service.set_schedule(student.id, weekdays={0, 1, 2, 3, 4}, hour=17)

    created = await service.create_due(now_sg="2026-08-05T17:00:00+08:00")

    assert len(created) == 1
    assert created[0].student_id == student.id
    assert created[0].selection_reason == "scheduled adaptive selection"


async def test_schedule_can_run_at_half_past_the_hour(session: AsyncSession) -> None:
    student = await enrolled_student(session)
    service = AssignmentService(session)
    await service.set_schedule(student.id, weekdays={2}, hour=18, minute=30)

    assert await service.create_due(now_sg="2026-08-05T18:00:00+08:00") == ()
    created = await service.create_due(now_sg="2026-08-05T18:30:00+08:00")

    assert len(created) == 1


async def test_repeated_tick_is_idempotent(session: AsyncSession) -> None:
    student = await enrolled_student(session)
    service = AssignmentService(session)
    await service.set_schedule(student.id, weekdays={2}, hour=17, count=1)

    first = await service.create_due(now_sg="2026-08-05T17:00:00+08:00")
    second = await service.create_due(now_sg="2026-08-05T17:00:30+08:00")

    assert len(first) == 1
    assert second == ()


async def test_multiple_daily_questions_are_distinct_when_catalogue_allows(
    session: AsyncSession,
) -> None:
    student = await enrolled_student(session)
    session.add(
        SourceQuestionRow(
            source_url="https://grail.moe/question-2.pdf",
            solution_url="https://grail.moe/answer-2.pdf",
            provider="Holy Grail",
            school="Example Secondary",
            year=2024,
            paper="2",
            question_number="7",
            syllabus_version="4049-2026",
            objective_codes=["A1.factorise"],
            marks=4,
            solution_kind="worked_solution",
            marking_steps=[],
            tutor_validated=True,
            eligible=True,
        )
    )
    await session.commit()
    service = AssignmentService(session)
    await service.set_schedule(student.id, weekdays={2}, hour=17, count=2)

    created = await service.create_due(now_sg="2026-08-05T17:00:00+08:00")

    assert len(created) == 2
    assert created[0].source_question_id != created[1].source_question_id
