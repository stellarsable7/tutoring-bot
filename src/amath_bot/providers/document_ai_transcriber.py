import asyncio
import base64
import json
from collections.abc import Mapping
from typing import Any, cast

import httpx
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials

from amath_bot.jobs.mark_attempt import (
    MarkingConfigurationError,
    MarkingPipelineError,
    OCRValidationError,
    RateLimitError,
)
from amath_bot.providers.vision_models import OCRResult

_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_CONFIGURATION_ERROR_STATUSES = frozenset({400, 401, 403, 404, 422})


class DocumentAITranscriber:
    """Enterprise Document OCR with the premium Math OCR add-on."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        location: str,
        processor_id: str,
        service_account_json: str,
    ) -> None:
        self._client = client
        self._url = (
            f"https://{location}-documentai.googleapis.com/v1/projects/{project_id}"
            f"/locations/{location}/processors/{processor_id}:process"
        )
        try:
            info = json.loads(service_account_json)
            self._credentials = Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
                info, scopes=(_SCOPE,)
            )
        except (TypeError, ValueError, KeyError) as error:
            raise MarkingConfigurationError(
                "Google Cloud service-account JSON is invalid"
            ) from error

    async def _access_token(self) -> str:
        if not self._credentials.valid:
            await asyncio.to_thread(self._credentials.refresh, Request())
        if not self._credentials.token:
            raise MarkingConfigurationError("Google Cloud access token is unavailable")
        return cast(str, self._credentials.token)

    async def transcribe(self, image: bytes) -> OCRResult:
        payload = {
            "rawDocument": {
                "mimeType": "image/png",
                "content": base64.b64encode(image).decode("ascii"),
            },
            "processOptions": {
                "ocrConfig": {
                    "enableSymbol": True,
                    "premiumFeatures": {"enableMathOcr": True},
                }
            },
        }
        try:
            token = await self._access_token()
            async with asyncio.timeout(60):
                response = await self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
        except MarkingConfigurationError:
            raise
        except (TimeoutError, httpx.RequestError, OSError) as error:
            raise MarkingPipelineError("Document AI Math OCR failed") from error
        if response.status_code == 429:
            raise RateLimitError("Document AI Math OCR failed")
        if response.status_code == 408 or response.status_code >= 500:
            raise MarkingPipelineError("Document AI Math OCR failed")
        if response.status_code in _CONFIGURATION_ERROR_STATUSES or response.status_code >= 400:
            raise MarkingConfigurationError(
                f"Document AI rejected Math OCR request ({response.status_code})"
            )

        raw_response = response.text
        try:
            envelope = response.json()
            document = cast(Mapping[str, Any], envelope["document"])
            text = document["text"]
            pages = document["pages"]
            if not isinstance(text, str) or not isinstance(pages, list):
                raise TypeError("Document AI response has invalid document fields")
            formulas: list[str] = []
            for page in pages:
                if not isinstance(page, Mapping):
                    raise TypeError("Document AI page is not an object")
                elements = page.get("visualElements", [])
                if not isinstance(elements, list):
                    raise TypeError("Document AI visualElements is not a list")
                for element in elements:
                    if (
                        not isinstance(element, Mapping)
                        or element.get("type") != "math_formula"
                    ):
                        continue
                    latex = self._anchored_text(text, element).strip()
                    latex = latex.removeprefix("$$").removesuffix("$$").strip()
                    if latex:
                        formulas.extend(
                            line.strip().lstrip("=").strip()
                            for line in latex.splitlines()
                            if line.strip()
                        )
            if not formulas:
                raise ValueError("Document AI returned no math_formula visual elements")
            return OCRResult.model_validate(
                {
                    "lines": [
                        {"id": index, "latex": latex}
                        for index, latex in enumerate(formulas, 1)
                    ],
                    "uncertain_tokens": [],
                }
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise OCRValidationError(
                f"{type(error).__name__}: {error}", raw_response
            ) from error

    @staticmethod
    def _anchored_text(text: str, element: Mapping[str, Any]) -> str:
        layout = cast(Mapping[str, Any], element["layout"])
        anchor = cast(Mapping[str, Any], layout["textAnchor"])
        segments = anchor["textSegments"]
        if not isinstance(segments, list):
            raise TypeError("math formula textSegments is not a list")
        chunks: list[str] = []
        for segment in segments:
            if not isinstance(segment, Mapping):
                raise TypeError("math formula text segment is not an object")
            start = int(segment.get("startIndex", 0))
            end = int(segment["endIndex"])
            chunks.append(text[start:end])
        return "".join(chunks)
