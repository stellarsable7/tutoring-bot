from pathlib import Path

import pytest

from amath_bot.discovery.holy_grail import HolyGrailDiscovery, LibraryDisallowed

FIXTURE = Path("tests/discovery/fixtures/library-page.html")


def test_discovers_o_level_amath_question_and_solution_pair() -> None:
    result = HolyGrailDiscovery.parse_library_page(FIXTURE.read_text())
    pair = result.pairs[0]
    assert pair.question_document.subject_id == 30
    assert pair.question_document.category_id == 1
    assert pair.question_document.document_name.endswith("QP")
    assert str(pair.question_document.detail_url) == "https://document.grail.moe/paper.pdf"
    assert pair.solution_document.document_name.endswith("MS")


def test_unpaired_documents_are_candidates_not_assignable() -> None:
    result = HolyGrailDiscovery.parse_library_page(FIXTURE.read_text())
    assert result.unpaired[0].external_id == 102
    assert result.unpaired[0].assignable is False


def test_reads_pagination_metadata() -> None:
    result = HolyGrailDiscovery.parse_library_page(FIXTURE.read_text())
    assert (result.page, result.pages, result.total) == (1, 1, 3)


def test_stops_if_library_is_disallowed() -> None:
    with pytest.raises(LibraryDisallowed):
        HolyGrailDiscovery.assert_library_allowed("User-agent: *\nDisallow: /library")
