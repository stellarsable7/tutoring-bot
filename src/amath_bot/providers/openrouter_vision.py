import asyncio
import base64
import logging
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from amath_bot.jobs.mark_attempt import (
    MarkingConfigurationError,
    MarkingPipelineError,
    MarkingValidationError,
    OCRValidationError,
    RateLimitError,
)
from amath_bot.providers.vision_models import OCRResult, ProposedGrade

# Pin each stage independently so changing the grader cannot affect transcription.
TRANSCRIPTION_MODEL = "google/gemma-4-26b-a4b-it:free"
GRADING_MODEL = "liquid/lfm-2.5-2.6b:free"
_CONFIGURATION_ERROR_STATUSES = frozenset({400, 401, 403, 404, 422})

_logger = logging.getLogger(__name__)
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class _OpenRouterProvider:
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
            "model": model,
            "stream": False,
            "provider": {"require_parameters": True, "sort": "throughput"},
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
        if temperature is not None:
            payload["temperature"] = temperature
        if reasoning_effort is not None:
            payload["reasoning"] = {"effort": reasoning_effort}
        try:
            async with asyncio.timeout(overall_timeout):
                response = await self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except (TimeoutError, httpx.RequestError) as error:
            raise MarkingPipelineError(failure_message) from error

        if response.status_code in _CONFIGURATION_ERROR_STATUSES:
            raise MarkingConfigurationError(
                f"OpenRouter rejected provider request ({response.status_code})"
            )
        if response.status_code == 429:
            raise RateLimitError(failure_message)
        if response.status_code == 408 or response.status_code >= 500:
            raise MarkingPipelineError(failure_message)
        if response.status_code >= 400:
            raise MarkingConfigurationError(
                f"OpenRouter rejected provider request ({response.status_code})"
            )

        response_content = response.text
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
            if stage == "OCR":
                detail = (
                    str(error)
                    if not isinstance(error, (KeyError, TypeError))
                    else f"{type(error).__name__}: {error}"
                )
                raise OCRValidationError(detail, response_content) from error
            raise MarkingValidationError(failure_message) from error

        selected_model = envelope.get("model")
        if isinstance(selected_model, str) and selected_model:
            _logger.info("OpenRouter completed %s via %s", stage, selected_model)
        return result


class OpenRouterTranscriber(_OpenRouterProvider):
    async def transcribe(self, image: bytes) -> OCRResult:
        prompt = (
            "You are a mathematical transcription system.\n\n"
            "Transcribe the student's handwritten mathematical working in reading order. "
            "Do not solve, correct, simplify, grade, or explain the work.\n\n"
            "SEMANTIC NORMALISATION\n"
            "Convert handwritten mathematical notation into standard LaTeX without changing its "
            "mathematical meaning. For example:\n- cosec x → \\csc{x}\n- cot x → \\cot{x}\n"
            "- cos²x → \\cos^{2}{x}\n\nLINE RULES\n"
            "1. Return one mathematical expression for each stage of the student's working.\n"
            "2. Do not include a leading equals sign in a line.\n"
            "3. If the student writes only '= expression', store only 'expression'.\n"
            "4. Exclude labels such as RHS, LHS, hence, therefore, and working annotations from the "
            "latex field.\n"
            "5. Preserve mathematical mistakes exactly. Normalise notation only; do not correct the "
            "mathematics.\n"
            "6. Use explicit braces and fractions: \\sin{x}, \\cos{x}, \\cot{x}, \\frac{a}{b}.\n"
            "7. Do not use \\text, Markdown, dollar signs, or display-math delimiters.\n"
            "8. Return raw JSON only. Do not wrap it in a code fence.\n\nUNCERTAINTY\n"
            "If a token is genuinely unreadable:\n- make the best literal transcription that keeps "
            "the line syntactically valid;\n- record the line ID, token and alternatives in "
            "uncertain_tokens;\n- do not invent an explanation.\n\n"
            "Return exactly this JSON structure:\n"
            '{"lines":[{"id":1,"latex":"..."}],"uncertain_tokens":'
            '[{"line_id":1,"token":"...","alternatives":["...","..."]}]}\n\n'
            "Use an empty uncertain_tokens array when everything is readable."
        )
        return await self._complete(
            prompt=prompt,
            images=(image,),
            schema=OCRResult,
            schema_name="ocr_result",
            stage="OCR",
            failure_message="OpenRouter vision OCR failed",
            model=TRANSCRIPTION_MODEL,
            max_tokens=1200,
            temperature=0,
            reasoning_effort="none",
            overall_timeout=60,
        )


