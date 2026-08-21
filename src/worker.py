from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import urlparse

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from enablement_studio.session import SESSION_TTL_SECONDS, session_key
from enablement_studio.worker_bridge import (
    apply_worker_llm_secret,
    blob_headers,
    header_map,
    js_copy_bytes,
    kv_options,
    resolve_session_id,
    run_public_request,
)
from workers import DurableObject, Request, Response, WorkerEntrypoint


class SessionVault(DurableObject):
    """Per-visitor sqlite blob. Not a shared guestbook of pasted JDs."""

    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env

    async def fetch(self, request):
        method = str(getattr(request, "method", "GET")).upper()
        if method == "GET":
            blob = await self.ctx.storage.get("db")
            exp = await self.ctx.storage.get("exp")
            if blob is None:
                return Response("", status=404)
            if exp is not None and int(exp) < int(time.time()):
                await self.ctx.storage.delete("db")
                await self.ctx.storage.delete("exp")
                return Response("", status=404)
            # storage.get("db") is a memoryview; workers.Response rejects that type.
            # Response(bytes) also hands JS a WASM view and corrupts the
            # SQLite header (workerd#6498). Copy onto the JS heap first.
            return Response(js_copy_bytes(bytes(blob)), headers=blob_headers())
        if method == "PUT":
            body = bytes(await request.bytes())
            await self.ctx.storage.put("db", body)
            await self.ctx.storage.put("exp", int(time.time()) + SESSION_TTL_SECONDS)
            return Response("ok")
        return Response("method not allowed", status=405)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        apply_worker_llm_secret(self.env)
        method = str(request.method).upper()
        url = str(request.url)
        headers = header_map(request)
        body = b""
        if method == "POST":
            body = bytes(await request.bytes())
        session_id = resolve_session_id(headers)
        blob = await _load_blob(self.env, session_id)
        status, resp_headers, resp_body, dumped = run_public_request(
            method, url, body, headers, blob, session_id
        )
        await _save_blob(self.env, session_id, dumped)
        path = urlparse(url).path or "/"
        static = getattr(self.env, "STATIC", None)
        if status == 404 and path.startswith("/static/") and static is not None:
            return await static.fetch(f"https://assets.local{path}")
        return Response(
            js_copy_bytes(resp_body),
            status=status,
            headers={name: value for name, value in resp_headers},
        )


async def _load_blob(env, session_id: str) -> bytes | None:
    kv = getattr(env, "SESSIONS", None)
    if kv is not None:
        data = await kv.get(session_key(session_id), "arrayBuffer")
        if data is None:
            return None
        return bytes(data)
    session = getattr(env, "SESSION", None)
    if session is None:
        return None
    stub = session.get(session.idFromName(session_id))
    response = await stub.fetch(Request("https://session.local/blob"))
    if int(response.status) == 404:
        return None
    return bytes(await response.bytes())


async def _save_blob(env, session_id: str, blob: bytes) -> None:
    kv = getattr(env, "SESSIONS", None)
    if kv is not None:
        await kv.put(session_key(session_id), js_copy_bytes(blob), kv_options())
        return
    session = getattr(env, "SESSION", None)
    if session is None:
        return
    stub = session.get(session.idFromName(session_id))
    await stub.fetch(
        Request(
            "https://session.local/blob",
            method="PUT",
            body=js_copy_bytes(blob),
            headers=blob_headers(),
        )
    )
