# A-Math Bot

Telegram-based daily practice for the 2026 Singapore-Cambridge GCE O-Level Additional Mathematics syllabus 4049.

This implementation provides:

- a versioned 4049 syllabus map;
- policy-enforced storage for source-linked questions;
- rate-limited discovery of O-Level Additional Mathematics exam papers from Holy Grail's public library;
- bounded extraction of matching question and published-solution sections; and
- a tutor-reviewed catalogue import command;
- consent-gated Telegram onboarding and tutor-only controls; and
- idempotent daily scheduling and retry-safe delivery.

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
export AMATH_TELEGRAM_BOT_TOKEN='123456:replace-with-botfather-token'
export AMATH_TUTOR_TELEGRAM_ID='123456789'
export AMATH_REVIEW_CALLBACK_SECRET='replace-with-at-least-32-random-characters'
```

Apply migrations:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run alembic upgrade head
```

## Telegram operation

Only `AMATH_TUTOR_TELEGRAM_ID` can run tutor commands. Students join through a
single-use `/start` invite and must consent before an account is created.

- `/students` lists enrolled students.
- `/schedule` configures weekdays, hour, and daily count.
- `/assign` explicitly assigns an eligible catalogue question.
- `/pause` pauses delivery.
- `/progress` shows learning progress.

The bot supports either polling or webhook deployment through the aiogram
dispatcher. The delivery scheduler ticks once per minute in `Asia/Singapore` and
uses database uniqueness constraints to prevent duplicate daily assignments.
Source attribution and solution metadata are retained for the tutor and are not
included in student-facing message text.

To validate configuration without connecting to Telegram:

```bash
AMATH_TELEGRAM_DRY_RUN=true UV_CACHE_DIR=/tmp/amath-uv-cache uv run python -m amath_bot.app
```

The expected log line is `telegram dry-run enabled`.

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

Run only the daily-delivery acceptance workflow with:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/acceptance/test_daily_delivery.py -q
```

Run the deterministic pilot-day exercise without contacting Telegram or an AI provider:

```bash
AMATH_TELEGRAM_DRY_RUN=true UV_CACHE_DIR=/tmp/amath-uv-cache \
  uv run python -m amath_bot.cli simulate-day --date 2026-08-05
```

Before enrolling students, run the labelled evaluation and confirm it exits successfully:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run python -m amath_bot.evaluation.runner \
  tests/evaluation/fixtures/sample_set.json
```

See [the pilot operations runbook](docs/operations/pilot-runbook.md) for deployment,
privacy, alerting, outage, review, and incident procedures.
