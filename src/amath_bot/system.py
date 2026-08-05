from datetime import UTC, datetime

from amath_bot.assignments.models import Assignment
from amath_bot.assignments.service import AssignmentService
from amath_bot.people.models import Student
from amath_bot.people.service import PeopleService
from amath_bot.telegram.assignments import AssignmentDeliveryService


class AmathSystem:
    """Small application facade used by process adapters and acceptance tests."""

    def __init__(
        self,
        people: PeopleService,
        assignments: AssignmentService,
        delivery: AssignmentDeliveryService,
    ) -> None:
        self._people = people
        self._assignments = assignments
        self._delivery = delivery

    async def join_student(
        self,
        invite_code: str,
        *,
        telegram_id: int,
        display_name: str,
        consent: bool,
    ) -> Student:
        return await self._people.redeem(
            invite_code,
            telegram_id=telegram_id,
            display_name=display_name,
            consented_at=datetime.now(UTC) if consent else None,
        )

    async def schedule(
        self, student_id: int, *, weekdays: set[int], hour: int, count: int = 1
    ) -> None:
        await self._assignments.set_schedule(
            student_id, weekdays=weekdays, hour=hour, count=count
        )

    async def tick(self, now_sg: str) -> tuple[Assignment, ...]:
        created = await self._assignments.create_due(now_sg=now_sg)
        await self._delivery.deliver_pending()
        return created
