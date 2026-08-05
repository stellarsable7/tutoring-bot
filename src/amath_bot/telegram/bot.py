from aiogram import Bot, Dispatcher

from amath_bot.people.service import PeopleService
from amath_bot.telegram.fallback import create_fallback_router
from amath_bot.telegram.reviews import ReviewHandler, create_review_router
from amath_bot.telegram.start import StartHandler, create_start_router
from amath_bot.telegram.tutor import TutorHandler, create_tutor_router


def create_dispatcher(
    people: PeopleService,
    *,
    tutor_handler: TutorHandler | None = None,
    review_handler: ReviewHandler | None = None,
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(create_start_router(StartHandler(people)))
    if tutor_handler is not None:
        dispatcher.include_router(create_tutor_router(tutor_handler))
    if review_handler is not None:
        dispatcher.include_router(create_review_router(review_handler))
    dispatcher.include_router(create_fallback_router())
    return dispatcher


def create_bot(token: str) -> Bot:
    return Bot(token=token)
