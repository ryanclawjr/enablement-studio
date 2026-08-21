from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from enablement_studio.handler import (
    PUBLIC_STATUS_LINE,
    handle,
    public_csrf,
)
from enablement_studio.paths import default_db_path
from enablement_studio.session import (
    MemoryKV,
    close_ephemeral_store,
    load_session_store,
    new_session_id,
    save_session_store,
    session_key,
)
from enablement_studio.store import Store
from enablement_studio.worker_bridge import (
    LLM_SECRET_NAME,
    apply_worker_llm_secret,
    run_public_request,
)

from test_serve import _assert_source_table, _assert_step_chrome, _assert_primary_object

REPO = Path(__file__).resolve().parents[1]


def _call(
    method: str,
    path: str,
    *,
    store: Store,
    body: str | bytes | None = None,
    headers: dict[str, str] | None = None,
    follow: bool = True,
    status_line: str = PUBLIC_STATUS_LINE,
    host: str = "enablement-studio.pages.dev",
):
    parsed = urlparse(path)
    query = parse_qs(parsed.query, keep_blank_values=True)
    raw = b""
    if isinstance(body, str):
        raw = body.encode("utf-8")
    elif body is not None:
        raw = body
    status, resp_headers, payload = handle(
        method,
        parsed.path or "/",
        query,
        raw,
        headers or {},
        store=store,
        csrf=public_csrf(host),
        status_line=status_line,
    )
    header_map = {name.lower(): value for name, value in resp_headers}
    location = header_map.get("location")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if follow and status in {301, 302, 303, 307, 308} and location:
        return _call(
            "GET",
            location,
            store=store,
            follow=False,
            status_line=status_line,
            host=host,
        )
    return status, text, location, resp_headers, payload


def test_public_handler_get_home_is_role_source(tmp_path: Path) -> None:
    store = Store(tmp_path / "public.db")
    status, body, location, _headers, _payload = _call("GET", "/", store=store)
    assert status == 200
    assert location is None
    _assert_source_table(body, status_line=PUBLIC_STATUS_LINE)
    assert "public · offline" in body
    assert "<textarea" in body
    assert "Run Harborline" in body
    assert 'class="collection"' in body
    assert "path-card" in body
    assert body.count("path-card") >= 6
    assert "Get Lifetime Access" not in body
    assert "Sign in" not in body
    assert 'class="door' not in body


def test_public_handler_serves_instrument_sans(tmp_path: Path) -> None:
    store = Store(tmp_path / "public.db")
    status, _text, _location, headers, payload = _call(
        "GET",
        "/static/fonts/instrument-sans-latin-400-normal.woff",
        store=store,
        follow=False,
    )
    assert status == 200
    header_map = {name.lower(): value for name, value in headers}
    assert "font/woff" in header_map["content-type"]
    assert payload.startswith(b"wOFF")
    status, _text, _location, _headers, _payload = _call(
        "GET", "/static/../engine.py", store=store, follow=False
    )
    assert status == 404


def test_public_harborline_walk_is_offline_generate(
    tmp_path: Path, job_text: str
) -> None:
    store = Store(tmp_path / "public.db")
    posted = urlencode({"product": "role", "text": job_text, "project": "default"})
    status, _body, location, _headers, _payload = _call(
        "POST", "/role", store=store, body=posted, follow=False
    )
    assert status == 303
    assert location is not None
    assert "step=graph" in location
    status, body, _followed, _headers, _payload = _call("GET", location, store=store)
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert "Account Executive" in body
    assert "Harborline Payments" in body
    assert "EXAMPLE DATA" in body
    assert "engine offline" in body
    _assert_primary_object(body, "skill-graph", "outline", "practice", "quiz")
    assert store.list_runs()[0].engine.value == "offline"
    assert default_db_path() != store.path


