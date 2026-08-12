import json
import os
from io import BytesIO
from pathlib import Path

import fitz  # type: ignore[import-untyped]
import httpx
import pytest
from PIL import Image, ImageDraw

from amath_bot.providers.openrouter_vision import OpenRouterGrader, OpenRouterTranscriber
from amath_bot.providers.vision_models import ProposedGrade

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("AMATH_RUN_LIVE_E2E") != "1"
        or not os.getenv("AMATH_OPENROUTER_API_KEY"),
        reason="live OpenRouter E2E requires explicit opt-in and an API key",
    ),
]


def _synthetic_working() -> bytes:
    image = Image.new("RGB", (900, 420), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text((60, 60), "2x + 3 = 7\n2x = 4\nx = 2", fill="black", spacing=35)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _solution_pages() -> tuple[bytes, ...]:
    payload = Path("data/solution_assets/sps-2025-p1-q1-solution.pdf").read_bytes()
    document = fitz.open(stream=payload, filetype="pdf")
    try:
        return tuple(
            page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False).tobytes("png")
            for page in document
        )
    finally:
        document.close()


def _published_maximum() -> int:
    catalogue = json.loads(Path("data/catalogue/sps-2025-paper-1.json").read_text())
    question = next(item for item in catalogue if item["question_number"] == "1")
    return int(question["marks"])


async def test_openrouter_free_transcribes_and_applies_published_scheme() -> None:
    api_key = os.environ["AMATH_OPENROUTER_API_KEY"]
    base_url = os.getenv("AMATH_OPENROUTER_URL", "https://openrouter.ai/api/v1")
    async with httpx.AsyncClient(timeout=180) as client:
        transcriber = OpenRouterTranscriber(client, api_key=api_key, base_url=base_url)
        grader = OpenRouterGrader(client, api_key=api_key, base_url=base_url)
        transcription = await transcriber.transcribe(_synthetic_working())
        maximum = _published_maximum()
        proposed = await grader.propose_grade(
            transcription=transcription.lines,
            problem_images=(),
            solution_images=_solution_pages(),
            maximum=maximum,
        )

    assert transcription.lines
    assert 0 <= transcription.confidence <= 1
    assert isinstance(proposed, ProposedGrade)
    assert proposed.total == sum(decision.marks_awarded for decision in proposed.decisions)
    assert proposed.total <= maximum
