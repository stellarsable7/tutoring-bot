import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.catalogue.models import SolutionKind, SourceQuestion
from amath_bot.catalogue.repository import CatalogueRepository, DuplicateSourceQuestion
from amath_bot.db import Base


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


@pytest.fixture
def eligible_question() -> SourceQuestion:
    return SourceQuestion(
        source_url="https://grail.moe/paper.pdf",
        solution_url="https://grail.moe/solution.pdf",
        provider="Holy Grail",
        school="Example Secondary",
        year=2024,
        paper="1",
        question_number="6",
        syllabus_version="4049-2026",
        objective_codes=("A1.complete-square",),
        marks=5,
        solution_kind=SolutionKind.WORKED_SOLUTION,
        tutor_validated=True,
    )


async def test_source_identity_is_unique(
    session: AsyncSession, eligible_question: SourceQuestion
) -> None:
    repository = CatalogueRepository(session)
    await repository.add(eligible_question)
    with pytest.raises(DuplicateSourceQuestion):
        await repository.add(eligible_question)


async def test_round_trips_assignable_question(
    session: AsyncSession, eligible_question: SourceQuestion
) -> None:
    repository = CatalogueRepository(session)
    created = await repository.add(eligible_question)
    loaded = await repository.get(created.id)
    assert loaded is not None
    assert loaded.question_number == "6"
    assert loaded.objective_codes == ("A1.complete-square",)
