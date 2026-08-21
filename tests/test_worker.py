from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.parse import urlencode

from enablement_studio.handler import PUBLIC_STATUS_LINE
from enablement_studio.session import SESSION_COOKIE, new_session_id

from test_serve import _assert_primary_object, _assert_source_table, _assert_step_chrome

REPO = Path(__file__).resolve().parents[1]
PUBLIC_HOST = "enablement-studio.ryanclawiii.workers.dev"
PUBLIC_ORIGIN = f"https://{PUBLIC_HOST}"
_WORKER: ModuleType | None = None


class FakeResponse:
    """workers.Response rejects memoryview. Reproduce that here."""

    def __init__(
        self,
        body: object = "",
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        if isinstance(body, memoryview):
            raise TypeError("Unsupported type in Response: memoryview")
        self.body = body
        self.status = status
        self.headers = headers or {}

    async def bytes(self) -> bytes:
        if isinstance(self.body, bytes):
            return self.body
        if isinstance(self.body, str):
            return self.body.encode("utf-8")
        return bytes(self.body)


class FakeRequest:
    def __init__(
        self,
        url: str,
        method: str = "GET",
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.method = method
        self._body = body
        self.headers = {
            str(key).lower(): str(value) for key, value in (headers or {}).items()
        }

    async def bytes(self) -> bytes:
        return bytes(self._body)


class FakeDurableObject:
    pass


class FakeWorkerEntrypoint:
    def __init__(self, ctx: object, env: object) -> None:
        self.ctx = ctx
        self.env = env


class MemoryviewStorage:
    """Durable Object storage.get('db') returns a memoryview of the PUT bytes."""

    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str) -> object:
        value = self._data.get(key)
        if key == "db" and isinstance(value, (bytes, bytearray)):
            return memoryview(bytes(value))
        return value

    async def put(self, key: str, value: object) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)


def _install_workers_stub() -> None:
    workers = ModuleType("workers")
    workers.DurableObject = FakeDurableObject
    workers.Request = FakeRequest
    workers.Response = FakeResponse
    workers.WorkerEntrypoint = FakeWorkerEntrypoint
    sys.modules["workers"] = workers


def _load_worker() -> ModuleType:
    global _WORKER
    if _WORKER is not None:
        return _WORKER
    _install_workers_stub()
    spec = importlib.util.spec_from_file_location(
        "enablement_cf_worker", REPO / "src" / "worker.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _WORKER = module
    return module


def _header(response: FakeResponse, name: str) -> str | None:
    wanted = name.lower()
    for key, value in response.headers.items():
        if key.lower() == wanted:
            return value
    return None


def _text(response: FakeResponse) -> str:
    body = response.body
    if isinstance(body, bytes):
        return body.decode("utf-8")
    return str(body)


def _make_app() -> tuple[Any, MemoryviewStorage]:
    worker = _load_worker()
    storage = MemoryviewStorage()
    vault = worker.SessionVault(SimpleNamespace(storage=storage), None)

    class SessionBinding:
        def idFromName(self, name: str) -> str:
            return name

        def get(self, _name: str) -> object:
            return vault

    env = SimpleNamespace(SESSION=SessionBinding(), STATIC=None)
    return worker.Default(None, env), storage


def test_session_vault_get_does_not_pass_memoryview_into_response() -> None:
    worker = _load_worker()
    storage = MemoryviewStorage()
    vault = worker.SessionVault(SimpleNamespace(storage=storage), None)
    missing = asyncio.run(vault.fetch(FakeRequest("https://session.local/blob")))
    assert missing.status == 404

    payload = b"SQLite format 3\x00session-db"
    put = asyncio.run(
        vault.fetch(
            FakeRequest("https://session.local/blob", method="PUT", body=payload)
        )
    )
    assert put.status == 200
    assert type(storage._data["db"]) is bytes
    assert storage._data["db"] == payload

    got = asyncio.run(vault.fetch(FakeRequest("https://session.local/blob")))
    assert got.status == 200
    assert type(got.body) is bytes
    assert not isinstance(got.body, memoryview)
    assert got.body == payload


def test_graph_after_harborline_does_not_pass_memoryview_into_response() -> None:
    source_app, _source_storage = _make_app()
    source = asyncio.run(
        source_app.fetch(FakeRequest(f"{PUBLIC_ORIGIN}/", headers={"host": PUBLIC_HOST}))
    )
    assert source.status == 200
    _assert_source_table(_text(source), status_line=PUBLIC_STATUS_LINE)

    app, storage = _make_app()
    sid = new_session_id()
    cookie = f"{SESSION_COOKIE}={sid}"
    headers = {
        "host": PUBLIC_HOST,
        "origin": PUBLIC_ORIGIN,
        "referer": f"{PUBLIC_ORIGIN}/",
        "cookie": cookie,
    }
    posted = urlencode({"action": "demo", "product": "role"}).encode("utf-8")
    post = asyncio.run(
        app.fetch(
            FakeRequest(
                f"{PUBLIC_ORIGIN}/",
                method="POST",
                body=posted,
                headers=headers,
            )
        )
    )
    assert post.status == 303
    location = _header(post, "location")
    assert location is not None
    assert "run=1" in location
    assert "step=graph" in location
    assert type(storage._data["db"]) is bytes
    set_cookie = _header(post, "set-cookie")
    assert set_cookie is not None
    assert sid in set_cookie

    graph_url = (
        location if location.startswith("http") else f"{PUBLIC_ORIGIN}{location}"
    )
    graph = asyncio.run(
        app.fetch(
            FakeRequest(
                graph_url,
                headers={"host": PUBLIC_HOST, "cookie": cookie},
            )
        )
    )
    assert graph.status == 200
    assert type(graph.body) is bytes
    assert not isinstance(graph.body, memoryview)
    body = _text(graph)
    _assert_step_chrome(body, "graph")
    assert "path-card" in body
    assert "Harborline Payments" in body
    assert "EXAMPLE DATA" in body
    assert "engine offline" in body
    _assert_primary_object(body, "skill-graph", "outline", "practice", "quiz")

    for step, present, absent in (
        ("objectives", "objectives", ("outline", "practice", "quiz")),
        ("outline", "outline", ("skill-graph", "practice", "quiz")),
        ("practice", "practice", ("outline", "quiz")),
        ("quiz", "quiz", ("outline", "practice")),
    ):
        page = asyncio.run(
            app.fetch(
                FakeRequest(
                    f"{PUBLIC_ORIGIN}/role?run=1&step={step}",
                    headers={"host": PUBLIC_HOST, "cookie": cookie},
                )
            )
        )
        assert page.status == 200
        text = _text(page)
        _assert_step_chrome(text, step)
        _assert_primary_object(text, present, *absent)

    expired = MemoryviewStorage()
    expired._data["db"] = storage._data["db"]
    expired._data["exp"] = int(time.time()) - 1
    worker = _load_worker()
    stale = worker.SessionVault(SimpleNamespace(storage=expired), None)
    gone = asyncio.run(stale.fetch(FakeRequest("https://session.local/blob")))
    assert gone.status == 404
