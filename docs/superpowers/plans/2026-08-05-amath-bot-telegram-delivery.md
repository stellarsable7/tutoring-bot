# A-Math Bot Telegram Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver source-linked daily assignments to invited students and let the single tutor control schedules and topics entirely through Telegram.

**Architecture:** Add an aiogram adapter around application services for identity, scheduling, selection, and delivery. Store schedules and assignment state in PostgreSQL; keep Telegram-specific objects outside the domain layer.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2, APScheduler 3, PostgreSQL 16, pytest

---

### Task 1: Add tutor and student identity with single-use invites

**Files:**
- Create: `src/amath_bot/people/models.py`
- Create: `src/amath_bot/people/service.py`
- Create: `src/amath_bot/people/tables.py`
- Create: `alembic/versions/0002_people.py`
- Create: `tests/people/test_invites.py`

- [ ] **Step 1: Write failing invite tests**

```python
async def test_invite_is_single_use(people_service) -> None:
    invite = await people_service.create_invite(tutor_telegram_id=100)
    student = await people_service.redeem(invite.code, telegram_id=200, display_name="Ada")
    assert student.syllabus_version == "4049-2026"
    with pytest.raises(InviteAlreadyUsed):
        await people_service.redeem(invite.code, telegram_id=201, display_name="Ben")
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/people/test_invites.py -v`

Expected: FAIL because people service is missing.

- [ ] **Step 3: Implement identities and atomic invite redemption**

Create `Tutor`, `Student`, and `Invite` domain models. Store only Telegram ID, display name, syllabus version, consent timestamp, pause state, and timestamps. Redeem invites inside one transaction with a row lock; hard-code the pilot to one allowlisted tutor and syllabus `4049-2026`.

- [ ] **Step 4: Apply migration and test**

Run: `uv run alembic upgrade head && uv run pytest tests/people/test_invites.py -v`

Expected: migration and invite tests pass.

- [ ] **Step 5: Commit identities**

```bash
git add src/amath_bot/people alembic/versions/0002_people.py tests/people
git commit -m "feat: add tutor invites and student identities"
```

### Task 2: Implement adaptive candidate ranking

**Files:**
- Create: `src/amath_bot/assignments/models.py`
- Create: `src/amath_bot/assignments/selector.py`
- Create: `tests/assignments/test_selector.py`

- [ ] **Step 1: Write failing remediation test**

```python
def test_weak_objective_prefers_near_transfer_not_exact_repeat() -> None:
    selected = select_question(
        candidates=[same_method_new_values, unrelated_question, exact_previous_question],
        mastery={"A1.complete-square": 0.25},
        prior_source_ids={exact_previous_question.id},
        pinned_objectives={"A1.complete-square"},
    )
    assert selected.id == same_method_new_values.id
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/assignments/test_selector.py -v`

Expected: FAIL because selector is missing.

- [ ] **Step 3: Implement a deterministic score**

Use a pure `score_candidate` function with explicit weights: pinned objective `+100`, weak objective `+(1-mastery)*40`, overdue review `+20`, difficulty-distance penalty `-10` per band, prior exact source `-1000`, and near-transfer after an error `+30`. Break ties by least-recently-used objective, then stable source ID. Add an `allow_exact_repeat` override used only by explicit tutor assignment.

- [ ] **Step 4: Run selector tests**

Run: `uv run pytest tests/assignments/test_selector.py -v`

Expected: remediation, spacing, and exact-repeat tests pass.

- [ ] **Step 5: Commit selector**

```bash
git add src/amath_bot/assignments tests/assignments/test_selector.py
git commit -m "feat: rank adaptive source questions"
```

### Task 3: Persist schedules and assignments

**Files:**
- Create: `src/amath_bot/assignments/tables.py`
- Create: `src/amath_bot/assignments/service.py`
- Create: `alembic/versions/0003_assignments.py`
- Create: `tests/assignments/test_service.py`

- [ ] **Step 1: Write failing schedule-generation test**

```python
async def test_due_schedule_creates_one_assignment_by_default(assignment_service, student) -> None:
    await assignment_service.set_schedule(student.id, weekdays={0, 1, 2, 3, 4}, hour=17, count=1)
    created = await assignment_service.create_due(now_sg="2026-08-05T17:00:00+08:00")
    assert len(created) == 1
    assert created[0].student_id == student.id
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/assignments/test_service.py -v`

Expected: FAIL because persistence is missing.

- [ ] **Step 3: Implement schedules, assignments, and idempotency**

Create tables for schedules and assignments. Add a named unique constraint on `(student_id, scheduled_date, sequence_number)` so scheduler retries cannot duplicate work. Store source question ID, status, delivery time, and selection reason. Default timezone to `Asia/Singapore` and count to one.

- [ ] **Step 4: Apply migration and test**

Run: `uv run alembic upgrade head && uv run pytest tests/assignments/test_service.py -v`

Expected: all assignment service tests pass.

