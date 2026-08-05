# A-Math Bot

Telegram-based daily practice for the 2026 Singapore-Cambridge GCE O-Level Additional Mathematics syllabus 4049.

This first implementation phase provides:

- a versioned 4049 syllabus map;
- policy-enforced storage for source-linked questions;
- rate-limited discovery of O-Level Additional Mathematics exam papers from Holy Grail's public library;
- bounded extraction of matching question and published-solution sections; and
- a tutor-reviewed catalogue import command.

Discovered candidates are never assignable automatically. A tutor must validate the question boundary, matching published worked solution or mark scheme, marks, and syllabus tags. Final-answer-only material is rejected.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 16 for production
- SQLite is used by automated tests

## Setup

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv sync
```

Set production configuration:

```bash
export AMATH_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost/amath_bot'
export AMATH_TIMEZONE='Asia/Singapore'
```

Apply migrations:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run alembic upgrade head
```

## Validate and import a reviewed catalogue

Dry-run validation exits non-zero if any item is rejected:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run python -m amath_bot.cli import-catalogue data/catalogue/example.json --dry-run
```

Import into the configured database:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run python -m amath_bot.cli import-catalogue data/catalogue/example.json
```

## Discovery policy

The Holy Grail adapter uses only public library pages and public document links. It checks `robots.txt`, identifies itself with a user agent, waits at least five seconds between requests, and uses conditional request headers when available. The filtered discovery URL targets `GCE 'O' Levels`, `Additional Mathematics`, and `Exam Papers`.

PDF processing rejects files larger than 25 MiB, documents over 100 pages, malformed PDFs, and question numbers without the same numbered section in a published solution. Discovery and extraction create unvalidated candidates only; the tutor-reviewed manifest is the trust boundary.

## Quality checks

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/amath-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/amath-uv-cache uv run mypy src
```
