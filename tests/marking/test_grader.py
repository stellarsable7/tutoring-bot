from typing import Any

import pytest

from amath_bot.marking.grader import Grader, InvalidGrade
from amath_bot.marking.schemes import MarkingStep, PublishedScheme
from amath_bot.marking.transcription import Transcription


class FakeMarker:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def mark(self, transcription, scheme, symbolic_checks):  # type: ignore[no-untyped-def]
        return self.payload


def transcription() -> Transcription:
    return Transcription.model_validate(
        {
            "pages": [
                {
                    "number": 1,
                    "lines": [
                        {
                            "index": 1,
                            "latex": "(x-2)(x-3)=0",
                            "literal_text": "open bracket x minus 2 close bracket...",
                            "bounding_box": [0.1, 0.1, 0.8, 0.2],
                            "confidence": 0.96,
                            "crossed_out": False,
                        },
                        {
                            "index": 2,
                            "latex": "x=2\\text{ or }x=3",
                            "literal_text": "x equals 2 or x equals 3",
                            "bounding_box": [0.1, 0.3, 0.8, 0.4],
                            "confidence": 0.94,
                            "crossed_out": False,
                        },
                    ],
                }
            ],
            "complete": True,
        }
    )


def scheme() -> PublishedScheme:
    return PublishedScheme(
        source_url="https://private.example/scheme",
        total_marks=2,
        steps=(
            MarkingStep(
                code="M1",
                mark_type="M",
                marks=1,
                expected_latex="(x-2)(x-3)=0",
                guidance="Correct factorisation method.",
            ),
            MarkingStep(
                code="A1",
                mark_type="A",
                marks=1,
                expected_latex="x=2,3",
                guidance="Both roots.",
                dependencies=("M1",),
            ),
        ),
    )


def valid_payload() -> dict[str, Any]:
    return {
        "total": 2,
        "decisions": [
            {
                "scheme_step_code": "M1",
                "awarded": True,
                "marks_awarded": 1,
                "student_line_indexes": [1],
                "reason": "Factorisation method shown.",
                "provider_confidence": 0.95,
            },
            {
                "scheme_step_code": "A1",
                "awarded": True,
                "marks_awarded": 1,
                "student_line_indexes": [2],
                "reason": "Both roots stated.",
                "provider_confidence": 0.93,
            },
        ],
    }


async def test_each_awarded_mark_has_scheme_and_line_evidence() -> None:
    result = await Grader(FakeMarker(valid_payload())).grade(
        transcription(), scheme(), symbolic_checks={"M1": True, "A1": True}
    )

    assert result.total <= scheme().total_marks
    assert all(decision.scheme_step_code for decision in result.decisions)
    assert all(
        decision.student_line_indexes for decision in result.decisions if decision.awarded
    )
    assert result.confidence.recognition == 0.94


@pytest.mark.parametrize("corruption", ["invented", "inflated", "missing_evidence"])
async def test_adversarial_provider_grade_is_rejected(corruption: str) -> None:
    payload = valid_payload()
    if corruption == "invented":
        payload["decisions"][0]["expected_answer"] = "x=2"  # type: ignore[index]
    elif corruption == "inflated":
        payload["total"] = 5
    else:
        payload["decisions"][0]["student_line_indexes"] = []  # type: ignore[index]

    with pytest.raises(InvalidGrade):
        await Grader(FakeMarker(payload)).grade(
            transcription(), scheme(), symbolic_checks={"M1": True, "A1": True}
        )
