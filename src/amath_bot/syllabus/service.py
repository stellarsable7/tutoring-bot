import json
from pathlib import Path

from amath_bot.syllabus.models import Objective, Syllabus


class UnknownSyllabus(ValueError):
    """Raised when a requested syllabus version is not loaded."""


class UnknownObjective(ValueError):
    """Raised when a requested objective is absent from a syllabus."""


class SyllabusService:
    def __init__(self, syllabuses: tuple[Syllabus, ...]) -> None:
        self._items = {item.version: item for item in syllabuses}

    @classmethod
    def from_json(cls, path: str | Path) -> "SyllabusService":
        with Path(path).open(encoding="utf-8") as source:
            payload = json.load(source)
        return cls((Syllabus.model_validate(payload),))

    def require_objective(self, version: str, code: str) -> Objective:
        syllabus = self._items.get(version)
        if syllabus is None:
            raise UnknownSyllabus(version)
        for objective in syllabus.objectives:
            if objective.code == code:
                return objective
        raise UnknownObjective(f"{version}:{code}")

    def topic_codes(self, version: str) -> set[str]:
        syllabus = self._items.get(version)
        if syllabus is None:
            raise UnknownSyllabus(version)
        return {objective.code.split(".", maxsplit=1)[0] for objective in syllabus.objectives}
