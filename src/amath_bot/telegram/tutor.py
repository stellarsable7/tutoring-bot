from dataclasses import dataclass
from typing import Protocol

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


class TutorUser(Protocol):
    id: int


class TutorMessage(Protocol):
    from_user: TutorUser


class TutorControls(Protocol):
    async def execute(self, command: str, args: tuple[str, ...]) -> str: ...


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

    async def schedule(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "schedule", args)

    async def assign(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "assign", args)

    async def pause(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "pause", args)

    async def progress(self, message: TutorMessage, args: tuple[str, ...]) -> TutorReply:
        return await self._run(message, "progress", args)


def create_tutor_router(handler: TutorHandler) -> Router:
    router = Router(name="tutor-controls")

    def register(command_name: str) -> None:
        @router.message(Command(command_name))
        async def command(message: Message) -> None:
            if message.from_user is None:
                return
            text = message.text or ""
            args = tuple(text.split()[1:])
            method = getattr(handler, command_name)
            reply = (
                await method(message, args)
                if command_name not in {"students", "invite"}
                else await method(message)
            )
            await message.answer(reply.text)

    for name in ("invite", "students", "schedule", "assign", "pause", "progress"):
        register(name)
    return router
