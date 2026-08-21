from __future__ import annotations

import http.client
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request

import pytest

from enablement_studio.cli import _build_parser, main
from enablement_studio.html_render import _render_critic, render_page, resolve_role_step
from enablement_studio.models import (
    SOURCE_NOTE,
    AlignmentScores,
    LessonCritique,
    Product,
    Rewrite,
)
from enablement_studio.paths import default_db_path, find_fixture
from enablement_studio.role.title_swap import apply_title_swap_validity
from enablement_studio.runs import generate_and_save
from enablement_studio.serve import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    bind_exposure_warning,
    make_server,
)
from enablement_studio.store import Store

from canned_ae_template import canned_ae_template_role


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


def _assert_step_chrome(body: str, step: str) -> None:
    assert f'data-step="{step}"' in body
    assert 'aria-label="Role path"' in body
    assert "Source" in body
    assert "Graph" in body
    assert "Objectives" in body
    assert "Outline" in body
    assert "Practice" in body
    assert "Quiz" in body
    assert 'aria-current="step"' in body
    assert 'type="radio"' not in body
    assert "path-card" in body
    assert body.count("path-card") >= 6
    current_at = body.index('aria-current="step"')
    current_chunk = body[max(0, current_at - 80) : current_at + 280]
    labels = {
        "source": "Source",
        "graph": "Graph",
        "objectives": "Objectives",
        "outline": "Outline",
        "practice": "Practice",
        "quiz": "Quiz",
    }
    assert labels[step] in current_chunk


def _assert_primary_object(body: str, present: str, *absent: str) -> None:
    assert f'class="{present}' in body
    for name in absent:
        assert f'class="{name} object"' not in body


def _assert_source_table(
    body: str,
    *,
    status_line: str = "this machine · 127.0.0.1 · offline",
) -> None:
    assert "Tablework" in body
    assert "<h1" in body
    h1_start = body.index("<h1")
    h1 = body[h1_start : body.index("</h1>", h1_start)]
    assert "Tablework" in h1
    assert "Enablement Studio" not in h1
    assert "<textarea" in body
    assert 'name="text"' in body
    assert "Run Harborline" in body
    assert "EXAMPLE DATA" in body
    assert 'name="project"' in body
    assert 'name="action" value="run"' in body
    assert 'name="action" value="llm"' in body
    _assert_step_chrome(body, "source")
    assert 'class="door' not in body
    assert status_line in body
    if status_line != "this machine · 127.0.0.1 · offline":
        assert "this machine · 127.0.0.1 · offline" not in body
    else:
        assert body.count("this machine") == 1
    assert "Board is empty" not in body
    assert 'type="radio"' not in body
    assert "onboarding buddy" not in body.lower()
    assert "job → skill graph → 30-minute module" not in body
    assert 'class="outline object"' not in body
    assert "SOURCE" in body
    assert "Paste a job" in body
    assert "Skills from the work" in body
    assert 'class="collection"' in body
    assert "version-dots" in body
    assert "document-sheet" in body
    assert "#16161d" in body
    assert "#1d1d25" in body
    assert "#ffe52f" in body
    assert "#f6f6f6" in body
    assert "#757575" in body
    assert "#191a1d" in body
    assert "rgba(236, 236, 236, 0.08)" in body
    assert "rgba(109, 112, 130, 0.21)" in body
    assert "rgba(132, 132, 132, 0.25)" in body
    assert "0 20px 50px rgba(255, 242, 80, 0.34)" in body
    assert "400ms ease" in body
    assert "80px 80px" in body
    assert "gap: 16px" in body
    assert "Instrument Sans" in body
    assert "/static/fonts/instrument-sans-latin-400-normal.woff" in body
    assert "translateY(-2px)" not in body
    assert "translateY(-1px)" not in body
    assert "font: 13px/1.45" not in body
    assert "13px/1.45" not in body
    assert "system-ui" not in body
    assert "Outfit" not in body
    assert "Syne" not in body
    assert "#0E0E12" not in body
    assert "BGG.svg" not in body
    assert "<canvas" not in body
    assert "minmax(0, 42rem) 12.5rem" not in body
    assert 'aside class="versions"' not in body
    assert 'class="path-step' not in body
    assert "fonts.googleapis.com" not in body
    assert "fonts.gstatic.com" not in body
    assert "#0d0d0d" not in body
    assert "#fffd63" not in body
    assert "#f4f4f2" not in body
    assert "#3d5a80" not in body
    assert "Get Lifetime Access" not in body
    assert "Sign in" not in body


