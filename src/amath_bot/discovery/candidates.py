import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, HttpUrl

from amath_bot.discovery.models import DiscoveredPair
from amath_bot.discovery.pdf_extract import ExtractedPdf, extract_pdf


class Downloader(Protocol):
    async def download(self, url: str) -> bytes: ...


class QuestionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_number: str
    question_text: str
    published_solution_text: str
    marks: int | None
    question_pages: tuple[int, ...]
    solution_pages: tuple[int, ...]
    source_url: HttpUrl
    solution_url: HttpUrl
    source_checksum_sha256: str
    solution_checksum_sha256: str
    tutor_validated: bool = False


class _Section(BaseModel):
    number: str
    text: str
    pages: tuple[int, ...]


class PdfQuestionExtractor:
    MAX_BYTES = 25 * 1024 * 1024
    MAX_PAGES = 100
    _QUESTION_START = re.compile(r"(?m)^(\d{1,2})[.)]?\s+")
    _MARKS = re.compile(r"\[(\d{1,2})\]\s*$")

    def __init__(self, downloader: Downloader) -> None:
        self._downloader = downloader

    async def extract(self, pair: DiscoveredPair) -> tuple[QuestionCandidate, ...]:
        question_url = str(pair.question_document.download_url)
        solution_url = str(pair.solution_document.download_url)
        question_payload = await self._downloader.download(question_url)
        solution_payload = (
            question_payload
            if solution_url == question_url
            else await self._downloader.download(solution_url)
        )
        question_pdf = extract_pdf(
            question_payload, max_bytes=self.MAX_BYTES, max_pages=self.MAX_PAGES
        )
        solution_pdf = extract_pdf(
            solution_payload, max_bytes=self.MAX_BYTES, max_pages=self.MAX_PAGES
        )
        questions = self._sections(question_pdf)
        solutions = {section.number: section for section in self._sections(solution_pdf)}
        candidates: list[QuestionCandidate] = []
        for question in questions:
            solution = solutions.get(question.number)
            if solution is None:
                continue
            marks_match = self._MARKS.search(question.text)
            candidates.append(
                QuestionCandidate.model_validate(
                    {
                        "question_number": question.number,
                        "question_text": question.text,
                        "published_solution_text": solution.text,
                        "marks": int(marks_match.group(1)) if marks_match else None,
                        "question_pages": question.pages,
                        "solution_pages": solution.pages,
                        "source_url": str(pair.question_document.detail_url),
                        "solution_url": str(pair.solution_document.detail_url),
                        "source_checksum_sha256": question_pdf.checksum_sha256,
                        "solution_checksum_sha256": solution_pdf.checksum_sha256,
                        "tutor_validated": False,
                    }
                )
            )
        return tuple(candidates)

    @classmethod
    def _sections(cls, document: ExtractedPdf) -> tuple[_Section, ...]:
        joined = "\f".join(page.text for page in document.pages)
        page_starts: list[tuple[int, int]] = []
        offset = 0
        for page in document.pages:
            page_starts.append((offset, page.number))
            offset += len(page.text) + 1
        matches = list(cls._QUESTION_START.finditer(joined))
        sections: list[_Section] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(joined)
            text = joined[match.start() : end].replace("\f", "\n").strip()
            pages = tuple(
                page_number
                for page_offset, page_number in page_starts
                if match.start() <= page_offset < end
            )
            if not pages:
                pages = (cls._page_at(match.start(), page_starts),)
            sections.append(_Section(number=match.group(1), text=text, pages=pages))
        return tuple(sections)

    @staticmethod
    def _page_at(offset: int, page_starts: list[tuple[int, int]]) -> int:
        page = 1
        for page_offset, page_number in page_starts:
            if page_offset > offset:
                break
            page = page_number
        return page
