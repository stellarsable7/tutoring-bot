from amath_bot.jobs.mark_attempt import MarkingConfigurationError, MarkingPipelineError
from amath_bot.marking.local_pipeline import VisionOCR
from amath_bot.providers.ollama_vision import ProposedDecision as OllamaProposedDecision
from amath_bot.providers.vision_models import OCRResult, ProposedDecision, ProposedGrade


def test_vision_result_models_are_provider_neutral() -> None:
    assert OCRResult.__module__ == "amath_bot.providers.vision_models"
    assert ProposedDecision.__module__ == "amath_bot.providers.vision_models"
    assert ProposedGrade.__module__ == "amath_bot.providers.vision_models"
    assert OllamaProposedDecision is ProposedDecision


def test_vision_ocr_protocol_remains_in_local_pipeline() -> None:
    assert VisionOCR.__module__ == "amath_bot.marking.local_pipeline"


def test_configuration_error_is_a_marking_pipeline_error() -> None:
    assert issubclass(MarkingConfigurationError, MarkingPipelineError)
