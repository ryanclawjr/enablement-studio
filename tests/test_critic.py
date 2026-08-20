from __future__ import annotations

from enablement_studio.critic import generate_critic
from enablement_studio.paths import find_fixture


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


def test_aligned_interchange_lesson_is_not_a_miss() -> None:
    text = find_fixture("eval_aligned_interchange_lesson.md").read_text(encoding="utf-8")
    result = generate_critic(text)
    assert result.scores.activity_alignment >= 4
    assert result.scores.assessment_alignment >= 4
    assert result.scores.overall >= 4
    rewrite = result.rewrite.replacement.lower()
    assert "buyer" not in rewrite
    assert "weekend cash" not in rewrite
    assert "interchange" in rewrite


def test_pallet_jack_rewrite_stays_warehouse() -> None:
    text = find_fixture("eval_pallet_jack_lesson.md").read_text(encoding="utf-8")
    result = generate_critic(text)
    rewrite = result.rewrite.replacement.lower()
    assert "pallet" in rewrite or "warehouse" in rewrite
    assert "buyer" not in rewrite
    assert "weekend cash" not in rewrite
    assert "small-business owner" not in rewrite
