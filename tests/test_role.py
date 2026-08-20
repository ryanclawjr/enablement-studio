from __future__ import annotations

from enablement_studio.paths import find_fixture
from enablement_studio.role import generate_role
from enablement_studio.textutil import extract_bullets


def test_role_fixture_is_complete(job_text: str) -> None:
    result = generate_role(job_text)
    assert result.example_data is True
    assert "Account Executive" in result.role_title
    assert result.skill_graph.nodes
    assert result.skill_graph.edges
    assert len(result.objectives) >= 3
    assert len(result.outline) == 4
    assert result.practice.instructions
    assert len(result.quiz) >= 3
    assert any(node.id == "discovery" for node in result.skill_graph.nodes)
    assert "live employer" in result.source_note.lower()
    assert all("matches the" not in node.name for node in result.skill_graph.nodes)
    assert any("demonstrate discovery" in item.statement.lower() for item in result.objectives)


def test_role_title_follows_input() -> None:
    sales = generate_role("Job title: Account Executive\n- Run discovery calls")
    support = generate_role(
        "Job title: Onboarding Specialist\n- Run kickoff calls\n- Update the CRM"
    )
    assert sales.role_title != support.role_title
    assert "Account Executive" in sales.role_title
    assert "Onboarding Specialist" in support.role_title


def test_extract_bullets_joins_wrapped_lines() -> None:
    text = (
        "- Design onboarding programs, ongoing training, and\n"
        "  just-in-time learning resources for SA teams\n"
        "- Identify skill and knowledge gaps\n"
    )
    bullets = extract_bullets(text)
    assert any("just-in-time" in item for item in bullets)
    assert any("knowledge gaps" in item for item in bullets)


def test_nurse_and_id_quiz_are_readable_statements() -> None:
    nurse = generate_role(
        find_fixture("eval_nurse_educator_job.txt").read_text(encoding="utf-8")
    )
    designer = generate_role(
        find_fixture("eval_instructional_designer_job.txt").read_text(encoding="utf-8")
    )
    nurse_blob = " ".join(
        [item.statement for item in nurse.objectives]
        + nurse.practice.instructions
        + [item.question for item in nurse.quiz]
    ).lower()
    designer_blob = " ".join(
        [item.statement for item in designer.objectives]
        + designer.practice.instructions
        + [item.question for item in designer.quiz]
    ).lower()
    assert "demonstrate coach" not in nurse_blob
    assert "demonstrate facilitate" not in designer_blob
    assert any("coach new hires" in item.statement.lower() for item in nurse.objectives)
    assert any("facilitate a pilot" in item.statement.lower() for item in designer.objectives)


def test_role_rejects_empty() -> None:
    try:
        generate_role("   ")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("expected ValueError")
