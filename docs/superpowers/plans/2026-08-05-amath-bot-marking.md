# A-Math Bot Handwriting and Marking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept grouped handwritten submissions and produce evidence-backed provisional method marks using vision transcription, SymPy verification, and only published worked solutions or mark schemes.

**Architecture:** Treat media ingestion, transcription, symbolic verification, and scheme application as separate ports. Persist every intermediate confidence and evidence record; never let the reasoning provider create an authoritative answer or missing marking step.

**Tech Stack:** Python 3.12, aiogram 3, Pydantic 2, PyMuPDF, Pillow, SymPy, cloud vision/reasoning provider behind protocols, PostgreSQL, pytest

---

### Task 1: Group images and PDFs into an attempt

**Files:**
- Create: `src/amath_bot/submissions/models.py`
- Create: `src/amath_bot/submissions/service.py`
- Create: `src/amath_bot/submissions/tables.py`
- Create: `alembic/versions/0004_submissions.py`
- Create: `tests/submissions/test_grouping.py`

- [ ] **Step 1: Write failing grouping test**

```python
async def test_multiple_uploads_remain_draft_until_submit(submission_service, assignment) -> None:
    attempt = await submission_service.add_image(assignment.id, "tg-file-1")
    await submission_service.add_image(assignment.id, "tg-file-2")
    assert attempt.status == "draft"
    submitted = await submission_service.submit(attempt.id)
    assert submitted.status == "queued"
    assert submitted.media_count == 2
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/submissions/test_grouping.py -v`

Expected: FAIL because submissions are missing.

- [ ] **Step 3: Implement draft, submit, and immutable page order**

Persist attempt status and ordered media references. Accept JPEG, PNG, HEIC converted to JPEG, or one PDF; reject mixing a PDF with images in the same attempt. `submit` must be idempotent and must reject an empty attempt.

- [ ] **Step 4: Apply migration and run tests**

Run: `uv run alembic upgrade head && uv run pytest tests/submissions/test_grouping.py -v`

Expected: grouping tests pass.

- [ ] **Step 5: Commit submissions**

```bash
git add src/amath_bot/submissions alembic/versions/0004_submissions.py tests/submissions
git commit -m "feat: group handwritten submission media"
```

### Task 2: Add encrypted temporary media storage and quality checks

**Files:**
- Create: `src/amath_bot/media/store.py`
- Create: `src/amath_bot/media/quality.py`
- Create: `tests/media/test_store.py`
- Create: `tests/media/test_quality.py`

- [ ] **Step 1: Write failing lifecycle test**

```python
async def test_store_encrypts_and_deletes_media(media_store, sample_jpeg) -> None:
    handle = await media_store.put(sample_jpeg, expires_in_hours=24)
    assert await media_store.read(handle) == sample_jpeg
    await media_store.delete(handle)
    with pytest.raises(MediaNotFound):
        await media_store.read(handle)
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/media -v`

Expected: FAIL because media package is missing.

- [ ] **Step 3: Implement storage and deterministic preflight checks**

Define a `TemporaryMediaStore` protocol and a local encrypted implementation for tests/development. Check minimum resolution, blur using Laplacian variance, extreme rotation, empty pages, PDF page count, and maximum payload size. Return typed issues such as `TOO_BLURRY`, `TOO_SMALL`, and `PAGE_LIMIT_EXCEEDED`; do not call AI for failed preflight media.

- [ ] **Step 4: Run media tests**

Run: `uv run pytest tests/media -v`

Expected: encryption, deletion, expiry, and quality fixture tests pass.

- [ ] **Step 5: Commit media lifecycle**

```bash
git add src/amath_bot/media tests/media
git commit -m "feat: secure and validate temporary media"
```

### Task 3: Define structured handwriting transcription

**Files:**
- Create: `src/amath_bot/marking/transcription.py`
- Create: `src/amath_bot/providers/vision.py`
- Create: `tests/marking/test_transcription.py`

