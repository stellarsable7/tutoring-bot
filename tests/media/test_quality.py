from io import BytesIO

import pymupdf
from PIL import Image, ImageDraw

from amath_bot.media.quality import MediaIssue, check_image, check_pdf


def jpeg(width: int, height: int, *, with_detail: bool) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    if with_detail:
        draw = ImageDraw.Draw(image)
        for offset in range(0, min(width, height), 20):
            draw.line((0, offset, width, height - offset), fill="black", width=3)
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def test_small_and_blank_images_fail_before_ai() -> None:
    assert MediaIssue.TOO_SMALL in check_image(jpeg(300, 300, with_detail=True))
    issues = check_image(jpeg(1200, 1200, with_detail=False))
    assert MediaIssue.EMPTY_PAGE in issues
    assert MediaIssue.TOO_BLURRY in issues


def test_clear_image_passes_preflight() -> None:
    assert check_image(jpeg(1200, 1200, with_detail=True)) == ()


def test_pdf_page_limit_is_enforced() -> None:
    document = pymupdf.open()
    for _ in range(11):
        document.new_page()
    payload = document.tobytes()
    document.close()

    assert check_pdf(payload, max_pages=10) == (MediaIssue.PAGE_LIMIT_EXCEEDED,)
