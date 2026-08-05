import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from amath_bot.assignments.service import AssignmentService
from amath_bot.people.service import PeopleService
from amath_bot.reviews.service import ReviewService
from amath_bot.scheduler import DailyAssignmentJob, create_scheduler
from amath_bot.settings import Settings
from amath_bot.telegram.assignments import AssignmentDeliveryService
from amath_bot.telegram.bot import create_bot, create_dispatcher
from amath_bot.telegram.controls import DatabaseTutorControls
from amath_bot.telegram.reviews import ReviewHandler
from amath_bot.telegram.tutor import TutorHandler

logger = logging.getLogger(__name__)


async def run_polling(settings: Settings) -> None:
    if settings.telegram_bot_token is None or settings.tutor_telegram_id is None:
        raise ValueError("Telegram token and tutor ID are required")
    if settings.review_callback_secret is None or len(settings.review_callback_secret) < 32:
        raise ValueError("review callback secret must be at least 32 characters")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bot: Bot = create_bot(settings.telegram_bot_token)
    scheduler = None
    try:
        identity = await bot.get_me()
        if identity.username is None:
            raise ValueError("Telegram bot must have a username")
        async with factory() as bot_session, factory() as scheduler_session:
            people = PeopleService(bot_session)
            assignments = AssignmentService(bot_session)
            controls = DatabaseTutorControls(
                bot_session,
                tutor_telegram_id=settings.tutor_telegram_id,
                bot_username=identity.username,
                people=people,
                assignments=assignments,
            )
            tutor = TutorHandler(
                tutor_telegram_id=settings.tutor_telegram_id,
                controls=controls,
            )
            review = ReviewHandler(
                tutor_telegram_id=settings.tutor_telegram_id,
                session=bot_session,
                reviews=ReviewService(bot_session),
                callback_secret=settings.review_callback_secret,
            )
            dispatcher = create_dispatcher(
                people, tutor_handler=tutor, review_handler=review
            )
            scheduler_job = DailyAssignmentJob(
                AssignmentService(scheduler_session),
                AssignmentDeliveryService(scheduler_session, bot),
            )
            scheduler = create_scheduler(scheduler_job, timezone=settings.timezone)
            scheduler.start()
            logger.info("starting Telegram polling")
            await dispatcher.start_polling(bot)
    finally:
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        await engine.dispose()
