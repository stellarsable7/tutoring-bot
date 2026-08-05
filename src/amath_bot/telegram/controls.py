from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.service import AssignmentService
from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.people.service import PeopleService
from amath_bot.people.tables import StudentRow
from amath_bot.telegram.progress import ProgressReporter


class DatabaseTutorControls:
    def __init__(
        self,
        session: AsyncSession,
        *,
        tutor_telegram_id: int,
        bot_username: str,
        people: PeopleService,
        assignments: AssignmentService,
        timezone: str = "Asia/Singapore",
    ) -> None:
        self._session = session
        self._tutor_id = tutor_telegram_id
        self._bot_username = bot_username.lstrip("@")
        self._people = people
        self._assignments = assignments
        self._timezone = timezone
        ZoneInfo(timezone)

    async def execute(self, command: str, args: tuple[str, ...]) -> str:
        methods = {
            "invite": self._invite,
            "students": self._students,
            "schedule": self._schedule,
            "assign": self._assign,
            "pause": self._pause,
            "resume": self._resume,
            "progress": self._progress,
        }
        method = methods.get(command)
        if method is None:
            return "Unknown tutor command."
        try:
            return await method(args)
        except (ValueError, TypeError) as error:
            return f"Could not run /{command}: {error}"
        except SQLAlchemyError:
            await self._session.rollback()
            return f"Could not run /{command}: database operation failed; please try again."

    async def _invite(self, args: tuple[str, ...]) -> str:
        if args:
            raise ValueError("usage: /invite")
        invite = await self._people.create_invite(self._tutor_id)
        return f"Student invite: https://t.me/{self._bot_username}?start={invite.code}"

    async def _students(self, args: tuple[str, ...]) -> str:
        if args:
            raise ValueError("usage: /students")
        students = tuple(
            await self._session.scalars(
                select(StudentRow)
                .where(StudentRow.tutor_telegram_id == self._tutor_id)
                .order_by(StudentRow.display_name)
            )
        )
        if not students:
            return "No students enrolled. Use /invite to create an invite."
        return "Students:\n" + "\n".join(
            f"- {student.display_name}{' (paused)' if student.paused else ''}"
            for student in students
        )

    async def _schedule(self, args: tuple[str, ...]) -> str:
        if len(args) < 3:
            raise ValueError("usage: /schedule NAME weekdays|0,1,2,3,4 HOUR [COUNT]")
        student = await self._student(args[0])
        weekdays = {0, 1, 2, 3, 4} if args[1] == "weekdays" else {int(v) for v in args[1].split(",")}
        hour = int(args[2])
        count = int(args[3]) if len(args) > 3 else 1
        await self._assignments.set_schedule(
            student.id, weekdays=weekdays, hour=hour, count=count
        )
        return f"Schedule saved for {student.display_name}."

    async def _assign(self, args: tuple[str, ...]) -> str:
        if len(args) != 2:
            raise ValueError("usage: /assign NAME OBJECTIVE_CODE")
        student = await self._student(args[0])
        objective = args[1]
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
        question = next((q for q in questions if objective in q.objective_codes), None)
        if question is None:
            raise ValueError("no eligible question matches that objective")
        existing_count = len(
            tuple(
                await self._session.scalars(
                    select(AssignmentRow.id).where(
                        AssignmentRow.student_id == student.id,
                        AssignmentRow.scheduled_date
                        == datetime.now(ZoneInfo(self._timezone)).date(),
                    )
                )
            )
        )
        row = AssignmentRow(
            student_id=student.id,
            source_question_id=question.id,
            scheduled_date=datetime.now(ZoneInfo(self._timezone)).date(),
            sequence_number=existing_count + 1,
            status="pending",
            selection_reason=f"tutor assigned objective {objective}",
        )
        self._session.add(row)
        await self._session.commit()
        return f"Question queued for {student.display_name}."

    async def _pause(self, args: tuple[str, ...]) -> str:
        if len(args) != 1:
            raise ValueError("usage: /pause NAME")
        student = await self._student(args[0])
        student.paused = True
        await self._session.commit()
        return f"Delivery paused for {student.display_name}."

    async def _resume(self, args: tuple[str, ...]) -> str:
        if len(args) != 1:
            raise ValueError("usage: /resume NAME")
        student = await self._student(args[0])
        student.paused = False
        await self._session.commit()
        return f"Delivery resumed for {student.display_name}."

    async def _progress(self, args: tuple[str, ...]) -> str:
        if len(args) != 1:
            raise ValueError("usage: /progress NAME")
        return (await ProgressReporter(self._session).for_student(args[0])).render()

    async def _student(self, display_name: str) -> StudentRow:
        student = await self._session.scalar(
            select(StudentRow).where(
                StudentRow.tutor_telegram_id == self._tutor_id,
                StudentRow.display_name == display_name,
            )
        )
        if student is None:
            raise ValueError("student not found")
        return student
