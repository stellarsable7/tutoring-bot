import base64
import logging
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from amath_bot.jobs.mark_attempt import MarkingConfigurationError, MarkingPipelineError
from amath_bot.providers.vision_models import OCRResult, ProposedGrade

OPENROUTER_MODEL = "openrouter/free"
_CONFIGURATION_ERROR_STATUSES = frozenset({400, 401, 403, 422})

_logger = logging.getLogger(__name__)
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class OpenRouterVisionOCR:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/chat/completions"

    async def transcribe(self, image: bytes) -> OCRResult:
        prompt = (
            "Transcribe only the student's handwritten mathematical working, in reading order. "
            "Preserve equations using plain text or LaTeX. Do not solve, correct, or infer missing "
            "work. Return JSON containing: complete (boolean), lines (array of strings), unclear "
            "(array describing each uncertain region), and confidence (number from 0 to 1). If any "
            "symbol or line is uncertain, set complete to false and name it in unclear."
        )
        return await self._complete(
            prompt=prompt,
            images=(image,),
            schema=OCRResult,
            schema_name="ocr_result",
            stage="OCR",
            failure_message="OpenRouter vision OCR failed",
        )

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
        proposed = await self._complete(
            prompt=prompt,
            images=solution_images,
            schema=ProposedGrade,
            schema_name="proposed_grade",
            stage="grading",
            failure_message="OpenRouter provisional grading failed",
            max_tokens=2200,
        )
        calculated_total = sum(item.marks_awarded for item in proposed.decisions)
        if calculated_total > maximum or sum(item.maximum for item in proposed.decisions) > maximum:
            raise MarkingPipelineError("provisional grade exceeds the published maximum")
        if any(item.marks_awarded > item.maximum for item in proposed.decisions):
            raise MarkingPipelineError("provisional decision exceeds its maximum")
        if any(item.marks_awarded and not item.student_lines for item in proposed.decisions):
            raise MarkingPipelineError("awarded marks lack student evidence")
        return proposed.model_copy(update={"total": calculated_total})

    async def _complete(
        self,
        *,
        prompt: str,
        images: Sequence[bytes],
        schema: type[_ModelT],
        schema_name: str,
        stage: str,
        failure_message: str,
        max_tokens: int | None = None,
    ) -> _ModelT:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,"
                    + base64.b64encode(image).decode("ascii")
                },
            }
            for image in images
        )
        payload: dict[str, Any] = {
            "model": OPENROUTER_MODEL,
            "stream": False,
            "temperature": 0,
            "provider": {"require_parameters": True},
            "messages": [{"role": "user", "content": content}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.RequestError as error:
            raise MarkingPipelineError(failure_message) from error

        if response.status_code in _CONFIGURATION_ERROR_STATUSES:
            raise MarkingConfigurationError(
                f"OpenRouter rejected provider request ({response.status_code})"
            )
        if response.status_code >= 400:
            raise MarkingPipelineError(failure_message)

        try:
            envelope = response.json()
            if not isinstance(envelope, Mapping):
                raise TypeError
            choices = envelope["choices"]
            if not isinstance(choices, list) or not choices:
                raise TypeError
            choice = choices[0]
            if not isinstance(choice, Mapping):
                raise TypeError
            message = choice["message"]
            if not isinstance(message, Mapping):
                raise TypeError
            if message.get("refusal") is not None:
                raise ValueError
            response_content = message["content"]
            if not isinstance(response_content, str):
                raise TypeError
            result = schema.model_validate_json(response_content)
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise MarkingPipelineError(failure_message) from error

        selected_model = envelope.get("model")
        if isinstance(selected_model, str) and selected_model:
            _logger.info("OpenRouter completed %s via %s", stage, selected_model)
        return result
