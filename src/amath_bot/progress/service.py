from datetime import date, timedelta

from amath_bot.progress.models import MasteryState


class ProgressService:
    def update(
        self,
        *,
        previous: float,
        score_ratio: float | None,
        confidence: float,
        attempted_on: date | None = None,
        resolved: bool = True,
    ) -> MasteryState:
        for name, value in (("previous", previous), ("confidence", confidence)):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if score_ratio is not None and not 0 <= score_ratio <= 1:
            raise ValueError("score_ratio must be between zero and one")
        if not resolved or score_ratio is None:
            return self._state(previous, (), updated=False)

        full_update = 0.7 * previous + 0.3 * score_ratio
        mastery = previous + confidence * (full_update - previous)
        reviews: tuple[date, ...] = ()
        if score_ratio >= 0.7 and attempted_on is not None:
            reviews = tuple(attempted_on + timedelta(days=days) for days in (3, 7, 21))
        return self._state(
            mastery,
            reviews,
            updated=True,
            remediation_required=score_ratio < 0.5 or mastery < 0.5,
        )

    @staticmethod
    def _state(
        mastery: float,
        reviews: tuple[date, ...],
        *,
        updated: bool,
        remediation_required: bool | None = None,
    ) -> MasteryState:
        remediation = mastery < 0.5 if remediation_required is None else remediation_required
        if remediation:
            mode = "near_transfer_remediation"
        elif mastery > 0.7:
            mode = "broadened_framing"
        else:
            mode = "standard_practice"
        return MasteryState(
            mastery=mastery,
            remediation_required=remediation,
            question_mode=mode,
            review_dates=reviews,
            updated=updated,
        )
