# OpenRouter Free Marking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace local Ollama marking with `openrouter/free` and persist retry timing in PostgreSQL using the exact `3, 10, 30, 30, 60...` schedule.

**Architecture:** Keep `LocalVisionPipeline` behind its existing `VisionOCR` protocol, move shared response models into a provider-neutral module, and add an `httpx`-based OpenRouter adapter with strict structured outputs. Extend `submission_attempts` with durable retry metadata; a three-second scheduler wake-up claims only due rows and applies either the normal retry sequence or a one-hour operational delay.

**Tech Stack:** Python 3.12, httpx, Pydantic 2, SQLAlchemy 2 async, Alembic, APScheduler 3, PostgreSQL 16, pytest/pytest-asyncio, Ruff, mypy.

## Parallelisation Map

The root orchestrator owns wave transitions, integration checks, and commits. Within a wave, it
dispatches one fresh subagent per task. Each subagent receives only its task text plus the approved
design spec and must not edit files owned by another task in that wave.

```text
Wave 1 — independent foundations
├── Agent A → Task 1: provider-neutral response models and error taxonomy
├── Agent B → Task 2: retry columns, migration, and submission defaults
└── Agent C → Task 3: OpenRouter settings and startup validation
          │
          ▼ orchestrator review + focused tests
Wave 2 — independent behavior
├── Agent D → Task 4: OpenRouter HTTP/vision adapter
└── Agent E → Task 5: due-row claiming and persistent retry policy
          │
          ▼ orchestrator review + provider/job test suites
Wave 3 — independent integration surfaces
├── Agent F → Task 6: runtime and scheduler integration; remove Ollama runtime
└── Agent G → Task 7: deployment configuration and operator documentation
          │
          ▼ orchestrator review + static configuration checks
Wave 4 — orchestrator-owned visible E2E and release gate
└── Root orchestrator inline → Task 8: live provider, PostgreSQL retry, Telegram journey,
                                and full verification
```

Do not run Wave 2 until every Wave 1 interface is merged. Do not run Wave 3 until both Wave 2
tasks pass. The orchestrator runs the listed focused tests after every wave and resolves conflicts
before dispatching the next wave.

## Wave Summary

- **Wave 1 — Foundations:** establishes stable shared types, durable database state, and validated
  configuration. These tasks touch disjoint production files and can proceed concurrently.
- **Wave 2 — Behavior:** implements the actual remote model calls and retry state machine in
  parallel. Both consume Wave 1 contracts but do not modify each other's files.
- **Wave 3 — Integration:** wires the finished components into polling while deployment/docs are
  updated independently. Ollama is removed only after the replacement is operational.
- **Wave 4 — Visible E2E and release gate:** is performed inline by the root orchestrator, never
  delegated. It validates a live free-routed vision request, PostgreSQL retry persistence, and the
  Telegram submission-to-review journey while the user can observe results and discuss failures.
  It then runs the complete suite, static analysis, dry-run startup, and stale-Ollama scan.

## E2E Ownership and Visibility

Only tests that cross meaningful production boundaries are E2E:

1. **Live OpenRouter contract:** real HTTPS, bearer authentication, `openrouter/free`, image input,
   provider capability filtering, strict structured output, and local Pydantic validation.
2. **PostgreSQL retry lifecycle:** real Alembic schema, PostgreSQL timestamp/index semantics,
   durable `queued → processing → queued` transitions, and eligibility at persisted retry times.
3. **Telegram marking journey:** real Telegram upload/download, PostgreSQL queue, live OpenRouter
   OCR and grading, and the final tutor-review notification and `/review` surface.

These sections must be implemented and run inline by the root orchestrator. They must not be
assigned to a subagent, because the user needs a continuous conversation with the process. Before
each E2E checkpoint, the orchestrator reports the boundary being exercised, exact command or user
action, expected observable result, and any credential/external-service prerequisite. During a
long-running check it posts a concise update at least once per minute. Afterward it reports elapsed
time, selected OpenRouter model when available, database status transitions, retry metadata, and a
sanitized failure summary. It never prints API keys, Telegram tokens, student images, or OCR text.

After each E2E checkpoint, the orchestrator pauses for the user to confirm what worked or describe
what did not before continuing. Deterministic tests for Pydantic schemas, retry-delay arithmetic,
HTTP status classification, settings parsing, and scheduler registration remain delegated because
external services would make those checks slower and less reproducible without adding coverage.

## Global Constraints

- Use the model slug `openrouter/free` as a code-level constant; do not permit a paid-model override.
- Send images as `data:image/png;base64,...` content through OpenRouter Chat Completions.
- Require strict JSON Schema support and keep all existing Pydantic and grading-invariant checks.
- Never include API keys, HTTP response bodies, student images, or student OCR text in stored errors or logs.
- Retry transient failures after `3, 10, 30, 30, 60` seconds, then every 60 seconds indefinitely.
- Retry authentication or request-configuration rejection after one hour while retaining the row as queued.
- Preserve mandatory tutor review for every generated mark.
- Do not persist partial OCR results in this iteration.
- Automated tests must use mocked HTTP and must never require a real OpenRouter key.

---

### Task 1: Provider-Neutral Result Models and Error Taxonomy

