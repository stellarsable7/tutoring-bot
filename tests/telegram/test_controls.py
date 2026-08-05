from dataclasses import dataclass

from amath_bot.telegram.controls import DatabaseTutorControls


@dataclass(frozen=True)
class FakeInvite:
    code: str


class FakePeople:
    async def create_invite(self, tutor_telegram_id: int) -> FakeInvite:
        assert tutor_telegram_id == 100
        return FakeInvite("invite-code")


class FakeAssignments:
    async def set_schedule(
        self,
        student_id: int,
        *,
        weekdays: set[int],
        hour: int,
        count: int = 1,
        timezone: str = "Asia/Singapore",
    ) -> None:
        raise AssertionError("not used")


async def test_invite_uses_deployed_bot_username() -> None:
    controls = DatabaseTutorControls(
        None,  # type: ignore[arg-type]
        tutor_telegram_id=100,
        bot_username="amath_practice_bot",
        people=FakePeople(),  # type: ignore[arg-type]
        assignments=FakeAssignments(),  # type: ignore[arg-type]
    )
    result = await controls.execute("invite", ())
    assert result == "Student invite: https://t.me/amath_practice_bot?start=invite-code"
