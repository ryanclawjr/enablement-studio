from __future__ import annotations

from enablement_studio.call import generate_call
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
