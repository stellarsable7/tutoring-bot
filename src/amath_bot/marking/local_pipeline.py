import asyncio
import re
from io import BytesIO
from typing import Any, Protocol, cast

import fitz  # type: ignore[import-untyped]
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amath_bot.assignments.tables import AssignmentRow
from amath_bot.catalogue.tables import SourceQuestionRow
from amath_bot.jobs.mark_attempt import (
    MarkingConfigurationError,
    MarkingOutcome,
    MarkingPipelineError,
)
from amath_bot.providers.vision_models import OCRResult, ProposedGrade
from amath_bot.submissions.tables import AttemptMediaRow, AttemptRow


class VisionTranscriber(Protocol):
    async def transcribe(self, image: bytes) -> OCRResult: ...


class TextGrader(Protocol):
    async def propose_grade(
        self,
        *,
        transcription: tuple[str, ...],
        problem_text: str,
        solution_text: str,
        maximum: int,
        expected_parts: tuple[str, ...] = (),
    ) -> ProposedGrade: ...


class LocalVisionPipeline:
    """Vision OCR with mandatory tutor review before a mark reaches a student."""

    def __init__(
        self,
        session: AsyncSession,
        bot: Bot,
        transcriber: VisionTranscriber,
        grader: TextGrader | None = None,
    ) -> None:
        self._session = session
        self._bot = bot
        self._transcriber = transcriber
        self._grader = grader if grader is not None else cast(TextGrader, transcriber)

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
        attempt, question = row
        if attempt.ocr_transcription is None:
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
                    results.append(await self._transcriber.transcribe(page))

            ocr_lines = [line for result in results for line in result.lines]
            lines = [f"{index}. {line.latex}" for index, line in enumerate(ocr_lines, 1)]
            unclear = [
                (
                    f"Line {detail.line_id}: uncertain token {detail.token}; "
                    f"alternatives: {', '.join(detail.alternatives) or 'none supplied'}"
                )
                for result in results
                for detail in result.uncertain_tokens
            ]
            confidence = 1.0 if not unclear else 0.5
            complete = not unclear
            attempt.ocr_transcription = [
                {"id": index, "latex": line.latex}
                for index, line in enumerate(ocr_lines, 1)
            ]
            attempt.ocr_unclear = unclear
            attempt.ocr_confidence = confidence
            attempt.ocr_complete = complete
            attempt.status = "transcribed"
            await self._session.commit()
        else:
            lines = self._stored_lines(attempt.ocr_transcription)
            unclear = list(attempt.ocr_unclear or [])
            confidence = attempt.ocr_confidence or 0.0
            complete = bool(attempt.ocr_complete)

        attempt.status = "grading"
        await self._session.commit()
        proposed: ProposedGrade | None = None
        if question.solution_asset_path:
            try:
                problem_text, solution_text = await asyncio.gather(
                    asyncio.to_thread(self._asset_text, question.asset_path),
                    asyncio.to_thread(self._asset_text, question.solution_asset_path),
                )
            except (OSError, fitz.FileDataError, RuntimeError) as error:
                raise MarkingPipelineError("published solution asset is unavailable") from error
            try:
                proposed = await self._grader.propose_grade(
                    transcription=tuple(lines),
                    problem_text=problem_text,
                    solution_text=solution_text,
                    maximum=question.marks,
                    expected_parts=await asyncio.to_thread(
                        self._question_parts, question.asset_path
                    ),
                )
            except MarkingConfigurationError as error:
                raise MarkingConfigurationError(
                    error.diagnostic, retry_status="transcribed"
                ) from error
            except MarkingPipelineError as error:
                raise MarkingPipelineError(
                    error.diagnostic, retry_status="transcribed"
                ) from error
            unclear.extend(proposed.unclear)
        decisions = (
            tuple(item.model_dump() for item in proposed.decisions)
            if proposed is not None
            else (
                {
                    "student_lines": lines,
                    "provider_confidence": confidence,
                    "ocr_complete": complete,
                    "unclear": unclear,
                },
            )
        )
        reasons = ["Tutor approval is required for AI-generated marks."]
        if unclear or not complete:
            description = "; ".join(unclear) or "The model could not read all of the working."
            reasons.append(f"Tutor clarification required: {description}")
        if proposed is None:
            reasons.append("No question-scoped published solution is stored for this question.")
        return MarkingOutcome(
            total=proposed.total if proposed is not None else 0,
            maximum=question.marks,
            feedback=(
                proposed.feedback
                if proposed is not None
                else ("OCR transcription prepared for tutor review.",)
            ),
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

    @staticmethod
    def _question_parts(asset_path: str | None) -> tuple[str, ...]:
        if not asset_path:
            return ()
        try:
            with fitz.open(asset_path) as document:
                text = "\n".join(page.get_text() for page in document)
        except (OSError, fitz.FileDataError, RuntimeError):
            return ()
        return tuple(dict.fromkeys(re.findall(r"\(([a-z])\)", text, flags=re.IGNORECASE)))

    @staticmethod
    def _asset_text(asset_path: str | None) -> str:
        if not asset_path:
            return ""
        with fitz.open(asset_path) as document:
            return "\n".join(page.get_text() for page in document).strip()

    @staticmethod
    def _stored_lines(stored: list[Any]) -> list[str]:
        lines: list[str] = []
        for index, value in enumerate(stored, 1):
            if isinstance(value, dict) and isinstance(value.get("latex"), str):
                lines.append(f"{value.get('id', index)}. {value['latex']}")
            else:
                lines.append(str(value))
        return lines
