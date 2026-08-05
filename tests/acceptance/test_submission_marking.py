from datetime import UTC, date, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.jobs.mark_attempt import MarkAttemptJob, MarkingOutcome
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.submissions.service import SubmissionService
from amath_bot.telegram.submissions import SubmissionHandler


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()

    def last_message_for(self, chat_id: int) -> str:
        return [text for recipient, text in self.messages if recipient == chat_id][-1]


class FakePipeline:
    async def mark(self, attempt_id: int) -> MarkingOutcome:
        return MarkingOutcome(
            total=4,
            maximum=5,
            feedback=(
                "Line 1: A valid method is shown; 1/1.",
                "Line 2: The substitution is consistent; 1/1.",
            ),
            review_reasons=(),
        )


class FakeMediaLifecycle:
    def __init__(self) -> None:
        self.deleted_attempts: list[int] = []

    async def delete_attempt_media(self, attempt_id: int) -> None:
        self.deleted_attempts.append(attempt_id)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def delivered_assignment(session: AsyncSession) -> AssignmentRow:
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
    await session.refresh(assignment)
    return assignment


async def test_student_submits_two_pages_and_receives_provisional_feedback(
    session: AsyncSession,
) -> None:
    assignment = await delivered_assignment(session)
    submissions = SubmissionHandler(SubmissionService(session), session)
    attempt = await submissions.receive_photo(
        student_telegram_id=200, file_id="page-1", mime_type="image/jpeg"
    )
    await submissions.receive_photo(
        student_telegram_id=200, file_id="page-2", mime_type="image/jpeg"
    )
    queued = await submissions.submit(student_telegram_id=200)
    fake_telegram = FakeTelegram()
    media = FakeMediaLifecycle()

    processed = await MarkAttemptJob(
        session, pipeline=FakePipeline(), notifier=fake_telegram, media=media
    ).run_pending()

    reply = fake_telegram.last_message_for(200)
    assert attempt.assignment_id == assignment.id
    assert queued.media_count == 2
    assert processed == 1
    assert "Mark finalized: 4/5" in reply
    assert "correct answer" not in reply.lower()
    assert media.deleted_attempts == [attempt.id]
