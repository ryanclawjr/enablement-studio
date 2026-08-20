from __future__ import annotations

import re

from enablement_studio.engine import generate
from enablement_studio.models import EngineName, Product, artifact_map
from enablement_studio.role import generate_role
from enablement_studio.role.title_swap import (
    apply_title_swap_validity,
    fails_title_swap,
)
from enablement_studio.store import Store

from canned_ae_template import canned_ae_template_role

_OBJECTIVE_VERB = re.compile(r"\bwill\s+([a-z]+)\b", re.I)

_ENABLEMENT_SKILLS = (
    "gap analysis",
    "onboarding",
    "technical packaging",
    "launch readiness",
    "impact",
)


def _graph_text(role) -> str:
    parts = [role.role_title]
    for node in role.skill_graph.nodes:
        parts.extend([node.id, node.name, node.detail])
    return " ".join(parts).lower()


def _practice_quiz_text(role) -> str:
    parts = [
        role.practice.title,
        role.practice.scenario,
        *role.practice.instructions,
        *role.practice.success_criteria,
    ]
    for item in role.quiz:
        parts.extend([item.question, item.answer, item.rationale, *item.choices])
    return " ".join(parts).lower()


def _objective_verbs(role) -> list[str]:
    verbs: list[str] = []
    for item in role.objectives:
        match = _OBJECTIVE_VERB.search(item.statement)
        assert match, f"no verb in {item.statement!r}"
        verbs.append(match.group(1).lower())
    return verbs


def test_title_swap_canned_ae_template_fails() -> None:
    canned = canned_ae_template_role(
        "Solution Architect Enablement Business Partner"
    )
    assert fails_title_swap(canned) is True


def test_title_swap_stripe_eval_passes(stripe_enablement_text: str) -> None:
    role = generate_role(stripe_enablement_text)
    assert fails_title_swap(role) is False
    assert role.invalid is False


def test_stripe_enablement_skills_come_from_source(stripe_enablement_text: str) -> None:
    role = generate_role(stripe_enablement_text)
    graph = _graph_text(role)
    measured = _practice_quiz_text(role)
    blob = f"{graph} {measured}"
    for phrase in _ENABLEMENT_SKILLS:
        assert phrase in blob, phrase
    assert "before presenting price" not in blob
    assert "buyer facts written in the crm" not in blob
    assert role.example_data is False
    assert "public" in role.source_note.lower()


def test_rule_2_enablement_partner_is_not_field_sa(stripe_enablement_text: str) -> None:
    role = generate_role(stripe_enablement_text)
    assert "Solution Architect" in role.role_title
    assert "Enablement" in role.role_title
    ids = {node.id for node in role.skill_graph.nodes}
    assert "discovery" not in ids
    assert "demo" not in ids
    assert not any(item.startswith("experience-") for item in ids)
    assert "gap-analysis" in ids
    assert "onboarding-design" in ids
    assert "technical-packaging" in ids
    assert "launch-readiness" in ids
    assert "impact-metrics" in ids


def test_field_sa_may_keep_seller_skills() -> None:
    role = generate_role(
        "Job title: Solution Architect\n"
        "- Run discovery with enterprise buyers\n"
        "- Demo the checkout path\n"
        "- Handle pricing objections\n"
    )
    ids = {node.id for node in role.skill_graph.nodes}
    assert "discovery" in ids
    assert "demo" in ids
    assert role.invalid is False


def test_objective_verbs_appear_in_graph_and_assessments(
    job_text: str, stripe_enablement_text: str
) -> None:
    for source in (job_text, stripe_enablement_text):
        role = generate_role(source)
        graph = _graph_text(role)
        measured = _practice_quiz_text(role)
        verbs = _objective_verbs(role)
        assert verbs
        for verb in verbs:
            assert verb in graph, verb
            assert verb in measured, verb


def test_harborline_remains_valid_successful_run(job_text: str) -> None:
    role = generate_role(job_text)
    assert role.invalid is False
    assert any(node.id == "discovery" for node in role.skill_graph.nodes)
    assert any("demonstrate discovery" in item.statement.lower() for item in role.objectives)


def test_title_swap_failure_is_not_stored_as_success(
    tmp_path, stripe_enablement_text: str
) -> None:
    canned = canned_ae_template_role()
    marked = apply_title_swap_validity(canned, stripe_enablement_text)
    assert marked.invalid is True
    assert fails_title_swap(marked) is True
    store = Store(tmp_path / "test.db")
    run = store.save_run(
        project="eval",
        product=Product.ROLE,
        title=marked.role_title,
        input_text=stripe_enablement_text,
        engine=EngineName.OFFLINE,
        artifacts=artifact_map(marked),
        invalid=marked.invalid,
    )
    loaded = store.get_run(run.id)
    assert loaded.invalid is True
    listed = store.list_runs(project="eval", product=Product.ROLE)
    assert listed[0].invalid is True


def test_harborline_store_run_is_valid(tmp_path, job_text: str) -> None:
    role = generate_role(job_text)
    output, engine = generate(Product.ROLE, job_text)
    assert engine is EngineName.OFFLINE
    assert output.invalid is False
    store = Store(tmp_path / "test.db")
    run = store.save_run(
        project="example",
        product=Product.ROLE,
        title=role.role_title,
        input_text=job_text,
        engine=engine,
        artifacts=artifact_map(role),
        invalid=role.invalid,
    )
    assert store.get_run(run.id).invalid is False
