from enum import StrEnum
from io import BytesIO

import pymupdf
from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError


class MediaIssue(StrEnum):
    TOO_LARGE = "TOO_LARGE"
    TOO_SMALL = "TOO_SMALL"
    TOO_BLURRY = "TOO_BLURRY"
    EMPTY_PAGE = "EMPTY_PAGE"
    EXTREME_ROTATION = "EXTREME_ROTATION"
    PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
    INVALID_MEDIA = "INVALID_MEDIA"


def check_image(
    payload: bytes,
    *,
    max_bytes: int = 15 * 1024 * 1024,
    minimum_dimension: int = 800,
) -> tuple[MediaIssue, ...]:
    if len(payload) > max_bytes:
        return (MediaIssue.TOO_LARGE,)
    try:
        with Image.open(BytesIO(payload)) as source:
            source.load()
            image = source.convert("L")
    except (UnidentifiedImageError, OSError):
        return (MediaIssue.INVALID_MEDIA,)

    issues: list[MediaIssue] = []
    if min(image.size) < minimum_dimension:
        issues.append(MediaIssue.TOO_SMALL)
    pixel_variance = ImageStat.Stat(image).var[0]
    edge_variance = ImageStat.Stat(image.filter(ImageFilter.FIND_EDGES)).var[0]
    if pixel_variance < 8:
        issues.append(MediaIssue.EMPTY_PAGE)
        issues.append(MediaIssue.TOO_BLURRY)
    elif edge_variance < 80:
        issues.append(MediaIssue.TOO_BLURRY)
    return tuple(issues)


def check_pdf(
    payload: bytes,
    *,
    max_bytes: int = 25 * 1024 * 1024,
    max_pages: int = 10,
) -> tuple[MediaIssue, ...]:
    if len(payload) > max_bytes:
        return (MediaIssue.TOO_LARGE,)
    if not payload.startswith(b"%PDF"):
        return (MediaIssue.INVALID_MEDIA,)
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")  # type: ignore[no-untyped-call]
    except (pymupdf.FileDataError, RuntimeError):
        return (MediaIssue.INVALID_MEDIA,)
    try:
        if document.page_count > max_pages:
            return (MediaIssue.PAGE_LIMIT_EXCEEDED,)
        issues: list[MediaIssue] = []
        for page_number in range(document.page_count):
            page = document.load_page(page_number)  # type: ignore[no-untyped-call]
            if page.rotation in {90, 270}:
                issues.append(MediaIssue.EXTREME_ROTATION)
            if not page.get_text("text").strip() and not page.get_images():
                issues.append(MediaIssue.EMPTY_PAGE)
        return tuple(dict.fromkeys(issues))
    finally:
        document.close()  # type: ignore[no-untyped-call]
