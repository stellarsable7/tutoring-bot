from aiogram import Bot, Dispatcher

from amath_bot.people.service import PeopleService
from amath_bot.telegram.start import StartHandler, create_start_router


def create_dispatcher(people: PeopleService) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(create_start_router(StartHandler(people)))
    return dispatcher


def create_bot(token: str) -> Bot:
    return Bot(token=token)
