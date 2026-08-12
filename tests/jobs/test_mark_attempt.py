from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import NoReturn

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.db import Base
from amath_bot.jobs.mark_attempt import (
    PROCESSING_LEASE,
    MarkAttemptJob,
    MarkingConfigurationError,
    MarkingOutcome,
    MarkingPipelineError,
    retry_delay,
)
from amath_bot.submissions.tables import AttemptRow


class NullNotifier:
    async def send_message(self, chat_id: int, text: str) -> object:
        return object()


class NullMedia:
    async def delete_attempt_media(self, attempt_id: int) -> None:
        pass


class FailingPipeline:
    def __init__(self, error: MarkingPipelineError) -> None:
        self.error = error

    async def mark(self, attempt_id: int) -> NoReturn:
        raise self.error


class SuccessfulPipeline:
    def __init__(self, outcome: MarkingOutcome) -> None:
        self.outcome = outcome

    async def mark(self, attempt_id: int) -> MarkingOutcome:
        return self.outcome


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    value = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with value.begin() as connection:
        assert SourceQuestionRow.__tablename__ == "source_questions"
        await connection.run_sync(Base.metadata.create_all)
    yield value
    await value.dispose()


def job(
    session: AsyncSession,
    pipeline: FailingPipeline | SuccessfulPipeline,
    now: datetime,
) -> MarkAttemptJob:
    return MarkAttemptJob(
        session,
        pipeline=pipeline,
        notifier=NullNotifier(),
        media=NullMedia(),
        now=lambda: now,
    )


def add_attempt(
    session: AsyncSession,
    *,
    status: str = "queued",
    retry_at: datetime | None = None,
    attempts: int = 0,
) -> AttemptRow:
    row = AttemptRow(
        assignment_id=1,
        status=status,
        marking_retry_at=retry_at,
        marking_attempts=attempts,
    )
    session.add(row)
    return row


@pytest.mark.parametrize(
    ("failed_attempt", "expected"),
    [
        (1, timedelta(seconds=3)),
        (2, timedelta(seconds=10)),
        (3, timedelta(seconds=30)),
        (4, timedelta(seconds=30)),
        (5, timedelta(seconds=60)),
        (6, timedelta(seconds=60)),
        (20, timedelta(seconds=60)),
    ],
)
def test_retry_delay_uses_bounded_schedule(
    failed_attempt: int, expected: timedelta
) -> None:
    assert retry_delay(failed_attempt) == expected


def test_retry_delay_rejects_nonpositive_attempt() -> None:
    with pytest.raises(ValueError, match="failed_attempt must be at least 1"):
        retry_delay(0)


@pytest.mark.asyncio
async def test_claim_next_selects_only_due_queued_rows_in_id_order(
    engine: AsyncEngine,
) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        null_due = add_attempt(session)
        past_due = add_attempt(session, retry_at=now - timedelta(microseconds=1))
        exact_due = add_attempt(session, retry_at=now)
        future = add_attempt(session, retry_at=now + timedelta(microseconds=1))
        nonqueued = add_attempt(session, status="processing")
        await session.commit()

        worker = job(
            session,
            SuccessfulPipeline(MarkingOutcome(total=1, maximum=1, feedback=(), review_reasons=())),
            now,
        )
        claimed_ids: list[int] = []
        while claimed := await worker._claim_next(now):
            claimed_ids.append(claimed.id)
            async with factory() as observer_session:
                observer = await observer_session.get(AttemptRow, claimed.id)
                assert observer is not None
                assert observer.status == "transcribing"

        assert claimed_ids == [null_due.id, past_due.id, exact_due.id]
        await session.refresh(future)
        await session.refresh(nonqueued)
        assert future.status == "queued"
        assert nonqueued.status == "processing"


@pytest.mark.asyncio
async def test_grading_failure_retries_from_persisted_transcription(
    engine: AsyncEngine,
) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        attempt = add_attempt(session, status="transcribed")
        attempt.ocr_transcription = ["x = 2"]
        await session.commit()

        await job(
            session,
            FailingPipeline(
                MarkingPipelineError("grading unavailable", retry_status="transcribed")
            ),
            now,
        ).run_pending()
        await session.refresh(attempt)

        assert attempt.status == "transcribed"
        assert attempt.ocr_transcription == ["x = 2"]
        assert attempt.marking_attempts == 1


@pytest.mark.asyncio
async def test_expired_stage_lease_is_reclaimed_without_losing_ocr(
    engine: AsyncEngine,
) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        attempt = add_attempt(
            session,
            status="grading",
            retry_at=now - timedelta(microseconds=1),
        )
        attempt.ocr_transcription = ["persisted line"]
        await session.commit()
        worker = job(
            session,
            SuccessfulPipeline(
                MarkingOutcome(total=1, maximum=1, feedback=(), review_reasons=("review",))
            ),
            now,
        )

        claimed = await worker._claim_next(now)

        assert claimed is not None
        assert claimed.id == attempt.id
        assert claimed.status == "grading"
        assert claimed.ocr_transcription == ["persisted line"]
        assert claimed.marking_retry_at == now + PROCESSING_LEASE


