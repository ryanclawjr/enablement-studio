from __future__ import annotations

from enablement_studio.critic import generate_critic


def test_critic_flags_misaligned_lesson(lesson_text: str) -> None:
    result = generate_critic(lesson_text)
    assert result.example_data is True
    assert 1 <= result.scores.objective_clarity <= 5
    assert result.scores.activity_alignment <= 2
    assert result.scores.assessment_alignment <= 2
    assert result.rewrite.target in {"activity", "assessment"}
    assert "rewrite" in result.rewrite.replacement.lower()
    assert result.findings


def test_critic_rewards_aligned_lesson() -> None:
    text = """
    EXAMPLE DATA — fictional lesson.
    Title: Discovery practice
    ## Learning objective
    The learner will demonstrate discovery by asking for current process, pain,
    and success criteria, as measured by a live role-play checklist.
    ## Activity
    Role-play discovery: ask for current process, pain, and success criteria.
    Partner scores the checklist.
    ## Assessment
    Knowledge check: list the three discovery questions and run them in a
    90-second role-play scored on the same checklist.
    """
    result = generate_critic(text)
    assert result.scores.activity_alignment >= 3
    assert result.scores.assessment_alignment >= 3
    assert result.scores.overall >= 3


def test_critic_rejects_empty() -> None:
    try:
        generate_critic("\n")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("expected ValueError")
