from collections.abc import Collection, Mapping, Sequence

from amath_bot.assignments.models import CandidateQuestion


def score_candidate(
    candidate: CandidateQuestion,
    *,
    mastery: Mapping[str, float],
    prior_source_ids: Collection[int],
    pinned_objectives: Collection[str],
    target_difficulty_band: int = 2,
    allow_exact_repeat: bool = False,
) -> float:
    objectives = set(candidate.objective_codes)
    score = 100.0 if objectives.intersection(pinned_objectives) else 0.0
    score += max((1.0 - mastery[code]) * 40 for code in objectives if code in mastery) if any(
        code in mastery for code in objectives
    ) else 0.0
    if candidate.overdue_review:
        score += 20
    score -= abs(candidate.difficulty_band - target_difficulty_band) * 10
    if candidate.source_id in prior_source_ids and not allow_exact_repeat:
        score -= 1000
    if candidate.near_transfer:
        score += 30
    return score


def select_question(
    *,
    candidates: Sequence[CandidateQuestion],
    mastery: Mapping[str, float],
    prior_source_ids: Collection[int],
    pinned_objectives: Collection[str],
    target_difficulty_band: int = 2,
    objective_last_used: Mapping[str, int] | None = None,
    allow_exact_repeat: bool = False,
) -> CandidateQuestion:
    if not candidates:
        raise ValueError("at least one candidate is required")

    last_used = objective_last_used or {}

    def rank(candidate: CandidateQuestion) -> tuple[float, float, int]:
        score = score_candidate(
            candidate,
            mastery=mastery,
            prior_source_ids=prior_source_ids,
            pinned_objectives=pinned_objectives,
            target_difficulty_band=target_difficulty_band,
            allow_exact_repeat=allow_exact_repeat,
        )
        objective_age = min(
            (last_used.get(code, float("-inf")) for code in candidate.objective_codes),
            default=float("-inf"),
        )
        return (-score, objective_age, candidate.source_id)

    return min(candidates, key=rank)
