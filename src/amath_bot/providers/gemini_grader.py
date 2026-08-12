import logging
from collections.abc import Mapping, Sequence
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from amath_bot.jobs.mark_attempt import (
    MarkingConfigurationError,
    MarkingPipelineError,
    MarkingValidationError,
    RateLimitError,
)
from amath_bot.providers.openrouter_vision import OpenRouterGrader

GEMINI_GRADING_MODEL = "gemini-3.1-flash-lite"
_CONFIGURATION_ERROR_STATUSES = frozenset({400, 401, 403, 404})

logger = logging.getLogger(__name__)
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class GeminiGrader(OpenRouterGrader):
    """Text-only grader using Google's Gemini API directly."""

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
            f"{base_url.rstrip('/')}/models/{GEMINI_GRADING_MODEL}:generateContent"
        )

    async def _complete(
        self,
        *,
        prompt: str,
        images: Sequence[bytes],
        schema: type[_ModelT],
        schema_name: str,
        stage: str,
        failure_message: str,
        model: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        overall_timeout: float = 180,
    ) -> _ModelT:
        del schema_name, model, reasoning_effort, overall_timeout
        if images:
            raise MarkingPipelineError("Gemini grading received unexpected image data")
        generation_config: dict[str, object] = {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema.model_json_schema(),
        }
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if temperature is not None:
            generation_config["temperature"] = temperature
        try:
            response = await self._client.post(
                self._url,
                headers={"x-goog-api-key": self._api_key},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": generation_config,
                },
            )
        except httpx.RequestError as error:
            raise MarkingPipelineError("Gemini provisional grading failed") from error
        if response.status_code in _CONFIGURATION_ERROR_STATUSES:
            raise MarkingConfigurationError(
                f"Gemini rejected provider request ({response.status_code})"
            )
        if response.status_code == 429:
            raise RateLimitError("Gemini provisional grading failed", retry_status="transcribed")
        if response.status_code == 408 or response.status_code >= 500:
            raise MarkingPipelineError("Gemini provisional grading failed")
        if response.status_code >= 400:
            raise MarkingConfigurationError(
                f"Gemini rejected provider request ({response.status_code})"
            )
        try:
            envelope = response.json()
            if not isinstance(envelope, Mapping):
                raise TypeError
            candidates = envelope["candidates"]
            if not isinstance(candidates, list) or not candidates:
                raise TypeError
            candidate = candidates[0]
            if not isinstance(candidate, Mapping):
                raise TypeError
            content = candidate["content"]
            if not isinstance(content, Mapping):
                raise TypeError
            parts = content["parts"]
            if not isinstance(parts, list) or not parts or not isinstance(parts[0], Mapping):
                raise TypeError
            text = parts[0]["text"]
            if not isinstance(text, str):
                raise TypeError
            result = schema.model_validate_json(text)
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise MarkingValidationError("Gemini provisional grading failed") from error
        logger.info("Gemini completed %s via %s", stage, GEMINI_GRADING_MODEL)
        return result
