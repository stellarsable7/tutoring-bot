import base64
import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from amath_bot.jobs.mark_attempt import MarkingConfigurationError, MarkingPipelineError
from amath_bot.providers.openrouter_vision import (
    GRADING_MODEL,
    TRANSCRIPTION_MODEL,
    OpenRouterVisionOCR,
)
from amath_bot.providers.vision_models import OCRResult, ProposedGrade

API_KEY = "secret-openrouter-key"


def _ocr_content(**updates: Any) -> str:
    value = {
        "lines": [{"id": 1, "latex": "x = 2"}],
        "uncertain_tokens": [],
    }
    value.update(updates)
    return json.dumps(value)


def _grade_content(**updates: Any) -> str:
    value = {
        "total": 99,
        "final_answer_correct": True,
        "method_valid": True,
        "overall_verdict": "correct",
        "reasoning": "The answer and supporting method are valid.",
        "decisions": [
            {
                "part": "a",
                "marks_awarded": 2,
                "maximum": 2,
                "scheme_evidence": "M1 and A1",
                "reason": "Matches the scheme",
                "student_lines": ["1. x = 2"],
                "provider_confidence": 0.8,
            },
            {
                "part": "b",
                "marks_awarded": 1,
                "maximum": 2,
                "scheme_evidence": "M1",
                "reason": "Correct method",
                "student_lines": ["2. y = 3"],
                "provider_confidence": 0.7,
            },
        ],
        "feedback": ["Check the final simplification."],
        "unclear": [],
    }
    value.update(updates)
    return json.dumps(value)


def _response(content: Any = None, **updates: Any) -> httpx.Response:
    message: dict[str, Any] = {"content": _ocr_content() if content is None else content}
    payload: dict[str, Any] = {"choices": [{"message": message}]}
    payload.update(updates)
    return httpx.Response(200, json=payload)


async def _adapter(handler: Callable[[httpx.Request], httpx.Response]) -> tuple[
    OpenRouterVisionOCR, httpx.AsyncClient
]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenRouterVisionOCR(client, api_key=API_KEY, base_url="https://router.test/v1/"), client


@pytest.mark.asyncio
async def test_transcribe_sends_pinned_free_vision_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return _response()

    adapter, client = await _adapter(handler)
    async with client:
        result = await adapter.transcribe(b"png-image")

    assert result == OCRResult(lines=({"id": 1, "latex": "x = 2"},))
    assert TRANSCRIPTION_MODEL == "google/gemma-4-26b-a4b-it:free"
    assert captured["url"] == "https://router.test/v1/chat/completions"
    assert captured["authorization"] == f"Bearer {API_KEY}"
    payload = captured["payload"]
    assert payload["model"] == "google/gemma-4-26b-a4b-it:free"
    assert payload["stream"] is False
    assert "temperature" not in payload
    assert payload["provider"] == {"require_parameters": True}
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "ocr_result",
            "strict": True,
            "schema": OCRResult.model_json_schema(),
        },
    }
    content = payload["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert "mathematical transcription system" in content[0]["text"]
    assert "Do not include a leading equals sign" in content[0]["text"]
    assert "uncertain_tokens" in content[0]["text"]
    assert '"alternatives"' in content[0]["text"]
    assert content[1] == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(b"png-image").decode("ascii")
        },
    }
    assert not ({"format", "options", "images", "num_predict"} & payload.keys())


@pytest.mark.asyncio
async def test_propose_grade_sends_extracted_text_and_recalculates_total() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _response(_grade_content())

    adapter, client = await _adapter(handler)
    async with client:
        result = await adapter.propose_grade(
            transcription=("x = 2", "y = 3"),
            problem_text="Solve x and y.",
            solution_text="Award M1 and A1.",
            maximum=4,
        )

    assert result.total == 3
    assert captured["temperature"] == 0
    assert captured["model"] == GRADING_MODEL
    assert GRADING_MODEL == "liquid/lfm-2.5-2.6b:free"
    assert captured["max_tokens"] == 2200
    assert captured["response_format"]["json_schema"] == {
        "name": "proposed_grade",
        "strict": True,
        "schema": ProposedGrade.model_json_schema(),
    }
    content = captured["messages"][0]["content"]
    prompt = content[0]["text"]
    assert "worth exactly 4 marks" in prompt
    assert "sum of all decision maximum values must equal" in prompt
    assert prompt.endswith("Student OCR:\n1. x = 2\n2. y = 3")
    assert "Question text:\nSolve x and y." in prompt
    assert "Published answer key:\nAward M1 and A1." in prompt
    assert len(content) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("maximum", "decisions"),
    [
        (2, [{"marks_awarded": 3, "maximum": 3, "student_lines": ["line"]}]),
        (2, [{"marks_awarded": 1, "maximum": 3, "student_lines": ["line"]}]),
        (4, [{"marks_awarded": 2, "maximum": 1, "student_lines": ["line"]}]),
        (4, [{"marks_awarded": 1, "maximum": 1, "student_lines": []}]),
    ],
    ids=["total", "aggregate-maxima", "decision-maximum", "student-evidence"],
)
async def test_grading_invariants(maximum: int, decisions: list[dict[str, Any]]) -> None:
    complete = []
    for index, update in enumerate(decisions):
        complete.append(
            {
                "part": str(index),
                "scheme_evidence": "visible step",
                "reason": "reason",
                "provider_confidence": 0.8,
                **update,
            }
        )

    adapter, client = await _adapter(lambda request: _response(_grade_content(decisions=complete)))
    async with client:
        with pytest.raises(MarkingPipelineError):
            await adapter.propose_grade(
                transcription=("line",),
                problem_text="problem",
                solution_text="scheme",
                maximum=maximum,
            )