def test_public_sessions_are_not_a_guestbook(job_text: str) -> None:
    kv = MemoryKV()
    alice = new_session_id()
    bob = new_session_id()
    posted = urlencode({"product": "role", "text": job_text, "project": "default"})

    alice_store = load_session_store(kv, alice)
    try:
        status, body, _location, _headers, _payload = _call(
            "POST", "/role", store=alice_store, body=posted
        )
        assert status == 200
        assert "Harborline Payments" in body
        save_session_store(kv, alice, alice_store)
    finally:
        close_ephemeral_store(alice_store)

    bob_store = load_session_store(kv, bob)
    try:
        status, body, _location, _headers, _payload = _call("GET", "/", store=bob_store)
        assert status == 200
        _assert_source_table(body, status_line=PUBLIC_STATUS_LINE)
        assert "Harborline Payments" not in body
        assert "weekend cash-flow" not in body
        assert bob_store.list_runs() == []
    finally:
        close_ephemeral_store(bob_store)

    alice_again = load_session_store(kv, alice)
    try:
        status, body, _location, _headers, _payload = _call("GET", "/", store=alice_again)
        assert status == 200
        assert alice_again.list_runs()
        assert "Harborline Payments" in alice_again.list_runs()[0].input_text
    finally:
        close_ephemeral_store(alice_again)


def test_session_kv_ttl_drops_visitor_paste(job_text: str) -> None:
    kv = MemoryKV()
    sid = new_session_id()
    store = load_session_store(kv, sid)
    try:
        _call(
            "POST",
            "/role",
            store=store,
            body=urlencode({"product": "role", "text": job_text, "project": "default"}),
        )
        save_session_store(kv, sid, store)
    finally:
        close_ephemeral_store(store)
    assert kv.get(session_key(sid)) is not None
    kv.put(session_key(sid), kv.get(session_key(sid)) or b"", ttl=-1)
    assert kv.get(session_key(sid)) is None


def test_run_public_request_sets_session_cookie(tmp_path: Path) -> None:
    sid = new_session_id()
    status, headers, body, dumped = run_public_request(
        "GET",
        "https://enablement-studio.pages.dev/",
        b"",
        {"host": "enablement-studio.pages.dev"},
        None,
        sid,
    )
    assert status == 200
    header_map = {name.lower(): value for name, value in headers}
    assert "es_sid=" in header_map["set-cookie"]
    assert sid in header_map["set-cookie"]
    assert "Secure" in header_map["set-cookie"]
    text = body.decode("utf-8")
    _assert_source_table(text, status_line=PUBLIC_STATUS_LINE)
    assert dumped


def test_public_csrf_rejects_foreign_origin(tmp_path: Path, job_text: str) -> None:
    store = Store(tmp_path / "public.db")
    posted = urlencode({"product": "role", "text": job_text, "project": "default"})
    status, body, _location, _headers, _payload = _call(
        "POST",
        "/role",
        store=store,
        body=posted,
        headers={"origin": "http://evil.example"},
        follow=False,
    )
    assert status == 403
    assert "rejected" in body.lower()
    assert store.list_runs() == []


def test_apply_worker_llm_secret_uses_env_only(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(LLM_SECRET_NAME, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".enablement_llm.env").write_text("ENABLEMENT_LLM_API_KEY=from-file\n")
    monkeypatch.setenv("HOME", str(home))

    class Empty:
        pass

    apply_worker_llm_secret(Empty())
    assert LLM_SECRET_NAME not in os.environ

    class Secret:
        ENABLEMENT_LLM_API_KEY = "  worker-secret  "

    apply_worker_llm_secret(Secret())
    assert os.environ[LLM_SECRET_NAME] == "worker-secret"


def test_worker_entry_and_wrangler_are_public_host_shape() -> None:
    worker = (REPO / "src/worker.py").read_text(encoding="utf-8")
    wrangler = (REPO / "wrangler.toml").read_text(encoding="utf-8")
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "from workers import WorkerEntrypoint, Response" in worker or (
        "from workers import DurableObject, Request, Response, WorkerEntrypoint"
        in worker
    )
    assert "class Default(WorkerEntrypoint)" in worker
    assert "enablement-studio" in wrangler
    assert 'compatibility_flags = ["python_workers"]' in wrangler
    assert "main = " in wrangler and "src/worker.py" in wrangler
    assert "[vars]" not in wrangler
    assert "sk-" not in wrangler
    assert "enablement_llm.env" not in worker
    assert "Path.home()" not in worker
    assert 'dependencies = []' in pyproject
    assert "SessionVault" in worker
    assert "SessionVault" in wrangler


def test_handler_does_not_read_home_llm_env() -> None:
    handler = (REPO / "src/enablement_studio/handler.py").read_text(encoding="utf-8")
    engine = (REPO / "src/enablement_studio/engine.py").read_text(encoding="utf-8")
    worker = (REPO / "src/worker.py").read_text(encoding="utf-8")
    for source in (handler, engine, worker):
        assert "enablement_llm.env" not in source
        assert ".enablement_llm" not in source
