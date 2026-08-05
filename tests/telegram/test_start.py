from dataclasses import dataclass
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.db import Base
from amath_bot.people.service import PeopleService
from amath_bot.telegram.start import StartHandler
from amath_bot.telegram.text import CONSENT_TEXT


@dataclass(frozen=True)
class FakeUser:
    id: int
    full_name: str


@dataclass(frozen=True)
class FakeMessage:
    from_user: FakeUser


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def test_start_requires_consent_before_redeeming(session: AsyncSession) -> None:
    people = PeopleService(session)
    invite = await people.create_invite(tutor_telegram_id=100)
    handler = StartHandler(people)
    message = FakeMessage(FakeUser(id=200, full_name="Ada"))

    replies = await handler.start(message, invite_code=invite.code)

    assert replies[-1].buttons == ("I consent", "Cancel")
    assert replies[-1].text == CONSENT_TEXT
    assert await people.find_student(message.from_user.id) is None


async def test_consent_redeems_pending_invite(session: AsyncSession) -> None:
    people = PeopleService(session)
    invite = await people.create_invite(tutor_telegram_id=100)
    handler = StartHandler(people)
    message = FakeMessage(FakeUser(id=200, full_name="Ada"))
    await handler.start(message, invite_code=invite.code)

    reply = await handler.consent(message, consented_at=datetime.now(UTC))

    assert reply.text == "You’re enrolled. Your tutor can now set your question schedule."
    assert await people.find_student(200) is not None
