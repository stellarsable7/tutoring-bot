import asyncio
import json
import re
import time
from collections.abc import Callable
from urllib.robotparser import RobotFileParser

import httpx

from amath_bot.discovery.models import DiscoveredDocument, DiscoveredPair, DiscoveryResult


class DiscoveryPayloadError(ValueError):
    """Raised when the public library payload cannot be parsed safely."""


class LibraryDisallowed(RuntimeError):
    """Raised when the site's robots rules disallow library discovery."""


class HolyGrailDiscovery:
    BASE_URL = "https://grail.moe"
    LIBRARY_PATH = "/library"
    CATEGORY_ID = 1
    SUBJECT_ID = 30
    USER_AGENT = "AMathTutorBot/0.1 (+catalogue discovery; contact configured by operator)"
    MIN_REQUEST_INTERVAL_SECONDS = 5.0

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._clock = clock
        self._last_request_at: float | None = None
        self._etag: str | None = None
        self._last_modified: str | None = None

    @staticmethod
    def assert_library_allowed(robots_text: str) -> None:
        parser = RobotFileParser()
        parser.set_url(f"{HolyGrailDiscovery.BASE_URL}/robots.txt")
        parser.parse(robots_text.splitlines())
        if not parser.can_fetch(
            HolyGrailDiscovery.USER_AGENT,
            f"{HolyGrailDiscovery.BASE_URL}{HolyGrailDiscovery.LIBRARY_PATH}",
        ):
            raise LibraryDisallowed("Holy Grail robots.txt disallows /library")

    async def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self.MIN_REQUEST_INTERVAL_SECONDS - (self._clock() - self._last_request_at)
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def fetch_library_page(self, page: int = 1) -> DiscoveryResult | None:
        await self._wait_for_rate_limit()
        headers = {"User-Agent": self.USER_AGENT}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified
        response = await self._client.get(
            f"{self.BASE_URL}{self.LIBRARY_PATH}",
            params={
                "category": "GCE 'O' Levels",
                "subject": "Additional Mathematics",
                "doc_type": "Exam Papers",
                "page": page,
            },
            headers=headers,
        )
        self._last_request_at = self._clock()
        if response.status_code == 304:
            return None
        response.raise_for_status()
        self._etag = response.headers.get("etag")
        self._last_modified = response.headers.get("last-modified")
        return self.parse_library_page(response.text)

    @classmethod
    def parse_library_page(cls, html: str) -> DiscoveryResult:
        match = re.search(r'\\"items\\":(\[.*?\]),\\"total\\":(\d+)', html)
        page_match = re.search(r'\\"page\\":(\d+)', html)
        pages_match = re.search(r'\\"pages\\":(\d+)', html)
        if match is None or page_match is None or pages_match is None:
            raise DiscoveryPayloadError("Next.js library payload not found")
        try:
            payload = json.loads(match.group(1).replace(r'\"', '"').replace(r"\u0026", "&"))
        except json.JSONDecodeError as error:
            raise DiscoveryPayloadError("invalid library item JSON") from error

        documents = tuple(cls._document(item) for item in payload if cls._is_o_level_amath(item))
        return cls._pair(
            documents,
            page=int(page_match.group(1)),
            pages=int(pages_match.group(1)),
            total=int(match.group(2)),
        )

    @classmethod
    def _document(cls, item: dict[str, object]) -> DiscoveredDocument:
        external_id = cls._required_int(item, "id")
        year_value = item.get("year")
        year = cls._as_int(year_value, "year") if year_value is not None else None
        return DiscoveredDocument.model_validate(
            {
                "external_id": external_id,
                "category_id": cls._required_int(item, "category"),
                "subject_id": cls._required_int(item, "subject"),
                "document_type_id": cls._required_int(item, "type"),
                "year": year,
                "document_name": str(item["document_name"]),
                "file_name": str(item["file_name"]),
                "detail_url": f"https://document.grail.moe/{item['file_name']}",
                "download_url": f"https://api.grail.moe/note/download/{external_id}",
            }
        )

    @classmethod
    def _required_int(cls, item: dict[str, object], key: str) -> int:
        if key not in item:
            raise DiscoveryPayloadError(f"missing {key}")
        return cls._as_int(item[key], key)

    @staticmethod
    def _as_int(value: object, key: str) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise DiscoveryPayloadError(f"invalid {key}")
        try:
            return int(value)
        except ValueError as error:
            raise DiscoveryPayloadError(f"invalid {key}") from error

    @classmethod
    def _is_o_level_amath(cls, item: dict[str, object]) -> bool:
        return (
            item.get("category") == cls.CATEGORY_ID
            and item.get("subject") == cls.SUBJECT_ID
            and item.get("approved") is True
        )

    @classmethod
    def _pair(
        cls, documents: tuple[DiscoveredDocument, ...], *, page: int, pages: int, total: int
    ) -> DiscoveryResult:
        questions: dict[str, list[DiscoveredDocument]] = {}
        solutions: dict[str, list[DiscoveredDocument]] = {}
        unmatched: list[DiscoveredDocument] = []
        pairs: list[DiscoveredPair] = []
        used_ids: set[int] = set()
        for document in documents:
            classification = cls._classify_name(document.document_name)
            if classification is None:
                unmatched.append(document)
                continue
            kind, base = classification
            if kind == "combined":
                pairs.append(
                    DiscoveredPair(
                        question_document=document,
                        solution_document=document,
                    )
                )
                used_ids.add(document.external_id)
                continue
            (questions if kind == "question" else solutions).setdefault(base, []).append(document)

        for base, question_items in questions.items():
            solution_items = solutions.get(base, [])
            if len(question_items) == 1 and len(solution_items) == 1:
                question = question_items[0]
                solution = solution_items[0]
                pairs.append(
                    DiscoveredPair(question_document=question, solution_document=solution)
                )
                used_ids.update((question.external_id, solution.external_id))
        unmatched.extend(item for item in documents if item.external_id not in used_ids)
        unique_unmatched = {item.external_id: item for item in unmatched}
        return DiscoveryResult(
            pairs=tuple(pairs),
            unpaired=tuple(unique_unmatched.values()),
            page=page,
            pages=pages,
            total=total,
        )

    @staticmethod
    def _classify_name(name: str) -> tuple[str, str] | None:
        normalized = re.sub(r"\s+", " ", name.strip()).casefold()
        combined = re.search(
            r"(?:\s|[-_])(qp|question paper|paper)\s*(?:&|and|with)\s*"
            r"(ms|mark scheme|ans|answers?|solutions?)$",
            normalized,
        )
        if combined:
            return "combined", normalized[: combined.start()].strip(" -_")
        markers = (
            ("question", r"(?:\s|[-_])(qp|question paper|questions?|papers?)$"),
            ("solution", r"(?:\s|[-_])(ms|mark scheme|ans|answers?|solutions?)$"),
        )
        for kind, pattern in markers:
            match = re.search(pattern, normalized)
            if match:
                return kind, normalized[: match.start()].strip(" -_")
        return None
