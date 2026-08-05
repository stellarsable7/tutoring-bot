from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.submissions.service import EmptyAttempt, MixedMediaTypes, SubmissionService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def assignment_id(session: AsyncSession) -> int:
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
        solution_url="https://private.example/7",
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
    await session.commit()
    return assignment.id


async def test_multiple_uploads_remain_draft_until_submit(session: AsyncSession) -> None:
    service = SubmissionService(session)
    assignment = await assignment_id(session)

    attempt = await service.add_image(assignment, "tg-file-1", mime_type="image/jpeg")
    await service.add_image(assignment, "tg-file-2", mime_type="image/png")
    submitted = await service.submit(attempt.id)

    assert attempt.status == "draft"
    assert submitted.status == "queued"
    assert submitted.media_count == 2
    assert [item.telegram_file_id for item in submitted.media] == ["tg-file-1", "tg-file-2"]
    assert await service.submit(attempt.id) == submitted


async def test_pdf_cannot_be_mixed_with_images(session: AsyncSession) -> None:
    service = SubmissionService(session)
    assignment = await assignment_id(session)
    await service.add_pdf(assignment, "tg-pdf", mime_type="application/pdf")

    with pytest.raises(MixedMediaTypes):
        await service.add_image(assignment, "tg-image", mime_type="image/jpeg")


async def test_empty_attempt_cannot_be_submitted(session: AsyncSession) -> None:
    service = SubmissionService(session)
    attempt = await service.create_draft(await assignment_id(session))

    with pytest.raises(EmptyAttempt):
        await service.submit(attempt.id)
