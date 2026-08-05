from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.db import Base
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.telegram.controls import DatabaseTutorControls


@dataclass(frozen=True)
class FakeInvite:
    code: str


class FakePeople:
    async def create_invite(self, tutor_telegram_id: int) -> FakeInvite:
        assert tutor_telegram_id == 100
        return FakeInvite("invite-code")


class FakeAssignments:
    async def set_schedule(
        self,
        student_id: int,
        *,
        weekdays: set[int],
        hour: int,
        count: int = 1,
        timezone: str = "Asia/Singapore",
    ) -> None:
        raise AssertionError("not used")


async def test_invite_uses_deployed_bot_username() -> None:
    controls = DatabaseTutorControls(
        None,  # type: ignore[arg-type]
        tutor_telegram_id=100,
        bot_username="amath_practice_bot",
        people=FakePeople(),  # type: ignore[arg-type]
        assignments=FakeAssignments(),  # type: ignore[arg-type]
    )
    result = await controls.execute("invite", ())
    assert result == "Student invite: https://t.me/amath_practice_bot?start=invite-code"


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def test_remove_requires_confirmation_and_deletes_student(session: AsyncSession) -> None:
    session.add(TutorRow(telegram_id=100))
    session.add(
        StudentRow(
            telegram_id=200,
            tutor_telegram_id=100,
            display_name="Ada Lovelace",
            consented_at=datetime.now(UTC),
        )
    )
    await session.commit()
    controls = DatabaseTutorControls(
        session,
        tutor_telegram_id=100,
        bot_username="amath_practice_bot",
        people=FakePeople(),  # type: ignore[arg-type]
        assignments=FakeAssignments(),  # type: ignore[arg-type]
    )

    refused = await controls.execute("remove", ("Ada Lovelace",))
    assert refused == 'Could not run /remove: usage: /remove "NAME" CONFIRM'
    assert await session.scalar(select(StudentRow)) is not None

    removed = await controls.execute("remove", ("Ada", "Lovelace", "CONFIRM"))
    assert removed == "Removed Ada Lovelace and all associated bot records."
    assert await session.scalar(select(StudentRow)) is None
