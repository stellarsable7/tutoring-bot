# A-Math Bot Foundation and Catalogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a runnable Python service with a versioned 4049 syllabus map and a catalogue that admits only source-linked questions with published worked solutions or mark schemes.

**Architecture:** Use a modular Python package with SQLAlchemy repositories behind domain services. Keep source discovery separate from eligibility validation so Holy Grail metadata can be imported without making unverified questions assignable.

**Tech Stack:** Python 3.12, uv, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL 16, HTTPX, pytest, Ruff, mypy

---

### Task 1: Project scaffold and health check

**Files:**
- Create: `pyproject.toml`
- Create: `src/amath_bot/__init__.py`
- Create: `src/amath_bot/settings.py`
- Create: `src/amath_bot/app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write the failing health-check test**

```python
from amath_bot.app import health


def test_health_reports_ok() -> None:
    assert health() == {"status": "ok", "service": "amath-bot"}
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/test_app.py -v`

Expected: FAIL because `amath_bot.app` does not exist.

- [ ] **Step 3: Add package configuration and minimal implementation**

```toml
[project]
name = "amath-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "alembic>=1.13,<2",
  "httpx>=0.27,<1",
  "pydantic-settings>=2.4,<3",
  "sqlalchemy[asyncio]>=2.0,<3",
  "asyncpg>=0.29,<1",
]

