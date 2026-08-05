from aiogram import F, Router
from aiogram.types import Message


def create_fallback_router() -> Router:
    router = Router(name="safe-fallbacks")

    @router.message(F.photo | F.document)
    async def unavailable_marking(message: Message) -> None:
        await message.answer(
            "Photo and PDF marking is not enabled yet. No submitted file was stored."
        )

    @router.message()
    async def unknown_message(message: Message) -> None:
        await message.answer("I didn’t recognize that. Tutors can use /help.")

    return router
