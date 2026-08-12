import asyncio
from types import SimpleNamespace

import pytest

from amath_bot import runtime
from amath_bot.runtime import SessionCleanupMiddleware
from amath_bot.settings import Settings


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


@pytest.mark.parametrize("failing_resource", ["scheduler", "client", "bot", "engine"])
async def test_cleanup_attempts_every_resource_and_raises_first_cleanup_error(
    failing_resource: str,
) -> None:
    events: list[str] = []

    def record(resource: str) -> None:
        events.append(resource)
        if resource == failing_resource:
            raise RuntimeError(f"{resource} cleanup failed")

    class Scheduler:
        running = True

        def shutdown(self, *, wait: bool) -> None:
            assert wait is False
            record("scheduler")

    class Client:
        async def aclose(self) -> None:
            record("client")

    class BotSession:
        async def close(self) -> None:
            record("bot")

    class Bot:
        session = BotSession()

    class Engine:
        async def dispose(self) -> None:
            record("engine")

    with pytest.raises(RuntimeError, match=f"{failing_resource} cleanup failed"):
        await runtime._cleanup_runtime(  # type: ignore[attr-defined]
            Scheduler(), Client(), Bot(), Engine(), active_exception=None
        )

    assert events == ["scheduler", "client", "bot", "engine"]


async def test_cleanup_does_not_mask_active_polling_exception() -> None:
    events: list[str] = []

    class Scheduler:
        running = True

        def shutdown(self, *, wait: bool) -> None:
            events.append("scheduler")
            raise RuntimeError("cleanup failed")

    class Client:
        async def aclose(self) -> None:
            events.append("client")

    class BotSession:
        async def close(self) -> None:
            events.append("bot")

    class Bot:
        session = BotSession()

    class Engine:
        async def dispose(self) -> None:
            events.append("engine")

    polling_error = RuntimeError("polling failed")

    await runtime._cleanup_runtime(  # type: ignore[attr-defined]
        Scheduler(), Client(), Bot(), Engine(), active_exception=polling_error
    )

    assert events == ["scheduler", "client", "bot", "engine"]


async def test_tracked_callbacks_wait_until_an_in_flight_callback_unwinds() -> None:
    tracker = runtime._TrackedCallbacks()  # type: ignore[attr-defined]
    started = asyncio.Event()
    release = asyncio.Event()
    events: list[str] = []

    async def callback() -> None:
        started.set()
        try:
            await release.wait()
        finally:
            events.append("unwound")

    task = asyncio.create_task(tracker.wrap(callback)())
    await started.wait()
    waiter = asyncio.create_task(tracker.wait())
    await asyncio.sleep(0)
    assert waiter.done() is False

    release.set()
    await waiter
    await task

    assert events == ["unwound"]


async def test_scoped_session_is_removed_after_handler_failure() -> None:
    sessions = FakeSessions()
    middleware = SessionCleanupMiddleware(sessions)  # type: ignore[arg-type]

    async def handler(event, data):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await middleware(handler, object(), {})  # type: ignore[arg-type]
    assert sessions.removed == 1


@pytest.mark.parametrize("api_key", [None, "", "   ", "\t\n"])
async def test_run_polling_rejects_missing_openrouter_key_before_startup(
    monkeypatch: pytest.MonkeyPatch, api_key: str | None
) -> None:
    engine_created = False

    def create_engine(*args: object, **kwargs: object) -> object:
        nonlocal engine_created
        engine_created = True
        raise AssertionError("engine must not be created")

    monkeypatch.setattr(runtime, "create_async_engine", create_engine)
    settings = Settings(
        telegram_bot_token="token",
        tutor_telegram_id=1,
        review_callback_secret="x" * 32,
        openrouter_api_key=api_key,
    )

    with pytest.raises(ValueError, match="AMATH_OPENROUTER_API_KEY"):
        await runtime.run_polling(settings)

    assert engine_created is False