**Wave:** 1, Agent A

**Files:**
- Create: `src/amath_bot/providers/vision_models.py`
- Modify: `src/amath_bot/providers/ollama_vision.py`
- Modify: `src/amath_bot/marking/local_pipeline.py:13-27`
- Modify: `src/amath_bot/jobs/mark_attempt.py:13`
- Test: `tests/marking/test_local_pipeline_contract.py`

**Interfaces:**
- Consumes: existing `OCRResult`, `ProposedDecision`, and `ProposedGrade` definitions.
- Produces: `OCRResult`, `ProposedDecision`, and `ProposedGrade` from
  `amath_bot.providers.vision_models`; `MarkingConfigurationError(MarkingPipelineError)` from
  `amath_bot.jobs.mark_attempt`; unchanged `VisionOCR` signatures.

- [ ] **Step 1: Write a failing provider-neutral contract test**

Create `tests/marking/test_local_pipeline_contract.py`:

```python
from amath_bot.jobs.mark_attempt import MarkingConfigurationError, MarkingPipelineError
from amath_bot.marking.local_pipeline import VisionOCR
from amath_bot.providers.vision_models import OCRResult, ProposedGrade


def test_provider_models_are_not_owned_by_ollama() -> None:
    assert OCRResult.__module__ == "amath_bot.providers.vision_models"
    assert ProposedGrade.__module__ == "amath_bot.providers.vision_models"
    assert VisionOCR.__module__ == "amath_bot.marking.local_pipeline"


def test_configuration_error_is_a_marking_pipeline_error() -> None:
    assert issubclass(MarkingConfigurationError, MarkingPipelineError)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/marking/test_local_pipeline_contract.py -v
```

Expected: FAIL because `vision_models` and `MarkingConfigurationError` do not exist.

- [ ] **Step 3: Move the models and add the error subtype**

Create `src/amath_bot/providers/vision_models.py` with the three Pydantic models currently at the
top of `ollama_vision.py`, preserving every field and constraint exactly:

```python
from pydantic import BaseModel, ConfigDict, Field


class OCRResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    complete: bool
    lines: tuple[str, ...]
    unclear: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)


class ProposedDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    part: str
    marks_awarded: int = Field(ge=0)
    maximum: int = Field(ge=1)
    scheme_evidence: str = Field(min_length=1)
    reason: str
    student_lines: tuple[str, ...]
    provider_confidence: float = Field(ge=0, le=1)


class ProposedGrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total: int = Field(ge=0)
    decisions: tuple[ProposedDecision, ...]
    feedback: tuple[str, ...]
    unclear: tuple[str, ...] = ()
```

Import these classes from the neutral module in both `ollama_vision.py` and `local_pipeline.py`.
In `mark_attempt.py`, add:

```python
class MarkingConfigurationError(MarkingPipelineError):
    """A safe operator-actionable provider configuration failure."""
```

- [ ] **Step 4: Run contract and current marking tests**

Run:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/marking/test_local_pipeline_contract.py tests/marking tests/acceptance/test_submission_marking.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the neutral contracts**

```bash
git add src/amath_bot/providers/vision_models.py src/amath_bot/providers/ollama_vision.py \
  src/amath_bot/marking/local_pipeline.py src/amath_bot/jobs/mark_attempt.py \
  tests/marking/test_local_pipeline_contract.py
git commit -m "refactor: make vision result contracts provider neutral"
```

### Task 2: Persistent Retry Schema and Submission Defaults

**Wave:** 1, Agent B

**Files:**
- Create: `alembic/versions/0012_marking_retries.py`
- Modify: `src/amath_bot/submissions/tables.py:1-31`
- Modify: `src/amath_bot/submissions/service.py:107-127`
- Create: `tests/submissions/test_retry_schema.py`
- Modify: `tests/submissions/test_grouping.py`

**Interfaces:**
- Consumes: `submission_attempts` table at migration revision `0011_solution_assets`.
- Produces: `AttemptRow.marking_attempts: int`, `AttemptRow.marking_retry_at: datetime | None`,
  and `AttemptRow.marking_last_error: str | None`; Alembic revision `0012_marking_retries`.

- [ ] **Step 1: Write failing ORM schema tests**

Create `tests/submissions/test_retry_schema.py`:

```python
from sqlalchemy import CheckConstraint

from amath_bot.submissions.tables import AttemptRow


def test_attempt_retry_columns_have_safe_defaults() -> None:
    table = AttemptRow.__table__
    assert table.c.marking_attempts.nullable is False
    assert str(table.c.marking_attempts.server_default.arg) == "0"
    assert table.c.marking_retry_at.nullable is True
    assert table.c.marking_retry_at.index is True
    assert table.c.marking_last_error.type.length == 500
    assert any(
        isinstance(item, CheckConstraint)
        and item.name == "ck_submission_attempts_marking_attempts_nonnegative"
        for item in table.constraints
    )
```

Extend the queued-submission test in `tests/submissions/test_grouping.py` to load its `AttemptRow`
and assert:

```python
assert row.marking_attempts == 0
assert row.marking_retry_at is None
assert row.marking_last_error is None
```

Also add an idempotency assertion: submitting a row already in `queued` must not reset nonzero
retry metadata.

