import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from amath_bot.catalogue.importer import ImportResult, parse_manifest
from amath_bot.catalogue.repository import CatalogueRepository, DuplicateSourceQuestion
from amath_bot.settings import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amath-bot")
    commands = parser.add_subparsers(dest="command", required=True)
    import_command = commands.add_parser("import-catalogue")
    import_command.add_argument("path", type=Path)
    import_command.add_argument("--dry-run", action="store_true")
    return parser


def _print_result(result: ImportResult) -> None:
    print(f"accepted={len(result.accepted)} rejected={len(result.rejected)}")
    for rejected in result.rejected:
        print(f"item[{rejected.index}]: {', '.join(rejected.reasons)}")


async def _persist(result: ImportResult) -> int:
    engine = create_async_engine(Settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    duplicates = 0
    try:
        async with factory() as session:
            repository = CatalogueRepository(session)
            for item in result.accepted:
                try:
                    await repository.add(item)
                except DuplicateSourceQuestion:
                    duplicates += 1
    finally:
        await engine.dispose()
    print(f"imported={len(result.accepted) - duplicates} duplicates={duplicates}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command != "import-catalogue":
        raise AssertionError("unreachable command")
    result = parse_manifest(arguments.path)
    _print_result(result)
    if result.rejected:
        return 1
    if arguments.dry_run:
        return 0
    return asyncio.run(_persist(result))


if __name__ == "__main__":
    raise SystemExit(main())
