from dataclasses import dataclass, field

from amath_bot.telegram.tutor import TutorHandler, command_args, deletion_batches


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

    async def student_telegram_id(self, display_name: str) -> int:
        assert display_name == "Ada"
        return 200


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
    await handler.assign(message, ("Ada",))
    await handler.test(message, ())
    await handler.pause(message, ("Ada",))
    await handler.resume(message, ("Ada",))
    await handler.remove(message, ("Ada", "CONFIRM"))
    await handler.progress(message, ("Ada",))

    assert [name for name, _ in controls.calls] == [
        "students",
        "schedule",
        "assign",
        "test",
        "pause",
        "resume",
        "remove",
        "progress",
    ]


def test_deletion_batches_are_newest_first_and_bounded() -> None:
    batches = deletion_batches(250, limit=205)

    assert [len(batch) for batch in batches] == [100, 100, 5]
    assert batches[0][0] == 250
    assert batches[-1][-1] == 46


def test_command_args_accept_mobile_whitespace_and_confirmation_case() -> None:
    assert command_args('/clear\u00a0confirm') == ("confirm",)
    assert command_args('/clearstudent\u00a0"Ada Lovelace"\u00a0CONFIRM') == (
        "Ada Lovelace",
        "CONFIRM",
    )
