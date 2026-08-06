import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware, Bot
from aiogram.types import BotCommand, TelegramObject
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from amath_bot.assignments.service import AssignmentService
from amath_bot.people.service import PeopleService
from amath_bot.people.tables import TutorRow
from amath_bot.reviews.service import ReviewService
from amath_bot.scheduler import DailyAssignmentJob, create_scheduler
from amath_bot.settings import Settings
from amath_bot.telegram.assignments import AssignmentDeliveryService
from amath_bot.telegram.bot import create_bot, create_dispatcher
from amath_bot.telegram.controls import DatabaseTutorControls
from amath_bot.telegram.review_notifications import TelegramReviewNotifier
from amath_bot.telegram.reviews import ReviewHandler
from amath_bot.telegram.tutor import TutorHandler

logger = logging.getLogger(__name__)


class SessionCleanupMiddleware(BaseMiddleware):
    def __init__(self, sessions: async_scoped_session[AsyncSession]) -> None:
        self._sessions = sessions

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        finally:
            await self._sessions.remove()


async def run_polling(settings: Settings) -> None:
    if settings.telegram_bot_token is None or settings.tutor_telegram_id is None:
        raise ValueError("Telegram token and tutor ID are required")
    if settings.review_callback_secret is None or len(settings.review_callback_secret) < 32:
        raise ValueError("review callback secret must be at least 32 characters")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    scoped = async_scoped_session(factory, scopefunc=asyncio.current_task)
    bot: Bot = create_bot(settings.telegram_bot_token)
    scheduler = None
    try:
        identity = await bot.get_me()
        if identity.username is None:
            raise ValueError("Telegram bot must have a username")
        async with factory() as startup_session:
            if await startup_session.get(TutorRow, settings.tutor_telegram_id) is None:
                startup_session.add(TutorRow(telegram_id=settings.tutor_telegram_id))
                await startup_session.commit()
        async with factory() as scheduler_session:
            bot_session = cast(AsyncSession, scoped)
            people = PeopleService(bot_session)
            assignments = AssignmentService(bot_session)
            controls = DatabaseTutorControls(
                bot_session,
                tutor_telegram_id=settings.tutor_telegram_id,
                bot_username=identity.username,
                people=people,
                assignments=assignments,
                timezone=settings.timezone,
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
                notifier=TelegramReviewNotifier(bot_session, bot),
            )
            dispatcher = create_dispatcher(
                people, tutor_handler=tutor, review_handler=review
            )
            dispatcher.update.outer_middleware(SessionCleanupMiddleware(scoped))
            await bot.set_my_commands(
                [
                    BotCommand(command="help", description="Show available commands"),
                    BotCommand(command="invite", description="Create a student invite"),
                    BotCommand(command="students", description="List enrolled students"),
                    BotCommand(command="schedule", description="Set a student's schedule"),
                    BotCommand(command="assign", description="Assign a question"),
                    BotCommand(command="pause", description="Pause a student"),
                    BotCommand(command="resume", description="Resume a student"),
                    BotCommand(command="remove", description="Permanently remove a student"),
                    BotCommand(command="clear", description="Clear recent private-chat messages"),
                    BotCommand(command="clearstudent", description="Clear a student's recent chat"),
                    BotCommand(command="progress", description="Show student progress"),
                    BotCommand(command="review", description="Review flagged marking"),
                ]
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