- [ ] **Step 2: Run the focused tests to verify they fail**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/submissions/test_retry_schema.py tests/submissions/test_grouping.py -v
```

Expected: FAIL because the retry columns do not exist.

- [ ] **Step 3: Add ORM fields and migration**

Add a table constraint and fields in `AttemptRow`:

```python
__table_args__ = (
    CheckConstraint(
        "marking_attempts >= 0",
        name="ck_submission_attempts_marking_attempts_nonnegative",
    ),
)

marking_attempts: Mapped[int] = mapped_column(
    Integer, default=0, server_default="0", nullable=False
)
marking_retry_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True, index=True
)
marking_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

Create migration `0012_marking_retries.py` with `down_revision = "0011_solution_assets"`. Its
upgrade must add the three columns, named check constraint, and
`ix_submission_attempts_marking_retry_at`. Its downgrade must drop the index, constraint, and
columns in reverse order. Use `server_default=sa.text("0")` for existing rows.

When `SubmissionService.submit()` changes `draft` to `queued`, explicitly set the three retry
values to `0`, `None`, and `None`. Keep the early return for an already queued attempt before these
assignments so retry history is not erased.

- [ ] **Step 4: Run schema and submission tests**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/submissions/test_retry_schema.py tests/submissions/test_grouping.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit retry persistence**

```bash
git add alembic/versions/0012_marking_retries.py src/amath_bot/submissions/tables.py \
  src/amath_bot/submissions/service.py tests/submissions/test_retry_schema.py \
  tests/submissions/test_grouping.py
git commit -m "feat: persist marking retry state"
```

### Task 3: OpenRouter Settings and Startup Validation

**Wave:** 1, Agent C

**Files:**
- Modify: `src/amath_bot/settings.py`
- Modify: `src/amath_bot/app.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: existing `Settings` environment prefix `AMATH_`.
- Produces: `Settings.openrouter_api_key: str | None` and
  `Settings.openrouter_url: str = "https://openrouter.ai/api/v1"`; polling startup requires a
  nonblank key, while dry-run remains key-free.

- [ ] **Step 1: Write failing configuration tests**

Extend `tests/test_app.py`:

```python
import pytest

from amath_bot.app import validate_polling_settings


def test_openrouter_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.openrouter_api_key is None
    assert settings.openrouter_url == "https://openrouter.ai/api/v1"
    assert not hasattr(settings, "ollama_url")
    assert not hasattr(settings, "ollama_vision_model")


def test_polling_requires_openrouter_key() -> None:
    settings = Settings(
        _env_file=None,
        telegram_bot_token="token",
        tutor_telegram_id=123,
        review_callback_secret="x" * 32,
    )
    with pytest.raises(ValueError, match="AMATH_OPENROUTER_API_KEY"):
        validate_polling_settings(settings)


def test_polling_accepts_openrouter_key() -> None:
    settings = Settings(
        _env_file=None,
        telegram_bot_token="token",
        tutor_telegram_id=123,
        review_callback_secret="x" * 32,
        openrouter_api_key="test-key",
    )
    validate_polling_settings(settings)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/test_app.py -v
```

Expected: FAIL because the settings and validation function do not exist.

- [ ] **Step 3: Implement settings and validation**

Replace Ollama fields in `Settings` with:

```python
openrouter_api_key: str | None = None
openrouter_url: str = "https://openrouter.ai/api/v1"
```

Remove `marking_interval_seconds`; the exact three-second cadence will become a runtime constant in
Task 6. Extract `validate_polling_settings(settings: Settings) -> None` in `app.py`. It must retain
the existing Telegram/tutor/callback checks and additionally reject a missing or whitespace-only
OpenRouter key with a message naming `AMATH_OPENROUTER_API_KEY`. Call it only after the dry-run
early return, then invoke `run_polling`.

- [ ] **Step 4: Run app tests**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/test_app.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit settings validation**

```bash
git add src/amath_bot/settings.py src/amath_bot/app.py tests/test_app.py
git commit -m "feat: validate OpenRouter polling configuration"
```

### Task 4: OpenRouter Vision Adapter

**Wave:** 2, Agent D

**Files:**
- Create: `src/amath_bot/providers/openrouter_vision.py`
- Create: `tests/providers/test_openrouter_vision.py`

**Interfaces:**
- Consumes: neutral `OCRResult`, `ProposedDecision`, `ProposedGrade`; `MarkingPipelineError` and
  `MarkingConfigurationError` from Task 1.
- Produces:

```python
OPENROUTER_MODEL = "openrouter/free"

class OpenRouterVisionOCR:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None: ...

    async def transcribe(self, image: bytes) -> OCRResult: ...

    async def propose_grade(
        self,
        *,
        transcription: tuple[str, ...],
        solution_images: tuple[bytes, ...],
        maximum: int,
    ) -> ProposedGrade: ...
