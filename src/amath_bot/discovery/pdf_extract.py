import hashlib
from dataclasses import dataclass

import pymupdf


class PdfExtractionError(ValueError):
    """Raised when a source is not a readable PDF."""


class PdfLimitError(PdfExtractionError):
    """Raised when a PDF exceeds configured processing bounds."""


@dataclass(frozen=True)
class PdfPage:
    number: int
    text: str


@dataclass(frozen=True)
class ExtractedPdf:
    checksum_sha256: str
    pages: tuple[PdfPage, ...]


def extract_pdf(payload: bytes, *, max_bytes: int, max_pages: int) -> ExtractedPdf:
    if len(payload) > max_bytes:
        raise PdfLimitError(f"PDF exceeds {max_bytes} bytes")
    if not payload.startswith(b"%PDF"):
        raise PdfExtractionError("source is not a PDF")
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")  # type: ignore[no-untyped-call]
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise PdfExtractionError("malformed PDF") from error
    try:
        if document.page_count > max_pages:
            raise PdfLimitError(f"PDF exceeds {max_pages} pages")
        pages = tuple(
            PdfPage(
                number=index + 1,
                text=document.load_page(index).get_text("text"),  # type: ignore[no-untyped-call]
            )
            for index in range(document.page_count)
        )
    finally:
        document.close()  # type: ignore[no-untyped-call]
    return ExtractedPdf(checksum_sha256=hashlib.sha256(payload).hexdigest(), pages=pages)
