import shlex
from dataclasses import dataclass
from typing import Protocol

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message


class TutorUser(Protocol):
    id: int


class TutorMessage(Protocol):
    from_user: TutorUser


class TutorControls(Protocol):
    async def execute(self, command: str, args: tuple[str, ...]) -> str: ...

    async def student_telegram_id(self, display_name: str) -> int: ...


@dataclass(frozen=True)
class TutorReply:
    text: str


class TutorHandler:
    def __init__(self, *, tutor_telegram_id: int, controls: TutorControls) -> None:
        self._tutor_telegram_id = tutor_telegram_id
        self._controls = controls

    async def _run(
        self, message: TutorMessage, command: str, args: tuple[str, ...] = ()
    ) -> TutorReply:
        if message.from_user.id != self._tutor_telegram_id:
            return TutorReply("Tutor access required.")
        return TutorReply(await self._controls.execute(command, args))

    async def students(self, message: TutorMessage) -> TutorReply:
        return await self._run(message, "students")

    async def invite(self, message: TutorMessage) -> TutorReply:
        return await self._run(message, "invite")

    async def help(self, message: TutorMessage) -> TutorReply:
        if message.from_user.id != self._tutor_telegram_id:
            return TutorReply("Tutor access required.")
        return TutorReply(
            "Tutor commands:\n"
            "/invite — create a student invite\n"
            "/students — list students\n"
            "/schedule NAME weekdays HH:MM [COUNT] — set delivery\n"
            '/assign "NAME" — send a random unseen question\n'
            "/pause NAME — pause delivery\n"
            "/resume NAME — resume delivery\n"
            '/remove "NAME" CONFIRM — permanently remove a student\n'
            "/clear CONFIRM — delete recent private-chat messages for both sides\n"
            '/clearstudent "NAME" CONFIRM — clear a student’s recent bot chat\n'
            "/progress NAME — show progress\n"
            "/review — review flagged work\n"
            "/reread — rerun OCR and vision for the current review\n"
            "/mark SCORE feedback — specify the mark for the current review"
        )

    async def schedule(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "schedule", args)

    async def assign(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "assign", args)

    async def pause(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "pause", args)

    async def resume(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "resume", args)

    async def remove(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "remove", args)

    async def progress(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "progress", args)

    def is_tutor(self, telegram_id: int) -> bool:
        return telegram_id == self._tutor_telegram_id

    async def student_telegram_id(self, display_name: str) -> int:
        return await self._controls.student_telegram_id(display_name)


def deletion_batches(latest_message_id: int, *, limit: int = 500) -> tuple[list[int], ...]:
    """Return newest-first API batches without crossing Telegram's 100-ID limit."""
    oldest = max(1, latest_message_id - limit + 1)
    ids = list(range(latest_message_id, oldest - 1, -1))
    return tuple(ids[index : index + 100] for index in range(0, len(ids), 100))


def command_args(text: str) -> tuple[str, ...]:
    """Parse quoted arguments while normalizing mobile-keyboard Unicode whitespace."""
    return tuple(shlex.split(" ".join(text.split()))[1:])


def create_tutor_router(handler: TutorHandler) -> Router:
    router = Router(name="tutor-controls")

    def register(command_name: str) -> None:
        @router.message(Command(command_name))
        async def command(message: Message) -> None:
            if message.from_user is None:
                return
            text = message.text or ""
            try:
                args = command_args(text)
            except ValueError as error:
                await message.answer(f"Invalid command: {error}")
                return
            if command_name in {"clear", "clearstudent"}:
                if not handler.is_tutor(message.from_user.id):
                    await message.answer("Tutor access required.")
                    return
                bot = message.bot
                if bot is None:
                    await message.answer("Could not access the bot connection.")
                    return
                if command_name == "clear":
                    if message.chat.type != "private":
                        await message.answer("/clear is only available in a private bot chat.")
                        return
                    if len(args) != 1 or args[0].strip().casefold() != "confirm":
                        await message.answer(
                            "This deletes recent messages for both sides. Use /clear CONFIRM."
                        )
                        return
                    target_chat_id = message.chat.id
                    latest_message_id = message.message_id
                else:
                    if len(args) < 2 or args[-1].strip().casefold() != "confirm":
                        await message.answer('Use /clearstudent "NAME" CONFIRM.')
                        return
                    display_name = " ".join(args[:-1])
                    try:
                        target_chat_id = await handler.student_telegram_id(display_name)
                    except ValueError as error:
                        await message.answer(f"Could not run /clearstudent: {error}")
                        return
                    marker = await bot.send_message(target_chat_id, "Clearing recent bot chat…")
                    latest_message_id = marker.message_id
                batches_attempted = 0
                for message_ids in deletion_batches(latest_message_id):
                    batches_attempted += 1
                    try:
                        await bot.delete_messages(target_chat_id, message_ids)
                    except TelegramAPIError:
                        # A batch can contain messages outside Telegram's 48-hour window.
                        # Retry newest-first so one old/undeletable ID cannot preserve
                        # otherwise deletable recent messages in the same batch.
                        consecutive_failures = 0
                        for message_id in message_ids:
                            try:
                                await bot.delete_message(target_chat_id, message_id)
                            except TelegramAPIError:
                                consecutive_failures += 1
                                if consecutive_failures >= 10:
                                    break
                            else:
                                consecutive_failures = 0
                        break
                if command_name == "clearstudent":
                    await message.answer(
                        f"Clear attempted for {display_name} "
                        f"({batches_attempted} message batch(es))."
                    )
                return
            method = getattr(handler, command_name)
            reply = (
                await method(message, args)
                if command_name not in {"help", "students", "invite"}
                else await method(message)
            )
            await message.answer(reply.text)

    for name in (
        "help",
        "invite",
        "students",
        "schedule",
        "assign",
        "pause",
        "resume",
        "remove",
        "progress",
        "clear",
        "clearstudent",
    ):
        register(name)
    return router
