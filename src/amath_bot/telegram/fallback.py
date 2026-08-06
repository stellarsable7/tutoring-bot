from aiogram import Router
from aiogram.types import Message


def create_fallback_router() -> Router:
    router = Router(name="safe-fallbacks")

    @router.message()
    async def unknown_message(message: Message) -> None:
        await message.answer("I didn’t recognize that. Tutors can use /help.")

    return router
