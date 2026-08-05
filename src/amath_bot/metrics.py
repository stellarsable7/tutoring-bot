from collections import defaultdict


class MetricRegistry:
    """Small aggregate-only registry with a Prometheus text representation."""

    ALLOWED = frozenset(
        {
            "assignments_completed_total",
            "assignments_on_time_total",
            "marking_exact_agreement_total",
            "marking_within_one_agreement_total",
            "marking_overrides_total",
            "marking_review_duration_seconds",
            "marking_processing_failures_total",
            "submission_media_deletion_failures_total",
        }
    )

    def __init__(self) -> None:
        self._values: defaultdict[str, float] = defaultdict(float)

    def increment(self, name: str = "submission_media_deletion_failures_total", amount: float = 1) -> None:
        if name not in self.ALLOWED:
            raise ValueError("metric is not an approved identity-free aggregate")
        if amount < 0:
            raise ValueError("metric increments cannot be negative")
        self._values[name] += amount

    def observe(self, name: str, value: float) -> None:
        self.increment(name, value)

    def render(self) -> str:
        return "\n".join(f"{name} {self._values[name]:g}" for name in sorted(self.ALLOWED)) + "\n"
