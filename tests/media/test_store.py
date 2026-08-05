from datetime import UTC, datetime, timedelta

import pytest

from amath_bot.media.store import EncryptedLocalMediaStore, MediaExpired, MediaNotFound


async def test_store_encrypts_and_deletes_media(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = EncryptedLocalMediaStore(tmp_path)
    sample_jpeg = b"not-plaintext-student-media"

    handle = await store.put(sample_jpeg, expires_in_hours=24)

    assert await store.read(handle) == sample_jpeg
    assert sample_jpeg not in handle.path.read_bytes()
    await store.delete(handle)
    with pytest.raises(MediaNotFound):
        await store.read(handle)


async def test_expired_media_is_deleted_on_read(tmp_path) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 8, 5, tzinfo=UTC)
    store = EncryptedLocalMediaStore(tmp_path, now=lambda: now)
    handle = await store.put(b"student-media", expires_in_hours=1)
    store.now = lambda: now + timedelta(hours=2)

    with pytest.raises(MediaExpired):
        await store.read(handle)
    assert not handle.path.exists()
