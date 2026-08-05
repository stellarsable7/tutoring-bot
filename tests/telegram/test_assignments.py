from datetime import UTC, date, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.telegram.assignments import (
    AssignmentDelivery,
    AssignmentDeliveryService,
    AssignmentRenderer,
)


class FlakySender:
    def __init__(self) -> None:
        self.fail = True
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        if self.fail:
            raise OSError("temporary Telegram outage")
        self.sent.append((chat_id, text))
        return object()


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def test_delivery_contains_link_and_question_identity() -> None:
    assignment = AssignmentDelivery(
        assignment_id=7,
        student_telegram_id=200,
        source_url="https://document.grail.moe/example-paper.pdf",
        provider="Holy Grail",
        school="Example Secondary",
        year=2024,
        paper="1",
        question_number="6",
        marks=5,
        scheduled_date=date(2026, 8, 5),
    )

    message = await AssignmentRenderer().render(assignment)

    assert str(assignment.source_url) in message.text
    assert "Paper 1 · Question 6" in message.text
    assert "5 marks" in message.text
    assert "about 8 minutes" in message.text
    assert "solution" not in message.text.lower()
    assert "Holy Grail" not in message.text
    assert "Example Secondary" not in message.text


async def test_failed_send_returns_assignment_to_pending_for_retry(session: AsyncSession) -> None:
    session.add(TutorRow(telegram_id=100))
    student = StudentRow(
        telegram_id=200,
        tutor_telegram_id=100,
        display_name="Ada",
        syllabus_version="4049-2026",
        consented_at=datetime.now(UTC),
    )
    question = SourceQuestionRow(
        source_url="https://document.grail.moe/paper.pdf",
        solution_url="https://document.grail.moe/answers.pdf",
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
        status="pending",
        selection_reason="scheduled adaptive selection",
    )
    session.add(assignment)
    await session.commit()

    sender = FlakySender()
    delivery = AssignmentDeliveryService(session, sender)
    assert await delivery.deliver_pending() == 0
    await session.refresh(assignment)
    assert assignment.status == "pending"

    sender.fail = False
    assert await delivery.deliver_pending() == 1
    await session.refresh(assignment)
    assert assignment.status == "delivered"
    assert len(sender.sent) == 1
