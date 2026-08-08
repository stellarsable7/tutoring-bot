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

## Deploy with Docker Compose

Install Docker Desktop, then copy the example environment file and replace every placeholder:

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f bot
```

Alternatively, create the file with hidden prompts and restrictive permissions; the script
validates the Telegram token before asking for the OpenRouter key:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run python scripts/configure_env.py \
  --telegram-id YOUR_NUMERIC_TELEGRAM_ID
```

The bot container waits for PostgreSQL, applies every Alembic migration, and starts Telegram
long polling. Only one bot replica should run during the pilot because it also owns the
minute-based assignment scheduler. Stop it with `docker compose down`; the named PostgreSQL
volume is retained. Use `docker compose down -v` only when you deliberately intend to erase the
pilot database.

Create the Telegram bot with BotFather, put its token in `.env`, and obtain your numeric Telegram
ID from a trusted ID bot or Telegram API update. Set a random callback secret of at least 32
characters. Create an OpenRouter API key and set `AMATH_OPENROUTER_API_KEY`. The bot refuses to
start when this key is missing. Never commit `.env`.

The marking pipeline uses OpenRouter's `openrouter/free` router. It never automatically switches
to paid inference, so inference charges are zero, but free-provider capacity, latency, available
model, and answer quality can vary. Student images, OCR text, and published solutions leave the
deployment machine and are sent through OpenRouter to the selected free provider. Free providers
may log requests or use them for training; review the current provider policies and disclose this
before enrolment. Every proposed grade must be reviewed by the tutor before it becomes final.

Set production configuration:

```bash
export AMATH_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost/amath_bot'
export AMATH_TIMEZONE='Asia/Singapore'
export AMATH_TELEGRAM_BOT_TOKEN='123456:replace-with-botfather-token'
export AMATH_TUTOR_TELEGRAM_ID='123456789'
export AMATH_REVIEW_CALLBACK_SECRET='replace-with-at-least-32-random-characters'
export AMATH_OPENROUTER_API_KEY='replace-with-openrouter-api-key'
```

Apply migrations:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run alembic upgrade head
```

## Telegram operation

Only `AMATH_TUTOR_TELEGRAM_ID` can run tutor commands. Students join through a
single-use `/start` invite and must consent before an account is created.

- `/help` lists the tutor commands and their argument formats.
- `/invite` creates a single-use student enrolment link.
- `/students` lists enrolled students.
- `/schedule NAME weekdays HH:MM [COUNT]` configures delivery (for example, `18:30`).
- `/assign NAME OBJECTIVE` explicitly assigns an eligible catalogue question.
- `/pause NAME` pauses delivery; `/resume NAME` resumes it.
- `/remove "NAME" CONFIRM` permanently removes a student and their associated bot records.
- `/clear CONFIRM` deletes up to 500 recent private-chat messages for both sides, subject to
  Telegram's 48-hour deletion limit.
- `/clearstudent "NAME" CONFIRM` does the same in an enrolled student's bot chat.
- `/progress NAME` shows learning progress.
- `/review` opens the next flagged marking review.

The bot supports either polling or webhook deployment through the aiogram
dispatcher. The assignment scheduler ticks once per minute in `Asia/Singapore` and uses database
uniqueness constraints to prevent duplicate daily assignments. Independently, the marking worker
wakes every 3 seconds. Transient failures persist retry deadlines of 3, 10, 30, 30, then 60
seconds; further attempts continue every 60 seconds indefinitely. Authentication or configuration
failures retry hourly. These deadlines survive process restarts.
Source attribution and solution metadata are retained for the tutor and are not
included in student-facing message text.

To rotate the OpenRouter key, replace `AMATH_OPENROUTER_API_KEY` in `.env`, then recreate the bot
container so Compose loads the new value:

```bash
docker compose up -d --no-deps --force-recreate bot
docker compose ps --status running bot
docker compose logs --since 2m bot
```

Confirm the bot is listed as running (and healthy if a health check is configured) and that the
recent log contains `starting Telegram polling`. Only then revoke the old key in OpenRouter. Do
not print the old or new key in logs or shell history.

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
