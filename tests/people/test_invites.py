from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.db import Base
from amath_bot.people.service import InviteAlreadyUsed, PeopleService
from amath_bot.people.tables import TutorRow


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def test_invite_is_single_use(session: AsyncSession) -> None:
    service = PeopleService(session)
    invite = await service.create_invite(tutor_telegram_id=100)
    assert await session.scalar(select(TutorRow.telegram_id)) == 100
    student = await service.redeem(
        invite.code,
        telegram_id=200,
        display_name="Ada",
        consented_at=datetime.now(UTC),
    )
    assert student.syllabus_version == "4049-2026"
    with pytest.raises(InviteAlreadyUsed):
        await service.redeem(
            invite.code,
            telegram_id=201,
            display_name="Ben",
            consented_at=datetime.now(UTC),
        )


async def test_redeem_requires_consent(session: AsyncSession) -> None:
    service = PeopleService(session)
    invite = await service.create_invite(tutor_telegram_id=100)
    with pytest.raises(ValueError, match="consent"):
        await service.redeem(
            invite.code,
            telegram_id=200,
            display_name="Ada",
            consented_at=None,
        )
