from __future__ import annotations

import json

from enablement_studio.cli import main
from enablement_studio.models import Product
from enablement_studio.paths import default_db_path, find_fixture
from enablement_studio.store import Store


def test_three_demo_commands(capsys) -> None:
    assert main(["demo", "role"]) == 0
    role_out = capsys.readouterr().out
    assert "EXAMPLE DATA" in role_out
    assert "SKILL GRAPH" in role_out
    assert "LEARNING OBJECTIVES" in role_out
    assert "30-MINUTE MODULE" in role_out
    assert "PRACTICE" in role_out
    assert "QUIZ" in role_out

    assert main(["demo", "call"]) == 0
    call_out = capsys.readouterr().out
    assert "AGENT NOTES" in call_out
    assert "[learner]" in call_out
    assert "[customer]" in call_out
    assert "[coach]" in call_out
    assert "ENABLEMENT FIX" in call_out

    assert main(["demo", "critic"]) == 0
    critic_out = capsys.readouterr().out
    assert "ALIGNMENT SCORES" in critic_out
    assert "REWRITE" in critic_out

    store = Store(default_db_path())
    runs = store.list_runs()
    assert len(runs) == 3
    products = {run.product.value for run in runs}
    assert products == {"role", "call", "critic"}
    assert all(run.engine.value == "offline" for run in runs)
    assert all(run.version == 1 for run in runs)

    assert main(["list"]) == 0
    listed = capsys.readouterr().out
    assert "role" in listed
    first_id = runs[0].id
    assert main(["show", str(first_id)]) == 0
    shown = capsys.readouterr().out
    assert "Run" in shown


def test_compare_and_json(capsys) -> None:
    assert main(["demo", "role", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["role_title"]
    assert main(["role", "--text", "Job title: Onboarding Specialist\n- Update the CRM"]) == 0
    capsys.readouterr()
    store = Store(default_db_path())
    runs = store.list_runs()
    assert len(runs) == 2
    assert main(["compare", str(runs[0].id), str(runs[1].id)]) == 0
    diff = capsys.readouterr().out
    assert "Compare runs" in diff


def test_missing_run_is_an_error(capsys) -> None:
    assert main(["show", "99"]) == 2
    err = capsys.readouterr().err
    assert "99" in err


def test_role_requires_input() -> None:
    assert main(["role"]) == 2


def test_cli_role_stripe_eval_is_enablement(capsys) -> None:
    path = find_fixture("eval_stripe_sa_enablement_job.txt")
    assert main(["role", "--file", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["invalid"] is False
    blob = json.dumps(payload).lower()
    assert "before presenting price" not in blob
    assert "buyer facts written in the crm" not in blob
    assert "onboarding" in blob
    assert "gap analysis" in blob
    assert "launch readiness" in blob
    store = Store(default_db_path())
    runs = store.list_runs(product=Product.ROLE)
    assert runs
    assert runs[-1].invalid is False
