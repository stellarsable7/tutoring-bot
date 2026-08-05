from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.submissions.models import Attempt, SubmissionMedia
from amath_bot.submissions.tables import AttemptMediaRow, AttemptRow


class AttemptNotFound(ValueError):
    pass


class EmptyAttempt(ValueError):
    pass


class MixedMediaTypes(ValueError):
    pass


class UnsupportedMediaType(ValueError):
    pass


class AttemptAlreadySubmitted(ValueError):
    pass


class SubmissionService:
    IMAGE_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"image/jpeg", "image/png", "image/heic", "image/heif"}
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(self, assignment_id: int) -> Attempt:
        row = AttemptRow(assignment_id=assignment_id, status="draft")
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return await self._model(row)

    async def add_image(
        self, assignment_id: int, telegram_file_id: str, *, mime_type: str
    ) -> Attempt:
        if mime_type not in self.IMAGE_TYPES:
            raise UnsupportedMediaType(mime_type)
        return await self._add(assignment_id, telegram_file_id, mime_type, "image")

    async def add_pdf(
        self, assignment_id: int, telegram_file_id: str, *, mime_type: str
    ) -> Attempt:
        if mime_type != "application/pdf":
            raise UnsupportedMediaType(mime_type)
        return await self._add(assignment_id, telegram_file_id, mime_type, "pdf")

    async def _add(
        self,
        assignment_id: int,
        telegram_file_id: str,
        mime_type: str,
        media_kind: str,
    ) -> Attempt:
        attempt = await self._session.scalar(
            select(AttemptRow)
            .where(AttemptRow.assignment_id == assignment_id, AttemptRow.status == "draft")
            .order_by(AttemptRow.id.desc())
            .limit(1)
        )
        if attempt is None:
            attempt = AttemptRow(assignment_id=assignment_id, status="draft")
            self._session.add(attempt)
            await self._session.flush()

        kinds = set(
            await self._session.scalars(
                select(AttemptMediaRow.media_kind).where(
                    AttemptMediaRow.attempt_id == attempt.id
                )
            )
        )
        count = await self._session.scalar(
            select(func.count()).select_from(AttemptMediaRow).where(
                AttemptMediaRow.attempt_id == attempt.id
            )
        )
        if kinds and media_kind not in kinds:
            raise MixedMediaTypes("a PDF cannot be mixed with images")
        if media_kind == "pdf" and count:
            raise MixedMediaTypes("an attempt accepts only one PDF")

        self._session.add(
            AttemptMediaRow(
                attempt_id=attempt.id,
                position=int(count or 0) + 1,
                telegram_file_id=telegram_file_id,
                mime_type=mime_type,
                media_kind=media_kind,
            )
        )
        await self._session.commit()
        return await self._model(attempt)

    async def submit(self, attempt_id: int) -> Attempt:
        attempt = await self._session.scalar(
            select(AttemptRow).where(AttemptRow.id == attempt_id).with_for_update()
        )
        if attempt is None:
            raise AttemptNotFound(str(attempt_id))
        if attempt.status == "queued":
            return await self._model(attempt)
        if attempt.status != "draft":
            raise AttemptAlreadySubmitted(attempt.status)
        count = await self._session.scalar(
            select(func.count()).select_from(AttemptMediaRow).where(
                AttemptMediaRow.attempt_id == attempt.id
            )
        )
        if not count:
            raise EmptyAttempt("at least one image or PDF is required")
        attempt.status = "queued"
        attempt.queued_at = datetime.now(UTC)
        await self._session.commit()
        return await self._model(attempt)

    async def _model(self, row: AttemptRow) -> Attempt:
        media_rows = await self._session.scalars(
            select(AttemptMediaRow)
            .where(AttemptMediaRow.attempt_id == row.id)
            .order_by(AttemptMediaRow.position)
        )
        return Attempt(
            id=row.id,
            assignment_id=row.assignment_id,
            status=row.status,
            media=tuple(
                SubmissionMedia.model_validate(media, from_attributes=True)
                for media in media_rows
            ),
        )
