import asyncio
import logging

from amath_bot.runtime import run_polling
from amath_bot.settings import Settings

logger = logging.getLogger(__name__)


def health() -> dict[str, str]:
    """Return a dependency-free process health payload."""
    return {"status": "ok", "service": "amath-bot"}


def validate_polling_settings(settings: Settings) -> None:
    if (
        not settings.telegram_bot_token
        or settings.tutor_telegram_id is None
        or not settings.review_callback_secret
    ):
        raise ValueError(
            "AMATH_TELEGRAM_BOT_TOKEN, AMATH_TUTOR_TELEGRAM_ID, and "
            "AMATH_REVIEW_CALLBACK_SECRET are required"
        )
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        raise ValueError("AMATH_GEMINI_API_KEY is required")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings()
    if settings.telegram_dry_run:
        logger.info("telegram dry-run enabled")
        return 0
    validate_polling_settings(settings)
    asyncio.run(run_polling(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
