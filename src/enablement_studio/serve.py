from __future__ import annotations

import sqlite3
import sys
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from enablement_studio.html_render import (
    render_page,
    resolve_role_step,
    role_path,
)
from enablement_studio.models import Product, SavedRun
from enablement_studio.paths import default_db_path, demo_text
from enablement_studio.runs import generate_and_save, output_from_run
from enablement_studio.store import Store

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PROJECT = "default"
MAX_BODY_BYTES = 1_000_000
STATIC_ROOT = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}
BIND_EXPOSURE_WARNING = (
    "warning: --host 0.0.0.0 exposes stored job postings and transcripts "
    "on the LAN with no authentication. Default bind is 127.0.0.1."
)
NEXT_NOTE = {
    Product.CALL: "Call is next.",
    Product.CRITIC: "Critic is next.",
}


def bind_exposure_warning(host: str) -> str | None:
    if host in {"0.0.0.0", "::"}:
        return BIND_EXPOSURE_WARNING
    return None


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    httpd = make_server(host, port)
    print(f"Tablework local UI  http://{host}:{port}")
    print("Loopback by default. Same SQLite store as the CLI. Ctrl-C to stop.")
    warning = bind_exposure_warning(host)
    if warning:
        print(warning, file=sys.stderr)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def make_server(host: str = DEFAULT_HOST, port: int = 0) -> HTTPServer:
    httpd = ThreadingHTTPServer((host, port), EnablementHandler)
    httpd.daemon_threads = True
    return httpd


class EnablementHandler(BaseHTTPRequestHandler):
    server_version = "Tablework/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = _normalize_path(parsed.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if path in {"/", "/role"}:
            self._get_studio(query)
            return
        if path.startswith("/static/"):
            self._send_static(path)
            return
        if path == "/call":
            self._redirect("/?next=call", status=302)
            return
        if path == "/critic":
            self._redirect("/?next=critic", status=302)
            return
        self._send(404, _error_page("Not found."))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = _normalize_path(parsed.path)
        if path not in {"/", "/role"}:
            self._send(404, _error_page("Not found."))
            return
        if not _csrf_ok(self):
            self._send(403, _error_page("cross-origin POST rejected."))
            return
        try:
            fields = self._read_form()
        except ValueError as exc:
            self._send(400, _form_error(str(exc)))
            return
        if path == "/":
            product = _product_or_none(fields.get("product", ""))
            if product in {Product.CALL, Product.CRITIC}:
                self._redirect(f"/?next={product.value}", status=302)
                return
        self._post_role(fields)

    def log_message(self, fmt: str, *args: Any) -> None:
        return None

    def _get_studio(self, query: dict[str, list[str]]) -> None:
        product = _product_or_none(_first(query, "product"))
        if product in {Product.CALL, Product.CRITIC}:
            self._redirect(f"/?next={product.value}", status=302)
            return
        notice = None
        next_raw = _first(query, "next")
        if next_raw == Product.CALL.value:
            notice = NEXT_NOTE[Product.CALL]
        elif next_raw == Product.CRITIC.value:
            notice = NEXT_NOTE[Product.CRITIC]
        store = Store(default_db_path())
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
                self._send(404, _error_page(f"run {run_raw} not found"))
                return
            if run.product is not Product.ROLE:
                self._redirect(f"/?next={run.product.value}", status=302)
                return
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
                self._send(404, _error_page(f"run {compare_raw} not found"))
                return
        step = resolve_role_step(_first(query, "step"), run=run, output=output)
        body = render_page(
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
        )
        self._send(200, body)

    def _post_role(self, fields: dict[str, str]) -> None:
        project = fields.get("project", "").strip() or DEFAULT_PROJECT
        action = fields.get("action", "run").strip() or "run"
        text = fields.get("text", "")
        if action == "demo":
            try:
                text = demo_text(Product.ROLE.value)
            except (FileNotFoundError, ValueError) as exc:
                self._send(200, _form_error(str(exc), fields=fields))
                return
        if not text.strip():
            self._send(200, _form_error(_empty_run_message(Product.ROLE), fields=fields))
            return
        store = Store(default_db_path())
        try:
            _output, _engine, run = generate_and_save(
                Product.ROLE,
                text,
                project=project,
                store=store,
                force_offline=action != "llm",
            )
        except ValueError as exc:
            self._send(200, _form_error(str(exc), fields=fields))
            return
        self._redirect(role_path(run.id, "graph"), status=303)

    def _read_form(self) -> dict[str, str]:
        length_raw = self.headers.get("Content-Length", "0")
        try:
            length = int(length_raw)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body is empty or too large")
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}

    def _send(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_static(self, path: str) -> None:
        target = _safe_static_file(path[len("/static/") :])
        if target is None:
            self._send(404, _error_page("Not found."))
            return
        payload = target.read_bytes()
        content_type = STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "public, max-age=31536000")
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str, status: int = 302) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()


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


def _csrf_ok(handler: EnablementHandler) -> bool:
    origin = handler.headers.get("Origin")
    referer = handler.headers.get("Referer")
    if not origin and not referer:
        return True
    host, port = handler.server.server_address
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    if host not in {"0.0.0.0", "::"}:
        allowed_hosts.add(str(host).lower())
    return _url_is_this_server(origin or referer or "", allowed_hosts, int(port))


def _url_is_this_server(url: str, allowed_hosts: set[str], port: int) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").lower()
    if hostname not in allowed_hosts:
        return False
    default_port = 443 if parsed.scheme == "https" else 80
    return (parsed.port or default_port) == port


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


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


def _form_error(message: str, fields: dict[str, str] | None = None) -> str:
    data = fields or {}
    project = (data.get("project") or DEFAULT_PROJECT).strip() or DEFAULT_PROJECT
    store = Store(default_db_path())
    return render_page(
        product=Product.ROLE,
        project=project,
        text=data.get("text", ""),
        runs=store.list_runs(project=project, product=Product.ROLE),
        error=message,
        step="source",
    )


def _error_page(message: str) -> str:
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>Tablework</title></head><body><p>{escape(message)}</p>"
        "<p><a href='/'>Back</a></p></body></html>"
    )
