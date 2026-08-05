from collections.abc import Mapping
from typing import Any, Protocol

from amath_bot.marking.schemes import PublishedScheme
from amath_bot.marking.transcription import Transcription


class ReasoningMarker(Protocol):
    async def mark(
        self,
        transcription: Transcription,
        scheme: PublishedScheme,
        symbolic_checks: Mapping[str, bool],
    ) -> Mapping[str, Any]: ...

