from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import parse_qs, urlparse

from enablement_studio.html_render import (
    LOCAL_STATUS_LINE,
    render_page,
    resolve_role_step,
    role_path,
)
from enablement_studio.models import Product, SavedRun
from enablement_studio.paths import demo_text
from enablement_studio.runs import generate_and_save, output_from_run
from enablement_studio.store import Store

DEFAULT_PROJECT = "default"
MAX_BODY_BYTES = 1_000_000
PUBLIC_STATUS_LINE = "public · offline"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}
NEXT_NOTE = {
    Product.CALL: "Call is next.",
    Product.CRITIC: "Critic is next.",
}

HeaderList = list[tuple[str, str]]
HandlerResult = tuple[int, HeaderList, bytes]


@dataclass(frozen=True)
class CsrfPolicy:
    allowed_hosts: frozenset[str]
    port: int | None = None


def local_csrf(host: str, port: int) -> CsrfPolicy:
    allowed = {"127.0.0.1", "localhost", "::1"}
    if host not in {"0.0.0.0", "::"}:
        allowed.add(str(host).lower())
    return CsrfPolicy(allowed_hosts=frozenset(allowed), port=int(port))


def public_csrf(host_header: str) -> CsrfPolicy:
    hostname = _hostname_from_host_header(host_header)
    allowed = {hostname} if hostname else set()
    return CsrfPolicy(allowed_hosts=frozenset(allowed), port=None)


def handle(
    method: str,
    path: str,
    query: Mapping[str, Sequence[str]],
    body: bytes,
    headers: Mapping[str, str],
    *,
    store: Store,
    csrf: CsrfPolicy,
    status_line: str = LOCAL_STATUS_LINE,
) -> HandlerResult:
    method_name = method.upper()
    normalized = _normalize_path(path)
    query_map = {key: [str(value) for value in values] for key, values in query.items()}
    header_map = {str(key).lower(): str(value) for key, value in headers.items()}
    if method_name == "GET":
        return _get(normalized, query_map, store, status_line)
    if method_name == "POST":
        if not _csrf_ok(header_map, csrf):
            return _simple(403, _error_page("cross-origin POST rejected."))
        if len(body) > MAX_BODY_BYTES:
            return _studio_error(
                store,
                "request body is empty or too large",
                {},
                status_line,
                status=400,
            )
        return _post(normalized, body, store, status_line)
    return _simple(405, _error_page("method not allowed."))


def _get(
    path: str,
    query: dict[str, list[str]],
    store: Store,
    status_line: str,
) -> HandlerResult:
    if path in {"/", "/role"}:
        return _get_studio(query, store, status_line)
    if path.startswith("/static/"):
        return _send_static(path)
    if path == "/call":
        return _redirect("/?next=call", status=302)
    if path == "/critic":
        return _redirect("/?next=critic", status=302)
    return _simple(404, _error_page("Not found."))


def _post(
    path: str,
    body: bytes,
    store: Store,
    status_line: str,
) -> HandlerResult:
    if path not in {"/", "/role"}:
        return _simple(404, _error_page("Not found."))
    try:
        fields = _parse_form(body)
    except ValueError as exc:
        return _studio_error(store, str(exc), {}, status_line, status=400)
    if path == "/":
        product = _product_or_none(fields.get("product", ""))
        if product in {Product.CALL, Product.CRITIC}:
            return _redirect(f"/?next={product.value}", status=302)
    return _post_role(fields, store, status_line)


def _get_studio(
    query: dict[str, list[str]],
    store: Store,
    status_line: str,
) -> HandlerResult:
    product = _product_or_none(_first(query, "product"))
    if product in {Product.CALL, Product.CRITIC}:
        return _redirect(f"/?next={product.value}", status=302)
    notice = None
    next_raw = _first(query, "next")
    if next_raw == Product.CALL.value:
        notice = NEXT_NOTE[Product.CALL]
    elif next_raw == Product.CRITIC.value:
        notice = NEXT_NOTE[Product.CRITIC]
    project = _first(query, "project") or DEFAULT_PROJECT
    text = ""
    error: str | None = None
    output = None
    run: SavedRun | None = None
    compare_run: SavedRun | None = None
    compare_output = None
    run_raw = _first(query, "run")
    compare_raw = _first(query, "compare")
    if run_raw:
        try:
            run = store.get_run(int(run_raw))
            output = output_from_run(run)
        except (KeyError, ValueError, OverflowError, sqlite3.Error):
            return _simple(404, _error_page(f"run {run_raw} not found"))
        if run.product is not Product.ROLE:
            return _redirect(f"/?next={run.product.value}", status=302)
        project = run.project
        text = run.input_text
    elif _first(query, "demo") == "1":
        try:
            text = demo_text(Product.ROLE.value)
        except (FileNotFoundError, ValueError) as exc:
            error = str(exc)
    if compare_raw:
        try:
            compare_run = store.get_run(int(compare_raw))
            compare_output = output_from_run(compare_run)
        except (KeyError, ValueError, OverflowError, sqlite3.Error):
            return _simple(404, _error_page(f"run {compare_raw} not found"))
    step = resolve_role_step(_first(query, "step"), run=run, output=output)
    page = render_page(
        product=Product.ROLE,
        project=project,
        text=text,
        runs=store.list_runs(project=project, product=Product.ROLE),
        error=error,
        output=output,
        run=run,
        compare_output=compare_output,
        compare_run=compare_run,
        step=step,
        notice=notice,
        status_line=status_line,
    )
    return _html(200, page)


