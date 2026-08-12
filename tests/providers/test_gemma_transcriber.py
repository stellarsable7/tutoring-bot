import json
from typing import Any

import httpx
import pytest

from amath_bot.jobs.mark_attempt import OCRValidationError, RateLimitError
from amath_bot.providers.gemma_transcriber import (
    GEMMA_TRANSCRIPTION_MODEL,
    GemmaTranscriber,
)


@pytest.mark.asyncio
async def test_gemma_transcriber_uses_google_api_directly() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers["x-goog-api-key"]
        captured["payload"] = json.loads(request.content)
        text = json.dumps(
            {"lines": [{"id": 1, "latex": "x=2"}], "uncertain_tokens": []}
        )
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GemmaTranscriber(
            client, api_key="google-key", base_url="https://google.test/v1beta"
        ).transcribe(b"image")

    assert GEMMA_TRANSCRIPTION_MODEL == "gemma-4-26b-a4b-it"
    assert captured["url"] == (
        "https://google.test/v1beta/models/gemma-4-26b-a4b-it:generateContent"
    )
    assert captured["key"] == "google-key"
    config = captured["payload"]["generationConfig"]
    assert config["temperature"] == 0
    assert config["maxOutputTokens"] == 1200
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert config["responseMimeType"] == "application/json"
    assert result.lines[0].latex == "x=2"


@pytest.mark.asyncio
async def test_gemma_transcriber_stores_raw_deterministic_failure() -> None:
    raw = json.dumps(
        {"lines": [{"id": 1, "latex": "\\text{comment}"}], "uncertain_tokens": []}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": raw}]}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OCRValidationError) as raised:
            await GemmaTranscriber(client, api_key="key").transcribe(b"image")
    assert raised.value.raw_response == raw
    assert "commentary" in raised.value.validation_error


@pytest.mark.asyncio
async def test_gemma_transcriber_classifies_429_as_retryable() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429))
    ) as client:
        with pytest.raises(RateLimitError):
            await GemmaTranscriber(client, api_key="key").transcribe(b"image")