- [ ] **Step 1: Write failing schema test**

```python
def test_transcription_keeps_line_confidence_and_crossouts() -> None:
    result = Transcription.model_validate({
        "pages": [{"number": 1, "lines": [
            {"index": 1, "latex": "x^2-5x+6=0", "confidence": 0.98, "crossed_out": False}
        ]}],
        "complete": True,
    })
    assert result.pages[0].lines[0].confidence == 0.98
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/marking/test_transcription.py -v`

Expected: FAIL because transcription schema is missing.

- [ ] **Step 3: Implement strict schemas and provider protocol**

Create immutable `TranscribedLine`, `TranscribedPage`, and `Transcription` Pydantic models. Confidence is constrained to `[0,1]`; every line includes LaTeX, literal text, bounding box, and crossed-out status. Define `VisionTranscriber.transcribe(media: tuple[MediaHandle, ...]) -> Transcription`. Reject provider output with extra fields or missing confidence rather than guessing.

- [ ] **Step 4: Test valid and malformed provider fixtures**

Run: `uv run pytest tests/marking/test_transcription.py -v`

Expected: valid fixtures pass and malformed fixtures raise `TranscriptionSchemaError`.

- [ ] **Step 5: Commit transcription boundary**

```bash
git add src/amath_bot/marking src/amath_bot/providers tests/marking/test_transcription.py
git commit -m "feat: define confidence-aware transcription"
```

### Task 4: Parse published schemes and verify mathematics

**Files:**
- Create: `src/amath_bot/marking/schemes.py`
- Create: `src/amath_bot/marking/symbolic.py`
- Create: `tests/marking/test_schemes.py`
- Create: `tests/marking/test_symbolic.py`

- [ ] **Step 1: Write failing symbolic tests**

```python
def test_equivalent_factorised_and_expanded_forms() -> None:
    assert equivalent("(x-2)*(x-3)", "x**2-5*x+6") is True


def test_unsafe_expression_is_rejected() -> None:
    with pytest.raises(UnsupportedExpression):
        equivalent("__import__('os')", "0")
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/marking/test_schemes.py tests/marking/test_symbolic.py -v`

Expected: FAIL because scheme and symbolic modules are missing.

- [ ] **Step 3: Implement authoritative scheme types and safe SymPy parsing**

Define `MarkingStep(code, mark_type, marks, expected_latex, guidance, dependencies)` and `PublishedScheme(source_url, total_marks, steps)`. Validate that step marks sum to total marks and that every dependency refers to an earlier step. Parse only an allowlist of symbols and SymPy functions in a resource-limited worker; never use Python `eval`.

- [ ] **Step 4: Run scheme and symbolic tests**

Run: `uv run pytest tests/marking/test_schemes.py tests/marking/test_symbolic.py -v`

Expected: schema, equivalence, timeout, and unsafe-input tests pass.

- [ ] **Step 5: Commit scheme verification**

```bash
git add src/amath_bot/marking tests/marking/test_schemes.py tests/marking/test_symbolic.py
git commit -m "feat: verify work against published schemes"
```

### Task 5: Apply marks with evidence and confidence

**Files:**
- Create: `src/amath_bot/marking/grader.py`
- Create: `src/amath_bot/providers/reasoning.py`
- Create: `tests/marking/test_grader.py`

- [ ] **Step 1: Write failing grading test**

```python
async def test_each_awarded_mark_has_scheme_and_line_evidence(grader, transcription, scheme) -> None:
    result = await grader.grade(transcription, scheme)
    assert result.total <= scheme.total_marks
    assert all(decision.scheme_step_code for decision in result.decisions)
    assert all(decision.student_line_indexes for decision in result.decisions if decision.awarded)
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/marking/test_grader.py -v`

Expected: FAIL because grader is missing.

- [ ] **Step 3: Implement bounded grading**

