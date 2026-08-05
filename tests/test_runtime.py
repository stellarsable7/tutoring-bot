import pytest

from amath_bot.runtime import SessionCleanupMiddleware


class FakeSessions:
    def __init__(self) -> None:
        self.removed = 0

    async def remove(self) -> None:
        self.removed += 1


async def test_scoped_session_is_removed_after_success() -> None:
    sessions = FakeSessions()
    middleware = SessionCleanupMiddleware(sessions)  # type: ignore[arg-type]

    async def handler(event, data):  # type: ignore[no-untyped-def]
        return "ok"

    assert await middleware(handler, object(), {}) == "ok"  # type: ignore[arg-type]
    assert sessions.removed == 1


async def test_scoped_session_is_removed_after_handler_failure() -> None:
    sessions = FakeSessions()
    middleware = SessionCleanupMiddleware(sessions)  # type: ignore[arg-type]

    async def handler(event, data):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await middleware(handler, object(), {})  # type: ignore[arg-type]
    assert sessions.removed == 1
