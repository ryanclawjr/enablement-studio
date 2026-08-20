from __future__ import annotations

from enablement_studio.models import (
    SOURCE_NOTE,
    AgentNote,
    CallCoaching,
    EnablementFix,
)
from enablement_studio.textutil import (
    extract_title,
    is_example_data,
    parse_turns,
    word_count,
)

_SELLER_HINTS = (
    "ae",
    "account executive",
    "rep",
    "seller",
    "sales",
    "alex",
    "trainer",
    "coach",
)
_BUYER_HINTS = (
    "prospect",
    "customer",
    "buyer",
    "owner",
    "jordan",
    "learner",
)


def generate_call(text: str) -> CallCoaching:
    source = text.strip()
    if not source:
        raise ValueError("call input is empty")
    title = extract_title(source, "Coaching call")
    turns = parse_turns(source)
    speakers = list(dict.fromkeys(turn.speaker for turn in turns))
    seller, buyer = _roles(speakers, turns)
    signals = _signals(turns, seller, buyer)
    notes = _notes(title, seller, buyer, signals)
    fix = _fix(signals)
    return CallCoaching(
        example_data=is_example_data(source),
        source_note=SOURCE_NOTE,
        call_title=title,
        speakers=speakers or ["Speaker"],
        signals=signals,
        notes=notes,
        enablement_fix=fix,
    )


def _roles(speakers: list[str], turns: list) -> tuple[str, str]:
    seller = ""
    buyer = ""
    for name in speakers:
        lowered = name.lower()
        if not seller and any(hint in lowered for hint in _SELLER_HINTS):
            seller = name
        if not buyer and any(hint in lowered for hint in _BUYER_HINTS):
            buyer = name
    if not seller and speakers:
        seller = speakers[0]
    if not buyer:
        buyer = next((name for name in speakers if name != seller), "the other party")
    if not seller:
        counts: dict[str, int] = {}
        for turn in turns:
            counts[turn.speaker] = counts.get(turn.speaker, 0) + word_count(turn.text)
        if counts:
            seller = max(counts, key=counts.get)
    return seller or "the seller", buyer or "the buyer"


def _signals(turns: list, seller: str, buyer: str) -> list[str]:
    seller_text = " ".join(turn.text for turn in turns if turn.speaker == seller)
    buyer_text = " ".join(turn.text for turn in turns if turn.speaker == buyer)
    seller_words = word_count(seller_text)
    buyer_words = word_count(buyer_text)
    total = max(seller_words + buyer_words, 1)
    seller_share = seller_words / total
    questions = seller_text.count("?")
    lowered = seller_text.lower()
    buyer_lowered = buyer_text.lower()
    signals: list[str] = []
    if seller_share >= 0.62:
        signals.append(
            f"Talk ratio is seller-heavy ({int(seller_share * 100)}% of spoken words)."
        )
    if questions < 3:
        signals.append(f"Seller asked only {questions} question(s) on the transcript.")
    price_early = _price_before_discovery(turns, seller)
    if price_early:
        signals.append("Price or promo appeared before current-process discovery.")
    if not any(token in lowered for token in ("next step", "follow up", "calendar", "thursday", "tuesday")):
        signals.append("No dated next step was confirmed.")
    ignored_pain = any(
        token in buyer_lowered for token in ("chargeback", "pain", "weekend", "problem", "issue")
    ) and not any(token in lowered for token in ("chargeback", "weekend", "that problem", "you mentioned"))
    if ignored_pain:
        signals.append("Buyer named a concrete problem that the seller did not pick up.")
    if not signals:
        signals.append("Transcript is usable; still tighten the close and the written next step.")
    return signals


def _price_before_discovery(turns: list, seller: str) -> bool:
    saw_price = False
    saw_discovery = False
    for turn in turns:
        if turn.speaker != seller:
            continue
        lowered = turn.text.lower()
        if any(token in lowered for token in ("price", "pricing", "promo", "2.4%", "discount", "rate")):
            saw_price = True
            if not saw_discovery:
                return True
        if any(
            token in lowered
            for token in ("current processor", "today how", "what happens when", "who else", "success look")
        ):
            saw_discovery = True
    return False


def _notes(title: str, seller: str, buyer: str, signals: list[str]) -> list[AgentNote]:
    lead = signals[0]
    learner = AgentNote(
        "learner",
        "You pitched before you earned the right",
        (
            f"{seller} on '{title}': {lead} "
            f"Next live call, ask {buyer} three questions about how money moves today "
            "before you mention a rate. Write the answers where your manager can see them."
        ),
    )
    customer = AgentNote(
        "customer",
        "The buyer already told you what matters",
        (
            f"{buyer} showed up with a real operation to protect. "
            "They need to hear their own problem restated, then one proof point, "
            "then a next step that does not require a leap of faith."
        ),
    )
    coach = AgentNote(
        "coach",
        "Coach one behavior, not the whole call",
        (
            f"Inspect the first six minutes only. If {seller} mentions price before "
            "current-process questions, stop the tape and rerun that opening. "
            "Do not stack feedback about tone, slides, and brand."
        ),
    )
    return [learner, customer, coach]


def _fix(signals: list[str]) -> EnablementFix:
    if any("Price" in signal or "price" in signal for signal in signals):
        return EnablementFix(
            title="Discovery-before-rate drill",
            problem="Sellers open with promo pricing, so buyers never feel heard.",
            fix=(
                "Ship a 10-minute paired drill: three current-process questions, "
                "one restatement of pain, then—and only then—a rate card. "
                "Managers score a 4-item checklist."
            ),
            measure="On the next three recorded calls, price talk starts after minute six.",
        )
    if any("Talk ratio" in signal for signal in signals):
        return EnablementFix(
            title="Question quota card",
            problem="Sellers occupy the airtime and never collect inspectable facts.",
            fix="Give a pocket card: four open questions before any feature sentence.",
            measure="CRM notes list four buyer facts after each first call.",
        )
    return EnablementFix(
        title="Dated next-step script",
        problem="Calls end without an owner and a date.",
        fix="Add a 60-second close: propose a date, get the buyer to repeat it, log it.",
        measure="100% of first calls have a dated next step in the CRM within an hour.",
    )
