from dataclasses import dataclass, field

from amath_bot.telegram.tutor import TutorHandler


@dataclass(frozen=True)
class FakeUser:
    id: int


@dataclass(frozen=True)
class FakeMessage:
    from_user: FakeUser


@dataclass
class FakeControls:
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    async def execute(self, command: str, args: tuple[str, ...]) -> str:
        self.calls.append((command, args))
        return f"ran {command}"


async def test_student_cannot_use_tutor_commands() -> None:
    controls = FakeControls()
    handler = TutorHandler(tutor_telegram_id=100, controls=controls)

    response = await handler.students(FakeMessage(FakeUser(200)))

    assert response.text == "Tutor access required."
    assert controls.calls == []


async def test_allowlisted_tutor_can_use_all_commands() -> None:
    controls = FakeControls()
    handler = TutorHandler(tutor_telegram_id=100, controls=controls)
    message = FakeMessage(FakeUser(100))

    await handler.students(message)
    await handler.help(message)
    await handler.schedule(message, ("Ada", "weekdays", "17"))
    await handler.assign(message, ("Ada", "A1.complete-square"))
    await handler.pause(message, ("Ada",))
    await handler.resume(message, ("Ada",))
    await handler.progress(message, ("Ada",))

    assert [name for name, _ in controls.calls] == [
        "students",
        "schedule",
        "assign",
        "pause",
        "resume",
        "progress",
    ]
