from amath_bot.catalogue.models import SolutionKind, SourceQuestion


def eligibility_errors(item: SourceQuestion) -> list[str]:
    errors: list[str] = []
    if item.solution_url is None or item.solution_kind not in {
        SolutionKind.WORKED_SOLUTION,
        SolutionKind.MARK_SCHEME,
    }:
        errors.append("published worked solution required")
    if not item.objective_codes:
        errors.append("at least one syllabus objective required")
    if not item.tutor_validated:
        errors.append("tutor validation required")
    return errors
