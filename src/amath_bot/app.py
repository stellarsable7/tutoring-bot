import logging

from amath_bot.settings import Settings

logger = logging.getLogger(__name__)


def health() -> dict[str, str]:
    """Return a dependency-free process health payload."""
    return {"status": "ok", "service": "amath-bot"}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings()
    if settings.telegram_dry_run:
        logger.info("telegram dry-run enabled")
        return 0
    if not settings.telegram_bot_token or settings.tutor_telegram_id is None:
        raise ValueError(
            "AMATH_TELEGRAM_BOT_TOKEN and AMATH_TUTOR_TELEGRAM_ID are required"
        )
    logger.info("telegram configuration validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
