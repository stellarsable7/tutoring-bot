from io import BytesIO
from typing import Protocol

import fitz  # type: ignore[import-untyped]
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.jobs.mark_attempt import MarkingOutcome, MarkingPipelineError
from amath_bot.providers.ollama_vision import OCRResult
from amath_bot.submissions.tables import AttemptMediaRow, AttemptRow


class VisionOCR(Protocol):
    async def transcribe(self, image: bytes) -> OCRResult: ...


class LocalVisionPipeline:
    """Local OCR with mandatory tutor review before a mark reaches a student."""

    def __init__(self, session: AsyncSession, bot: Bot, ocr: VisionOCR) -> None:
        self._session = session
        self._bot = bot
        self._ocr = ocr

    async def mark(self, attempt_id: int) -> MarkingOutcome:
        row = (
            await self._session.execute(
                select(AttemptRow, SourceQuestionRow)
                .join(AssignmentRow, AssignmentRow.id == AttemptRow.assignment_id)
                .join(SourceQuestionRow, SourceQuestionRow.id == AssignmentRow.source_question_id)
                .where(AttemptRow.id == attempt_id)
            )
        ).one_or_none()
        if row is None:
            raise MarkingPipelineError("attempt or assigned question was not found")
        _attempt, question = row
        media = tuple(
            await self._session.scalars(
                select(AttemptMediaRow)
                .where(AttemptMediaRow.attempt_id == attempt_id)
                .order_by(AttemptMediaRow.position)
            )
        )
        if not media:
            raise MarkingPipelineError("attempt contains no media")

        results: list[OCRResult] = []
        for item in media:
            downloaded = BytesIO()
            await self._bot.download(item.telegram_file_id, destination=downloaded)
            payload = downloaded.getvalue()
            pages = self._pdf_pages(payload) if item.media_kind == "pdf" else (payload,)
            for page in pages:
                results.append(await self._ocr.transcribe(page))

        lines = [line for result in results for line in result.lines]
        unclear = [detail for result in results for detail in result.unclear]
        confidence = min((result.confidence for result in results), default=0.0)
        decisions = (
            {
                "student_lines": lines,
                "provider_confidence": confidence,
                "ocr_complete": all(result.complete for result in results),
                "unclear": unclear,
            },
        )
        reasons = ["Tutor approval is required for locally generated marks."]
        if unclear or not all(result.complete for result in results):
            description = "; ".join(unclear) or "The model could not read all of the working."
            reasons.append(f"Tutor clarification required: {description}")
        if not question.marking_steps:
            reasons.append("No validated step-by-step marking scheme is stored for this question.")
        return MarkingOutcome(
            total=0,
            maximum=question.marks,
            feedback=("OCR transcription prepared for tutor review.",),
            review_reasons=tuple(reasons),
            decisions=decisions,
        )

    @staticmethod
    def _pdf_pages(payload: bytes) -> tuple[bytes, ...]:
        try:
            document = fitz.open(stream=payload, filetype="pdf")
            if document.page_count > 10:
                raise MarkingPipelineError("PDF submissions are limited to 10 pages")
            return tuple(
                page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False).tobytes("png")
                for page in document
            )
        except (fitz.FileDataError, RuntimeError) as error:
            raise MarkingPipelineError("submitted PDF is unreadable") from error
