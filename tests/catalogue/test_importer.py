import json

from amath_bot.catalogue.importer import parse_manifest


def valid_item() -> dict[str, object]:
    return {
        "source_url": "https://document.grail.moe/paper.pdf",
        "solution_url": "https://document.grail.moe/solution.pdf",
        "provider": "Holy Grail",
        "school": "Example Secondary",
        "year": 2024,
        "paper": "1",
        "question_number": "6",
        "syllabus_version": "4049-2026",
        "objective_codes": ["A1.complete-square"],
        "marks": 5,
        "solution_kind": "worked_solution",
        "tutor_validated": True,
    }


def test_manifest_separates_valid_and_rejected_items(tmp_path) -> None:
    path = tmp_path / "items.json"
    path.write_text(json.dumps([valid_item(), {"solution_kind": "final_answer"}]))
    result = parse_manifest(path)
    assert len(result.accepted) == 1
    assert result.rejected[0].index == 1
    assert result.rejected[0].reasons == ("invalid source metadata",)


def test_manifest_rejects_unvalidated_item(tmp_path) -> None:
    item = valid_item()
    item["tutor_validated"] = False
    path = tmp_path / "items.json"
    path.write_text(json.dumps([item]))
    result = parse_manifest(path)
    assert result.rejected[0].reasons == ("tutor validation required",)
