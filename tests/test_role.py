from __future__ import annotations

from enablement_studio.role import generate_role


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


def test_role_rejects_empty() -> None:
    try:
        generate_role("   ")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("expected ValueError")