Define `MarkDecision`, `GradeResult`, and a `ReasoningMarker` protocol. Pass the immutable published scheme, transcription, and symbolic-check results to the provider. Reject any returned step code absent from the scheme, any total above the scheme total, or any invented expected answer. Compute overall confidence from recognition, scheme match, symbolic agreement, and provider confidence; keep the four values separately.

- [ ] **Step 4: Run adversarial grading fixtures**

Run: `uv run pytest tests/marking/test_grader.py -v`

Expected: normal marking passes; invented-step, inflated-total, and missing-evidence outputs are rejected.

- [ ] **Step 5: Commit grader**

```bash
git add src/amath_bot/marking/grader.py src/amath_bot/providers/reasoning.py tests/marking/test_grader.py
git commit -m "feat: produce evidence-backed provisional marks"
```

### Task 6: Generate safe line feedback and mandatory flags

**Files:**
- Create: `src/amath_bot/marking/feedback.py`
- Create: `src/amath_bot/marking/review_policy.py`
- Create: `tests/marking/test_feedback.py`
- Create: `tests/marking/test_review_policy.py`

- [ ] **Step 1: Write failing no-answer test**

```python
def test_feedback_rejects_answer_or_corrected_work() -> None:
    with pytest.raises(UnsafeFeedback):
        validate_feedback("The correct answer is x = 2; replace line 3 with x = 2.", forbidden={"x = 2"})
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/marking/test_feedback.py tests/marking/test_review_policy.py -v`

Expected: FAIL because policies are missing.

- [ ] **Step 3: Implement feedback and review rules**

Generate comments from mark decisions using templates such as `Line {n}: {reason}; {marks_awarded}/{marks_available}.` Build a forbidden-answer set from all expected expressions in the published scheme and reject feedback containing them or correction phrases. Force review for recognition below `0.90`, overall marking confidence below `0.85`, symbolic/provider disagreement, incomplete pages, or an alternative method without scheme coverage.

- [ ] **Step 4: Run policy tests**

Run: `uv run pytest tests/marking/test_feedback.py tests/marking/test_review_policy.py -v`

Expected: answer-leak and low-confidence cases are blocked or flagged.

- [ ] **Step 5: Commit safety policies**

```bash
git add src/amath_bot/marking tests/marking/test_feedback.py tests/marking/test_review_policy.py
git commit -m "feat: enforce safe feedback and marking review"
```

### Task 7: Connect Telegram submissions to the marking queue

**Files:**
- Create: `src/amath_bot/telegram/submissions.py`
- Create: `src/amath_bot/jobs/mark_attempt.py`
- Create: `tests/acceptance/test_submission_marking.py`

- [ ] **Step 1: Write failing end-to-end test**

```python
async def test_student_submits_two_pages_and_receives_provisional_feedback(system, fake_telegram) -> None:
    await system.receive_photo(student_id=200, file_id="page-1")
    await system.receive_photo(student_id=200, file_id="page-2")
    await system.submit(student_id=200)
    await system.run_marking_jobs()
    reply = fake_telegram.last_message_for(200)
    assert "Provisional: 4/5" in reply.text
    assert "correct answer" not in reply.text.lower()
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/acceptance/test_submission_marking.py -v`

Expected: FAIL because the queue integration is missing.

- [ ] **Step 3: Implement orchestration**

Add photo/PDF handlers, **Submit attempt** confirmation, preflight feedback, durable job state, provider calls, provisional response rendering, and review creation. Do not delete flagged media here; record a 24-hour expiry. Delete high-confidence media after the grade and feedback transaction commits.

- [ ] **Step 4: Run marking acceptance and quality checks**

Run: `uv run pytest tests/acceptance/test_submission_marking.py -v && uv run ruff check src tests && uv run mypy src`

Expected: all checks pass.

- [ ] **Step 5: Commit marking pipeline**

```bash
git add src/amath_bot/telegram/submissions.py src/amath_bot/jobs tests/acceptance/test_submission_marking.py
git commit -m "feat: mark grouped Telegram submissions"
```