```

- [ ] **Step 1: Write the failing OCR request-contract test**

Create `tests/providers/test_openrouter_vision.py` using `httpx.MockTransport`. The handler must
capture `json.loads(request.content)`, assert the URL and bearer header, and return:

```python
httpx.Response(
    200,
    json={
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "complete": True,
                            "lines": ["x = 2"],
                            "unclear": [],
                            "confidence": 0.9,
                        }
                    )
                }
            }
        ]
    },
)
```

Assert model `openrouter/free`, `stream is False`, `temperature == 0`,
`provider == {"require_parameters": True}`, strict `ocr_result` JSON Schema equal to
`OCRResult.model_json_schema()`, text-first content, and the exact base64 PNG data URL.

- [ ] **Step 2: Run the OCR test to verify it fails**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/providers/test_openrouter_vision.py::test_transcribe_sends_openrouter_free_strict_vision_request -v
```

Expected: FAIL because `OpenRouterVisionOCR` does not exist.

- [ ] **Step 3: Implement the shared completion helper and OCR method**

Use an injected `httpx.AsyncClient` and post to
`f"{base_url.rstrip('/')}/chat/completions"`. Construct content like:

```python
content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
content.extend(
    {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64,"
            + base64.b64encode(image).decode("ascii")
        },
    }
    for image in images
)
```

Use this response format:

```python
"response_format": {
    "type": "json_schema",
    "json_schema": {
        "name": schema_name,
        "strict": True,
        "schema": schema.model_json_schema(),
    },
},
"provider": {"require_parameters": True},
```

Parse `choices[0].message.content` with `schema.model_validate_json(content)`. Reject refusals and
non-string content. When the response contains a nonempty top-level `model` string, log
`"OpenRouter completed <stage> via <model>"` at INFO; this is safe operational metadata and gives
the live E2E check visibility into the free route selected. Map HTTP 429/5xx, transport errors,
malformed envelopes, malformed JSON, and schema violations to a safe stage-specific
`MarkingPipelineError`.

- [ ] **Step 4: Write and run the grading request test**

Add `test_propose_grade_sends_all_solution_images_and_recalculates_total`. Supply two image byte
strings and two numbered OCR lines. Return a valid grade with a deliberately incorrect provider
`total`; assert image order, strict `proposed_grade` schema, prompt maximum and numbered lines, and
that the returned total equals the sum of awarded decisions.

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/providers/test_openrouter_vision.py::test_propose_grade_sends_all_solution_images_and_recalculates_total -v
```

Expected before implementation completion: FAIL. Expected after completing `propose_grade`: PASS.

- [ ] **Step 5: Add grading-invariant tests and implementation**

Parameterize these responses and assert `MarkingPipelineError`:

```python
cases = (
    "awarded total exceeds question maximum",
    "aggregate decision maxima exceeds question maximum",
    "decision award exceeds its maximum",
    "awarded decision has no student_lines",
)
```

Copy the existing invariant logic exactly, including recalculating and replacing `total`.

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/providers/test_openrouter_vision.py -k invariant -v
```

Expected: PASS.

- [ ] **Step 6: Add retryable and operational failure tests**

Parameterize retryable statuses `429, 500, 502, 503`, `httpx.ConnectError`, and
`httpx.ReadTimeout`; each must raise `MarkingPipelineError` but not
`MarkingConfigurationError`. Parameterize operational statuses `400, 401, 403, 422`; each must
raise `MarkingConfigurationError`. Include a sentinel in the HTTP body and assert it does not
appear in the exception text.

For an operational response, raise only a fixed safe message:

```python
raise MarkingConfigurationError(
    f"OpenRouter rejected provider request ({response.status_code})"
)
```

Add cases for non-JSON HTTP bodies, missing/empty `choices`, missing `message`, null/non-string
content, refusal, malformed content JSON, extra fields, and out-of-range confidence. These are
ordinary retryable `MarkingPipelineError` instances.

Add a `caplog` assertion using a successful response containing
`"model": "example/free-vision-model"`; assert the selected model is logged but the response
content and bearer key are not.

- [ ] **Step 7: Run provider tests and static checks**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/providers/test_openrouter_vision.py -q
UV_CACHE_DIR=/tmp/amath-uv-cache uv run ruff check \
  src/amath_bot/providers/openrouter_vision.py tests/providers/test_openrouter_vision.py
UV_CACHE_DIR=/tmp/amath-uv-cache uv run mypy src/amath_bot/providers/openrouter_vision.py
```

Expected: all PASS.

- [ ] **Step 8: Commit the adapter**

```bash
git add src/amath_bot/providers/openrouter_vision.py tests/providers/test_openrouter_vision.py
git commit -m "feat: call OpenRouter free vision models"
```

### Task 5: Due-Row Claiming and Persistent Retry Policy

**Wave:** 2, Agent E

**Files:**
- Modify: `src/amath_bot/jobs/mark_attempt.py`
- Create: `tests/jobs/test_mark_attempt.py`

**Interfaces:**
- Consumes: Task 1 `MarkingConfigurationError`; Task 2 retry fields.
- Produces: `retry_delay(failed_attempt: int) -> timedelta`; `MarkAttemptJob(..., now: Callable[[], datetime] = ...)`; due-only one-row claiming and persistent retry transitions.

- [ ] **Step 1: Write the failing pure retry-policy test**

Create `tests/jobs/test_mark_attempt.py`:

```python
from datetime import timedelta

import pytest

from amath_bot.jobs.mark_attempt import retry_delay


