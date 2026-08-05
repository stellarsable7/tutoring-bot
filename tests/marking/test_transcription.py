import pytest

from amath_bot.marking.transcription import Transcription, TranscriptionSchemaError
from amath_bot.providers.vision import parse_transcription


def valid_payload() -> dict[str, object]:
    return {
        "pages": [
            {
                "number": 1,
                "lines": [
                    {
                        "index": 1,
                        "latex": "x^2-5x+6=0",
                        "literal_text": "x squared minus 5x plus 6 equals 0",
                        "bounding_box": [0.1, 0.2, 0.8, 0.3],
                        "confidence": 0.98,
                        "crossed_out": False,
                    }
                ],
            }
        ],
        "complete": True,
    }


def test_transcription_keeps_line_confidence_and_crossouts() -> None:
    result = Transcription.model_validate(valid_payload())

    assert result.pages[0].lines[0].confidence == 0.98
    assert result.pages[0].lines[0].crossed_out is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda line: line.pop("confidence"),
        lambda line: line.update(confidence=1.2),
        lambda line: line.update(guessed_answer="x=2"),
    ],
)
def test_malformed_provider_output_is_rejected(mutation) -> None:  # type: ignore[no-untyped-def]
    payload = valid_payload()
    line = payload["pages"][0]["lines"][0]  # type: ignore[index]
    mutation(line)

    with pytest.raises(TranscriptionSchemaError):
        parse_transcription(payload)