async def test_http_client_is_closed_when_bot_startup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeClient:
        def __init__(self, *, timeout: int) -> None:
            assert timeout == 180
            events.append("client-created")

        async def aclose(self) -> None:
            events.append("client-closed")

    class FakeEngine:
        async def dispose(self) -> None:
            events.append("engine-disposed")

    class FakeBotSession:
        async def close(self) -> None:
            events.append("bot-closed")

    class FakeBot:
        session = FakeBotSession()

        async def get_me(self) -> object:
            raise RuntimeError("startup failed")

    monkeypatch.setattr(runtime.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(runtime, "create_async_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(runtime, "async_sessionmaker", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "async_scoped_session", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "create_bot", lambda token: FakeBot())
    settings = Settings(
        telegram_bot_token="token",
        tutor_telegram_id=1,
        review_callback_secret="x" * 32,
        openrouter_api_key="key",
    )

    with pytest.raises(RuntimeError, match="startup failed"):
        await runtime.run_polling(settings)

    assert events == ["client-created", "client-closed", "bot-closed", "engine-disposed"]


async def test_runtime_registers_openrouter_marking_with_shared_client_and_fresh_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    sessions: list[object] = []
    callback = None
    marking_started = asyncio.Event()
    daily_started = asyncio.Event()
    provider_arguments: list[tuple[object, str, str]] = []
    providers_created: list[object] = []
    pipeline_arguments: tuple[object, object, object, object] | None = None

    class PollingStopped(RuntimeError):
        pass

    class FakeClient:
        def __init__(self, *, timeout: int) -> None:
            assert timeout == 180

        async def aclose(self) -> None:
            events.append("client-closed")

    class FakeEngine:
        async def dispose(self) -> None:
            events.append("engine-disposed")

    class FakeSession:
        async def get(self, row: object, key: object) -> object:
            return object()

        def add(self, row: object) -> None:
            raise AssertionError("existing tutor must not be added")

        async def commit(self) -> None:
            raise AssertionError("existing tutor must not be committed")

    class SessionContext:
        def __init__(self) -> None:
            self.session = FakeSession()
            self.ordinal = len(sessions)
            sessions.append(self.session)

        async def __aenter__(self) -> object:
            return self.session

        async def __aexit__(self, *args: object) -> None:
            if self.ordinal == 1:
                events.append("scheduler-session-exited")
            elif self.ordinal == 2:
                events.append("marking-session-exited")

    class FakeFactory:
        def __call__(self) -> SessionContext:
            return SessionContext()

    class FakeBotSession:
        async def close(self) -> None:
            events.append("bot-closed")

    class FakeBot:
        session = FakeBotSession()

        async def get_me(self) -> object:
            return SimpleNamespace(username="amath_bot")

        async def set_my_commands(self, commands: object) -> None:
            return None

        async def send_message(self, chat_id: int, text: str) -> None:
            return None

    class FakeUpdate:
        def outer_middleware(self, middleware: object) -> None:
            return None

    class FakeDispatcher:
        update = FakeUpdate()

        async def start_polling(self, bot: object) -> None:
            assert callback is not None
            scheduler.callback_task = asyncio.create_task(callback())
            await marking_started.wait()
            await daily_started.wait()
            raise PollingStopped("done")

    class FakeScheduler:
        running = True
        callback_task: asyncio.Task[object] | None = None
        daily_callback: object = None
        daily_task: asyncio.Task[object] | None = None

        def start(self) -> None:
            assert callable(self.daily_callback)
            self.daily_task = asyncio.create_task(self.daily_callback())

        def shutdown(self, *, wait: bool) -> None:
            assert wait is False
            events.append("scheduler-stopped")
            assert self.callback_task is not None
            self.callback_task.cancel()
            assert self.daily_task is not None
            self.daily_task.cancel()

    def make_provider(client: object, *, api_key: str, base_url: str) -> object:
        provider_arguments.append((client, api_key, base_url))
        provider = object()
        providers_created.append(provider)
        return provider

    def make_pipeline(
        session: object, bot: object, transcriber: object, grader: object
    ) -> object:
        nonlocal pipeline_arguments
        pipeline_arguments = (session, bot, transcriber, grader)
        return object()

    class FakeMarkAttemptJob:
        def __init__(self, session: object, **kwargs: object) -> None:
            assert session is sessions[-1]

        async def run_pending(self) -> int:
            marking_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                events.append("callback-unwound")
            return 0

    def register_marking_job(scheduler: object, registered: object) -> None:
        nonlocal callback
        callback = registered

    factory = FakeFactory()
    bot = FakeBot()
    scheduler = FakeScheduler()
    monkeypatch.setattr(runtime.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(runtime, "create_async_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(runtime, "async_sessionmaker", lambda *args, **kwargs: factory)
    monkeypatch.setattr(runtime, "async_scoped_session", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "create_bot", lambda token: bot)
    monkeypatch.setattr(runtime, "create_dispatcher", lambda *args, **kwargs: FakeDispatcher())
    def make_scheduler(*args: object, **kwargs: object) -> FakeScheduler:
        assert kwargs["daily_callback"] is not None
        scheduler.daily_callback = kwargs["daily_callback"]
        return scheduler

    monkeypatch.setattr(runtime, "create_scheduler", make_scheduler)
    monkeypatch.setattr(runtime, "add_marking_job", register_marking_job)
    monkeypatch.setattr(runtime, "OpenRouterTranscriber", make_provider)
    monkeypatch.setattr(runtime, "OpenRouterGrader", make_provider)
    monkeypatch.setattr(runtime, "LocalVisionPipeline", make_pipeline)
    monkeypatch.setattr(runtime, "MarkAttemptJob", FakeMarkAttemptJob)
    async def daily_run() -> object:
        daily_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            events.append("daily-callback-unwound")
        return object()

    monkeypatch.setattr(runtime, "DailyAssignmentJob", lambda *args, **kwargs: SimpleNamespace(run=daily_run))
    for name in (
        "PeopleService",
        "AssignmentService",
        "DatabaseTutorControls",
        "TutorHandler",
        "ReviewHandler",
        "ReviewService",
        "TelegramReviewNotifier",
        "SubmissionHandler",
        "SubmissionService",
        "AssignmentDeliveryService",
    ):
        monkeypatch.setattr(runtime, name, lambda *args, **kwargs: object())

    settings = Settings(
        telegram_bot_token="token",
        tutor_telegram_id=1,
        review_callback_secret="x" * 32,
        openrouter_api_key=" secret-key ",
        openrouter_url="https://router.test/v1",
    )

    with pytest.raises(PollingStopped, match="done"):
        await runtime.run_polling(settings)

    assert len(provider_arguments) == 2
    for client, api_key, base_url in provider_arguments:
        assert isinstance(client, FakeClient)
        assert api_key == " secret-key "
        assert base_url == "https://router.test/v1"
    assert pipeline_arguments == (sessions[2], bot, *providers_created)
    assert len(sessions) == 3
    assert events[0] == "scheduler-stopped"
    assert events.index("callback-unwound") < events.index("scheduler-session-exited")
    assert events.index("daily-callback-unwound") < events.index("scheduler-session-exited")
    assert events.index("marking-session-exited") < events.index("scheduler-session-exited")
    assert events[-4:] == [
        "scheduler-session-exited",
        "client-closed",
        "bot-closed",
        "engine-disposed",
    ]
