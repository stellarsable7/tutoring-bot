from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.catalogue.eligibility import eligibility_errors
from amath_bot.catalogue.models import SolutionKind, SourceQuestion, StoredQuestion
from amath_bot.catalogue.tables import SourceQuestionRow


class DuplicateSourceQuestion(ValueError):
    """Raised when a source identity already exists."""


class IneligibleSourceQuestion(ValueError):
    """Raised when a question does not satisfy catalogue policy."""


def _stored(row: SourceQuestionRow) -> StoredQuestion:
    return StoredQuestion.model_validate(
        {
            "id": row.id,
            "source_url": row.source_url,
            "solution_url": row.solution_url,
            "provider": row.provider,
            "school": row.school,
            "year": row.year,
            "paper": row.paper,
            "question_number": row.question_number,
            "syllabus_version": row.syllabus_version,
            "objective_codes": tuple(row.objective_codes),
            "marks": row.marks,
            "solution_kind": SolutionKind(row.solution_kind) if row.solution_kind else None,
            "tutor_validated": row.tutor_validated,
        }
    )


class CatalogueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, item: SourceQuestion) -> StoredQuestion:
        errors = eligibility_errors(item)
        if errors:
            raise IneligibleSourceQuestion("; ".join(errors))
        row = SourceQuestionRow(
            source_url=str(item.source_url),
            solution_url=str(item.solution_url) if item.solution_url else None,
            provider=item.provider,
            school=item.school,
            year=item.year,
            paper=item.paper,
            question_number=item.question_number,
            syllabus_version=item.syllabus_version,
            objective_codes=list(item.objective_codes),
            marks=item.marks,
            solution_kind=item.solution_kind.value if item.solution_kind else None,
            tutor_validated=item.tutor_validated,
            eligible=True,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise DuplicateSourceQuestion(
                f"{item.provider}:{item.school}:{item.year}:{item.paper}:{item.question_number}"
            ) from error
        await self._session.refresh(row)
        return _stored(row)

    async def get(self, question_id: int) -> StoredQuestion | None:
        row = await self._session.get(SourceQuestionRow, question_id)
        return None if row is None else _stored(row)