@pytest.mark.asyncio
async def test_transient_failures_persist_exact_retry_schedule_across_sessions(
    engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    current = datetime(2026, 8, 8, 12, tzinfo=UTC)
    async with factory() as session:
        attempt = add_attempt(session)
        await session.commit()
        attempt_id = attempt.id

    for failed_attempt in range(1, 7):
        async with factory() as session:
            processed = await job(
                session,
                FailingPipeline(MarkingPipelineError("provider temporarily unavailable")),
                current,
            ).run_pending()
            assert processed == 0
            row = await session.get(AttemptRow, attempt_id)
            assert row is not None
            deadline = current + retry_delay(failed_attempt)
            # SQLite returns timezone-naive DateTime values even for timezone=True columns.
            assert row.marking_retry_at == deadline.replace(tzinfo=None)
            assert row.status == "queued"
            assert row.marking_attempts == failed_attempt
            assert row.marking_last_error == "provider temporarily unavailable"

        async with factory() as session:
            before = deadline - timedelta(microseconds=1)
            assert await job(
                session,
                FailingPipeline(MarkingPipelineError("unused")),
                before,
            ).run_pending() == 0
            row = await session.get(AttemptRow, attempt_id)
            assert row is not None
            assert row.marking_attempts == failed_attempt

        current = deadline


@pytest.mark.asyncio
async def test_configuration_failure_retries_in_exactly_one_hour(engine: AsyncEngine) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        attempt = add_attempt(session)
        await session.commit()
        await job(
            session,
            FailingPipeline(MarkingConfigurationError("provider is not configured")),
            now,
        ).run_pending()
        await session.refresh(attempt)
        # SQLite returns timezone-naive DateTime values even for timezone=True columns.
        assert attempt.marking_retry_at == (now + timedelta(hours=1)).replace(tzinfo=None)
        assert attempt.marking_attempts == 1
        assert attempt.marking_last_error == "provider is not configured"


@pytest.mark.asyncio
async def test_configuration_failure_logs_only_bounded_safe_diagnostic(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    diagnostic = "safe:" + "x" * 600
    unlogged_suffix = "OPENROUTER_API_KEY=must-not-appear"
    async with factory() as session:
        add_attempt(session)
        await session.commit()

        with caplog.at_level("WARNING", logger="amath_bot.jobs.mark_attempt"):
            await job(
                session,
                FailingPipeline(
                    MarkingConfigurationError(diagnostic + unlogged_suffix)
                ),
                now,
            ).run_pending()

    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == (
        f"Marking configuration failure; retrying in one hour: {diagnostic[:500]}"
    )
    assert unlogged_suffix not in caplog.text


def test_pipeline_error_exposes_bounded_caller_supplied_safe_message() -> None:
    safe_reason = "safe:" + "x" * 600
    error = MarkingPipelineError(safe_reason)

    assert str(error) == safe_reason
    assert error.diagnostic == safe_reason[:500]


def test_configuration_error_retains_status_bearing_safe_diagnostic() -> None:
    error = MarkingConfigurationError("OpenRouter API key is not configured")

    assert str(error) == "OpenRouter API key is not configured"
    assert error.diagnostic == "OpenRouter API key is not configured"


@pytest.mark.parametrize(
    ("review_reasons", "expected_status"),
    [((), "marked"), (("ambiguous work",), "flagged")],
)
@pytest.mark.asyncio
async def test_success_clears_retry_metadata_retains_attempt_count_and_outcome(
    engine: AsyncEngine,
    review_reasons: tuple[str, ...],
    expected_status: str,
) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        attempt = add_attempt(
            session,
            retry_at=now - timedelta(seconds=1),
            attempts=2,
        )
        attempt.marking_last_error = "old safe error"
        await session.commit()
        processed = await job(
            session,
            SuccessfulPipeline(
                MarkingOutcome(
                    total=4,
                    maximum=5,
                    feedback=("Good method",),
                    review_reasons=review_reasons,
                )
            ),
            now,
        ).run_pending()
        await session.refresh(attempt)

        assert processed == 1
        assert attempt.status == expected_status
        assert attempt.marking_attempts == 2
        assert attempt.marking_retry_at is None
        assert attempt.marking_last_error is None
        assert attempt.result_total == 4
        assert attempt.result_maximum == 5


@pytest.mark.asyncio
async def test_total_above_maximum_is_persisted_as_retry(engine: AsyncEngine) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        attempt = add_attempt(session)
        await session.commit()
        processed = await job(
            session,
            SuccessfulPipeline(
                MarkingOutcome(total=6, maximum=5, feedback=(), review_reasons=())
            ),
            now,
        ).run_pending()
        await session.refresh(attempt)

        assert processed == 0
        assert attempt.status == "queued"
        assert attempt.marking_attempts == 1
        assert attempt.marking_last_error == "marking total exceeds maximum"
        # SQLite returns timezone-naive DateTime values even for timezone=True columns.
        assert attempt.marking_retry_at == (now + timedelta(seconds=3)).replace(tzinfo=None)