@pytest.mark.asyncio
async def test_grading_rejects_missing_labeled_question_part() -> None:
    decisions = [
        {
            "part": "(a)",
            "marks_awarded": 1,
            "maximum": 6,
            "scheme_evidence": "visible step",
            "reason": "reason",
            "student_lines": ["line"],
            "provider_confidence": 0.8,
        }
    ]
    adapter, client = await _adapter(
        lambda request: _response(_grade_content(decisions=decisions))
    )

    async with client:
        with pytest.raises(MarkingPipelineError, match="omits a labeled"):
            await adapter.propose_grade(
                transcription=("line",),
                problem_text="problem",
                solution_text="scheme",
                maximum=6,
                expected_parts=("a", "b"),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503])
async def test_retryable_http_statuses_are_ordinary_pipeline_errors(status: int) -> None:
    adapter, client = await _adapter(
        lambda request: httpx.Response(status, text="sentinel-response-secret")
    )
    async with client:
        with pytest.raises(MarkingPipelineError) as raised:
            await adapter.transcribe(b"image")
    assert not isinstance(raised.value, MarkingConfigurationError)
    assert "sentinel-response-secret" not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_transport_failures_are_ordinary_pipeline_errors(
    error_type: type[httpx.RequestError],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_type("sentinel-transport-secret", request=request)

    adapter, client = await _adapter(handler)
    async with client:
        with pytest.raises(MarkingPipelineError) as raised:
            await adapter.transcribe(b"image")
    assert not isinstance(raised.value, MarkingConfigurationError)
    assert "sentinel-transport-secret" not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_operational_statuses_are_safe_configuration_errors(status: int) -> None:
    adapter, client = await _adapter(
        lambda request: httpx.Response(status, text="sentinel-response-secret")
    )
    async with client:
        with pytest.raises(MarkingConfigurationError) as raised:
            await adapter.transcribe(b"image")
    assert str(raised.value) == f"OpenRouter rejected provider request ({status})"
    assert API_KEY not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": 4}}]}),
        httpx.Response(
            200, json={"choices": [{"message": {"content": _ocr_content(), "refusal": "no"}}]}
        ),
        _response("not-json"),
        _response(_ocr_content(extra="forbidden")),
        _response(_ocr_content(lines=[{"id": 0, "latex": "x"}])),
    ],
    ids=[
        "non-json-envelope",
        "missing-choices",
        "empty-choices",
        "missing-message",
        "null-content",
        "nonstring-content",
        "refusal",
        "malformed-content",
        "extra-fields",
        "invalid-line-id",
    ],
)
async def test_malformed_responses_are_ordinary_pipeline_errors(response: httpx.Response) -> None:
    adapter, client = await _adapter(lambda request: response)
    async with client:
        with pytest.raises(MarkingPipelineError) as raised:
            await adapter.transcribe(b"image")
    assert not isinstance(raised.value, MarkingConfigurationError)


@pytest.mark.asyncio
async def test_logs_selected_model_without_sensitive_values(caplog: pytest.LogCaptureFixture) -> None:
    sensitive_content = _ocr_content(
        lines=[{"id": 1, "latex": "private student content"}]
    )
    adapter, client = await _adapter(
        lambda request: _response(sensitive_content, model="example/free-vision-model")
    )
    with caplog.at_level(logging.INFO):
        async with client:
            await adapter.transcribe(b"image")

    assert "OpenRouter completed OCR via example/free-vision-model" in caplog.text
    assert "private student content" not in caplog.text
    assert API_KEY not in caplog.text
