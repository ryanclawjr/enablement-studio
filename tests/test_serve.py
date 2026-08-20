from __future__ import annotations

import http.client
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request

import pytest

from enablement_studio.cli import _build_parser, main
from enablement_studio.html_render import _render_critic, render_page
from enablement_studio.models import (
    SOURCE_NOTE,
    AlignmentScores,
    LessonCritique,
    Product,
    Rewrite,
)
from enablement_studio.paths import default_db_path, find_fixture
from enablement_studio.role.title_swap import apply_title_swap_validity
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


def test_get_home_names_three_products(server) -> None:
    status, body, _location = _http(server, "GET", "/")
    assert status == 200
    assert "Role studio" in body
    assert "Role → Enablement" in body
    assert "Call → Coach" in body
    assert "Lesson critic" in body
    assert "onboarding buddy" not in body.lower()
    assert 'type="radio"' not in body
    assert 'name="product"' in body
    assert "Run Harborline example (EXAMPLE DATA)" in body


def test_make_server_is_threaded() -> None:
    httpd = make_server("127.0.0.1", 0)
    try:
        assert isinstance(httpd, ThreadingHTTPServer)
        assert httpd.daemon_threads is True
    finally:
        httpd.server_close()


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
    assert "Harborline Payments" in body
    assert "weekend cash-flow" in body
    assert 'data-family="seller"' in body
    assert 'class="skill-graph' in body
    assert 'class="objectives' in body
    assert 'class="outline' in body
    assert 'class="practice' in body
    assert 'class="quiz' in body
    assert "not a successful Role module" not in body


def test_post_empty_text_stays_on_studio(server) -> None:
    posted = urlencode({"product": "role", "text": "", "project": "default"})
    status, body, _location = _http(server, "POST", "/", body=posted, follow=False)
    assert status == 200
    assert "Role studio" in body
    assert "Sit a JD, SOP, or policy on the table." in body
    assert "Run Harborline example (EXAMPLE DATA)" in body
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
    status, body, _location = _http(server, "POST", "/", body=posted)
    elapsed = time.monotonic() - started
    assert elapsed < 3
    assert status == 200
    assert "SKILL GRAPH" in body
    assert "Account Executive" in body
    assert "engine offline" in body
    assert "LEARNING OBJECTIVES" in body
    assert "30-MINUTE MODULE" in body
    assert "APPLICATION QUIZ" in body
    get_started = time.monotonic()
    get_status, home, _location = _http(server, "GET", "/")
    assert time.monotonic() - get_started < 2
    assert get_status == 200
    assert "Role studio" in home


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
        result["post"] = _http(server, "POST", "/", body=posted)

    worker = threading.Thread(target=do_post)
    worker.start()
    assert started.wait(timeout=3)
    get_started = time.monotonic()
    status, body, _location = _http(server, "GET", "/")
    assert time.monotonic() - get_started < 2
    assert status == 200
    assert "Role studio" in body
    assert "Sit a JD, SOP, or policy on the table" in body or "Nothing on the board yet" in body
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    posted_result = result["post"]
    assert isinstance(posted_result, tuple)
    post_status, post_body, _post_location = posted_result
    assert post_status == 200
    assert "SKILL GRAPH" in post_body
    assert "engine offline" in post_body


def test_harborline_demo_action_returns_role_board(server) -> None:
    posted = urlencode(
        {"product": "role", "text": "", "project": "default", "action": "demo"}
    )
    status, body, _location = _http(server, "POST", "/", body=posted)
    assert status == 200
    assert "Account Executive" in body
    assert "SKILL GRAPH" in body
    assert "LEARNING OBJECTIVES" in body
    assert "30-MINUTE MODULE" in body
    assert "APPLICATION QUIZ" in body
    assert "Harborline Payments" in body
    assert "EXAMPLE DATA" in body
    assert "engine offline" in body
    assert 'type="radio"' not in body
    store = Store(default_db_path())
    assert len(store.list_runs()) == 1
    assert store.list_runs()[0].engine.value == "offline"


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
    assert "EXAMPLE DATA — fictional sample" in body or "EXAMPLE DATA fixtures" in body
    assert Store(default_db_path()).list_runs() == []