- [ ] **Step 5: Commit scheduling domain**

```bash
git add src/amath_bot/assignments alembic/versions/0003_assignments.py tests/assignments
git commit -m "feat: persist idempotent daily assignments"
```

### Task 4: Add Telegram `/start` and consent flow

**Files:**
- Modify: `pyproject.toml`
- Create: `src/amath_bot/telegram/bot.py`
- Create: `src/amath_bot/telegram/start.py`
- Create: `src/amath_bot/telegram/text.py`
- Create: `tests/telegram/test_start.py`

- [ ] **Step 1: Write failing handler test**

```python
async def test_start_requires_consent_before_redeeming(handler, telegram_message) -> None:
    replies = await handler.start(telegram_message, invite_code="ABC123")
    assert replies[-1].buttons == ("I consent", "Cancel")
    assert await handler.people.find_student(telegram_message.from_user.id) is None
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/telegram/test_start.py -v`

Expected: FAIL because Telegram adapter is missing.

- [ ] **Step 3: Implement the adapter**

Add `aiogram>=3.13,<4` to dependencies. Create a router whose handlers call `PeopleService`; do not place database logic in handlers. The consent text must state what is stored, that handwriting is processed by a cloud provider, the image retention rule, Telegram infrastructure limits, and how the tutor can request deletion.

- [ ] **Step 4: Run tests**

Run: `uv sync && uv run pytest tests/telegram/test_start.py -v`

Expected: onboarding tests pass.

- [ ] **Step 5: Commit onboarding**

```bash
git add pyproject.toml uv.lock src/amath_bot/telegram tests/telegram/test_start.py
git commit -m "feat: onboard students with recorded consent"
```

### Task 5: Deliver assignments and add tutor commands

**Files:**
- Create: `src/amath_bot/telegram/assignments.py`
- Create: `src/amath_bot/telegram/tutor.py`
- Create: `src/amath_bot/scheduler.py`
- Create: `tests/telegram/test_assignments.py`
- Create: `tests/telegram/test_tutor_auth.py`

- [ ] **Step 1: Write failing delivery and authorization tests**

```python
async def test_delivery_contains_link_and_question_identity(deliver, assignment) -> None:
    message = await deliver.render(assignment)
    assert str(assignment.source_url) in message.text
    assert "Paper 1 · Question 6" in message.text
    assert "5 marks" in message.text


async def test_student_cannot_use_tutor_commands(tutor_router, student_message) -> None:
    response = await tutor_router.students(student_message)
    assert response.text == "Tutor access required."
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/telegram/test_assignments.py tests/telegram/test_tutor_auth.py -v`

Expected: FAIL because handlers are missing.

- [ ] **Step 3: Implement delivery and commands**

Render source provider, school, year, paper, question number, URL, marks, and estimated time; never render solution metadata. Implement `/students`, `/schedule`, `/assign`, `/pause`, and `/progress` as thin handlers protected by the allowlisted tutor ID. Use APScheduler to call `create_due` once per minute and deliver pending assignments with retry-safe status transitions.

- [ ] **Step 4: Run Telegram and scheduler tests**

Run: `uv run pytest tests/telegram tests/assignments -v`

Expected: delivery, auth, idempotency, and command tests pass.

- [ ] **Step 5: Commit delivery**

```bash
git add src/amath_bot/telegram src/amath_bot/scheduler.py tests/telegram
git commit -m "feat: deliver and manage Telegram assignments"
```

### Task 6: Telegram delivery acceptance test

**Files:**
- Create: `tests/acceptance/test_daily_delivery.py`
- Modify: `README.md`

- [ ] **Step 1: Add end-to-end acceptance test**

```python
async def test_invited_student_receives_one_eligible_daily_question(system, fake_telegram) -> None:
    student = await system.join_student("ABC123", telegram_id=200, consent=True)
    await system.schedule(student.id, weekdays={2}, hour=17, count=1)
    await system.tick("2026-08-05T17:00:00+08:00")
    sent = fake_telegram.messages_for(200)
    assert len(sent) == 1
    assert "https://" in sent[0].text
    assert "Question" in sent[0].text
```

- [ ] **Step 2: Run complete test suite**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`

Expected: all checks pass.

- [ ] **Step 3: Document Telegram configuration**

Document `AMATH_TELEGRAM_BOT_TOKEN`, `AMATH_TUTOR_TELEGRAM_ID`, webhook/polling startup, invite creation, schedule commands, and the acceptance test command.

- [ ] **Step 4: Smoke-test with Telegram disabled**

Run: `AMATH_TELEGRAM_DRY_RUN=true uv run python -m amath_bot.app`

Expected: service starts, validates configuration, and logs `telegram dry-run enabled` without sending a message.

- [ ] **Step 5: Commit acceptance workflow**

```bash
git add README.md tests/acceptance/test_daily_delivery.py
git commit -m "test: verify daily Telegram delivery"
```
