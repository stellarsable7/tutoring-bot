from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from amath_bot.people.service import PeopleService
from amath_bot.telegram.text import CONSENT_TEXT


class UserLike(Protocol):
    id: int
    full_name: str


class MessageLike(Protocol):
    from_user: UserLike


@dataclass(frozen=True)
class Reply:
    text: str
    buttons: tuple[str, ...] = ()


class StartHandler:
    def __init__(self, people: PeopleService) -> None:
        self.people = people
        self._pending_invites: dict[int, str] = {}

    async def start(self, message: MessageLike, *, invite_code: str) -> tuple[Reply, ...]:
        self._pending_invites[message.from_user.id] = invite_code
        return (Reply(CONSENT_TEXT, ("I consent", "Cancel")),)

    async def consent(self, message: MessageLike, *, consented_at: datetime) -> Reply:
        code = self._pending_invites.pop(message.from_user.id, None)
        if code is None:
            return Reply("This invite session has expired. Please open your invite link again.")
        await self.people.redeem(
            code,
            telegram_id=message.from_user.id,
            display_name=message.from_user.full_name,
            consented_at=consented_at,
        )
        return Reply("You’re enrolled. Your tutor can now set your question schedule.")

    async def cancel(self, message: MessageLike) -> Reply:
        self._pending_invites.pop(message.from_user.id, None)
        return Reply("Enrollment cancelled. No student account was created.")


def create_start_router(handler: StartHandler) -> Router:
    router = Router(name="student-onboarding")

    @router.message(CommandStart(deep_link=True))
    async def start(message: Message, command: object) -> None:
        args = getattr(command, "args", None)
        if message.from_user is None or not isinstance(args, str) or not args:
            await message.answer("Use the private invite link sent by your tutor.")
            return
        reply = (await handler.start(message, invite_code=args))[-1]  # type: ignore[arg-type]
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="I consent", callback_data="consent:yes"),
                    InlineKeyboardButton(text="Cancel", callback_data="consent:no"),
                ]
            ]
        )
        await message.answer(reply.text, reply_markup=keyboard)

    @router.callback_query(F.data == "consent:yes")
    async def consent(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return
        reply = await handler.consent(callback.message, consented_at=datetime.now().astimezone())  # type: ignore[arg-type]
        await callback.message.answer(reply.text)
        await callback.answer()

    @router.callback_query(F.data == "consent:no")
    async def cancel(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return
        reply = await handler.cancel(callback.message)  # type: ignore[arg-type]
        await callback.message.answer(reply.text)
        await callback.answer()

    return router

