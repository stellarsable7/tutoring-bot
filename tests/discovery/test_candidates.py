import pymupdf
import pytest

from amath_bot.discovery.candidates import PdfQuestionExtractor
from amath_bot.discovery.models import DiscoveredDocument, DiscoveredPair
from amath_bot.discovery.pdf_extract import PdfLimitError


def pdf_bytes(*pages: str) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def discovered_pair() -> DiscoveredPair:
    paper = DiscoveredDocument(
        external_id=100,
        category_id=1,
        subject_id=30,
        document_type_id=2,
        year=2024,
        document_name="Example AM P1 QP",
        file_name="paper.pdf",
        detail_url="https://document.grail.moe/paper.pdf",
        download_url="https://api.grail.moe/note/download/100",
    )
    solution = DiscoveredDocument(
        external_id=101,
        category_id=1,
        subject_id=30,
        document_type_id=2,
        year=2024,
        document_name="Example AM P1 MS",
        file_name="solution.pdf",
        detail_url="https://document.grail.moe/solution.pdf",
        download_url="https://api.grail.moe/note/download/101",
    )
    return DiscoveredPair(question_document=paper, solution_document=solution)


class FakeDownloader:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    async def download(self, url: str) -> bytes:
        return self.payloads[url]


async def test_extracts_matching_question_numbers_from_published_pair() -> None:
    pair = discovered_pair()
    downloader = FakeDownloader(
        {
            str(pair.question_document.download_url): pdf_bytes(
                "1 Solve x + 1 = 3. [2]\n2 Factorise x squared - 5x + 6. [3]"
            ),
            str(pair.solution_document.download_url): pdf_bytes(
                "1 x = 2. M1 A1 [2]\n2 (x - 2)(x - 3). B3 [3]"
            ),
        }
    )
    candidates = await PdfQuestionExtractor(downloader).extract(pair)
    assert [item.question_number for item in candidates] == ["1", "2"]
    assert all(item.question_text for item in candidates)
    assert all(item.published_solution_text for item in candidates)
    assert all(item.tutor_validated is False for item in candidates)


async def test_missing_solution_section_is_excluded() -> None:
    pair = discovered_pair()
    downloader = FakeDownloader(
        {
            str(pair.question_document.download_url): pdf_bytes("1 First [2]\n2 Second [3]"),
            str(pair.solution_document.download_url): pdf_bytes("1 Published answer [2]"),
        }
    )
    candidates = await PdfQuestionExtractor(downloader).extract(pair)
    assert [item.question_number for item in candidates] == ["1"]


async def test_oversized_payload_is_rejected() -> None:
    pair = discovered_pair()
    oversized = b"%PDF" + b"x" * (PdfQuestionExtractor.MAX_BYTES + 1)
    downloader = FakeDownloader(
        {
            str(pair.question_document.download_url): oversized,
            str(pair.solution_document.download_url): pdf_bytes("1 Answer"),
        }
    )
    with pytest.raises(PdfLimitError):
        await PdfQuestionExtractor(downloader).extract(pair)
