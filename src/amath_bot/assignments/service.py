from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.models import Assignment
from amath_bot.assignments.tables import AssignmentRow, ScheduleRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.people.tables import StudentRow


class AssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_schedule(
        self,
        student_id: int,
        *,
        weekdays: set[int],
        hour: int,
        count: int = 1,
        timezone: str = "Asia/Singapore",
    ) -> None:
        if not weekdays or not weekdays.issubset(set(range(7))):
            raise ValueError("weekdays must contain values from 0 to 6")
        if hour not in range(24):
            raise ValueError("hour must be from 0 to 23")
        if count < 1:
            raise ValueError("count must be positive")
        ZoneInfo(timezone)

        row = await self._session.get(ScheduleRow, student_id)
        if row is None:
            row = ScheduleRow(student_id=student_id, weekdays=sorted(weekdays), hour=hour)
            self._session.add(row)
        row.weekdays = sorted(weekdays)
        row.hour = hour
        row.count = count
        row.timezone = timezone
        await self._session.commit()

    async def create_due(self, *, now_sg: str | datetime) -> tuple[Assignment, ...]:
        now = datetime.fromisoformat(now_sg) if isinstance(now_sg, str) else now_sg
        if now.tzinfo is None:
            raise ValueError("now_sg must include a timezone")

        schedules = await self._session.execute(
            select(ScheduleRow, StudentRow)
            .join(StudentRow, StudentRow.id == ScheduleRow.student_id)
            .where(StudentRow.paused.is_(False))
            .order_by(ScheduleRow.student_id)
        )
        created: list[Assignment] = []
        for schedule, student in schedules:
            local_now = now.astimezone(ZoneInfo(schedule.timezone))
            if local_now.weekday() not in schedule.weekdays or local_now.hour != schedule.hour:
                continue
            questions = tuple(
                await self._session.scalars(
                select(SourceQuestionRow)
                .where(
                    SourceQuestionRow.eligible.is_(True),
                    SourceQuestionRow.syllabus_version == student.syllabus_version,
                )
                .order_by(SourceQuestionRow.id)
                )
            )
            if not questions:
                continue
            prior_question_ids = set(
                await self._session.scalars(
                    select(AssignmentRow.source_question_id).where(
                        AssignmentRow.student_id == student.id
                    )
                )
            )
            for sequence in range(1, schedule.count + 1):
                exists = await self._session.scalar(
                    select(AssignmentRow.id).where(
                        AssignmentRow.student_id == student.id,
                        AssignmentRow.scheduled_date == local_now.date(),
                        AssignmentRow.sequence_number == sequence,
                    )
                )
                if exists is not None:
                    continue
                question = next(
                    (item for item in questions if item.id not in prior_question_ids),
                    questions[(sequence - 1) % len(questions)],
                )
                row = AssignmentRow(
                    student_id=student.id,
                    source_question_id=question.id,
                    scheduled_date=local_now.date(),
                    sequence_number=sequence,
                    status="pending",
                    selection_reason="scheduled adaptive selection",
                )
                self._session.add(row)
                await self._session.flush()
                prior_question_ids.add(question.id)
                created.append(Assignment.model_validate(row, from_attributes=True))
        await self._session.commit()
        return tuple(created)
