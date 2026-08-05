from pathlib import Path

from amath_bot.evaluation.models import LabelledCase
from amath_bot.evaluation.runner import EvaluationRunner, load_cases


def test_launch_gate_requires_accuracy_and_ambiguity_flags() -> None:
    cases = load_cases(Path(__file__).parent / "fixtures" / "sample_set.json")
    report = EvaluationRunner().run(cases)
    assert report.exact_agreement >= 0.90
    assert report.within_one_mark >= 0.95
    assert report.missed_material_ambiguities == 0
    assert report.answer_leaks == 0
    assert report.launch_ready is True


def test_answer_leak_fails_launch_gate() -> None:
    case = LabelledCase(
        case_id="leak",
        consent_provenance="synthetic",
        category="algebra",
        expected_transcription="work",
        actual_transcription="work",
        tutor_total=1,
        predicted_total=1,
        feedback="The answer is x=2",
        forbidden_answers=frozenset({"x=2"}),
    )
    report = EvaluationRunner().run((case,))
    assert report.answer_leaks == 1
    assert report.launch_ready is False
