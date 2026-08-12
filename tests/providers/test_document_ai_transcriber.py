import base64
import json
from typing import Any

import httpx
import pytest

from amath_bot.jobs.mark_attempt import OCRValidationError, RateLimitError
from amath_bot.providers.document_ai_transcriber import DocumentAITranscriber

SERVICE_ACCOUNT = json.dumps(
    {
        "type": "service_account",
        "project_id": "project",
        "private_key_id": "key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\ninvalid-for-mock\n-----END PRIVATE KEY-----\n",
        "client_email": "ocr@project.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
)


def transcriber(client: httpx.AsyncClient) -> DocumentAITranscriber:
    instance = object.__new__(DocumentAITranscriber)
    instance._client = client
    instance._url = (
        "https://us-documentai.googleapis.com/v1/projects/project/locations/us/"
        "processors/processor:process"
    )
    return instance


def test_document_ai_uses_application_default_credentials_when_json_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = object()
    monkeypatch.setattr(
        "amath_bot.providers.document_ai_transcriber.google.auth.default",
        lambda *, scopes: (credentials, "chloe-tutoring-bot"),
    )

    instance = DocumentAITranscriber(
        httpx.AsyncClient(),
        project_id="chloe-tutoring-bot",
        location="us",
        processor_id="processor",
    )

    assert instance._credentials is credentials


@pytest.mark.asyncio
async def test_document_ai_enables_enterprise_math_ocr() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        document = {
            "text": "noise\\frac{a}{b}\n2x",
            "pages": [
                {
                    "visualElements": [
                        {
                            "type": "math_formula",
                            "layout": {
                                "textAnchor": {
                                    "textSegments": [{"startIndex": "5", "endIndex": "16"}]
                                }
                            },
                        },
                        {
                            "type": "math_formula",
                            "layout": {
                                "textAnchor": {
                                    "textSegments": [{"startIndex": "17", "endIndex": "19"}]
                                }
                            },
                        },
                    ]
                }
            ],
        }
        return httpx.Response(200, json={"document": document})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        instance = transcriber(client)

        async def token() -> str:
            return "access-token"

        instance._access_token = token  # type: ignore[method-assign]
        result = await instance.transcribe(b"png")

    assert captured["url"].startswith("https://us-documentai.googleapis.com/v1/")
    assert captured["authorization"] == "Bearer access-token"
    payload = captured["payload"]
    assert payload["rawDocument"] == {
        "mimeType": "image/png",
        "content": base64.b64encode(b"png").decode("ascii"),
    }
    assert payload["processOptions"]["ocrConfig"]["premiumFeatures"] == {
        "enableMathOcr": True
    }
    assert payload["processOptions"]["ocrConfig"]["enableSymbol"] is True
    assert [line.latex for line in result.lines] == ["\\frac{a}{b}", "2x"]


@pytest.mark.asyncio
async def test_document_ai_stores_raw_response_when_no_formula_is_returned() -> None:
    response = {"document": {"text": "ordinary text", "pages": [{}]}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))
    ) as client:
        instance = transcriber(client)

        async def token() -> str:
            return "access-token"

        instance._access_token = token  # type: ignore[method-assign]
        with pytest.raises(OCRValidationError) as raised:
            await instance.transcribe(b"png")
    assert json.loads(raised.value.raw_response) == response
    assert "no math_formula" in raised.value.validation_error


@pytest.mark.asyncio
async def test_document_ai_classifies_429_as_retryable() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429))
    ) as client:
        instance = transcriber(client)

        async def token() -> str:
            return "access-token"

        instance._access_token = token  # type: ignore[method-assign]
        with pytest.raises(RateLimitError):
            await instance.transcribe(b"png")
