from __future__ import annotations

import sqlite3
import sys
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from enablement_studio.html_render import render_page
from enablement_studio.models import Product, SavedRun
from enablement_studio.paths import default_db_path, demo_text
from enablement_studio.runs import generate_and_save, output_from_run
from enablement_studio.store import Store

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PROJECT = "default"
MAX_BODY_BYTES = 1_000_000
BIND_EXPOSURE_WARNING = (
    "warning: --host 0.0.0.0 exposes stored job postings and transcripts "
    "on the LAN with no authentication. Default bind is 127.0.0.1."
)


def bind_exposure_warning(host: str) -> str | None:
    if host in {"0.0.0.0", "::"}:
        return BIND_EXPOSURE_WARNING
    return None


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    httpd = make_server(host, port)
    print(f"Enablement Studio local UI  http://{host}:{port}")
    print("Loopback by default. Same SQLite store as the CLI. Ctrl-C to stop.")
    warning = bind_exposure_warning(host)
    if warning:
        print(warning, file=sys.stderr)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def make_server(host: str = DEFAULT_HOST, port: int = 0) -> HTTPServer:
    return HTTPServer((host, port), EnablementHandler)


class EnablementHandler(BaseHTTPRequestHandler):
    server_version = "EnablementStudio/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/":
            self._send(404, _error_page("Not found."))
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        store = Store(default_db_path())
        product = _product_or_none(_first(query, "product")) or Product.ROLE
        project = _first(query, "project") or DEFAULT_PROJECT
        text = ""
        error: str | None = None
        output = None
        run: SavedRun | None = None
        run_raw = _first(query, "run")
        if run_raw:
            try:
                run = store.get_run(int(run_raw))
                output = output_from_run(run)
            except (KeyError, ValueError, OverflowError, sqlite3.Error):
                self._send(404, _error_page(f"run {run_raw} not found"))
                return
            product = run.product
            project = run.project
            text = run.input_text
        elif _first(query, "demo") == "1":
            try:
                text = demo_text(product.value)
            except (FileNotFoundError, ValueError) as exc:
                error = str(exc)
        body = render_page(
            product=product,
            project=project,
            text=text,
            runs=store.list_runs(),
            error=error,
            output=output,
            run=run,
        )
        self._send(200, body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/":
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
        text = fields.get("text", "")
        if not text.strip():
            self._send(400, _form_error("provide text to run", fields=fields))
            return
        product = _product_or_none(fields.get("product", ""))
        if product is None:
            self._send(400, _form_error("unknown product", fields=fields))
            return
        project = fields.get("project", "").strip() or DEFAULT_PROJECT
        store = Store(default_db_path())
        try:
            _output, _engine, run = generate_and_save(
                product, text, project=project, store=store
            )
        except ValueError as exc:
            self._send(400, _form_error(str(exc), fields=fields))
            return
        self._redirect(f"/?{urlencode({'run': str(run.id)})}")

    def log_message(self, fmt: str, *args: Any) -> None:
        return None

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

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()


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


def _form_error(message: str, fields: dict[str, str] | None = None) -> str:
    data = fields or {}
    product = _product_or_none(data.get("product")) or Product.ROLE
    project = (data.get("project") or DEFAULT_PROJECT).strip() or DEFAULT_PROJECT
    store = Store(default_db_path())
    return render_page(
        product=product,
        project=project,
        text=data.get("text", ""),
        runs=store.list_runs(),
        error=message,
    )


def _error_page(message: str) -> str:
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>Enablement Studio</title></head><body><p>{escape(message)}</p>"
        "<p><a href='/'>Back</a></p></body></html>"
    )
