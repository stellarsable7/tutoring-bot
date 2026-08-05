import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken


class MediaNotFound(FileNotFoundError):
    pass


class MediaExpired(MediaNotFound):
    pass


@dataclass(frozen=True)
class MediaHandle:
    id: str
    path: Path
    expires_at: datetime


class TemporaryMediaStore(Protocol):
    async def put(self, payload: bytes, *, expires_in_hours: int) -> MediaHandle: ...

    async def read(self, handle: MediaHandle) -> bytes: ...

    async def delete(self, handle: MediaHandle) -> None: ...


class EncryptedLocalMediaStore:
    def __init__(
        self,
        root: Path,
        *,
        encryption_key: bytes | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._fernet = Fernet(encryption_key or Fernet.generate_key())
        self.now = now or (lambda: datetime.now(UTC))

    async def put(self, payload: bytes, *, expires_in_hours: int) -> MediaHandle:
        if expires_in_hours < 1:
            raise ValueError("expiry must be at least one hour")
        media_id = secrets.token_urlsafe(24)
        path = self._root / f"{media_id}.enc"
        path.write_bytes(self._fernet.encrypt(payload))
        path.chmod(0o600)
        return MediaHandle(
            id=media_id,
            path=path,
            expires_at=self.now() + timedelta(hours=expires_in_hours),
        )

    async def read(self, handle: MediaHandle) -> bytes:
        if self.now() >= handle.expires_at:
            await self.delete(handle)
            raise MediaExpired(handle.id)
        try:
            encrypted = handle.path.read_bytes()
        except FileNotFoundError as error:
            raise MediaNotFound(handle.id) from error
        try:
            return self._fernet.decrypt(encrypted)
        except InvalidToken as error:
            raise MediaNotFound(f"unreadable media: {handle.id}") from error

    async def delete(self, handle: MediaHandle) -> None:
        handle.path.unlink(missing_ok=True)

