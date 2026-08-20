from __future__ import annotations

from enablement_studio.call import generate_call
from enablement_studio.paths import find_fixture
from enablement_studio.textutil import parse_turns


def test_call_fixture_notes_and_fix(call_text: str) -> None:
    result = generate_call(call_text)
    assert result.example_data is True
    audiences = [note.audience for note in result.notes]
    assert audiences == ["learner", "customer", "coach"]
    assert result.enablement_fix.title
    assert result.enablement_fix.fix
    assert any("price" in signal.lower() for signal in result.signals)
    assert result.speakers == ["Alex Rivera", "Jordan Kim"]
    assert [turn.speaker for turn in parse_turns(call_text)][:1] == ["Alex Rivera"]


def test_call_detects_talk_ratio() -> None:
    transcript = (
        "EXAMPLE DATA — fictional.\n"
        "Account Executive: Feature feature feature pricing promo dashboard "
        "platform rate card close today promo promo.\n"
        "Prospect: Okay.\n"
    )
    result = generate_call(transcript)
    assert any("Talk ratio" in signal for signal in result.signals)


def test_call_rejects_empty() -> None:
    try:
        generate_call("")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def _call_blob(result) -> str:
    parts = [result.call_title, result.enablement_fix.title]
    parts.extend([result.enablement_fix.problem, result.enablement_fix.fix])
    parts.append(result.enablement_fix.measure)
    for note in result.notes:
        parts.extend([note.headline, note.body])
    parts.extend(result.signals)
    return " ".join(parts).lower()


def test_clean_discovery_call_does_not_claim_early_pitch() -> None:
    text = find_fixture("eval_clean_discovery_call.txt").read_text(encoding="utf-8")
    result = generate_call(text)
    blob = _call_blob(result)
    assert "you pitched before you earned the right" not in blob
    assert result.speakers == ["Alex Rivera", "Jordan Kim"]


def test_ehr_skills_lab_has_no_money_moves_fix() -> None:
    text = find_fixture("eval_ehr_skills_lab_call.txt").read_text(encoding="utf-8")
    result = generate_call(text)
    blob = _call_blob(result)
    for phrase in (
        "how money moves",
        "rate card",
        "crm",
        "before you mention a rate",
        "you pitched before you earned the right",
    ):
        assert phrase not in blob, phrase
    assert "ehr" in blob or "skills-lab" in blob or "skills lab" in blob or "chart" in blob
