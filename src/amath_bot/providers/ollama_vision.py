import base64
from typing import Any

import httpx
from pydantic import ValidationError

from amath_bot.jobs.mark_attempt import MarkingPipelineError
from amath_bot.providers.vision_models import OCRResult, ProposedDecision, ProposedGrade

__all__ = ["OCRResult", "ProposedDecision", "ProposedGrade"]


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
            "You are a mark-scheme applier, not a maths solver. The attached image(s) are the only "
            "authoritative published worked solution and annotated marking scheme. Do not derive an "
            "answer, invent an alternative scheme, or use your own solution. "
            f"The question is worth exactly {maximum} marks. Compare the student's OCR text only "
            "against explicit visible steps and mark annotations in the images. Every awarded mark "
            "must quote or precisely identify its visible published scheme step in scheme_evidence "
            "and cite the matching student_lines. If a scheme step is unreadable or absent, award "
            "zero for it and add the exact issue to unclear for the tutor. Method and follow-through "
            "marks may be awarded only when explicitly supported by the published scheme. Feedback "
            "must diagnose the submitted work without giving a corrected answer or model solution. "
            "Return JSON with total, decisions, feedback, and unclear. Each decision must contain "
            "part, marks_awarded, maximum, scheme_evidence, reason, student_lines, and a numeric "
            "provider_confidence from 0 to 1.\n\nStudent OCR:\n"
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
        if any(item.marks_awarded and not item.student_lines for item in proposed.decisions):
            raise MarkingPipelineError("awarded marks lack student evidence")
        return proposed.model_copy(update={"total": calculated_total})
