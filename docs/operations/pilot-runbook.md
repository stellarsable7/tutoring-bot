# A-Math Bot Pilot Runbook

This runbook is the operating checklist for the four-week, tutor-supervised pilot. Do not
enrol students until the catalogue, marking evaluation, provider privacy controls, backups,
and deletion alerts have all passed their launch checks.

## Deploy

Production releases are automated from GitHub. Every successful push to the `deploy` branch
runs tests, Ruff, and mypy; builds an immutable image in Artifact Registry; and updates the
singleton Compute Engine VM through IAP. GitHub authenticates with Workload Identity Federation,
not a service-account key. Application secrets remain in Google Secret Manager.

The deployed image starts only the bot. The VM deployment script runs `alembic upgrade head`
before replacing the container, and it restores the previous image if Telegram polling does not
start. Migrations must remain backward-compatible with the immediately previous release because
application rollback does not downgrade the database.

To inspect production without printing secrets:

```bash
gcloud compute ssh amath-bot --zone=asia-southeast1-b --tunnel-through-iap \
  --command='sudo docker ps --filter name=amath-bot'
gcloud compute ssh amath-bot --zone=asia-southeast1-b --tunnel-through-iap \
  --command='sudo journalctl CONTAINER_NAME=amath-bot --since=-10m --no-pager'
```

To redeploy or roll back deliberately, obtain an immutable digest from Artifact Registry and run
the installed deployment command through IAP:

```bash
gcloud compute ssh amath-bot --zone=asia-southeast1-b --tunnel-through-iap \
  --command="sudo /usr/local/sbin/deploy-amath-bot 'asia-southeast1-docker.pkg.dev/chloe-tutoring-bot/amath-bot/amath-bot@sha256:DIGEST'"
```

Do not use mutable tags for a manual rollback.

Use Python 3.12, PostgreSQL 16, and a dedicated Telegram bot. Store configuration in the
deployment secret manager, never in source control:

```bash
export AMATH_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@HOST/amath_bot'
export AMATH_TIMEZONE='Asia/Singapore'
export AMATH_TELEGRAM_BOT_TOKEN='BOTFATHER_TOKEN'
export AMATH_TUTOR_TELEGRAM_ID='ALLOWLISTED_NUMERIC_ID'
export AMATH_REVIEW_CALLBACK_SECRET='AT_LEAST_32_RANDOM_CHARACTERS'
export AMATH_OPENROUTER_API_KEY='OPENROUTER_API_KEY'
UV_CACHE_DIR=/tmp/amath-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/amath-uv-cache uv run alembic upgrade head
```

Validate configuration with `AMATH_TELEGRAM_DRY_RUN=true uv run python -m amath_bot.app`.
The service fails at startup if `AMATH_OPENROUTER_API_KEY` is absent. Run the service under a
supervisor with one scheduler leader. Restrict database and log access to the operator and tutor;
enable encrypted daily PostgreSQL backups and test a restore before launch. Backups must follow
the same retention policy as primary records.

## Student and catalogue controls

Only the configured tutor ID may create single-use invites or use tutor/review controls.
Before issuing an invite, explain the recorded personal data and AI processing. Enrolment must
stop if consent is declined. A tutor must verify each question boundary, marks, objective tags,
and matching published worked solution; final-answer-only material remains ineligible.

The bot uses OpenRouter's `google/gemma-4-26b-a4b-it:free` model for transcription and
`qwen/qwen3-vl-32b-instruct` for grading. Grading is paid inference, so verify current OpenRouter
pricing and account limits during preflight. Capacity, latency, availability, and answer quality
are variable. Student images, extracted OCR text, and published
solutions leave the deployment machine and pass through OpenRouter to a free provider. Those
providers may log requests or train on them. Review and record the current OpenRouter and selected
provider data terms outside the student database, disclose them during consent, and do not enrol a
student unless they are acceptable. Every proposed grade requires tutor review before it is final.

## Preflight and dry run

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/amath-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/amath-uv-cache uv run mypy src
UV_CACHE_DIR=/tmp/amath-uv-cache uv run python -m amath_bot.evaluation.runner \
  tests/evaluation/fixtures/sample_set.json
AMATH_TELEGRAM_DRY_RUN=true UV_CACHE_DIR=/tmp/amath-uv-cache \
  uv run python -m amath_bot.cli simulate-day --date 2026-08-05
```

The evaluator must report at least 90% exact agreement, 95% within-one-mark agreement, zero
missed material ambiguities, and zero answer leaks. Replace the sample fixture with the approved
consented labelled pilot set for the actual launch decision.

## Daily operation

Each morning, check delivery and processing-failure aggregates. Each day, the tutor runs
`/review`, compares the image/transcription with the linked published scheme, and approves,
overrides, or requests a clearer upload before the 24-hour deadline. Never put student names,
Telegram IDs, images, or transcription text in metric labels or application logs.

Alert immediately when `submission_media_deletion_failures_total` increases. Confirm the retry
worker succeeds and `media_deleted_at` is recorded; do not manually mark deletion complete.
Unreviewed flagged attempts become unresolved at 24 hours, retain no media, and receive no final
mark. Review access logs and pending-review counts at the end of each day.

The assignment scheduler runs once per minute; this is separate from the marking worker, which
wakes every 3 seconds. For transient provider failures, persisted retry deadlines are 3, 10, 30,
30, then 60 seconds, followed by 60-second retries indefinitely. Authentication and configuration
failures retry hourly. Because deadlines are stored in PostgreSQL, restarting the bot does not
reset the sequence. Investigate a sustained retry backlog rather than repeatedly restarting.

To rotate the OpenRouter key, update `AMATH_OPENROUTER_API_KEY` in `.env` or the deployment secret
manager. Compose does not reload environment variables on `restart`, so recreate the bot and
inspect its state and recent startup log:

```bash
docker compose up -d --no-deps --force-recreate bot
docker compose ps --status running bot
docker compose logs --since 2m bot
```

Confirm the bot is listed as running (and healthy if a health check is configured) and the recent
log contains `starting Telegram polling`. Keep the old key active until both checks pass, then
revoke it in OpenRouter. Do not print either key.

## Outages and incidents

During a Telegram or AI-provider outage, pause new delivery and keep retry queues bounded. Do not
extend media retention to compensate. If marking cannot complete within the window, delete media
and mark the attempt unresolved. After recovery, verify idempotent assignment delivery before
unpausing.

For suspected data exposure: pause the service, preserve privacy-safe audit metadata, rotate bot,
database, and callback secrets as applicable, determine affected records and retention state,
notify the responsible operator, and follow the organisation's breach-notification procedure.
Do not copy student media into tickets or chat.

## Weekly and final review

Weekly, review aggregate completion and on-time rates, exact and within-one-mark agreement,
override rate, review duration, processing failures, deletion failures, mastery trends, and missed
assignments. Investigate categories rather than individual identities in exported reports.

At four weeks, launch beyond the pilot only if accuracy and ambiguity gates still pass on the
approved labelled set, there were no answer leaks, every media item was deleted within policy,
all incidents are closed, and the tutor judges the workload sustainable. Otherwise pause,
remediate, and repeat evaluation before expansion.
