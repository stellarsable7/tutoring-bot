from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.people.tables import StudentRow
from amath_bot.submissions.models import Attempt
from amath_bot.submissions.service import AttemptNotFound, SubmissionService
from amath_bot.submissions.tables import AttemptRow


class SubmissionHandler:
    def __init__(self, submissions: SubmissionService, session: AsyncSession) -> None:
        self._submissions = submissions
        self._session = session

    async def receive_photo(
        self, *, student_telegram_id: int, file_id: str, mime_type: str
    ) -> Attempt:
        assignment_id = await self._latest_assignment(student_telegram_id)
        return await self._submissions.add_image(assignment_id, file_id, mime_type=mime_type)

    async def receive_pdf(
        self, *, student_telegram_id: int, file_id: str, mime_type: str
    ) -> Attempt:
        assignment_id = await self._latest_assignment(student_telegram_id)
        return await self._submissions.add_pdf(assignment_id, file_id, mime_type=mime_type)

    async def submit(self, *, student_telegram_id: int) -> Attempt:
        attempt_id = await self._session.scalar(
            select(AttemptRow.id)
            .join(AssignmentRow, AssignmentRow.id == AttemptRow.assignment_id)
            .join(StudentRow, StudentRow.id == AssignmentRow.student_id)
            .where(
                StudentRow.telegram_id == student_telegram_id,
                AttemptRow.status == "draft",
            )
            .order_by(AttemptRow.id.desc())
            .limit(1)
        )
        if attempt_id is None:
            raise AttemptNotFound("no draft attempt for this student")
        return await self._submissions.submit(attempt_id)

    async def _latest_assignment(self, student_telegram_id: int) -> int:
        assignment_id = await self._session.scalar(
            select(AssignmentRow.id)
            .join(StudentRow, StudentRow.id == AssignmentRow.student_id)
            .where(
                StudentRow.telegram_id == student_telegram_id,
                AssignmentRow.status == "delivered",
            )
            .order_by(AssignmentRow.id.desc())
            .limit(1)
        )
        if assignment_id is None:
            raise AttemptNotFound("no delivered assignment for this student")
        return assignment_id