def test_invalid_role_is_plain_english_not_success(server) -> None:
    text = find_fixture("eval_warehouse_sop.txt").read_text(encoding="utf-8")
    posted = urlencode({"product": "role", "text": text, "project": "default"})
    status, body, _location = _http(server, "POST", "/", body=posted)
    assert status == 200
    assert "not a successful Role module" in body
    assert "unknown" in body.lower()
    assert "studio-failed" in body
    assert "pallet-jack" in body or "pallet jack" in body
    store = Store(default_db_path())
    assert store.list_runs()[0].invalid is True


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
    assert "not a successful role module" in lowered
    assert "title-swap" in lowered or "swapping the job title" in lowered
    assert "account executive" in lowered
    assert 'class="studio-ok"' not in html


def test_enablement_frame_visible_for_designer(server) -> None:
    text = find_fixture("eval_instructional_designer_job.txt").read_text(
        encoding="utf-8"
    )
    posted = urlencode({"product": "role", "text": text, "project": "studio"})
    status, body, _location = _http(server, "POST", "/", body=posted)
    assert status == 200
    assert 'data-family="enablement"' in body
    assert 'data-frame="designer"' in body
    assert "Northglass Academy" in body
    assert "storyboard" in body.lower() or "needs analysis" in body.lower()


def test_partner_frame_visible_for_stripe_eval(server, stripe_enablement_text: str) -> None:
    posted = urlencode(
        {"product": "role", "text": stripe_enablement_text, "project": "eval"}
    )
    status, body, _location = _http(server, "POST", "/", body=posted)
    assert status == 200
    assert 'data-family="enablement"' in body
    assert 'data-frame="partner"' in body
    assert "PUBLIC POSTING" in body or "public job posting" in body.lower()
    assert "not a successful Role module" not in body


def test_history_is_this_project_and_product(server, job_text: str, call_text: str) -> None:
    _http(
        server,
        "POST",
        "/",
        body=urlencode({"product": "role", "text": job_text, "project": "alpha"}),
    )
    _http(
        server,
        "POST",
        "/",
        body=urlencode({"product": "call", "text": call_text, "project": "alpha"}),
    )
    other = find_fixture("eval_warehouse_sop.txt").read_text(encoding="utf-8")
    _http(
        server,
        "POST",
        "/",
        body=urlencode({"product": "role", "text": other, "project": "beta"}),
    )
    store = Store(default_db_path())
    alpha_role = next(
        run
        for run in store.list_runs(project="alpha", product=Product.ROLE)
    )
    status, body, _location = _http(server, "GET", f"/?run={alpha_role.id}")
    assert status == 200
    assert f"/?run={alpha_role.id}" in body
    beta_role = next(
        run for run in store.list_runs(project="beta", product=Product.ROLE)
    )
    call_run = next(
        run for run in store.list_runs(project="alpha", product=Product.CALL)
    )
    history = body[body.index("This project") :] if "This project" in body else body
    assert f"/?run={beta_role.id}" not in history
    assert f"/?run={call_run.id}" not in history


def test_compare_two_role_runs(server, job_text: str, stripe_enablement_text: str) -> None:
    _http(
        server,
        "POST",
        "/",
        body=urlencode({"product": "role", "text": job_text, "project": "studio"}),
    )
    _http(
        server,
        "POST",
        "/",
        body=urlencode(
            {"product": "role", "text": stripe_enablement_text, "project": "studio"}
        ),
    )
    store = Store(default_db_path())
    runs = store.list_runs(project="studio", product=Product.ROLE)
    assert len(runs) == 2
    left, right = runs[0], runs[1]
    status, body, _location = _http(
        server, "GET", f"/?run={left.id}&amp;compare={right.id}".replace("&amp;", "&")
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
        "/",
        body=urlencode({"product": "role", "text": job_text, "project": "default"}),
    )
    run = Store(default_db_path()).list_runs()[0]
    status, body, _location = _http(
        server, "GET", f"/?run={run.id}&compare={2**63}"
    )
    assert status == 404
    assert "not found" in body.lower()
