import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.jobs.mark_attempt import (
    MarkAttemptJob,
    MarkingOutcome,
    MarkingPipelineError,
)
from amath_bot.people.tables import StudentRow, TutorRow
from amath_bot.submissions.service import SubmissionService
from amath_bot.submissions.tables import AttemptRow

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("AMATH_RUN_POSTGRES_E2E") != "1"
        or not os.getenv("AMATH_E2E_DATABASE_URL"),
        reason="PostgreSQL E2E requires explicit opt-in and a disposable database",
    ),
]


class NullNotifier:
    async def send_message(self, chat_id: int, text: str) -> object:
        return object()


class NullMedia:
    async def delete_attempt_media(self, attempt_id: int) -> None:
        return None


class ObservedFailure:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        observed: list[str],
    ) -> None:
        self._factory = factory
        self._observed = observed

    async def mark(self, attempt_id: int) -> MarkingOutcome:
        async with self._factory() as observer:
            row = await observer.get(AttemptRow, attempt_id)
            assert row is not None
            self._observed.append(row.status)
        raise MarkingPipelineError("free provider temporarily unavailable")


class ObservedSuccess:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        observed: list[str],
    ) -> None:
        self._factory = factory
        self._observed = observed

    async def mark(self, attempt_id: int) -> MarkingOutcome:
        async with self._factory() as observer:
            row = await observer.get(AttemptRow, attempt_id)
            assert row is not None
            self._observed.append(row.status)
        return MarkingOutcome(
            total=1,
            maximum=1,
            feedback=("Synthetic E2E result",),
            review_reasons=("Tutor approval is required",),
        )


async def _queued_attempt(factory: async_sessionmaker[AsyncSession]) -> int:
    suffix = uuid4().int % 1_000_000_000
    async with factory() as session:
        tutor_id = 8_000_000_000 + suffix
        tutor = TutorRow(telegram_id=tutor_id)
        student = StudentRow(
            telegram_id=9_000_000_000 + suffix,
            tutor_telegram_id=tutor_id,
            display_name=f"E2E-{suffix}",
            syllabus_version="4049-2026",
            consented_at=datetime.now(UTC),
        )
        question = SourceQuestionRow(
            source_url=f"https://e2e.invalid/question/{suffix}",
            solution_url=f"https://e2e.invalid/solution/{suffix}",
            provider="E2E",
            school="E2E School",
            year=2026,
            paper="1",
            question_number=str(suffix),
            syllabus_version="4049-2026",
            objective_codes=["A1.sign"],
            marks=1,
            solution_kind="mark_scheme",
            marking_steps=[],
            tutor_validated=True,
            eligible=True,
        )
        session.add(tutor)
        await session.flush()
        session.add_all((student, question))
        await session.flush()
        assignment = AssignmentRow(
            student_id=student.id,
            source_question_id=question.id,
            scheduled_date=date(2026, 8, 8),
            sequence_number=1,
            status="delivered",
            selection_reason="PostgreSQL E2E",
        )
        session.add(assignment)
        await session.commit()
        await session.refresh(assignment)
        submissions = SubmissionService(session)
        draft = await submissions.add_image(
            assignment.id,
            f"e2e-file-{suffix}",
            mime_type="image/png",
        )
        queued = await submissions.submit(draft.id)
        assert queued.status == "queued"
        return queued.id


async def _run(
    factory: async_sessionmaker[AsyncSession],
    pipeline: ObservedFailure | ObservedSuccess,
    now: datetime,
) -> int:
    async with factory() as session:
        return await MarkAttemptJob(
            session,
            pipeline=pipeline,
            notifier=NullNotifier(),
            media=NullMedia(),
            now=lambda: now,
        ).run_pending()


async def _state(
    factory: async_sessionmaker[AsyncSession], attempt_id: int
) -> tuple[str, int, datetime | None, str | None]:
    async with factory() as session:
        row = await session.get(AttemptRow, attempt_id)
        assert row is not None
        return row.status, row.marking_attempts, row.marking_retry_at, row.marking_last_error


async def test_retry_state_survives_postgresql_sessions() -> None:
    database_url = os.environ["AMATH_E2E_DATABASE_URL"]
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    observed: list[str] = []
    started = datetime(2026, 8, 8, 12, tzinfo=UTC)
    try:
        attempt_id = await _queued_attempt(factory)
        assert await _state(factory, attempt_id) == ("queued", 0, None, None)

        assert await _run(factory, ObservedFailure(factory, observed), started) == 0
        first = await _state(factory, attempt_id)
        assert first == (
            "queued",
            1,
            started + timedelta(seconds=3),
            "free provider temporarily unavailable",
        )

        assert (
            await _run(
                factory,
                ObservedFailure(factory, observed),
                started + timedelta(seconds=2),
            )
            == 0
        )
        assert await _state(factory, attempt_id) == first

        second_at = started + timedelta(seconds=3)
        assert await _run(factory, ObservedFailure(factory, observed), second_at) == 0
        second = await _state(factory, attempt_id)
        assert second == (
            "queued",
            2,
            second_at + timedelta(seconds=10),
            "free provider temporarily unavailable",
        )

        success_at = started + timedelta(seconds=13)
        assert await _run(factory, ObservedSuccess(factory, observed), success_at) == 1
        assert await _state(factory, attempt_id) == ("flagged", 2, None, None)
        assert observed == ["processing", "processing", "processing"]
    finally:
        await engine.dispose()
