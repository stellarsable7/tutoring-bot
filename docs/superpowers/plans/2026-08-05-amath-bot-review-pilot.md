# A-Math Bot Review and Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the tutor review loop, enforce deletion and access controls, calculate learning progress, and prove the four-week pilot launch gates.

**Architecture:** Build review, privacy, and progress services over immutable marking evidence. Use scheduled deletion jobs and an offline labelled evaluation runner; keep operational metrics free of images and full transcriptions.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2, PostgreSQL 16, pytest, Prometheus client

---

### Task 1: Persist reviews and tutor overrides

**Files:**
- Create: `src/amath_bot/reviews/models.py`
- Create: `src/amath_bot/reviews/service.py`
- Create: `src/amath_bot/reviews/tables.py`
- Create: `alembic/versions/0005_reviews.py`
- Create: `tests/reviews/test_service.py`

- [ ] **Step 1: Write failing override audit test**

```python
async def test_override_preserves_original_grade(review_service, flagged_attempt) -> None:
    review = await review_service.override(flagged_attempt.id, tutor_id=100, total=3, feedback="Line 2: method mark not earned.")
    assert review.original_total == 4
    assert review.final_total == 3
    assert review.tutor_id == 100
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/reviews/test_service.py -v`

Expected: FAIL because reviews are missing.

- [ ] **Step 3: Implement immutable audit records**

Store original decisions, final decisions, tutor ID, reason, and timestamps. Support approve, override marks, replace safe feedback, and request resubmission. Re-run the answer-leak validator on tutor-edited feedback before sending it to a student.

- [ ] **Step 4: Apply migration and test**

Run: `uv run alembic upgrade head && uv run pytest tests/reviews/test_service.py -v`

Expected: review tests pass.

- [ ] **Step 5: Commit review domain**

```bash
git add src/amath_bot/reviews alembic/versions/0005_reviews.py tests/reviews
git commit -m "feat: audit tutor marking overrides"
```

### Task 2: Implement Telegram `/review`

**Files:**
- Create: `src/amath_bot/telegram/reviews.py`
- Create: `tests/telegram/test_reviews.py`

- [ ] **Step 1: Write failing review flow test**

```python
async def test_tutor_approves_flagged_attempt(review_handler, tutor_message, flagged_attempt) -> None:
    card = await review_handler.next(tutor_message)
    assert card.attempt_id == flagged_attempt.id
    result = await review_handler.approve(tutor_message, card.callback_token)
    assert result.text == "Mark approved and student notified."
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/telegram/test_reviews.py -v`

Expected: FAIL because handler is missing.

- [ ] **Step 3: Implement tutor-only review cards**

Show expiring media, transcription, published scheme link, proposed decisions, confidence breakdown, and reason for flagging. Buttons perform approve, edit marks, replace feedback, and request clearer upload. Sign callback payloads and verify tutor ID and attempt state on every action.

- [ ] **Step 4: Run authorization and review tests**

Run: `uv run pytest tests/telegram/test_reviews.py tests/telegram/test_tutor_auth.py -v`

Expected: tutor flow passes and student callback attempts are rejected.

- [ ] **Step 5: Commit Telegram review**

```bash
git add src/amath_bot/telegram/reviews.py tests/telegram/test_reviews.py
git commit -m "feat: review provisional marks in Telegram"
```

### Task 3: Enforce the 24-hour media lifecycle

**Files:**
- Create: `src/amath_bot/privacy/media_lifecycle.py`
- Create: `src/amath_bot/jobs/delete_expired_media.py`
- Create: `tests/privacy/test_media_lifecycle.py`

- [ ] **Step 1: Write failing expiry test**

```python
async def test_unreviewed_flag_deletes_media_and_stays_unresolved(lifecycle, flagged_attempt) -> None:
    await lifecycle.expire(now=flagged_attempt.created_at + timedelta(hours=24, seconds=1))
    refreshed = await lifecycle.get(flagged_attempt.id)
    assert refreshed.media_deleted_at is not None
    assert refreshed.status == "unresolved"
    assert refreshed.final_total is None
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/privacy/test_media_lifecycle.py -v`

Expected: FAIL because lifecycle service is missing.

- [ ] **Step 3: Implement deletion state machine**

Delete high-confidence media after the marking transaction, reviewed media after the review transaction, and unresolved flagged media at 24 hours. Retry deletion failures with capped exponential backoff, increment a privacy alert metric, and never mark a failed deletion as complete. Attempt deletion of Telegram bot-accessible media messages and record only success/failure metadata.

- [ ] **Step 4: Run lifecycle tests**

Run: `uv run pytest tests/privacy/test_media_lifecycle.py -v`

Expected: finalization, expiry, retry, and unresolved-state tests pass.

- [ ] **Step 5: Commit lifecycle enforcement**

```bash
git add src/amath_bot/privacy src/amath_bot/jobs/delete_expired_media.py tests/privacy
git commit -m "feat: enforce submission media deletion"
```

### Task 4: Calculate mastery and remediation progress

**Files:**
- Create: `src/amath_bot/progress/models.py`
- Create: `src/amath_bot/progress/service.py`
- Create: `tests/progress/test_mastery.py`

- [ ] **Step 1: Write failing mastery test**

```python
def test_recent_failure_lowers_mastery_and_schedules_near_transfer(progress_service) -> None:
    state = progress_service.update(previous=0.70, score_ratio=0.20, confidence=0.95)
    assert state.mastery < 0.70
    assert state.remediation_required is True
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/progress/test_mastery.py -v`

Expected: FAIL because progress service is missing.

