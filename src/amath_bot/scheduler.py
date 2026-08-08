from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

MARKING_INTERVAL_SECONDS = 3


class DueAssignments(Protocol):
    async def create_due(self, *, now_sg: datetime) -> object: ...


class PendingDelivery(Protocol):
    async def deliver_pending(self) -> int: ...


class DailyAssignmentJob:
    def __init__(self, assignments: DueAssignments, delivery: PendingDelivery) -> None:
        self._assignments = assignments
        self._delivery = delivery

    async def run(self) -> int:
        await self._assignments.create_due(now_sg=datetime.now().astimezone())
        return await self._delivery.deliver_pending()


def create_scheduler(
    job: DailyAssignmentJob,
    *,
    timezone: str = "Asia/Singapore",
    daily_callback: Callable[[], Awaitable[object]] | None = None,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        daily_callback or job.run,
        trigger="cron",
        minute="*",
        id="daily-assignment-delivery",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    return scheduler


def add_marking_job(
    scheduler: AsyncIOScheduler, callback: Callable[[], Awaitable[None]]
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