def test_get_home_is_role_source(server) -> None:
    status, body, _location = _http(server, "GET", "/")
    assert status == 200
    _assert_source_table(body)


def test_local_fonts_are_served(server) -> None:
    status, body, _location = _http(server, "GET", "/")
    assert status == 200
    assert "fonts.googleapis.com" not in body
    host, port = server.server_address
    conn = http.client.HTTPConnection(host, port, timeout=15)
    try:
        conn.request("GET", "/static/fonts/instrument-sans-latin-400-normal.woff")
        response = conn.getresponse()
        assert response.status == 200
        assert "font/woff" in (response.getheader("Content-Type") or "")
        payload = response.read()
        assert payload.startswith(b"wOFF")
    finally:
        conn.close()
    status, _body, _location = _http(server, "GET", "/static/../engine.py")
    assert status == 404


def test_get_role_is_same_source_table(server) -> None:
    status, _body, location = _http(server, "GET", "/role", follow=False)
    assert status in {200, 302}
    if status == 302:
        assert location == "/" or (location or "").startswith("/?")
    status, body, _location = _http(server, "GET", "/role")
    assert status == 200
    _assert_source_table(body)


def test_old_product_query_stays_on_table(server) -> None:
    status, body, location = _http(server, "GET", "/?product=role", follow=False)
    assert status == 200
    assert location is None
    _assert_source_table(body)
    status, _body, location = _http(server, "GET", "/?product=call", follow=False)
    assert status == 302
    assert location == "/?next=call"
    status, body, _location = _http(server, "GET", "/?product=call")
    assert status == 200
    _assert_source_table(body)
    assert "Call is next." in body
    status, _body, location = _http(server, "GET", "/?product=critic", follow=False)
    assert status == 302
    assert location == "/?next=critic"


def test_call_critic_next_keeps_the_table(server) -> None:
    status, _body, location = _http(server, "GET", "/call", follow=False)
    assert status == 302
    assert location == "/?next=call"
    status, body, _location = _http(server, "GET", "/critic")
    assert status == 200
    _assert_source_table(body)
    assert "Critic is next." in body
    assert 'class="door' not in body


def test_make_server_is_threaded() -> None:
    httpd = make_server("127.0.0.1", 0)
    try:
        assert isinstance(httpd, ThreadingHTTPServer)
        assert httpd.daemon_threads is True
    finally:
        httpd.server_close()


def test_post_role_harborline_lands_on_graph(server, job_text: str) -> None:
    posted = urlencode(
        {"product": "role", "text": job_text, "project": "default"}
    )
    status, _body, location = _http(server, "POST", "/role", body=posted, follow=False)
    assert status == 303
    assert location is not None
    assert location.startswith("/role?")
    assert "run=" in location
    assert "step=graph" in location
    status, body, _followed = _http(server, "GET", location)
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert "Account Executive" in body
    assert "offline" in body
    assert "EXAMPLE DATA" in body
    store = Store(default_db_path())
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0].product.value == "role"
    assert runs[0].engine.value == "offline"
    assert "Account Executive" in runs[0].title
    assert "Harborline Payments" in body
    assert "weekend cash-flow" in body
    assert 'data-family="seller"' in body
    _assert_primary_object(body, "skill-graph", "outline", "practice", "quiz")
    assert "Invalid module" not in body
    assert f"run={runs[0].id}" in body
    assert "step=objectives" in body


