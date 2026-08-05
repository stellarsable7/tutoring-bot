from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.privacy.media_lifecycle import MediaLifecycle
from amath_bot.submissions.tables import AttemptRow


@dataclass
class FakeDeleter:
    fail: bool = False
    deleted: list[int] = field(default_factory=list)

    async def delete_attempt_media(self, attempt_id: int) -> None:
        if self.fail:
            raise OSError("telegram unavailable")
        self.deleted.append(attempt_id)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def add_attempt(session: AsyncSession, *, status: str, expires: datetime) -> AttemptRow:
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
        scheduled_date=datetime.now(UTC).date(),
        sequence_number=1,
        status="delivered",
        selection_reason="test",
    )
    session.add(assignment)
    await session.flush()
    attempt = AttemptRow(
        assignment_id=assignment.id,
        status=status,
        result_total=4,
        result_maximum=5,
        media_expires_at=expires,
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return attempt


async def test_unreviewed_flag_deletes_media_and_stays_unresolved(
    session: AsyncSession,
) -> None:
    created = datetime(2026, 8, 5, tzinfo=UTC)
    attempt = await add_attempt(session, status="flagged", expires=created + timedelta(hours=24))
    deleter = FakeDeleter()
    lifecycle = MediaLifecycle(session, deleter=deleter)

    await lifecycle.expire(now=created + timedelta(hours=24, seconds=1))

    await session.refresh(attempt)
    assert attempt.media_deleted_at is not None
    assert attempt.status == "unresolved"
    assert attempt.finalized_at is not None
    assert deleter.deleted == [attempt.id]


async def test_failed_deletion_is_retried_and_not_marked_complete(session: AsyncSession) -> None:
    now = datetime(2026, 8, 5, tzinfo=UTC)
    attempt = await add_attempt(session, status="reviewed", expires=now + timedelta(hours=24))
    deleter = FakeDeleter(fail=True)
    lifecycle = MediaLifecycle(session, deleter=deleter)

    assert await lifecycle.expire(now=now) == 0
    await session.refresh(attempt)
    assert attempt.media_deleted_at is None
    assert attempt.media_delete_attempts == 1
    assert attempt.media_delete_retry_at == (now + timedelta(minutes=1)).replace(tzinfo=None)

    deleter.fail = False
    assert await lifecycle.expire(now=now + timedelta(minutes=1)) == 1
    await session.refresh(attempt)
    assert attempt.media_deleted_at is not None
