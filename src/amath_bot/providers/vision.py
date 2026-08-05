from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from amath_bot.marking.transcription import Transcription, TranscriptionSchemaError
from amath_bot.media.store import MediaHandle


class VisionTranscriber(Protocol):
    async def transcribe(self, media: tuple[MediaHandle, ...]) -> Transcription: ...


def parse_transcription(payload: Mapping[str, Any]) -> Transcription:
    try:
        return Transcription.model_validate(payload)
    except ValidationError as error:
        raise TranscriptionSchemaError("vision provider returned an invalid transcription") from error
