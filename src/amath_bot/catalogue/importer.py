import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from amath_bot.catalogue.eligibility import eligibility_errors
from amath_bot.catalogue.models import SourceQuestion


@dataclass(frozen=True)
class RejectedItem:
    index: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ImportResult:
    accepted: tuple[SourceQuestion, ...]
    rejected: tuple[RejectedItem, ...]


def parse_manifest(path: str | Path) -> ImportResult:
    with Path(path).open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, list):
        raise TypeError("catalogue manifest must contain a JSON array")
    accepted: list[SourceQuestion] = []
    rejected: list[RejectedItem] = []
    for index, raw_item in enumerate(payload):
        try:
            item = SourceQuestion.model_validate(raw_item)
        except ValidationError:
            rejected.append(RejectedItem(index=index, reasons=("invalid source metadata",)))
            continue
        errors = eligibility_errors(item)
        if errors:
            rejected.append(RejectedItem(index=index, reasons=tuple(errors)))
            continue
        accepted.append(item)
    return ImportResult(accepted=tuple(accepted), rejected=tuple(rejected))
