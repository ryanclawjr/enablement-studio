from __future__ import annotations

from pathlib import Path

import pytest

from enablement_studio.paths import find_fixture


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENABLEMENT_DB", str(tmp_path / "enablement.db"))
    monkeypatch.delenv("ENABLEMENT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ENABLEMENT_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("ENABLEMENT_LLM_MODEL", raising=False)


@pytest.fixture
def job_text() -> str:
    return find_fixture("example_account_executive_job.txt").read_text(encoding="utf-8")


@pytest.fixture
def call_text() -> str:
    return find_fixture("example_sales_call.txt").read_text(encoding="utf-8")


@pytest.fixture
def lesson_text() -> str:
    return find_fixture("example_new_hire_lesson.md").read_text(encoding="utf-8")
