from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from enablement_studio.handler import (
    MAX_BODY_BYTES,
    CsrfPolicy,
    form_error,
    handle,
    local_csrf,
)
from enablement_studio.html_render import LOCAL_STATUS_LINE
from enablement_studio.paths import default_db_path
from enablement_studio.store import Store

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
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
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def log_message(self, fmt: str, *args: Any) -> None:
        return None

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        store = Store(default_db_path())
        if self.command == "POST":
            try:
                body = self._read_body()
            except ValueError as exc:
                status, headers, payload = form_error(
                    store,
                    str(exc),
                    status=400,
                    status_line=LOCAL_STATUS_LINE,
                )
                self._write(status, headers, payload)
                return
        else:
            body = b""
        headers = {key.lower(): value for key, value in self.headers.items()}
        status, resp_headers, resp_body = handle(
            self.command,
            parsed.path,
            parse_qs(parsed.query, keep_blank_values=True),
            body,
            headers,
            store=store,
            csrf=self._csrf_policy(),
            status_line=LOCAL_STATUS_LINE,
        )
        self._write(status, resp_headers, resp_body)

    def _read_body(self) -> bytes:
        length_raw = self.headers.get("Content-Length", "0")
        try:
            length = int(length_raw)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body is empty or too large")
        return self.rfile.read(length)

    def _csrf_policy(self) -> CsrfPolicy:
        host, port = self.server.server_address
        return local_csrf(str(host), int(port))

    def _write(
        self,
        status: int,
        headers: list[tuple[str, str]],
        body: bytes,
    ) -> None:
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)
