from types import SimpleNamespace
from typing import Any

import pytest

from amath_bot.jobs.mark_attempt import MarkingConfigurationError, MarkingPipelineError
from amath_bot.marking.local_pipeline import LocalVisionPipeline, TextGrader, VisionTranscriber
from amath_bot.providers.vision_models import OCRResult, ProposedDecision, ProposedGrade


def test_vision_result_models_are_provider_neutral() -> None:
    assert OCRResult.__module__ == "amath_bot.providers.vision_models"
    assert ProposedDecision.__module__ == "amath_bot.providers.vision_models"
    assert ProposedGrade.__module__ == "amath_bot.providers.vision_models"


def test_marking_stage_protocols_remain_in_local_pipeline() -> None:
    assert VisionTranscriber.__module__ == "amath_bot.marking.local_pipeline"
    assert TextGrader.__module__ == "amath_bot.marking.local_pipeline"


def test_configuration_error_is_a_marking_pipeline_error() -> None:
    assert issubclass(MarkingConfigurationError, MarkingPipelineError)


@pytest.mark.asyncio
async def test_pipeline_describes_generated_marks_as_ai_generated() -> None:
    class QueryResult:
        def one_or_none(self) -> tuple[object, object]:
            return (
                SimpleNamespace(
                    ocr_transcription=None,
                    ocr_unclear=None,
                    ocr_confidence=None,
                    ocr_complete=None,
                    status="transcribing",
                ),
                SimpleNamespace(solution_asset_path=None, marks=1),
            )

    class Session:
        async def execute(self, _query: object) -> QueryResult:
            return QueryResult()

        async def scalars(self, _query: object) -> tuple[object, ...]:
            return (
                SimpleNamespace(
                    telegram_file_id="submission-file",
                    media_kind="photo",
                ),
            )

        async def commit(self) -> None:
            return None

    class Bot:
        async def download(self, _file_id: str, *, destination: Any) -> None:
            destination.write(b"image")

    class OCR:
        async def transcribe(self, _image: bytes) -> OCRResult:
            return OCRResult(lines=("working",), confidence=1.0, complete=True, unclear=())

        async def propose_grade(self, **_kwargs: object) -> ProposedGrade:
            raise AssertionError("a grade is not proposed without a solution")

    pipeline = LocalVisionPipeline(Session(), Bot(), OCR())  # type: ignore[arg-type]

    outcome = await pipeline.mark(1)

    assert "Tutor approval is required for AI-generated marks." in outcome.review_reasons
    assert all("local" not in reason.lower() for reason in outcome.review_reasons)
