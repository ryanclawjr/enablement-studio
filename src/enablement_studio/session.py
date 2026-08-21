from __future__ import annotations

import os
import re
import secrets
import tempfile
import time
from pathlib import Path
from typing import Protocol

from enablement_studio.store import Store

SESSION_COOKIE = "es_sid"
SESSION_TTL_SECONDS = 3600
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class SessionBackend(Protocol):
    def get(self, key: str) -> bytes | None: ...

    def put(self, key: str, value: bytes, ttl: int = SESSION_TTL_SECONDS) -> None: ...


class MemoryKV:
    """In-process stand-in for Workers KV: one key per visitor, short TTL."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, float | None]] = {}

    def get(self, key: str) -> bytes | None:
        item = self._data.get(key)
        if item is None:
            return None
        blob, expires_at = item
        if expires_at is not None and expires_at < time.time():
            del self._data[key]
            return None
        return blob

    def put(self, key: str, value: bytes, ttl: int = SESSION_TTL_SECONDS) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._data[key] = (value, expires_at)


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


def parse_session_id(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name != SESSION_COOKIE:
            continue
        candidate = value.strip()
        if _SESSION_RE.fullmatch(candidate):
            return candidate
        return None
    return None


def cookie_header(session_id: str, *, secure: bool) -> str:
    parts = [
        f"{SESSION_COOKIE}={session_id}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={SESSION_TTL_SECONDS}",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def session_key(session_id: str) -> str:
    return f"s:{session_id}"


def open_ephemeral_store(blob: bytes | None = None) -> Store:
    handle, name = tempfile.mkstemp(prefix="enablement-", suffix=".db")
    os.close(handle)
    path = Path(name)
    if blob:
        path.write_bytes(blob)
    return Store(path)


def dump_store(store: Store) -> bytes:
    path = Path(store.path)
    with store.connect() as connection:
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(FULL)")
    return path.read_bytes()


def close_ephemeral_store(store: Store) -> None:
    path = Path(store.path)
    path.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm", "-journal"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def load_session_store(backend: SessionBackend, session_id: str) -> Store:
    return open_ephemeral_store(backend.get(session_key(session_id)))


def save_session_store(backend: SessionBackend, session_id: str, store: Store) -> None:
    backend.put(session_key(session_id), dump_store(store), ttl=SESSION_TTL_SECONDS)
