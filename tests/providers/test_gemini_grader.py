import json
from typing import Any

import httpx
import pytest

from amath_bot.jobs.mark_attempt import MarkingConfigurationError, MarkingPipelineError
from amath_bot.providers.gemini_grader import GEMINI_GRADING_MODEL, GeminiGrader
from amath_bot.providers.vision_models import ProposedGrade


def _grade_content() -> str:
    return json.dumps(
        {
            "total": 5,
            "final_answer_correct": True,
            "method_valid": True,
            "overall_verdict": "correct",
            "reasoning": "The identity is proved.",
            "decisions": [
                {
                    "part": "whole question",
                    "marks_awarded": 5,
                    "maximum": 5,
                    "scheme_evidence": "Correct algebraic chain to the RHS.",
                    "reason": "All substantive transformations are valid.",
                    "student_lines": ["1. LHS = RHS"],
                    "provider_confidence": 0.95,
                }
            ],
            "feedback": ["Correct proof."],
            "unclear": [],
        }
    )


@pytest.mark.asyncio
async def test_gemini_grader_uses_direct_text_api_and_structured_schema() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers["x-goog-api-key"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": _grade_content()}]}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GeminiGrader(
            client, api_key="gemini-secret", base_url="https://gemini.test/v1beta/"
        ).propose_grade(
            transcription=("LHS = RHS",),
            problem_text="Prove the identity.",
            solution_text="A correct chain earns five marks.",
            maximum=5,
        )

    assert result.total == 5
    assert GEMINI_GRADING_MODEL == "gemini-3.1-flash-lite"
    assert captured["url"] == (
        "https://gemini.test/v1beta/models/gemini-3.1-flash-lite:generateContent"
    )
    assert captured["key"] == "gemini-secret"
    config = captured["payload"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == ProposedGrade.model_json_schema()
    assert config["temperature"] == 0
    assert config["maxOutputTokens"] == 2200
    assert len(captured["payload"]["contents"][0]["parts"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_gemini_configuration_errors_are_operator_actionable(status: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as client:
        with pytest.raises(MarkingConfigurationError, match=str(status)):
            await GeminiGrader(client, api_key="secret").propose_grade(
                transcription=("line",),
                problem_text="problem",
                solution_text="scheme",
                maximum=1,
            )


@pytest.mark.asyncio
async def test_gemini_rejects_malformed_response() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as client:
        with pytest.raises(MarkingPipelineError, match="Gemini provisional"):
            await GeminiGrader(client, api_key="secret").propose_grade(
                transcription=("line",),
                problem_text="problem",
                solution_text="scheme",
                maximum=1,
            )
