import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx
from aiogram import BaseMiddleware, Bot
from aiogram.types import BotCommand, TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from amath_bot.assignments.service import AssignmentService
from amath_bot.jobs.mark_attempt import MarkAttemptJob
from amath_bot.marking.local_pipeline import LocalVisionPipeline
from amath_bot.people.service import PeopleService
from amath_bot.people.tables import TutorRow
from amath_bot.providers.openrouter_vision import OpenRouterGrader, OpenRouterTranscriber
from amath_bot.reviews.service import ReviewService
from amath_bot.scheduler import DailyAssignmentJob, add_marking_job, create_scheduler
from amath_bot.settings import Settings
from amath_bot.submissions.service import SubmissionService
from amath_bot.telegram.assignments import AssignmentDeliveryService
from amath_bot.telegram.bot import create_bot, create_dispatcher
from amath_bot.telegram.controls import DatabaseTutorControls
from amath_bot.telegram.review_notifications import TelegramReviewNotifier
from amath_bot.telegram.reviews import ReviewHandler
from amath_bot.telegram.submissions import SubmissionHandler
from amath_bot.telegram.tutor import TutorHandler

logger = logging.getLogger(__name__)


class _DeferredMediaDeletion:
    async def delete_attempt_media(self, attempt_id: int) -> None:
        # Telegram owns the original upload. Database references remain available for tutor review.
        return None


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


class _TrackedCallbacks:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def wrap(self, callback: Callable[[], Awaitable[Any]]) -> Callable[[], Awaitable[Any]]:
        async def tracked() -> Any:
            task = asyncio.current_task()
            if task is None:
                return await callback()
            self._tasks.add(task)
            try:
                return await callback()
            finally:
                self._tasks.discard(task)

        return tracked

    async def wait(self) -> None:
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)


async def _shutdown_scheduler(
    scheduler: AsyncIOScheduler,
    callbacks: _TrackedCallbacks,
    *,
    active_exception: BaseException | None,
) -> None:
    shutdown_error: Exception | None = None
    if scheduler.running:
        try:
            scheduler.shutdown(wait=False)
        except Exception as error:  # noqa: BLE001 - callbacks still must unwind
            shutdown_error = error
    await callbacks.wait()

    if shutdown_error is None:
        return
    if active_exception is None:
        raise shutdown_error
    logger.error(
        "scheduler shutdown failed while handling another exception",
        exc_info=(type(shutdown_error), shutdown_error, shutdown_error.__traceback__),
    )


async def _cleanup_runtime(
    scheduler: AsyncIOScheduler | None,
    http_client: httpx.AsyncClient | None,
    bot: Bot | None,
    engine: AsyncEngine | None,
    *,
    active_exception: BaseException | None,
) -> None:
    cleanup_errors: list[Exception] = []

    if scheduler is not None and scheduler.running:
        try:
            scheduler.shutdown(wait=False)
        except Exception as error:  # noqa: BLE001 - later resources must still be closed
            cleanup_errors.append(error)
    if http_client is not None:
        try:
            await http_client.aclose()
        except Exception as error:  # noqa: BLE001 - later resources must still be closed
            cleanup_errors.append(error)
    if bot is not None:
        try:
            await bot.session.close()
        except Exception as error:  # noqa: BLE001 - later resources must still be closed
            cleanup_errors.append(error)
    if engine is not None:
        try:
            await engine.dispose()
        except Exception as error:  # noqa: BLE001 - report only after all cleanup attempts
            cleanup_errors.append(error)

    if not cleanup_errors:
        return
    if active_exception is None:
        raise cleanup_errors[0]
    for cleanup_error in cleanup_errors:
        logger.error(
            "runtime resource cleanup failed while handling another exception",
            exc_info=(type(cleanup_error), cleanup_error, cleanup_error.__traceback__),
        )


async def run_polling(settings: Settings) -> None:
    if settings.telegram_bot_token is None or settings.tutor_telegram_id is None:
        raise ValueError("Telegram token and tutor ID are required")
    tutor_telegram_id = settings.tutor_telegram_id
    if settings.review_callback_secret is None or len(settings.review_callback_secret) < 32:
        raise ValueError("review callback secret must be at least 32 characters")
    if settings.openrouter_api_key is None or not settings.openrouter_api_key.strip():
        raise ValueError("AMATH_OPENROUTER_API_KEY is required")
    openrouter_api_key = settings.openrouter_api_key

    engine = None
    bot: Bot | None = None
    http_client: httpx.AsyncClient | None = None
    scheduler = None
    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        scoped = async_scoped_session(factory, scopefunc=asyncio.current_task)
        bot = create_bot(settings.telegram_bot_token)
        http_client = httpx.AsyncClient(timeout=180)
        transcriber = OpenRouterTranscriber(
            http_client,
            api_key=openrouter_api_key,
            base_url=settings.openrouter_url,
        )
        grader = OpenRouterGrader(
            http_client,
            api_key=openrouter_api_key,
            base_url=settings.openrouter_url,
        )
        identity = await bot.get_me()
        if identity.username is None:
            raise ValueError("Telegram bot must have a username")
        async with factory() as startup_session:
            if await startup_session.get(TutorRow, settings.tutor_telegram_id) is None:
                startup_session.add(TutorRow(telegram_id=settings.tutor_telegram_id))
                await startup_session.commit()
        async with factory() as scheduler_session:
            callbacks = _TrackedCallbacks()
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
            submissions = SubmissionHandler(SubmissionService(bot_session), bot_session)
            dispatcher = create_dispatcher(
                people,
                tutor_handler=tutor,
                review_handler=review,
                submission_handler=submissions,
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
                    BotCommand(command="reread", description="Run OCR again for current review"),
                    BotCommand(command="mark", description="Specify a reviewed mark"),
                    BotCommand(command="submit", description="Submit uploaded working for review"),
                ]
            )
            scheduler_job = DailyAssignmentJob(
                AssignmentService(scheduler_session),
                AssignmentDeliveryService(scheduler_session, bot),
            )
            scheduler = create_scheduler(
                scheduler_job,
                timezone=settings.timezone,
                daily_callback=callbacks.wrap(scheduler_job.run),
            )

            async def mark_pending() -> None:
                async with factory() as marking_session:
                    pipeline = LocalVisionPipeline(
                        marking_session,
                        bot,
                        transcriber,
                        grader,
                    )
                    processed = await MarkAttemptJob(
                        marking_session,
                        pipeline=pipeline,
                        notifier=bot,
                        media=_DeferredMediaDeletion(),
                    ).run_pending()
                    if processed:
                        await bot.send_message(
                            tutor_telegram_id,
                            f"{processed} submission(s) are ready. Use /review to inspect them.",
                        )

            try:
                add_marking_job(scheduler, callbacks.wrap(mark_pending))
                scheduler.start()
                logger.info("starting Telegram polling")
                await dispatcher.start_polling(bot)
            finally:
                active_exception = sys.exception()
                scheduler_to_shutdown = scheduler
                scheduler = None
                await _shutdown_scheduler(
                    scheduler_to_shutdown,
                    callbacks,
                    active_exception=active_exception,
                )
    finally:
        await _cleanup_runtime(
            scheduler,
            http_client,
            bot,
            engine,
            active_exception=sys.exception(),
        )