class OpenRouterGrader(_OpenRouterProvider):
    async def propose_grade(
        self,
        *,
        transcription: tuple[str, ...],
        problem_text: str,
        solution_text: str,
        maximum: int,
        expected_parts: tuple[str, ...] = (),
        symbolic_verification: tuple[dict[str, Any], ...] = (),
    ) -> ProposedGrade:
        required_parts = ", ".join(f"({part})" for part in expected_parts)
        coverage_instruction = (
            f" The question has these labeled parts: {required_parts}. Return at least one "
            "decision for every listed part, even when the student attempted no work for that "
            "part; in that case award zero and explain that no matching work was found."
            if expected_parts
            else " Return a decision for every labeled part visible in the published scheme."
        )
        prompt = (
            "You are a secondary-school A-Mathematics marker. Mark the student's solution for "
            "mathematical correctness, not whether it matches the model answer's exact method. "
            "Award full credit when the reasoning is mathematically valid and reaches the required "
            "result. Accept all algebraically equivalent expressions and alternative valid methods. "
            "Do not deduct marks for using a longer method, omitting explanations for routine "
            "algebraic simplifications, understandable handwriting, minor notation issues that do "
            "not change the mathematical meaning, or not using the model answer's identity or "
            "method. Deduct marks only for a specific mathematical error, an unjustified non-routine "
            "step, or failure to answer the question. Do not invent an error merely to avoid full "
            "marks. Before scoring, reconstruct the student's argument step by step and verify each "
            "equality. If an image or transcription is ambiguous, report exactly what is unclear "
            "instead of assuming the student is wrong. The maximum score is attainable; if every "
            "substantive step is correct, award full marks. For an identity proof, check that each "
            "expression equals the preceding expression; a correct algebraic chain ending at the RHS "
            "earns full credit. Do not require domain restrictions unless explicitly requested or "
            "ignoring them invalidates the proof. Set final_answer_correct and method_valid, map the "
            "verdict Correct/Partially correct/Incorrect to overall_verdict correct/partial/incorrect, "
            "put the concise marking explanation in reasoning, list specific errors in decision "
            "reasons (or state None), and give one concise feedback sentence. "
            "The question and published answer key below were extracted from PDF files, so their "
            "spacing may be imperfect. Use them as context alongside the student transcription. "
            f"The question is worth exactly {maximum} marks. Apply marks consistently with the "
            "published mark allocation while accepting mathematically valid alternative methods. "
            "For every awarded mark, scheme_evidence must identify the relevant published marking "
            "criterion or explain the mathematically equivalent achievement "
            "and cite the matching student_lines. If a scheme step is unreadable or absent, award "
            "according to demonstrated mathematical merit and add the exact issue to unclear for "
            "the tutor. Apply method and follow-through marks consistently. Feedback "
            "must diagnose the submitted work without giving a corrected answer or model solution. "
            + coverage_instruction
            + " The sum of all decision maximum values must equal the question maximum exactly. "
            "Return JSON with total, decisions, feedback, and unclear. Each decision must contain "
            "part, marks_awarded, maximum, scheme_evidence, reason, student_lines, and a numeric "
            "provider_confidence from 0 to 1.\n\nQuestion text:\n"
            + problem_text
            + "\n\nPublished answer key:\n"
            + solution_text
            + "\n\nServer-side symbolic verification (diagnostic only; parser failure does not "
            "imply the OCR is wrong):\n"
            + "\n".join(str(item) for item in symbolic_verification)
            + "\n\nStudent OCR:\n"
            + "\n".join(f"{index}. {line}" for index, line in enumerate(transcription, 1))
        )
        proposed = await self._complete(
            prompt=prompt,
            images=(),
            schema=ProposedGrade,
            schema_name="proposed_grade",
            stage="grading",
            failure_message="OpenRouter provisional grading failed",
            model=GRADING_MODEL,
            max_tokens=2200,
            temperature=0,
        )
        calculated_total = sum(item.marks_awarded for item in proposed.decisions)
        decision_maximum = sum(item.maximum for item in proposed.decisions)
        if calculated_total > maximum:
            raise MarkingValidationError("provisional grade exceeds the published maximum")
        if decision_maximum != maximum:
            raise MarkingValidationError(
                "provisional grade does not cover the full published maximum"
            )
        if any(item.marks_awarded > item.maximum for item in proposed.decisions):
            raise MarkingValidationError("provisional decision exceeds its maximum")
        if any(item.marks_awarded and not item.student_lines for item in proposed.decisions):
            raise MarkingValidationError("awarded marks lack student evidence")
        returned_parts = {self._normalize_part(item.part) for item in proposed.decisions}
        missing_parts = [
            part for part in expected_parts if self._normalize_part(part) not in returned_parts
        ]
        if missing_parts:
            raise MarkingValidationError("provisional grade omits a labeled question part")
        return proposed.model_copy(update={"total": calculated_total})

    @staticmethod
    def _normalize_part(value: str) -> str:
        return value.strip().strip("()").strip().casefold()



class OpenRouterVisionOCR(OpenRouterTranscriber, OpenRouterGrader):
    """Compatibility adapter; new wiring uses separate transcriber and grader instances."""
