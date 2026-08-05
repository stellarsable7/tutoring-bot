from amath_bot.catalogue.eligibility import eligibility_errors
from amath_bot.catalogue.models import SolutionKind, SourceQuestion


def question(kind: SolutionKind | None) -> SourceQuestion:
    return SourceQuestion(
        source_url="https://grail.moe/example-paper.pdf",
        solution_url=None if kind is None else "https://grail.moe/example-solution.pdf",
        provider="Holy Grail",
        school="Example Secondary",
        year=2024,
        paper="1",
        question_number="6",
        syllabus_version="4049-2026",
        objective_codes=("A1.complete-square",),
        marks=5,
        solution_kind=kind,
        tutor_validated=True,
    )


def test_requires_worked_solution_or_mark_scheme() -> None:
    assert "published worked solution required" in eligibility_errors(question(None))
    assert "published worked solution required" in eligibility_errors(
        question(SolutionKind.FINAL_ANSWER)
    )
    assert eligibility_errors(question(SolutionKind.WORKED_SOLUTION)) == []


def test_requires_tutor_validation() -> None:
    candidate = question(SolutionKind.MARK_SCHEME).model_copy(update={"tutor_validated": False})
    assert eligibility_errors(candidate) == ["tutor validation required"]
