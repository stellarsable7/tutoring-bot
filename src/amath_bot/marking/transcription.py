from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

Confidence = Annotated[float, Field(ge=0, le=1)]
Coordinate = Annotated[float, Field(ge=0, le=1)]


class TranscriptionSchemaError(ValueError):
    pass


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TranscribedLine(StrictFrozenModel):
    index: PositiveInt
    latex: str
    literal_text: str
    bounding_box: tuple[Coordinate, Coordinate, Coordinate, Coordinate]
    confidence: Confidence
    crossed_out: bool


class TranscribedPage(StrictFrozenModel):
    number: PositiveInt
    lines: tuple[TranscribedLine, ...]


class Transcription(StrictFrozenModel):
    pages: tuple[TranscribedPage, ...]
    complete: bool

