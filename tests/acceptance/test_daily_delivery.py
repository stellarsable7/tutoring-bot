from datetime import date

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.service import AssignmentService
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.people.service import PeopleService
from amath_bot.system import AmathSystem
from amath_bot.telegram.assignments import AssignmentDeliveryService


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()

    def messages_for(self, chat_id: int) -> list[str]:
        return [text for recipient, text in self.messages if recipient == chat_id]


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def test_invited_student_receives_one_eligible_daily_question(
    session: AsyncSession,
) -> None:
    people = PeopleService(session)
    invite = await people.create_invite(tutor_telegram_id=100)
    session.add(
        SourceQuestionRow(
            source_url="https://questions.example/assignment/opaque-7",
            solution_url="https://private.example/mark-scheme/7",
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
    )
    await session.commit()
    fake_telegram = FakeTelegram()
    system = AmathSystem(
        people,
        AssignmentService(session),
        AssignmentDeliveryService(session, fake_telegram),
    )

    student = await system.join_student(
        invite.code, telegram_id=200, display_name="Ada", consent=True
    )
    await system.schedule(student.id, weekdays={2}, hour=17, count=1)
    created = await system.tick("2026-08-05T17:00:00+08:00")
    await system.tick("2026-08-05T17:00:30+08:00")

    sent = fake_telegram.messages_for(200)
    assert len(created) == 1
    assert len(sent) == 1
    assert "https://" in sent[0]
    assert "Question 6" in sent[0]
    assert "Holy Grail" not in sent[0]
    assert created[0].scheduled_date == date(2026, 8, 5)
