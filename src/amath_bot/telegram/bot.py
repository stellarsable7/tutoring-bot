from aiogram import Bot, Dispatcher

from amath_bot.people.service import PeopleService
from amath_bot.telegram.start import StartHandler, create_start_router
from amath_bot.telegram.tutor import TutorHandler, create_tutor_router


def create_dispatcher(
    people: PeopleService, *, tutor_handler: TutorHandler | None = None
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(create_start_router(StartHandler(people)))
    if tutor_handler is not None:
        dispatcher.include_router(create_tutor_router(tutor_handler))
    return dispatcher


def create_bot(token: str) -> Bot:
    return Bot(token=token)
