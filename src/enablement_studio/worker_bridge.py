from __future__ import annotations

import os
from typing import Any
from urllib.parse import parse_qs, urlparse

from enablement_studio.handler import PUBLIC_STATUS_LINE, handle, public_csrf
from enablement_studio.session import (
    SESSION_TTL_SECONDS,
    close_ephemeral_store,
    cookie_header,
    dump_store,
    new_session_id,
    open_ephemeral_store,
    parse_session_id,
    session_key,
)
from enablement_studio.store import Store

LLM_SECRET_NAME = "ENABLEMENT_LLM_API_KEY"


def apply_worker_llm_secret(env: object) -> None:
    key = getattr(env, LLM_SECRET_NAME, None)
    if not key:
        return
    text = str(key).strip()
    if not text:
        return
    os.environ[LLM_SECRET_NAME] = text


def header_map(request: object) -> dict[str, str]:
    headers: dict[str, str] = {}
    raw = getattr(request, "headers", None)
    if raw is None:
        return headers
    items = getattr(raw, "items", None)
    if callable(items):
        for key, value in items():
            headers[str(key).lower()] = str(value)
        return headers
    getter = getattr(raw, "get", None)
    if not callable(getter):
        return headers
    for name in (
        "cookie",
        "origin",
        "referer",
        "host",
        "content-type",
        "content-length",
    ):
        value = getter(name) or getter(name.title())
        if value:
            headers[name] = str(value)
    return headers


def resolve_session_id(headers: dict[str, str]) -> str:
    return parse_session_id(headers.get("cookie")) or new_session_id()


def dispatch_public(
    method: str,
    url: str,
    body: bytes,
    headers: dict[str, str],
    store: Store,
) -> tuple[int, list[tuple[str, str]], bytes]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    return handle(
        method,
        parsed.path or "/",
        query,
        body,
        headers,
        store=store,
        csrf=public_csrf(headers.get("host", "")),
        status_line=PUBLIC_STATUS_LINE,
    )


def run_public_request(
    method: str,
    url: str,
    body: bytes,
    headers: dict[str, str],
    blob: bytes | None,
    session_id: str,
) -> tuple[int, list[tuple[str, str]], bytes, bytes]:
    store = open_ephemeral_store(blob)
    try:
        status, resp_headers, resp_body = dispatch_public(
            method, url, body, headers, store
        )
        dumped = dump_store(store)
    finally:
        close_ephemeral_store(store)
    merged = list(resp_headers)
    merged.append(("Set-Cookie", cookie_header(session_id, secure=True)))
    return status, merged, resp_body, dumped


def kv_options() -> dict[str, Any]:
    return {"expirationTtl": SESSION_TTL_SECONDS}


__all__ = [
    "LLM_SECRET_NAME",
    "apply_worker_llm_secret",
    "dispatch_public",
    "header_map",
    "kv_options",
    "resolve_session_id",
    "run_public_request",
    "session_key",
]