def test_post_empty_text_stays_on_source(server) -> None:
    posted = urlencode({"product": "role", "text": "", "project": "default"})
    status, body, _location = _http(server, "POST", "/role", body=posted, follow=False)
    assert status == 200
    _assert_step_chrome(body, "source")
    assert "Source is empty. Paste a job or SOP, or Run Harborline." in body
    assert "Run Harborline" in body
    assert "EXAMPLE DATA" in body
    assert "Board is empty" not in body
    assert 'type="radio"' not in body
    assert "<!DOCTYPE html>" in body
    assert Store(default_db_path()).list_runs() == []


def test_run_with_slow_llm_env_returns_offline_board(
    server, job_text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow_urlopen(_request: Request, timeout: object = None) -> None:
        time.sleep(25)
        raise TimeoutError("LLM should not run on studio Run")

    monkeypatch.setenv("ENABLEMENT_LLM_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        "enablement_studio.engine.urllib.request.urlopen", slow_urlopen
    )
    posted = urlencode(
        {"product": "role", "text": job_text, "project": "default", "action": "run"}
    )
    started = time.monotonic()
    status, body, _location = _http(server, "POST", "/role", body=posted)
    elapsed = time.monotonic() - started
    assert elapsed < 3
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert "Account Executive" in body
    assert "engine offline" in body
    _assert_primary_object(body, "skill-graph", "outline", "practice", "quiz")
    get_started = time.monotonic()
    get_status, home, _location = _http(server, "GET", "/")
    assert time.monotonic() - get_started < 2
    assert get_status == 200
    assert "Tablework" in home
    assert "<textarea" in home
    assert 'class="door' not in home


def test_in_flight_llm_does_not_block_get(
    server, job_text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()

    def blocking_urlopen(_request: Request, timeout: object = None) -> None:
        started.set()
        if not release.wait(timeout=10):
            raise TimeoutError("test did not release LLM")
        raise TimeoutError("released")

    monkeypatch.setenv("ENABLEMENT_LLM_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        "enablement_studio.engine.urllib.request.urlopen", blocking_urlopen
    )
    posted = urlencode(
        {"product": "role", "text": job_text, "project": "default", "action": "llm"}
    )
    result: dict[str, object] = {}

    def do_post() -> None:
        result["post"] = _http(server, "POST", "/role", body=posted)

    worker = threading.Thread(target=do_post)
    worker.start()
    assert started.wait(timeout=3)
    get_started = time.monotonic()
    status, body, _location = _http(server, "GET", "/")
    assert time.monotonic() - get_started < 2
    assert status == 200
    assert "Tablework" in body
    assert "Board is empty" not in body
    role_status, role_body, _role_loc = _http(server, "GET", "/role")
    assert role_status == 200
    _assert_step_chrome(role_body, "source")
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    posted_result = result["post"]
    assert isinstance(posted_result, tuple)
    post_status, post_body, _post_location = posted_result
    assert post_status == 200
    _assert_step_chrome(post_body, "graph")
    assert "engine offline" in post_body


def test_harborline_demo_redirects_to_graph_step(server) -> None:
    posted = urlencode(
        {"product": "role", "text": "", "project": "default", "action": "demo"}
    )
    status, _body, location = _http(server, "POST", "/role", body=posted, follow=False)
    assert status == 303
    assert location is not None
    assert "step=graph" in location
    status, body, _followed = _http(server, "GET", location)
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert "Account Executive" in body
    assert "Harborline Payments" in body
    assert "EXAMPLE DATA" in body
    assert "engine offline" in body
    _assert_primary_object(body, "skill-graph", "outline", "practice", "quiz")
    assert 'type="radio"' not in body
    store = Store(default_db_path())
    assert len(store.list_runs()) == 1
    assert store.list_runs()[0].engine.value == "offline"


def test_continue_links_walk_role_steps(server) -> None:
    posted = urlencode(
        {"product": "role", "text": "", "project": "default", "action": "demo"}
    )
    status, body, _location = _http(server, "POST", "/role", body=posted)
    assert status == 200
    run = Store(default_db_path()).list_runs()[0]
    assert f"run={run.id}" in body
    assert "step=objectives" in body
    steps = (
        ("objectives", "objectives", ("outline", "practice", "quiz")),
        ("outline", "outline", ("skill-graph", "practice", "quiz")),
        ("practice", "practice", ("outline", "quiz")),
        ("quiz", "quiz", ("outline", "practice")),
    )
    for step, present, absent in steps:
        status, body, _location = _http(
            server, "GET", f"/role?run={run.id}&step={step}"
        )
        assert status == 200
        _assert_step_chrome(body, step)
        _assert_primary_object(body, present, *absent)
        assert "Account Executive" in body
    status, body, _location = _http(server, "GET", f"/role?run={run.id}")
    assert status == 200
    _assert_step_chrome(body, "graph")
    _assert_primary_object(body, "skill-graph", "outline", "practice", "quiz")


def test_resolve_role_step_defaults() -> None:
    assert resolve_role_step(None, run=None, output=None) == "source"
    assert resolve_role_step("quiz", run=None, output=None) == "source"


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
    status, body, _location = _http(server, "GET", f"/role?run={2**63}")
    assert status == 404
    assert "not found" in body.lower()


def test_foreign_origin_post_is_403(server, job_text: str) -> None:
    posted = urlencode({"product": "role", "text": job_text, "project": "default"})
    status, body, _location = _http(
        server,
        "POST",
        "/role",
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
        "/role",
        body=posted,
        extra_headers={"Origin": f"http://{host}:{port}"},
    )
    assert status == 200
    assert "Account Executive" in body
    _assert_step_chrome(body, "graph")


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
    status, body, _location = _http(server, "GET", "/role?demo=1")
    assert status == 200
    assert "Harborline Payments" in body
    assert "EXAMPLE DATA" in body
    _assert_step_chrome(body, "source")
    assert Store(default_db_path()).list_runs() == []
    status, body, location = _http(
        server, "GET", "/?product=role&demo=1", follow=False
    )
    assert status == 200
    assert location is None
    assert "Harborline Payments" in body
    _assert_step_chrome(body, "source")


def test_invalid_role_stops_walk_on_graph(server) -> None:
    text = find_fixture("eval_warehouse_sop.txt").read_text(encoding="utf-8")
    posted = urlencode({"product": "role", "text": text, "project": "default"})
    status, body, _location = _http(server, "POST", "/role", body=posted)
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert "Invalid module" in body or "not a successful Role module" in body
    assert "unknown" in body.lower()
    assert "studio-failed" in body
    assert "pallet-jack" in body or "pallet jack" in body
    assert 'class="outline object"' not in body
    assert 'class="quiz object"' not in body
    assert "Continue" not in body
    store = Store(default_db_path())
    run = store.list_runs()[0]
    assert run.invalid is True
    status, body, _location = _http(
        server, "GET", f"/role?run={run.id}&step=outline"
    )
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert "Invalid module" in body
    assert 'class="outline object"' not in body


def test_title_swap_failure_copy_is_plain_english() -> None:
    canned = apply_title_swap_validity(
        canned_ae_template_role(),
        find_fixture("eval_stripe_sa_enablement_job.txt").read_text(encoding="utf-8"),
    )
    assert canned.invalid is True
    html = render_page(
        product=Product.ROLE,
        project="eval",
        text="Job title: Solution Architect Enablement Business Partner\n- Identify skill gaps",
        runs=[],
        output=canned,
    )
    lowered = html.lower()
    assert "invalid module" in lowered or "not a successful role module" in lowered
    assert "title-swap" in lowered or "swapping the job title" in lowered
    assert "account executive" in lowered
    assert 'class="studio-ok"' not in html
    assert 'data-step="graph"' in html
    assert 'class="outline object"' not in html


def test_enablement_frame_visible_for_designer(server) -> None:
    text = find_fixture("eval_instructional_designer_job.txt").read_text(
        encoding="utf-8"
    )
    posted = urlencode({"product": "role", "text": text, "project": "studio"})
    status, body, _location = _http(server, "POST", "/role", body=posted)
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert 'data-family="enablement"' in body
    assert 'data-frame="designer"' in body
    assert "Instructional Designer" in body
    assert "storyboard" in body.lower() or "needs analysis" in body.lower()


def test_partner_frame_visible_for_stripe_eval(server, stripe_enablement_text: str) -> None:
    posted = urlencode(
        {"product": "role", "text": stripe_enablement_text, "project": "eval"}
    )
    status, body, _location = _http(server, "POST", "/role", body=posted)
    assert status == 200
    _assert_step_chrome(body, "graph")
    assert 'data-family="enablement"' in body
    assert 'data-frame="partner"' in body
    assert "PUBLIC POSTING" in body or "public job posting" in body.lower()
    assert "Invalid module" not in body
    assert "not a successful Role module" not in body


def test_history_is_this_project_and_product(server, job_text: str, call_text: str) -> None:
    _http(
        server,
        "POST",
        "/role",
        body=urlencode({"product": "role", "text": job_text, "project": "alpha"}),
    )
    generate_and_save(Product.CALL, call_text, project="alpha")
    other = find_fixture("eval_warehouse_sop.txt").read_text(encoding="utf-8")
    _http(
        server,
        "POST",
        "/role",
        body=urlencode({"product": "role", "text": other, "project": "beta"}),
    )
    store = Store(default_db_path())
    alpha_role = next(
        run
        for run in store.list_runs(project="alpha", product=Product.ROLE)
    )
    status, body, _location = _http(server, "GET", f"/role?run={alpha_role.id}")
    assert status == 200
    assert f"/role?run={alpha_role.id}" in body
    beta_role = next(
        run for run in store.list_runs(project="beta", product=Product.ROLE)
    )
    call_run = next(
        run for run in store.list_runs(project="alpha", product=Product.CALL)
    )
    history = body[body.index("Versions") :] if "Versions" in body else body
    assert f"/role?run={beta_role.id}" not in history
    assert f"/role?run={call_run.id}" not in history
    assert f"/?run={beta_role.id}" not in history


def test_compare_two_role_runs(server, job_text: str, stripe_enablement_text: str) -> None:
    _http(
        server,
        "POST",
        "/role",
        body=urlencode({"product": "role", "text": job_text, "project": "studio"}),
    )
    _http(
        server,
        "POST",
        "/role",
        body=urlencode(
            {"product": "role", "text": stripe_enablement_text, "project": "studio"}
        ),
    )
    store = Store(default_db_path())
    runs = store.list_runs(project="studio", product=Product.ROLE)
    assert len(runs) == 2
    left, right = runs[0], runs[1]
    status, body, _location = _http(
        server, "GET", f"/role?run={left.id}&compare={right.id}"
    )
    assert status == 200
    assert "Compare" in body
    assert "Account Executive" in body
    assert "Enablement Business Partner" in body
    assert "Harborline Payments" in body


def test_get_overflow_compare_id_is_404(server, job_text: str) -> None:
    _http(
        server,
        "POST",
        "/role",
        body=urlencode({"product": "role", "text": job_text, "project": "default"}),
    )
    run = Store(default_db_path()).list_runs()[0]
    status, body, _location = _http(
        server, "GET", f"/role?run={run.id}&compare={2**63}"
    )
    assert status == 404
    assert "not found" in body.lower()


def test_old_run_query_stays_on_home_graph(server, job_text: str) -> None:
    _http(
        server,
        "POST",
        "/role",
        body=urlencode({"product": "role", "text": job_text, "project": "default"}),
    )
    run = Store(default_db_path()).list_runs()[0]
    status, body, location = _http(server, "GET", f"/?run={run.id}", follow=False)
    assert status == 200
    assert location is None
    _assert_step_chrome(body, "graph")
    _assert_primary_object(body, "skill-graph", "outline", "practice", "quiz")
