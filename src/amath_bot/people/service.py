import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.people.models import Invite, Student
from amath_bot.people.tables import InviteRow, StudentRow, TutorRow


class InviteNotFound(ValueError):
    pass


class InviteAlreadyUsed(ValueError):
    pass


class StudentAlreadyEnrolled(ValueError):
    pass


class PeopleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_invite(self, tutor_telegram_id: int) -> Invite:
        tutor = await self._session.get(TutorRow, tutor_telegram_id)
        if tutor is None:
            self._session.add(TutorRow(telegram_id=tutor_telegram_id))
            # SQLAlchemy has no ORM relationship here, so make the FK ordering explicit.
            await self._session.flush()

        row = InviteRow(
            code=secrets.token_urlsafe(12),
            tutor_telegram_id=tutor_telegram_id,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise
        return Invite(code=row.code, tutor_telegram_id=row.tutor_telegram_id)

    async def find_student(self, telegram_id: int) -> Student | None:
        row = await self._session.scalar(
            select(StudentRow).where(StudentRow.telegram_id == telegram_id)
        )
        return None if row is None else Student.model_validate(row, from_attributes=True)

    async def redeem(
        self,
        code: str,
        *,
        telegram_id: int,
        display_name: str,
        consented_at: datetime | None,
    ) -> Student:
        if consented_at is None:
            raise ValueError("student consent is required")

        result = await self._session.execute(
            select(InviteRow).where(InviteRow.code == code).with_for_update()
        )
        invite = result.scalar_one_or_none()
        if invite is None:
            raise InviteNotFound("invite not found")
        if invite.used_at is not None:
            raise InviteAlreadyUsed("invite has already been used")

        invite.used_at = datetime.now(consented_at.tzinfo)
        row = StudentRow(
            telegram_id=telegram_id,
            tutor_telegram_id=invite.tutor_telegram_id,
            display_name=display_name,
            syllabus_version="4049-2026",
            consented_at=consented_at,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise StudentAlreadyEnrolled("this Telegram account is already enrolled") from error
        await self._session.refresh(row)
        return Student.model_validate(row, from_attributes=True)
