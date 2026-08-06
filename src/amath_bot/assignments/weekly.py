import hashlib
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PaperQuestion:
    id: int
    number: str
    marks: int


def six_day_plan(
    questions: Sequence[PaperQuestion], *, seed: str
) -> tuple[tuple[int, ...], ...]:
    """Shuffle one paper into six mark-balanced, capacity-balanced delivery days."""
    if not questions:
        return ((),) * 6

    def digest(value: str) -> bytes:
        return hashlib.sha256(f"{seed}:{value}".encode()).digest()

    shuffled = sorted(questions, key=lambda question: digest(question.number))
    base, extra = divmod(len(shuffled), 6)
    capacities = [base] * 6
    extra_order = sorted(range(6), key=lambda day: digest(f"day:{day}"))
    for day in extra_order[:extra]:
        capacities[day] += 1

    bins: list[list[PaperQuestion]] = [[] for _ in range(6)]
    totals = [0] * 6
    rank = {question.id: index for index, question in enumerate(shuffled)}
    for question in sorted(shuffled, key=lambda item: (-item.marks, rank[item.id])):
        available = [day for day in range(6) if len(bins[day]) < capacities[day]]
        day = min(available, key=lambda value: (totals[value], digest(f"tie:{value}")))
        bins[day].append(question)
        totals[day] += question.marks

    return tuple(
        tuple(item.id for item in sorted(day, key=lambda question: rank[question.id]))
        for day in bins
    )