@pytest.mark.parametrize(
    ("attempt", "seconds"),
    [(1, 3), (2, 10), (3, 30), (4, 30), (5, 60), (6, 60), (20, 60)],
)
def test_retry_delay(attempt: int, seconds: int) -> None:
    assert retry_delay(attempt) == timedelta(seconds=seconds)
```

- [ ] **Step 2: Run the policy test to verify it fails**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/jobs/test_mark_attempt.py::test_retry_delay -v
```

Expected: FAIL because `retry_delay` does not exist.

- [ ] **Step 3: Implement the pure retry function**

```python
def retry_delay(failed_attempt: int) -> timedelta:
    if failed_attempt < 1:
        raise ValueError("failed attempt must be positive")
    seconds = (3, 10, 30, 30)[failed_attempt - 1] if failed_attempt <= 4 else 60
    return timedelta(seconds=seconds)
```

Run the test again; expected PASS.

- [ ] **Step 4: Write due-row selection tests**

Build an in-memory SQLite fixture following `tests/acceptance/test_submission_marking.py`. Insert
attempts that are queued with retry times `None`, before now, exactly now, and after now, plus one
nonqueued row. Use a recording fake pipeline. Assert only the first three queued rows are passed to
the pipeline, in ID order.

Construct the job with a deterministic clock:

```python
job = MarkAttemptJob(
    session,
    pipeline=pipeline,
    notifier=notifier,
    media=media,
    now=lambda: fixed_now,
)
```

- [ ] **Step 5: Implement one-row due claiming**

Add the `now` callable to the constructor. Add `_claim_next(now)` using:

```python
select(AttemptRow).where(
    AttemptRow.status == "queued",
    or_(
        AttemptRow.marking_retry_at.is_(None),
        AttemptRow.marking_retry_at <= now,
    ),
).order_by(AttemptRow.id).limit(1).with_for_update(skip_locked=True)
```

Set the claimed row to `processing` and commit before returning it. Change `run_pending()` to
claim and process one row at a time until `_claim_next` returns `None`. Do not preload and release
locks for the whole queue.

- [ ] **Step 6: Write persistent transient-retry tests**

Use a pipeline that raises `MarkingPipelineError("safe transient failure")`. After each invocation,
refresh the row and assert status `queued`, incremented `marking_attempts`, stored safe diagnostic,
and exact `marking_retry_at`. Create a new `MarkAttemptJob` for each invocation and prove the row
is skipped one second before its deadline and selected exactly at its deadline. Cover the sequence
through attempt six.

Normalize SQLite timestamps with `.replace(tzinfo=UTC)` when the driver returns a naive value.

- [ ] **Step 7: Implement failure persistence and safe diagnostics**

Add a fixed safe diagnostic interface to `MarkingPipelineError` rather than storing arbitrary
exception details:

```python
class MarkingPipelineError(RuntimeError):
    def __init__(self, diagnostic: str = "marking pipeline failed") -> None:
        super().__init__(diagnostic)
        self.diagnostic = diagnostic[:500]
```

All provider-created messages are fixed strings or numeric HTTP statuses. On ordinary failure:

```python
attempt.status = "queued"
attempt.marking_attempts += 1
attempt.marking_last_error = error.diagnostic
attempt.marking_retry_at = self._now() + retry_delay(attempt.marking_attempts)
await self._session.commit()
```

Move the `outcome.total > outcome.maximum` check inside the same failure-persistence path so it
receives retry timing instead of escaping the worker loop.

- [ ] **Step 8: Add operational-delay and success-reset tests**

Test that `MarkingConfigurationError("OpenRouter rejected provider request (401)")` produces
exactly `now + timedelta(hours=1)`. Test a later success clears `marking_retry_at` and
`marking_last_error` while retaining `marking_attempts`, and preserves the existing marked/flagged
result behavior.

- [ ] **Step 9: Run job and acceptance tests**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/jobs/test_mark_attempt.py tests/acceptance/test_submission_marking.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit the retry worker**

```bash
git add src/amath_bot/jobs/mark_attempt.py tests/jobs/test_mark_attempt.py
git commit -m "feat: retry due marking jobs with persistent backoff"
```

### Task 6: Runtime and Scheduler Integration

**Wave:** 3, Agent F

**Files:**
- Modify: `src/amath_bot/scheduler.py`
- Modify: `src/amath_bot/runtime.py`
- Create: `tests/test_scheduler.py`
- Modify: `tests/test_runtime.py`
- Delete: `src/amath_bot/providers/ollama_vision.py`

**Interfaces:**
- Consumes: Task 3 settings, Task 4 `OpenRouterVisionOCR`, Task 5 due-row job.
- Produces: `add_marking_job(scheduler, callback) -> None`, fixed
  `MARKING_INTERVAL_SECONDS = 3`, and runtime-owned shared `httpx.AsyncClient` lifecycle.

- [ ] **Step 1: Write failing scheduler registration tests**

Create or extend `tests/test_scheduler.py`:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from amath_bot.scheduler import MARKING_INTERVAL_SECONDS, add_marking_job


async def callback() -> None:
    return None


