from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from amath_bot.catalogue.models import SolutionKind, SourceQuestion
from amath_bot.catalogue.repository import CatalogueRepository
from amath_bot.db import Base


async def test_assignable_items_are_4049_and_have_published_worked_solutions() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repository = CatalogueRepository(session)
        await repository.add(
            SourceQuestion(
                source_url="https://document.grail.moe/paper.pdf",
                solution_url="https://document.grail.moe/solution.pdf",
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
        )
        for item in await repository.assignable():
            assert item.syllabus_version == "4049-2026"
            assert item.solution_url is not None
            assert item.solution_kind in {
                SolutionKind.WORKED_SOLUTION,
                SolutionKind.MARK_SCHEME,
            }
            assert item.tutor_validated is True
    await engine.dispose()
