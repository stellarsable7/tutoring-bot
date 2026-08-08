from apscheduler.schedulers.asyncio import AsyncIOScheduler

from amath_bot.scheduler import (
    MARKING_INTERVAL_SECONDS,
    DailyAssignmentJob,
    add_marking_job,
    create_scheduler,
)


async def _mark_pending() -> None:
    return None


def test_marking_interval_is_three_seconds() -> None:
    assert MARKING_INTERVAL_SECONDS == 3


def test_add_marking_job_configures_single_coalescing_interval_job() -> None:
    scheduler = AsyncIOScheduler()

    add_marking_job(scheduler, _mark_pending)

    job = scheduler.get_job("openrouter-marking")
    assert job is not None
    assert job.func is _mark_pending
    assert job.trigger.interval.total_seconds() == MARKING_INTERVAL_SECONDS  # type: ignore[attr-defined]
    assert job.max_instances == 1
    assert job.coalesce is True


def test_add_marking_job_requests_replacement() -> None:
    class RecordingScheduler:
        options: dict[str, object] | None = None

        def add_job(self, callback: object, **options: object) -> None:
            self.options = options

    scheduler = RecordingScheduler()

    add_marking_job(scheduler, _mark_pending)  # type: ignore[arg-type]

    assert scheduler.options is not None
    assert scheduler.options["id"] == "openrouter-marking"
    assert scheduler.options["replace_existing"] is True


def test_create_scheduler_can_register_a_tracked_daily_callback() -> None:
    class Assignments:
        async def create_due(self, *, now_sg: object) -> object:
            return object()

    class Delivery:
        async def deliver_pending(self) -> int:
            return 0

    async def tracked_daily() -> object:
        return object()

    scheduler = create_scheduler(
        DailyAssignmentJob(Assignments(), Delivery()),  # type: ignore[arg-type]
        daily_callback=tracked_daily,
    )

    job = scheduler.get_job("daily-assignment-delivery")
    assert job is not None
    assert job.func is tracked_daily