def test_marking_job_polls_every_three_seconds() -> None:
    scheduler = AsyncIOScheduler()
    add_marking_job(scheduler, callback)
    job = scheduler.get_job("openrouter-marking")
    assert job is not None
    assert MARKING_INTERVAL_SECONDS == 3
    assert int(job.trigger.interval.total_seconds()) == 3
    assert job.max_instances == 1
    assert job.coalesce is True
```

- [ ] **Step 2: Run the scheduler test to verify it fails**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/test_scheduler.py -v
```

Expected: FAIL because the marking registration helper does not exist.

- [ ] **Step 3: Implement scheduler registration**

In `scheduler.py`, add:

```python
MARKING_INTERVAL_SECONDS = 3


def add_marking_job(
    scheduler: AsyncIOScheduler,
    callback: Callable[[], Awaitable[None]],
) -> None:
    scheduler.add_job(
        callback,
        trigger="interval",
        seconds=MARKING_INTERVAL_SECONDS,
        id="openrouter-marking",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
```

Use `collections.abc.Awaitable` and `Callable` for typing.

- [ ] **Step 4: Write runtime configuration-guard tests**

Extend `tests/test_runtime.py` with a direct-call test that supplies otherwise valid settings but
no key and asserts `run_polling()` raises `ValueError` naming `AMATH_OPENROUTER_API_KEY` before
Telegram or database work begins. This duplicates the boundary intentionally so direct callers
cannot bypass `app.py` validation.

- [ ] **Step 5: Wire OpenRouter and client lifecycle**

In `runtime.py`, validate and narrow the key first:

```python
api_key = settings.openrouter_api_key
if api_key is None or not api_key.strip():
    raise ValueError("AMATH_OPENROUTER_API_KEY is required")
```

Create one `httpx.AsyncClient(timeout=180)` for the polling lifetime. Construct
`OpenRouterVisionOCR(client, api_key=api_key, base_url=settings.openrouter_url)` inside the marking
callback, register it with `add_marking_job`, and close the client in `finally`. Keep the database
session per marking invocation. Rename the job ID from `local-vision-marking` to
`openrouter-marking`.

Delete `ollama_vision.py` only after `rg` confirms no production import remains.

- [ ] **Step 6: Run runtime, scheduler, provider, and job tests**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/test_scheduler.py tests/test_runtime.py tests/providers/test_openrouter_vision.py \
  tests/jobs/test_mark_attempt.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit runtime integration**

```bash
git add src/amath_bot/scheduler.py src/amath_bot/runtime.py tests/test_scheduler.py \
  tests/test_runtime.py src/amath_bot/providers/ollama_vision.py
git commit -m "feat: run marking through OpenRouter"
```

### Task 7: Deployment Configuration and Operator Documentation

**Wave:** 3, Agent G

**Files:**
- Modify: `.env.example`
- Modify: `compose.yaml`
- Modify: `scripts/configure_env.py`
- Create: `tests/test_configure_env.py`
- Modify: `README.md`
- Modify: `docs/operations/pilot-runbook.md`

**Interfaces:**
- Consumes: Task 3 environment names and Task 6 operational behavior.
- Produces: secure deployment input for `AMATH_OPENROUTER_API_KEY` and accurate privacy/retry runbook.

- [ ] **Step 1: Write failing environment-script tests**

In `tests/test_configure_env.py`, call `main()` after monkeypatching `sys.argv` with a temporary
`--output` path and `--telegram-id 123`. Monkeypatch `getpass.getpass` with consecutive values
`123456:test-telegram-token` and `test-openrouter-key`. Replace `urllib.request.urlopen` with a
context-manager fake whose JSON body is
`{"ok": true, "result": {"username": "test_bot"}}`. Assert `main()` returns zero and the generated
content contains:

```text
AMATH_OPENROUTER_API_KEY=test-openrouter-key
```

Assert the key is not printed and the output file mode is `0o600`. Add a blank-key case that raises
`ValueError` naming `AMATH_OPENROUTER_API_KEY`.

