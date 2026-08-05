from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.people.tables import StudentRow
from amath_bot.submissions.tables import AttemptRow


@dataclass(frozen=True)
class TutorProgress:
    student_name: str
    completed: int
    missed: int
    pending_reviews: int
    recent_marks: tuple[str, ...]
    objective_scores: tuple[str, ...]
    common_errors: tuple[str, ...]

    def render(self) -> str:
        marks = ", ".join(self.recent_marks) or "none"
        objectives = ", ".join(self.objective_scores) or "not enough data"
        errors = ", ".join(self.common_errors) or "none"
        return (
            f"Progress for {self.student_name}\n"
            f"Completed: {self.completed} | Missed: {self.missed} | "
            f"Pending reviews: {self.pending_reviews}\n"
            f"Recent marks: {marks}\nMastery by objective: {objectives}\n"
            f"Common review flags: {errors}"
        )


class ProgressReporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_student(self, display_name: str) -> TutorProgress:
        student = await self._session.scalar(
            select(StudentRow).where(StudentRow.display_name == display_name)
        )
        if student is None:
            raise ValueError("student not found")
        assignments = tuple(
            await self._session.scalars(
                select(AssignmentRow).where(AssignmentRow.student_id == student.id)
            )
        )
        assignment_ids = [assignment.id for assignment in assignments]
        attempts = (
            tuple(
                await self._session.scalars(
                    select(AttemptRow)
                    .where(AttemptRow.assignment_id.in_(assignment_ids))
                    .order_by(AttemptRow.created_at.desc(), AttemptRow.id.desc())
                )
            )
            if assignment_ids
            else ()
        )
        completed_attempts = [
            attempt
            for attempt in attempts
            if attempt.status in {"marked", "reviewed"} and attempt.result_maximum
        ]
        question_ids = [assignment.source_question_id for assignment in assignments]
        questions = {
            question.id: question
            for question in (
                tuple(
                    await self._session.scalars(
                        select(SourceQuestionRow).where(SourceQuestionRow.id.in_(question_ids))
                    )
                )
                if question_ids
                else ()
            )
        }
        assignment_questions = {
            assignment.id: questions.get(assignment.source_question_id)
            for assignment in assignments
        }
        totals: dict[str, list[float]] = {}
        for attempt in completed_attempts:
            question = assignment_questions.get(attempt.assignment_id)
            if question is None:
                continue
            ratio = (attempt.result_total or 0) / (attempt.result_maximum or 1)
            for objective in question.objective_codes:
                totals.setdefault(objective, []).append(ratio)
        objectives = tuple(
            f"{code} {sum(values) / len(values):.0%}" for code, values in sorted(totals.items())
        )
        errors: dict[str, int] = {}
        for attempt in attempts:
            for reason in attempt.review_reasons or []:
                errors[reason] = errors.get(reason, 0) + 1
        pending = sum(attempt.status == "flagged" for attempt in attempts)
        missed = sum(assignment.status in {"missed", "expired"} for assignment in assignments)
        return TutorProgress(
            student_name=student.display_name,
            completed=len(completed_attempts),
            missed=missed,
            pending_reviews=pending,
            recent_marks=tuple(
                f"{attempt.result_total}/{attempt.result_maximum}"
                for attempt in completed_attempts[:5]
            ),
            objective_scores=objectives,
            common_errors=tuple(
                name for name, _ in sorted(errors.items(), key=lambda item: (-item[1], item[0]))[:3]
            ),
        )
