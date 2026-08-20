from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.request import Request

import pytest

from enablement_studio.engine import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LLM_TIMEOUT_SECONDS,
    generate,
    llm_chat_body,
    llm_configured,
    llm_endpoint,
)
from enablement_studio.models import EngineName, Product, RoleEnablement
from enablement_studio.paths import find_fixture
from enablement_studio.prompts import (
    CALL_SYSTEM_PROMPT,
    CRITIC_SYSTEM_PROMPT,
    ROLE_SYSTEM_PROMPT,
    system_prompt,
)
from enablement_studio.role import generate_role


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _openai_envelope(content: str | dict[str, Any]) -> str:
    if isinstance(content, dict):
        content = json.dumps(content)
    return json.dumps({"choices": [{"message": {"content": content}}]})


def _set_fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLEMENT_LLM_API_KEY", "test-key-not-real")


def test_prompts_are_per_product() -> None:
    role = system_prompt(Product.ROLE)
    call = system_prompt(Product.CALL)
    critic = system_prompt(Product.CRITIC)
    assert role == ROLE_SYSTEM_PROMPT
    assert call == CALL_SYSTEM_PROMPT
    assert critic == CRITIC_SYSTEM_PROMPT
    assert role != call
    assert call != critic
    assert role != critic

    assert "Extract skills from THIS source" in role
    assert "Do not stamp a seller AE / discovery / price / CRM template" in role
    assert "Enablement / L&D / instructional design / customer-education / clinical-educator" in role
    assert "SA teams they support" in role
    assert "Seller / SE / field SA" in role
    assert "RoleEnablement.invalid" in role
    assert "empty skill graph" in role
    assert "title-portable" in role
    assert "before presenting price" in role
    assert "offer a discount" in role
    assert "weekend cash" in role
    assert "Every objective verb appears in the graph" in role
    assert "Practice and quiz measure those verbs" in role
    assert "role_title" in role
    assert "skill_graph" in role

    assert "Notes only for learner, customer, coach" in call
    assert "Exactly one enablement fix" in call
    assert "Do not invent speakers or facts" in call
    assert "you pitched before you earned the right" in call
    assert "EHR skills lab" in call
    assert "money / rate / CRM" in call
    assert "call_title" in call
    assert "enablement_fix" in call

    assert "objective_clarity" in critic
    assert "activity_alignment" in critic
    assert "assessment_alignment" in critic
    assert "rounded mean" in critic
    assert "share a verb" in critic
    assert "aligned interchange lesson must not collapse to 2" in critic
    assert "same verb" in critic
    assert "pallet-jack stays warehouse" in critic
    assert "lesson_title" in critic
    assert "rewrite" in critic


def test_request_shape_is_openai_json_object() -> None:
    assert DEFAULT_MODEL == "gpt-4.1-mini"
    assert DEFAULT_BASE_URL == "https://api.openai.com/v1"
    assert llm_endpoint() == "https://api.openai.com/v1/chat/completions"
    assert LLM_TIMEOUT_SECONDS == 20

    body = llm_chat_body(Product.ROLE, "source text")
    assert body["model"] == "gpt-4.1-mini"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert "reasoning" not in body
    assert "reasoning_effort" not in body
    assert "thinking" not in body
    dumped = json.dumps(body)
    assert "reasoning" not in dumped
    assert "thinking" not in dumped
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"] == ROLE_SYSTEM_PROMPT
    assert body["messages"][1]["content"].startswith("product=role\n\n")

    call_body = llm_chat_body(Product.CALL, "transcript")
    critic_body = llm_chat_body(Product.CRITIC, "lesson")
    assert call_body["messages"][0]["content"] == CALL_SYSTEM_PROMPT
    assert critic_body["messages"][0]["content"] == CRITIC_SYSTEM_PROMPT
    assert call_body["messages"][0]["content"] != critic_body["messages"][0]["content"]


def test_mock_role_json_returns_llm_engine(
    monkeypatch: pytest.MonkeyPatch, job_text: str
) -> None:
    payload = generate_role(job_text).to_dict()
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: object = None) -> _FakeResponse:
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        assert request.data is not None
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(_openai_envelope(payload))

    _set_fake_key(monkeypatch)
    monkeypatch.setattr("enablement_studio.engine.urllib.request.urlopen", fake_urlopen)
    output, engine = generate(Product.ROLE, job_text)
    assert engine is EngineName.LLM
    assert isinstance(output, RoleEnablement)
    assert output.role_title == payload["role_title"]
    assert output.skill_graph.nodes
    assert output.invalid is False
    assert captured["timeout"] == LLM_TIMEOUT_SECONDS
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["model"] == "gpt-4.1-mini"
    assert "reasoning" not in captured["body"]


def _timeout(_request: Request, timeout: object = None) -> _FakeResponse:
    raise TimeoutError("timed out")


def _non_json(_request: Request, timeout: object = None) -> _FakeResponse:
    return _FakeResponse("this is not json")


def _schema_invalid(_request: Request, timeout: object = None) -> _FakeResponse:
    return _FakeResponse(_openai_envelope({"role_title": "not enough keys"}))


@pytest.mark.parametrize("fake_urlopen", (_timeout, _non_json, _schema_invalid))
def test_llm_failures_fall_back_offline(
    monkeypatch: pytest.MonkeyPatch,
    job_text: str,
    fake_urlopen: Callable[..., _FakeResponse],
) -> None:
    expected = generate_role(job_text)
    _set_fake_key(monkeypatch)
    monkeypatch.setattr("enablement_studio.engine.urllib.request.urlopen", fake_urlopen)
    output, engine = generate(Product.ROLE, job_text)
    assert engine is EngineName.OFFLINE
    assert isinstance(output, RoleEnablement)
    assert output == expected


def test_no_key_never_opens_network(
    monkeypatch: pytest.MonkeyPatch, job_text: str
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("network should not be used without a key")

    monkeypatch.setattr("enablement_studio.engine.urllib.request.urlopen", boom)
    assert llm_configured() is False
    output, engine = generate(Product.ROLE, job_text)
    assert engine is EngineName.OFFLINE
    assert output.example_data is True


def test_eval_fixtures_stay_offline_without_keys(
    job_text: str, stripe_enablement_text: str
) -> None:
    assert llm_configured() is False
    cases = (
        (Product.ROLE, job_text),
        (Product.ROLE, stripe_enablement_text),
        (
            Product.CALL,
            find_fixture("eval_clean_discovery_call.txt").read_text(encoding="utf-8"),
        ),
        (
            Product.CALL,
            find_fixture("eval_ehr_skills_lab_call.txt").read_text(encoding="utf-8"),
        ),
        (
            Product.CRITIC,
            find_fixture("eval_aligned_interchange_lesson.md").read_text(
                encoding="utf-8"
            ),
        ),
        (
            Product.CRITIC,
            find_fixture("eval_pallet_jack_lesson.md").read_text(encoding="utf-8"),
        ),
    )
    for product, text in cases:
        output, engine = generate(product, text)
        assert engine is EngineName.OFFLINE
        if product is Product.ROLE:
            assert isinstance(output, RoleEnablement)