- [ ] **Step 2: Run the script tests to verify they fail**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/test_configure_env.py -v
```

Expected: FAIL because the script does not collect the OpenRouter key.

- [ ] **Step 3: Update environment generation and Compose**

Prompt for the key with `getpass.getpass`, reject blank input, write it only to the mode-0600 env
file, and never echo it. Add this placeholder to `.env.example`:

```dotenv
AMATH_OPENROUTER_API_KEY=replace-with-openrouter-api-key
```

In `compose.yaml`, replace both Ollama variables with:

```yaml
AMATH_OPENROUTER_API_KEY: ${AMATH_OPENROUTER_API_KEY}
AMATH_OPENROUTER_URL: ${AMATH_OPENROUTER_URL:-https://openrouter.ai/api/v1}
```

- [ ] **Step 4: Update README and pilot runbook**

Document all of these facts explicitly:

- the adapter uses `openrouter/free` and never `openrouter/auto`;
- inference price is zero, but capacity, latency, model identity, and quality vary;
- student images, OCR text, and solution pages leave the machine;
- free providers may log or train on inputs/outputs;
- every generated mark still requires tutor approval;
- the worker wakes every three seconds but respects persisted retry deadlines;
- transient retries follow `3, 10, 30, 30, 60...` indefinitely;
- auth/config rejection stays queued and retries hourly;
- missing keys fail polling startup; and
- key rotation requires updating `.env` and restarting the bot.

Remove the current README/runbook claims that no provider is selected or that marking is local or
private. Preserve the distinct once-per-minute assignment scheduler documentation.

- [ ] **Step 5: Verify deployment text and configuration**

```bash
AMATH_OPENROUTER_API_KEY=test-key POSTGRES_PASSWORD=test-password \
  docker compose config >/tmp/amath-compose-config.yaml
rg -n "OPENROUTER|OpenRouter|openrouter/free|marking_retry" \
  .env.example compose.yaml README.md docs/operations/pilot-runbook.md
rg -n "OLLAMA|Ollama|ollama|locally generated|local vision" \
  .env.example compose.yaml scripts README.md docs/operations || true
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/test_configure_env.py -q
```

Expected: Compose validates, OpenRouter references are present, stale Ollama/local-marking claims
are absent, and tests pass.

- [ ] **Step 6: Commit deployment and docs**

```bash
git add .env.example compose.yaml scripts/configure_env.py tests/test_configure_env.py \
  README.md docs/operations/pilot-runbook.md
git commit -m "docs: configure OpenRouter free marking"
```

### Task 8: Visible E2E and Integrated Release Verification

**Wave:** 4, root orchestrator inline. Do not delegate any step in this task.

**Files:**
- Create: `tests/e2e/test_openrouter_live.py`
- Create: `tests/e2e/test_marking_retry_postgres.py`
- Modify: `pyproject.toml`
- Modify only files implicated by a failing verification; do not broaden scope.

**Interfaces:**
- Consumes: all preceding tasks, `AMATH_OPENROUTER_API_KEY`, a disposable
  `AMATH_E2E_DATABASE_URL`, and user access to the configured Telegram tutor/student chats.
- Produces: visible evidence for live OpenRouter routing, PostgreSQL retry durability, the Telegram
  submission-to-review journey, a clean migration chain, and no stale Ollama dependency.

- [ ] **Step 1: Announce the inline E2E protocol and run deterministic preflight**

Tell the user that Wave 4 is now running inline, list the three E2E checkpoints, and state that
outputs will be sanitized. Confirm presence—not value—of both required environment variables:

```bash
test -n "${AMATH_OPENROUTER_API_KEY:-}" && echo "OpenRouter key: configured"
test -n "${AMATH_E2E_DATABASE_URL:-}" && echo "E2E database: configured"
```

Then run:

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/providers/test_openrouter_vision.py tests/jobs/test_mark_attempt.py \
  tests/submissions/test_retry_schema.py tests/test_app.py tests/test_runtime.py \
  tests/test_scheduler.py -q
```

Expected: PASS. Report pass/fail counts before continuing. If a prerequisite or deterministic test
fails, remain inline, explain the exact blocker, and let the user respond before continuing.

- [ ] **Step 2: Write a live OpenRouter E2E test inline**

Register the marker in `pyproject.toml`:

```toml
markers = [
  "e2e: requires explicitly configured external services",
]
```

Create `tests/e2e/test_openrouter_live.py` with `pytest.mark.e2e`. Skip the module unless both
`AMATH_RUN_LIVE_E2E=1` and `AMATH_OPENROUTER_API_KEY` exist, so an ordinary full test run never
contacts an external provider merely because a developer has a key in their environment. In the
test:

1. use Pillow to render black text `2x + 3 = 7`, `2x = 4`, and `x = 2` onto a white PNG held in a
   `BytesIO` buffer;
2. construct a real `httpx.AsyncClient(timeout=180)` and `OpenRouterVisionOCR`;
3. call `transcribe()` and assert `lines` is nonempty and `0 <= confidence <= 1`;
4. render `data/solution_assets/sps-2025-p1-q1-solution.pdf` to PNG with PyMuPDF;
5. call `propose_grade()` with the returned OCR lines and the published question maximum from
   `data/catalogue/sps-2025-paper-1.json`; and
6. assert the response is a `ProposedGrade`, its total equals the sum of decision awards, and its
   total does not exceed that published maximum.

The test must not print OCR lines, prompts, images, response bodies, or the key. INFO logs may show
only the selected OpenRouter model and stage.

- [ ] **Step 3: Run the live OpenRouter checkpoint visibly**

Before running, tell the user this makes two real free-tier requests and may expose the synthetic
image and public solution to the selected free provider. Then run without delegating:

```bash
AMATH_RUN_LIVE_E2E=1 UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/e2e/test_openrouter_live.py -m e2e -v -s --log-cli-level=INFO
```

Expected: PASS with safe INFO lines identifying the selected free model for OCR and grading. Report
elapsed time, selected model(s), and schema-validation outcome. If it fails because no compatible
free route is available, show only status/category, discuss it with the user, and retry only after
the user chooses to continue.

- [ ] **Step 4: Write and run the PostgreSQL retry E2E inline**

Create `tests/e2e/test_marking_retry_postgres.py`, marked `e2e` and skipped unless both
`AMATH_RUN_POSTGRES_E2E=1` and `AMATH_E2E_DATABASE_URL` exist. Point Alembic at that disposable
database, migrate to head, and use an async SQLAlchemy session against the same URL. Reuse the
complete tutor/student/question/assignment factory shape from
`tests/acceptance/test_submission_marking.py`; do not depend on pre-existing rows.

The test must submit one attempt and drive fresh `MarkAttemptJob` instances with an injected clock
and a recording pipeline through these observable states:

```text
queued/null retry
processing
queued/attempts=1/retry=now+3s
not selected at now+2s
selected at now+3s
queued/attempts=2/retry=now+13s
successful and flagged/retry=null/error=null
```

It must query the database through a newly opened session between worker invocations, proving the
state survives process/session boundaries rather than relying on an identity map. Run:

```bash
AMATH_DATABASE_URL="$AMATH_E2E_DATABASE_URL" \
  UV_CACHE_DIR=/tmp/amath-uv-cache uv run alembic upgrade head
AMATH_DATABASE_URL="$AMATH_E2E_DATABASE_URL" \
  AMATH_RUN_POSTGRES_E2E=1 UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest \
  tests/e2e/test_marking_retry_postgres.py -m e2e -v -s
AMATH_DATABASE_URL="$AMATH_E2E_DATABASE_URL" \
  UV_CACHE_DIR=/tmp/amath-uv-cache uv run alembic downgrade 0011_solution_assets
AMATH_DATABASE_URL="$AMATH_E2E_DATABASE_URL" \
  UV_CACHE_DIR=/tmp/amath-uv-cache uv run alembic upgrade head
```

Expected: all commands exit zero. Report the migration revisions and each sanitized status,
attempt-count, and retry-time transition. Never run downgrade against the production database.
Pause for the user's observations before the Telegram checkpoint.

- [ ] **Step 5: Run the Telegram submission-to-review E2E interactively**

Confirm `.env` contains the key without displaying it, then start the real stack inline:

```bash
docker compose up --build -d
docker compose ps
docker compose logs --since 2m bot
```

Tell the user when the bot is ready. Ask the user to use the configured tutor chat to assign a
catalogue question with a published solution, submit a clearly legible student image, and confirm
submission. While they interact, poll only sanitized operational state:

```bash
docker compose exec -T postgres psql -U amath -d amath_bot -c \
  "SELECT id, status, marking_attempts, marking_retry_at, \
   marking_last_error IS NOT NULL AS has_error \
   FROM submission_attempts ORDER BY id DESC LIMIT 1;"
docker compose logs --since 5m bot | \
  rg "OpenRouter completed|submission\(s\) are ready|ERROR|WARNING"
```

Expected journey:

```text
Telegram upload → draft → queued → processing → flagged
                                      │
                                      └→ tutor receives “ready” notification → /review shows result
```

Report every observed state change and selected model without exposing submission contents. If the
row retries, report attempt number, next retry time, and sanitized error category, then keep the
user updated at least once per minute. Ask the user whether the Telegram messages and `/review`
content are correct before stopping or continuing. Do not run `docker compose down -v`; preserve
the database volume.

- [ ] **Step 6: Run acceptance marking tests**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest tests/acceptance/test_submission_marking.py -q
```

Expected: PASS with queued submissions still becoming marked or tutor-flagged through the fake
pipeline.

- [ ] **Step 7: Run the full quality gate**

```bash
UV_CACHE_DIR=/tmp/amath-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/amath-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/amath-uv-cache uv run mypy src
AMATH_TELEGRAM_DRY_RUN=true UV_CACHE_DIR=/tmp/amath-uv-cache uv run python -m amath_bot.app
```

Expected: all commands exit zero; dry-run logs that it is enabled without requiring an API key.

- [ ] **Step 8: Scan for stale implementation and secret risks**

```bash
rg -n "OLLAMA|Ollama|ollama|qwen3-vl|local-vision-marking" \
  src tests compose.yaml .env.example README.md docs/operations || true
rg -n "OPENROUTER_API_KEY=.*sk-or|Bearer sk-or" . --glob '!.git/**' || true
git diff --check
git status --short
```

Expected: no stale Ollama runtime references, no committed real-looking OpenRouter secret, no
whitespace errors, and only intended changes.

- [ ] **Step 9: Commit E2E coverage and scoped verification fixes**

First commit the orchestrator-owned E2E tests:

```bash
git add pyproject.toml tests/e2e/test_openrouter_live.py tests/e2e/test_marking_retry_postgres.py
git commit -m "test: cover live OpenRouter marking flow"
```

If verification also required scoped fixes, confirm `git diff --name-only` contains only files
from Tasks 1–8, then stage the tracked fixes and commit them:

```bash
git add -u
git commit -m "fix: complete OpenRouter marking verification"
```

If no additional fixes were needed, do not create a second empty commit. Record the exact E2E and
verification evidence in the orchestrator's completion report, including any checkpoint the user
chose to defer.

## Orchestrator Review Gates

After each wave, the orchestrator must:

1. read every subagent summary and inspect its diff;
2. confirm agents did not edit overlapping files within the wave;
3. run that wave's focused test commands;
4. run `git diff --check` and `git status --short`;
5. correct interface drift before starting the next wave; and
6. dispatch a fresh review subagent for requirements compliance when implementation is complete.

The final orchestrator—not an implementation subagent—runs the complete verification commands and
reports the evidence.