def _post_role(
    fields: dict[str, str],
    store: Store,
    status_line: str,
) -> HandlerResult:
    project = fields.get("project", "").strip() or DEFAULT_PROJECT
    action = fields.get("action", "run").strip() or "run"
    text = fields.get("text", "")
    if action == "demo":
        try:
            text = demo_text(Product.ROLE.value)
        except (FileNotFoundError, ValueError) as exc:
            return _studio_error(store, str(exc), fields, status_line, status=200)
    if not text.strip():
        return _studio_error(
            store,
            _empty_run_message(Product.ROLE),
            fields,
            status_line,
            status=200,
        )
    try:
        _output, _engine, run = generate_and_save(
            Product.ROLE,
            text,
            project=project,
            store=store,
            force_offline=action != "llm",
        )
    except ValueError as exc:
        return _studio_error(store, str(exc), fields, status_line, status=200)
    return _redirect(role_path(run.id, "graph"), status=303)


def _parse_form(body: bytes) -> dict[str, str]:
    raw = body.decode("utf-8")
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _send_static(path: str) -> HandlerResult:
    target = _safe_static_file(path[len("/static/") :])
    if target is None:
        return _simple(404, _error_page("Not found."))
    payload = target.read_bytes()
    content_type = STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return (
        200,
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(payload))),
            ("Cache-Control", "public, max-age=31536000"),
        ],
        payload,
    )


def _html(status: int, body: str) -> HandlerResult:
    payload = body.encode("utf-8")
    return (
        status,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(payload))),
            ("Cache-Control", "no-store"),
        ],
        payload,
    )


def _simple(status: int, body: str) -> HandlerResult:
    return _html(status, body)


def _redirect(location: str, status: int = 302) -> HandlerResult:
    return (
        status,
        [
            ("Location", location),
            ("Content-Length", "0"),
        ],
        b"",
    )


def form_error(
    store: Store,
    message: str,
    fields: dict[str, str] | None = None,
    *,
    status: int,
    status_line: str = LOCAL_STATUS_LINE,
) -> HandlerResult:
    return _studio_error(
        store,
        message,
        fields or {},
        status_line,
        status=status,
    )


def _studio_error(
    store: Store,
    message: str,
    fields: dict[str, str],
    status_line: str,
    *,
    status: int,
) -> HandlerResult:
    project = (fields.get("project") or DEFAULT_PROJECT).strip() or DEFAULT_PROJECT
    page = render_page(
        product=Product.ROLE,
        project=project,
        text=fields.get("text", ""),
        runs=store.list_runs(project=project, product=Product.ROLE),
        error=message,
        step="source",
        status_line=status_line,
    )
    return _html(status, page)


def _normalize_path(path: str) -> str:
    if path != "/" and path.endswith("/"):
        return path.rstrip("/") or "/"
    return path or "/"


def _safe_static_file(rel: str) -> Path | None:
    if not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel:
        return None
    parts = Path(rel).parts
    if not parts or any(part in {"", ".."} for part in parts):
        return None
    root = STATIC_ROOT.resolve()
    candidate = (root / Path(*parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    if candidate.suffix.lower() not in STATIC_TYPES:
        return None
    return candidate


def _csrf_ok(headers: Mapping[str, str], policy: CsrfPolicy) -> bool:
    origin = headers.get("origin") or headers.get("referer")
    if not origin:
        return True
    return _url_is_allowed(origin, policy)


def _url_is_allowed(url: str, policy: CsrfPolicy) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").lower()
    if hostname not in policy.allowed_hosts:
        return False
    if policy.port is None:
        return True
    default_port = 443 if parsed.scheme == "https" else 80
    return (parsed.port or default_port) == policy.port


def _hostname_from_host_header(host_header: str) -> str:
    host = (host_header or "").strip()
    if not host:
        return ""
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            return host.lower()
        return host[1:end].lower()
    return host.split(":")[0].lower()


def _first(query: Mapping[str, Sequence[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return str(values[0])


def _product_or_none(value: str | None) -> Product | None:
    if not value:
        return None
    try:
        return Product(value)
    except ValueError:
        return None


def _empty_run_message(product: Product) -> str:
    if product is Product.ROLE:
        return "Source is empty. Paste a job or SOP, or Run Harborline."
    if product is Product.CALL:
        return "Source is empty. Paste a transcript, or Run Harborline."
    if product is Product.CRITIC:
        return "Source is empty. Paste an outline or storyboard, or Run Harborline."
    never: Product = product
    raise ValueError(f"unsupported product: {never}")


def _error_page(message: str) -> str:
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>Tablework</title></head><body><p>{escape(message)}</p>"
        "<p><a href='/'>Back</a></p></body></html>"
    )
