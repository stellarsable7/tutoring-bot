import pytest

from amath_bot.syllabus.service import SyllabusService, UnknownObjective


def test_loads_versioned_4049_objectives() -> None:
    service = SyllabusService.from_json("data/syllabus/4049-2026.json")
    objective = service.require_objective("4049-2026", "A1.complete-square")
    assert objective.topic == "Quadratic functions"


def test_rejects_unknown_objective() -> None:
    service = SyllabusService.from_json("data/syllabus/4049-2026.json")
    with pytest.raises(UnknownObjective):
        service.require_objective("4049-2026", "unknown")


def test_contains_every_official_topic() -> None:
    service = SyllabusService.from_json("data/syllabus/4049-2026.json")
    assert service.topic_codes("4049-2026") == {
        "A1", "A2", "A3", "A4", "A5", "A6", "G1", "G2", "G3", "C1"
    }
