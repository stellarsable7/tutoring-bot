from datetime import UTC, date, datetime
from pathlib import Path

import pytest_asyncio
from aiogram.types import FSInputFile
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
        self.documents: list[tuple[int, str, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        if self.fail:
            raise OSError("temporary Telegram outage")
        self.sent.append((chat_id, text))
        return object()

    async def send_document(
        self, chat_id: int, document: FSInputFile, *, caption: str
    ) -> object:
        if self.fail:
            raise OSError("temporary Telegram outage")
        self.documents.append((chat_id, str(document.path), caption))
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


async def test_question_asset_is_sent_without_full_paper_link(
    session: AsyncSession, tmp_path: Path
) -> None:
    asset = tmp_path / "question-6.pdf"
    asset.write_bytes(b"%PDF-1.4\n%%EOF")
    session.add(TutorRow(telegram_id=100))
    student = StudentRow(
        telegram_id=200,
        tutor_telegram_id=100,
        display_name="Ada",
        syllabus_version="4049-2026",
        consented_at=datetime.now(UTC),
    )
    question = SourceQuestionRow(
        source_url="https://document.grail.moe/full-paper.pdf",
        asset_path=str(asset),
        solution_url="https://document.grail.moe/answers.pdf",
        provider="Holy Grail",
        school="Example Secondary",
        year=2025,
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
    session.add(
        AssignmentRow(
            student_id=student.id,
            source_question_id=question.id,
            scheduled_date=date(2026, 8, 6),
            sequence_number=1,
            status="pending",
            selection_reason="weekly paper shuffle",
        )
    )
    await session.commit()
    sender = FlakySender()
    sender.fail = False

    assert await AssignmentDeliveryService(session, sender).deliver_pending() == 1
    assert sender.sent == []
    assert sender.documents[0][1] == str(asset)
    assert "full-paper.pdf" not in sender.documents[0][2]
    assert "Question 6" in sender.documents[0][2]
