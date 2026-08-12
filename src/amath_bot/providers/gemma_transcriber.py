import asyncio
import base64
from collections.abc import Mapping

import httpx
from pydantic import ValidationError

from amath_bot.jobs.mark_attempt import (
    MarkingConfigurationError,
    MarkingPipelineError,
    OCRValidationError,
    RateLimitError,
)
from amath_bot.providers.vision_models import OCRResult

GEMMA_TRANSCRIPTION_MODEL = "gemma-4-26b-a4b-it"
_CONFIGURATION_ERROR_STATUSES = frozenset({400, 401, 403, 404, 422})


class GemmaTranscriber:
    """Mathematical OCR through Google's hosted Gemma API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._url = (
            f"{base_url.rstrip('/')}/models/{GEMMA_TRANSCRIPTION_MODEL}:generateContent"
        )

    async def transcribe(self, image: bytes) -> OCRResult:
        prompt = (
            "You are a mathematical transcription system.\n\n"
            "Transcribe the student's handwritten mathematical working in reading order. "
            "Do not solve, correct, simplify, grade, or explain the work.\n\n"
            "SEMANTIC NORMALISATION\nConvert handwritten mathematical notation into standard "
            "LaTeX without changing its mathematical meaning. For example:\n"
            "- cosec x → \\csc{x}\n- cot x → \\cot{x}\n- cos²x → \\cos^{2}{x}\n\n"
            "LINE RULES\n1. Return one mathematical expression for each stage of the student's "
            "working.\n2. Do not include a leading equals sign in a line.\n"
            "3. If the student writes only '= expression', store only 'expression'.\n"
            "4. Exclude labels such as RHS, LHS, hence, therefore, and working annotations from "
            "the latex field.\n5. Preserve mathematical mistakes exactly. Normalise notation only; "
            "do not correct the mathematics.\n6. Use explicit braces and fractions: \\sin{x}, "
            "\\cos{x}, \\cot{x}, \\frac{a}{b}.\n7. Do not use \\text, Markdown, dollar "
            "signs, or display-math delimiters.\n8. Return raw JSON only. Do not wrap it in a "
            "code fence.\n\nUNCERTAINTY\nIf a token is genuinely unreadable:\n- make the best "
            "literal transcription that keeps the line syntactically valid;\n- record the line "
            "ID, token and alternatives in uncertain_tokens;\n- do not invent an explanation.\n\n"
            "Return exactly this JSON structure:\n"
            '{"lines":[{"id":1,"latex":"..."}],"uncertain_tokens":'
            '[{"line_id":1,"token":"...","alternatives":["...","..."]}]}\n\n'
            "Use an empty uncertain_tokens array when everything is readable."
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(image).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 1200,
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "responseJsonSchema": OCRResult.model_json_schema(),
            },
        }
        try:
            async with asyncio.timeout(60):
                response = await self._client.post(
                    self._url,
                    headers={"x-goog-api-key": self._api_key},
                    json=payload,
                )
        except (TimeoutError, httpx.RequestError) as error:
            raise MarkingPipelineError("Gemma OCR failed") from error
        if response.status_code in _CONFIGURATION_ERROR_STATUSES:
            raise MarkingConfigurationError(
                f"Google rejected Gemma OCR request ({response.status_code})"
            )
        if response.status_code == 429:
            raise RateLimitError("Gemma OCR failed")
        if response.status_code == 408 or response.status_code >= 500:
            raise MarkingPipelineError("Gemma OCR failed")
        if response.status_code >= 400:
            raise MarkingConfigurationError(
                f"Google rejected Gemma OCR request ({response.status_code})"
            )

        raw_response = response.text
        try:
            envelope = response.json()
            if not isinstance(envelope, Mapping):
                raise TypeError("response envelope is not an object")
            candidates = envelope["candidates"]
            if not isinstance(candidates, list) or not candidates:
                raise TypeError("response has no candidate")
            content = candidates[0]["content"]
            parts = content["parts"]
            raw_response = parts[0]["text"]
            if not isinstance(raw_response, str):
                raise TypeError("candidate text is not a string")
            return OCRResult.model_validate_json(raw_response)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise OCRValidationError(
                f"{type(error).__name__}: {error}", raw_response
            ) from error
