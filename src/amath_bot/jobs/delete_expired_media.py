from datetime import datetime

from amath_bot.privacy.media_lifecycle import MediaLifecycle


class DeleteExpiredMediaJob:
    def __init__(self, lifecycle: MediaLifecycle) -> None:
        self._lifecycle = lifecycle

    async def run(self, *, now: datetime | None = None) -> int:
        return await self._lifecycle.expire(now=now)