[dependency-groups]
dev = ["mypy>=1.11,<2", "pytest>=8.3,<9", "pytest-asyncio>=0.24,<1", "ruff>=0.6,<1"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
```

```python
# src/amath_bot/app.py
def health() -> dict[str, str]:
    return {"status": "ok", "service": "amath-bot"}
```

```python
# src/amath_bot/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/amath_bot"
    timezone: str = "Asia/Singapore"
    model_config = SettingsConfigDict(env_prefix="AMATH_", env_file=".env")
```

- [ ] **Step 4: Run quality checks**

Run: `uv run pytest tests/test_app.py -v && uv run ruff check src tests && uv run mypy src`

Expected: all commands pass.

- [ ] **Step 5: Commit the scaffold**

```bash
git add pyproject.toml src/amath_bot tests/test_app.py
git commit -m "build: scaffold amath bot service"
```

### Task 2: Define syllabus domain types and load the 4049 map

**Files:**
- Create: `src/amath_bot/syllabus/models.py`
- Create: `src/amath_bot/syllabus/service.py`
- Create: `data/syllabus/4049-2026.json`
- Create: `tests/syllabus/test_service.py`

- [ ] **Step 1: Write failing syllabus tests**

```python
import pytest
from amath_bot.syllabus.service import SyllabusService, UnknownObjective


def test_loads_versioned_4049_objectives() -> None:
    service = SyllabusService.from_json("data/syllabus/4049-2026.json")
    objective = service.require_objective("4049-2026", "A1.complete-square")
    assert objective.topic == "Quadratic functions"


def test_rejects_unknown_objective() -> None:
    service = SyllabusService.from_json("data/syllabus/4049-2026.json")
    with pytest.raises(UnknownObjective):
        service.require_objective("4049-2026", "unknown")
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/syllabus/test_service.py -v`

Expected: FAIL because the syllabus package is missing.

- [ ] **Step 3: Implement immutable syllabus models and lookup**

```python
# src/amath_bot/syllabus/models.py
from pydantic import BaseModel, ConfigDict


class Objective(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    domain: str
    topic: str
    description: str


class Syllabus(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: str
    objectives: tuple[Objective, ...]
```

```python
# src/amath_bot/syllabus/service.py
import json
from pathlib import Path
from amath_bot.syllabus.models import Objective, Syllabus


class UnknownObjective(ValueError):
    pass


class SyllabusService:
    def __init__(self, syllabuses: tuple[Syllabus, ...]) -> None:
        self._items = {item.version: item for item in syllabuses}

    @classmethod
    def from_json(cls, path: str) -> "SyllabusService":
        payload = json.loads(Path(path).read_text())
        return cls((Syllabus.model_validate(payload),))

    def require_objective(self, version: str, code: str) -> Objective:
        for objective in self._items[version].objectives:
            if objective.code == code:
                return objective
        raise UnknownObjective(f"{version}:{code}")
```

Create `data/syllabus/4049-2026.json` by transcribing every objective from the official SEAB 4049 PDF. Include the tested entry exactly as:

```json
{"version":"4049-2026","objectives":[{"code":"A1.complete-square","domain":"Algebra","topic":"Quadratic functions","description":"Find maximum or minimum values by completing the square."}]}
```

Expand the `objectives` array in the same commit until every bullet in the official syllabus has a stable code. Do not paraphrase in a way that changes scope.

- [ ] **Step 4: Run tests and validate the dataset**

Run: `uv run pytest tests/syllabus/test_service.py -v && uv run python -m json.tool data/syllabus/4049-2026.json >/dev/null`

Expected: tests pass and JSON validation exits 0.

- [ ] **Step 5: Commit the syllabus map**

```bash
git add src/amath_bot/syllabus data/syllabus/4049-2026.json tests/syllabus
git commit -m "feat: add versioned 4049 syllabus map"
```

### Task 3: Model source questions and eligibility

**Files:**
- Create: `src/amath_bot/catalogue/models.py`
- Create: `src/amath_bot/catalogue/eligibility.py`
- Create: `tests/catalogue/test_eligibility.py`

- [ ] **Step 1: Write failing eligibility tests**

```python
from amath_bot.catalogue.eligibility import eligibility_errors
from amath_bot.catalogue.models import SourceQuestion, SolutionKind


def question(kind: SolutionKind | None) -> SourceQuestion:
    return SourceQuestion(
        source_url="https://grail.moe/example-paper.pdf",
        solution_url=None if kind is None else "https://grail.moe/example-solution.pdf",
        provider="Holy Grail",
        school="Example Secondary",
        year=2024,
        paper="1",
        question_number="6",
        syllabus_version="4049-2026",
        objective_codes=("A1.complete-square",),
        marks=5,
        solution_kind=kind,
    )


def test_requires_worked_solution_or_mark_scheme() -> None:
    assert "published worked solution required" in eligibility_errors(question(None))
    assert "published worked solution required" in eligibility_errors(question(SolutionKind.FINAL_ANSWER))
    assert eligibility_errors(question(SolutionKind.WORKED_SOLUTION)) == []
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/catalogue/test_eligibility.py -v`

Expected: FAIL because catalogue types are missing.

- [ ] **Step 3: Implement catalogue types and pure eligibility rules**

```python
# src/amath_bot/catalogue/models.py
from enum import StrEnum
from pydantic import BaseModel, HttpUrl, PositiveInt


class SolutionKind(StrEnum):
    FINAL_ANSWER = "final_answer"
    WORKED_SOLUTION = "worked_solution"
    MARK_SCHEME = "mark_scheme"


class SourceQuestion(BaseModel):
    source_url: HttpUrl
    solution_url: HttpUrl | None
    provider: str
    school: str
    year: PositiveInt
    paper: str
    question_number: str
    syllabus_version: str
    objective_codes: tuple[str, ...]
    marks: PositiveInt
    solution_kind: SolutionKind | None
```

```python
# src/amath_bot/catalogue/eligibility.py
from amath_bot.catalogue.models import SourceQuestion, SolutionKind


def eligibility_errors(item: SourceQuestion) -> list[str]:
    errors: list[str] = []
    if item.solution_url is None or item.solution_kind not in {
        SolutionKind.WORKED_SOLUTION,
        SolutionKind.MARK_SCHEME,
    }:
        errors.append("published worked solution required")
    if not item.objective_codes:
        errors.append("at least one syllabus objective required")
    return errors
```

- [ ] **Step 4: Run focused and full tests**

Run: `uv run pytest tests/catalogue/test_eligibility.py -v && uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit eligibility rules**

```bash
git add src/amath_bot/catalogue tests/catalogue
git commit -m "feat: enforce catalogue source eligibility"
```

### Task 4: Persist catalogue records and reject duplicates

**Files:**
- Create: `src/amath_bot/db.py`
- Create: `src/amath_bot/catalogue/tables.py`
- Create: `src/amath_bot/catalogue/repository.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_catalogue.py`
- Create: `tests/catalogue/test_repository.py`

- [ ] **Step 1: Write a failing repository test**

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from amath_bot.catalogue.repository import CatalogueRepository, DuplicateSourceQuestion


async def test_source_identity_is_unique(session: AsyncSession, eligible_question) -> None:
    repository = CatalogueRepository(session)
    await repository.add(eligible_question)
    with pytest.raises(DuplicateSourceQuestion):
        await repository.add(eligible_question)
```

- [ ] **Step 2: Run against the test database**

Run: `AMATH_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/amath_test uv run pytest tests/catalogue/test_repository.py -v`

Expected: FAIL because persistence is missing.

- [ ] **Step 3: Implement the table and repository**

Define `source_questions` with a unique constraint on `(provider, school, year, paper, question_number)`, JSON arrays for objective codes and structured marking steps, timestamps, and an `eligible` boolean. In `CatalogueRepository.add`, call `eligibility_errors` before insertion and translate the named unique-constraint violation into `DuplicateSourceQuestion`.

```python
class DuplicateSourceQuestion(ValueError):
    pass


class IneligibleSourceQuestion(ValueError):
    pass
```

The Alembic migration must create and downgrade the table and named unique constraint `uq_source_identity`.

- [ ] **Step 4: Run migration and tests**

Run: `uv run alembic upgrade head && uv run pytest tests/catalogue/test_repository.py -v`

Expected: migration succeeds and repository tests pass.

- [ ] **Step 5: Commit persistence**

```bash
git add src/amath_bot/db.py src/amath_bot/catalogue alembic.ini alembic tests/catalogue
git commit -m "feat: persist eligible source questions"
```

### Task 5: Import and validate a tutor-reviewed catalogue manifest

**Files:**
- Create: `src/amath_bot/catalogue/importer.py`
- Create: `src/amath_bot/cli.py`
- Create: `data/catalogue/example.json`
- Create: `tests/catalogue/test_importer.py`

- [ ] **Step 1: Write failing importer test**

```python
from amath_bot.catalogue.importer import parse_manifest


def test_manifest_separates_valid_and_rejected_items(tmp_path) -> None:
    path = tmp_path / "items.json"
    path.write_text('[{"solution_kind":"final_answer"}]')
    result = parse_manifest(path)
    assert len(result.accepted) == 0
    assert result.rejected[0].reasons == ("invalid source metadata",)
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/catalogue/test_importer.py -v`

Expected: FAIL because importer is missing.

- [ ] **Step 3: Implement deterministic import reporting**

Create `ImportResult(accepted, rejected)` and `RejectedItem(index, reasons)` dataclasses. Validate every manifest item with `SourceQuestion.model_validate`, then `eligibility_errors`. Do not scrape or download paper contents in this task. Add `uv run python -m amath_bot.cli import-catalogue PATH --dry-run` that prints accepted and rejected counts and exits non-zero when any item is rejected.

- [ ] **Step 4: Run importer tests and dry run**

Run: `uv run pytest tests/catalogue/test_importer.py -v && uv run python -m amath_bot.cli import-catalogue data/catalogue/example.json --dry-run`

Expected: tests pass and the example manifest reports only eligible records.

- [ ] **Step 5: Commit importer**

```bash
git add src/amath_bot/catalogue/importer.py src/amath_bot/cli.py data/catalogue tests/catalogue
git commit -m "feat: import tutor-reviewed catalogue manifests"
```

### Task 6: Foundation acceptance check

**Files:**
- Create: `tests/acceptance/test_catalogue_ready.py`
- Create: `README.md`

- [ ] **Step 1: Add an acceptance test**

```python
from amath_bot.catalogue.models import SolutionKind


def test_assignable_items_are_4049_and_have_published_worked_solutions(catalogue) -> None:
    for item in catalogue.assignable():
        assert item.syllabus_version == "4049-2026"
        assert item.solution_url is not None
        assert item.solution_kind in {SolutionKind.WORKED_SOLUTION, SolutionKind.MARK_SCHEME}
```

- [ ] **Step 2: Run the complete suite**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`

Expected: all checks pass.

- [ ] **Step 3: Document local setup and catalogue import**

In `README.md`, document Python 3.12, uv, PostgreSQL, `AMATH_DATABASE_URL`, migrations, tests, and the dry-run/import commands. State explicitly that only tutor-reviewed metadata with a published worked solution or mark scheme becomes assignable.

- [ ] **Step 4: Re-run documentation commands**

Run every command copied into `README.md` in a clean shell.

Expected: each command exits 0.

- [ ] **Step 5: Commit foundation acceptance**

```bash
git add README.md tests/acceptance/test_catalogue_ready.py
git commit -m "docs: verify catalogue foundation workflow"
```
