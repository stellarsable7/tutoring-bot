from amath_bot.assignments.models import CandidateQuestion
from amath_bot.assignments.selector import select_question


def candidate(
    source_id: int,
    objective: str,
    *,
    difficulty_band: int = 2,
    overdue_review: bool = False,
    near_transfer: bool = False,
) -> CandidateQuestion:
    return CandidateQuestion(
        source_id=source_id,
        objective_codes=(objective,),
        difficulty_band=difficulty_band,
        overdue_review=overdue_review,
        near_transfer=near_transfer,
    )


def test_weak_objective_prefers_near_transfer_not_exact_repeat() -> None:
    same_method_new_values = candidate(10, "A1.complete-square", near_transfer=True)
    unrelated_question = candidate(20, "T1.identities")
    exact_previous_question = candidate(30, "A1.complete-square", near_transfer=True)

    selected = select_question(
        candidates=[same_method_new_values, unrelated_question, exact_previous_question],
        mastery={"A1.complete-square": 0.25},
        prior_source_ids={30},
        pinned_objectives={"A1.complete-square"},
    )

    assert selected.source_id == same_method_new_values.source_id


def test_overdue_review_and_least_recent_objective_break_ties() -> None:
    recent = candidate(10, "A1.factorise", overdue_review=True)
    older = candidate(20, "A1.complete-square", overdue_review=True)

    selected = select_question(
        candidates=[recent, older],
        mastery={},
        prior_source_ids=set(),
        pinned_objectives=set(),
        objective_last_used={"A1.factorise": 100, "A1.complete-square": 20},
    )

    assert selected.source_id == older.source_id


def test_exact_repeat_requires_explicit_override() -> None:
    repeated = candidate(10, "A1.complete-square")
    fresh = candidate(20, "A1.complete-square", difficulty_band=5)

    automatic = select_question(
        candidates=[repeated, fresh],
        mastery={"A1.complete-square": 0.5},
        prior_source_ids={10},
        pinned_objectives={"A1.complete-square"},
        target_difficulty_band=2,
    )
    explicit = select_question(
        candidates=[repeated],
        mastery={"A1.complete-square": 0.5},
        prior_source_ids={10},
        pinned_objectives={"A1.complete-square"},
        allow_exact_repeat=True,
    )

    assert automatic.source_id == fresh.source_id
    assert explicit.source_id == repeated.source_id


def test_stable_source_id_is_final_tie_breaker() -> None:
    selected = select_question(
        candidates=[candidate(20, "A1.factorise"), candidate(10, "A1.factorise")],
        mastery={},
        prior_source_ids=set(),
        pinned_objectives=set(),
    )

    assert selected.source_id == 10