- [ ] **Step 3: Implement transparent mastery updates**

Use an exponentially weighted score with `new = 0.7 * previous + 0.3 * score_ratio`; ignore unresolved attempts and multiply the update contribution by marking confidence. Require near-transfer remediation below `0.50`, broaden question framing above `0.70`, and schedule spaced review at 3, 7, and 21 days after a successful attempt.

- [ ] **Step 4: Run mastery tests**

Run: `uv run pytest tests/progress/test_mastery.py tests/assignments/test_selector.py -v`

Expected: mastery and selector integration tests pass.

- [ ] **Step 5: Commit progress model**

```bash
git add src/amath_bot/progress tests/progress
git commit -m "feat: track mastery and remediation"
```

### Task 5: Add privacy-safe progress and operational metrics

**Files:**
- Create: `src/amath_bot/metrics.py`
- Modify: `src/amath_bot/telegram/tutor.py`
- Create: `tests/test_metrics.py`
- Create: `tests/telegram/test_progress.py`

- [ ] **Step 1: Write failing metrics test**

```python
def test_metrics_never_include_identity_or_transcription(metric_registry) -> None:
    payload = metric_registry.render()
    assert "telegram_id" not in payload
    assert "transcription" not in payload
    assert "submission_media_deletion_failures_total" in payload
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_metrics.py tests/telegram/test_progress.py -v`

Expected: FAIL because metrics are missing.

- [ ] **Step 3: Implement aggregates and `/progress`**

Expose completion rate, on-time rate, exact and within-one-mark agreement, override rate, review duration, processing failures, and deletion failures without student identity labels. Render tutor progress using database aggregates: current mastery by objective, recent marks, common error categories, missed assignments, and pending reviews.

- [ ] **Step 4: Run metrics and privacy checks**

Run: `uv run pytest tests/test_metrics.py tests/telegram/test_progress.py -v`

Expected: aggregate values pass and forbidden labels are absent.

- [ ] **Step 5: Commit metrics**

```bash
git add src/amath_bot/metrics.py src/amath_bot/telegram/tutor.py tests/test_metrics.py tests/telegram/test_progress.py
git commit -m "feat: report privacy-safe pilot progress"
```

### Task 6: Build the labelled marking evaluation runner

**Files:**
- Create: `src/amath_bot/evaluation/models.py`
- Create: `src/amath_bot/evaluation/runner.py`
- Create: `tests/evaluation/fixtures/sample_set.json`
- Create: `tests/evaluation/test_runner.py`

- [ ] **Step 1: Write failing launch-gate test**

```python
def test_launch_gate_requires_accuracy_and_ambiguity_flags(evaluation_runner, labelled_set) -> None:
    report = evaluation_runner.run(labelled_set)
    assert report.exact_agreement >= 0.90
    assert report.within_one_mark >= 0.95
    assert report.missed_material_ambiguities == 0
    assert report.answer_leaks == 0
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/evaluation/test_runner.py -v`

Expected: FAIL because evaluation package is missing.

- [ ] **Step 3: Implement reproducible evaluation reports**

Define labelled cases with consent provenance, expected transcription, tutor total, expected flags, and forbidden answer strings. Report exact agreement, within-one-mark agreement, transcription errors, missed flags, answer leaks, and cases by handwriting/notation category. Exit non-zero when any approved launch gate fails.

- [ ] **Step 4: Run evaluation tests**

Run: `uv run pytest tests/evaluation/test_runner.py -v && uv run python -m amath_bot.evaluation.runner tests/evaluation/fixtures/sample_set.json`

Expected: tests pass and the fixture report prints every launch metric.

- [ ] **Step 5: Commit evaluator**

```bash
git add src/amath_bot/evaluation tests/evaluation
git commit -m "feat: enforce marking pilot launch gates"
```

### Task 7: End-to-end pilot readiness

**Files:**
- Create: `tests/acceptance/test_pilot_workflow.py`
- Create: `docs/operations/pilot-runbook.md`
- Modify: `README.md`

- [ ] **Step 1: Write the full pilot acceptance test**

```python
async def test_daily_assignment_submission_review_and_deletion(system, fake_telegram, clock) -> None:
    student = await system.join_student("ABC123", telegram_id=200, consent=True)
    assignment = await system.send_due_assignment(student.id)
    await system.submit_fixture(assignment.id, "ambiguous-two-page-attempt.pdf")
    result = await system.run_marking_jobs()
    assert result.status == "provisional_review_required"
    await system.tutor_approve(result.attempt_id, tutor_id=100)
    assert await system.media_exists(result.attempt_id) is False
    assert fake_telegram.last_message_for(200).text.startswith("Mark finalized:")
```

- [ ] **Step 2: Run all checks**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`

Expected: all checks pass.

- [ ] **Step 3: Write the pilot runbook**

Document deployment configuration, tutor allowlisting, student consent, catalogue checks, provider data controls, backups, media deletion alerts, outage handling, daily review, weekly metric review, incident response, and the four-week success review. Include exact commands for migrations, service startup, evaluation, and log/metric inspection.

- [ ] **Step 4: Execute a dry-run day**

Run: `AMATH_TELEGRAM_DRY_RUN=true uv run python -m amath_bot.cli simulate-day --date 2026-08-05`

Expected: one assignment is selected and rendered, a fixture submission is provisionally marked, a tutor review is simulated, and media deletion is confirmed.

- [ ] **Step 5: Commit pilot readiness**

```bash
git add README.md docs/operations/pilot-runbook.md tests/acceptance/test_pilot_workflow.py
git commit -m "docs: complete amath bot pilot runbook"
```
