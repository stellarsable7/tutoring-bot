import base64
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amath_bot.jobs.mark_attempt import MarkingPipelineError


class OCRResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    complete: bool
    lines: tuple[str, ...]
    unclear: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)


class ProposedDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    part: str
    marks_awarded: int = Field(ge=0)
    maximum: int = Field(ge=1)
    reason: str
    student_lines: tuple[str, ...]
    provider_confidence: float = Field(ge=0, le=1)


class ProposedGrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total: int = Field(ge=0)
    decisions: tuple[ProposedDecision, ...]
    feedback: tuple[str, ...]
    unclear: tuple[str, ...] = ()


class OllamaVisionOCR:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 180,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model
        self._timeout = timeout_seconds

    async def transcribe(self, image: bytes) -> OCRResult:
        prompt = (
            "Transcribe only the student's handwritten mathematical working, in reading order. "
            "Preserve equations using plain text or LaTeX. Do not solve, correct, or infer missing "
            "work. Return JSON containing: complete (boolean), lines (array of strings), unclear "
            "(array describing each uncertain region), and confidence (number from 0 to 1). If any "
            "symbol or line is uncertain, set complete to false and name it in unclear."
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "format": OCRResult.model_json_schema(),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image).decode("ascii")],
                }
            ],
            "options": {"temperature": 0, "num_predict": 1400},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload)
                response.raise_for_status()
            content = response.json()["message"]["content"]
            return OCRResult.model_validate_json(content)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as error:
            raise MarkingPipelineError("local vision OCR failed") from error

    async def propose_grade(
        self,
        *,
        transcription: tuple[str, ...],
        solution_images: tuple[bytes, ...],
        maximum: int,
    ) -> ProposedGrade:
        prompt = (
            "You are proposing a Singapore O-Level Additional Mathematics mark for tutor review. "
            "The attached image(s) are the published worked solution and annotated mark scheme. "
            f"The question is worth exactly {maximum} marks. Compare only the student's OCR text "
            "below with the published scheme. Award method/follow-through marks where the scheme "
            "supports them. Never invent a marking step. Feedback must diagnose the submitted "
            "method without revealing a corrected answer or model solution. Return JSON with total, "
            "decisions, feedback, and unclear. Each decision must contain part, marks_awarded, "
            "maximum, reason, student_lines, and provider_confidence. If the scheme or OCR is "
            "ambiguous, list the exact issue in unclear.\n\nStudent OCR:\n"
            + "\n".join(f"{index}. {line}" for index, line in enumerate(transcription, 1))
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "format": ProposedGrade.model_json_schema(),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [
                        base64.b64encode(image).decode("ascii") for image in solution_images
                    ],
                }
            ],
            "options": {"temperature": 0, "num_predict": 2200},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload)
                response.raise_for_status()
            proposed = ProposedGrade.model_validate_json(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as error:
            raise MarkingPipelineError("local provisional grading failed") from error
        calculated_total = sum(item.marks_awarded for item in proposed.decisions)
        if calculated_total > maximum or sum(item.maximum for item in proposed.decisions) > maximum:
            raise MarkingPipelineError("provisional grade exceeds the published maximum")
        if any(item.marks_awarded > item.maximum for item in proposed.decisions):
            raise MarkingPipelineError("provisional decision exceeds its maximum")
        return proposed.model_copy(update={"total": calculated_total})
