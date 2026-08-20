from __future__ import annotations

import http.client
import threading
from urllib.parse import urlencode

import pytest

from enablement_studio.cli import _build_parser, main
from enablement_studio.html_render import _render_critic
from enablement_studio.models import (
    SOURCE_NOTE,
    AlignmentScores,
    LessonCritique,
    Rewrite,
)
from enablement_studio.paths import default_db_path
from enablement_studio.serve import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    bind_exposure_warning,
    make_server,
)
from enablement_studio.store import Store


@pytest.fixture
def server():
    httpd = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def _http(
    server,
    method: str,
    path: str,
    *,
    body: str | None = None,
    follow: bool = True,
    extra_headers: dict[str, str] | None = None,
):
    host, port = server.server_address
    headers = {}
    payload = None
    if body is not None:
        payload = body.encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Content-Length"] = str(len(payload))
    if extra_headers:
        headers.update(extra_headers)
    conn = http.client.HTTPConnection(host, port, timeout=15)
    try:
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        status = response.status
        location = response.getheader("Location")
        text = response.read().decode("utf-8")
        if follow and status in {301, 302, 303, 307, 308} and location:
            conn.request("GET", location)
            response = conn.getresponse()
            status = response.status
            location = response.getheader("Location")
            text = response.read().decode("utf-8")
        return status, text, location
    finally:
        conn.close()


def test_get_home_names_three_products(server) -> None:
    status, body, _location = _http(server, "GET", "/")
    assert status == 200
    assert "Role → Enablement" in body
    assert "Call → Coach" in body
    assert "Lesson critic" in body


def test_post_role_harborline_saves_run(server, job_text: str) -> None:
    posted = urlencode(
        {"product": "role", "text": job_text, "project": "default"}
    )
    status, body, _location = _http(server, "POST", "/", body=posted)
    assert status == 200
    assert "Account Executive" in body
    assert "SKILL GRAPH" in body
    assert "offline" in body
    assert "EXAMPLE DATA" in body
    store = Store(default_db_path())
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0].product.value == "role"
    assert runs[0].engine.value == "offline"
    assert "Account Executive" in runs[0].title


def test_post_empty_text_is_400(server) -> None:
    posted = urlencode({"product": "role", "text": "", "project": "default"})
    status, body, _location = _http(server, "POST", "/", body=posted, follow=False)
    assert status == 400
    assert "Role → Enablement" in body
    assert Store(default_db_path()).list_runs() == []


def test_serve_help_exists(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["serve", "--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert "serve" in out
    assert "127.0.0.1" in out
    assert "8765" in out


def test_serve_defaults_to_loopback() -> None:
    args = _build_parser().parse_args(["serve"])
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8765
    assert DEFAULT_HOST != "0.0.0.0"


def test_get_overflow_run_id_is_404(server) -> None:
    status, body, _location = _http(server, "GET", f"/?run={2**63}")
    assert status == 404
    assert "not found" in body.lower()


def test_foreign_origin_post_is_403(server, job_text: str) -> None:
    posted = urlencode({"product": "role", "text": job_text, "project": "default"})
    status, body, _location = _http(
        server,
        "POST",
        "/",
        body=posted,
        follow=False,
        extra_headers={"Origin": "http://evil.example"},
    )
    assert status == 403
    assert "rejected" in body.lower()
    assert Store(default_db_path()).list_runs() == []


def test_same_origin_post_still_works(server, job_text: str) -> None:
    posted = urlencode({"product": "role", "text": job_text, "project": "default"})
    host, port = server.server_address
    status, body, _location = _http(
        server,
        "POST",
        "/",
        body=posted,
        extra_headers={"Origin": f"http://{host}:{port}"},
    )
    assert status == 200
    assert "Account Executive" in body


def test_zero_bind_warns_loopback_does_not() -> None:
    warning = bind_exposure_warning("0.0.0.0")
    assert warning is not None
    assert "LAN" in warning
    assert "no authentication" in warning or "no auth" in warning
    assert bind_exposure_warning("127.0.0.1") is None


def test_critic_scores_are_escaped() -> None:
    html = _render_critic(
        LessonCritique(
            example_data=False,
            source_note=SOURCE_NOTE,
            lesson_title="t",
            scores=AlignmentScores("<b>9</b>", "<img>", "</li>", "<script>"),
            findings=[],
            rewrite=Rewrite("activity", "r", "p"),
        )
    )
    assert "<b>9</b>" not in html
    assert "&lt;b&gt;9&lt;/b&gt;" in html
    assert "<img>" not in html
    assert "<script>" not in html


def test_get_demo_fills_harborline_fixture(server) -> None:
    status, body, _location = _http(server, "GET", "/?product=role&demo=1")
    assert status == 200
    assert "Harborline Payments" in body
    assert "EXAMPLE DATA" in body
    assert Store(default_db_path()).list_runs() == []
