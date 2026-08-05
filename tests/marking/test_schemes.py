import pytest
from pydantic import ValidationError

from amath_bot.marking.schemes import MarkingStep, PublishedScheme


def step(code: str, marks: int, dependencies: tuple[str, ...] = ()) -> MarkingStep:
    return MarkingStep(
        code=code,
        mark_type="M",
        marks=marks,
        expected_latex="x^2-5x+6",
        guidance="Expands or factorises correctly.",
        dependencies=dependencies,
    )


def test_published_scheme_requires_balanced_marks_and_ordered_dependencies() -> None:
    scheme = PublishedScheme(
        source_url="https://private.example/mark-scheme",
        total_marks=2,
        steps=(step("M1", 1), step("A1", 1, ("M1",))),
    )
    assert sum(item.marks for item in scheme.steps) == scheme.total_marks


def test_unknown_or_forward_dependency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PublishedScheme(
            source_url="https://private.example/mark-scheme",
            total_marks=2,
            steps=(step("A1", 1, ("M1",)), step("M1", 1)),
        )


def test_step_marks_must_equal_total() -> None:
    with pytest.raises(ValidationError):
        PublishedScheme(
            source_url="https://private.example/mark-scheme",
            total_marks=3,
            steps=(step("M1", 1), step("A1", 1, ("M1",))),
        )
