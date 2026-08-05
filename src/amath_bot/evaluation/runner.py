import argparse
import json
from collections import defaultdict
from pathlib import Path

from pydantic import TypeAdapter

from amath_bot.evaluation.models import CategoryReport, EvaluationReport, LabelledCase


class EvaluationRunner:
    def run(self, cases: tuple[LabelledCase, ...]) -> EvaluationReport:
        if not cases:
            return EvaluationReport(
                cases=0,
                exact_agreement=0,
                within_one_mark=0,
                transcription_errors=0,
                missed_material_ambiguities=0,
                answer_leaks=0,
                by_category={},
            )
        exact = sum(case.predicted_total == case.tutor_total for case in cases)
        within_one = sum(abs(case.predicted_total - case.tutor_total) <= 1 for case in cases)
        transcription_errors = sum(
            self._normalize(case.actual_transcription)
            != self._normalize(case.expected_transcription)
            for case in cases
        )
        missed_flags = sum(
            bool(case.expected_flags - case.predicted_flags) for case in cases
        )
        answer_leaks = sum(
            any(
                answer.casefold() in case.feedback.casefold()
                for answer in case.forbidden_answers
                if answer.strip()
            )
            for case in cases
        )
        grouped: defaultdict[str, list[LabelledCase]] = defaultdict(list)
        for case in cases:
            grouped[case.category].append(case)
        categories = {
            name: CategoryReport(
                cases=len(values),
                exact_agreement=sum(c.predicted_total == c.tutor_total for c in values)
                / len(values),
                transcription_errors=sum(
                    self._normalize(c.actual_transcription)
                    != self._normalize(c.expected_transcription)
                    for c in values
                ),
            )
            for name, values in grouped.items()
        }
        return EvaluationReport(
            cases=len(cases),
            exact_agreement=exact / len(cases),
            within_one_mark=within_one / len(cases),
            transcription_errors=transcription_errors,
            missed_material_ambiguities=missed_flags,
            answer_leaks=answer_leaks,
            by_category=categories,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())


def load_cases(path: Path) -> tuple[LabelledCase, ...]:
    return TypeAdapter(tuple[LabelledCase, ...]).validate_json(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate labelled A-Math marking cases")
    parser.add_argument("labelled_set", type=Path)
    args = parser.parse_args()
    report = EvaluationRunner().run(load_cases(args.labelled_set))
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if report.launch_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
