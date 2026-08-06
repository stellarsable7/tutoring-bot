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
            "format": "json",
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
