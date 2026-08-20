from __future__ import annotations

import re

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
)
_BUYER_HINTS = (
    "prospect",
    "customer",
    "buyer",
    "owner",
    "jordan",
)
_CLINICAL_HINTS = (
    "ehr",
    "nurse",
    "skills lab",
    "skills-lab",
    "allergy",
    "medication",
    "chart",
    "mar",
)
_TRAINING_HINTS = (
    "educator",
    "new hire",
    "facilitator",
    "preceptor",
    "teach-back",
    "teach it back",
    "skills-lab checklist",
)
_SALES_HINTS = (
    "promo",
    "pricing",
    "rate card",
    "prospect",
    "processor",
    "account executive",
    "discount",
)
_PAYMENTS_HINTS = (
    "processor",
    "interchange",
    "merchant",
    "rate card",
    "chargeback",
    "payout",
    "harborline",
    "card-present",
    "2.4 percent",
    "2.4%",
)


def _is_payments(source: str) -> bool:
    hay = source.lower()
    if re.search(r"\bpayments?\b", hay):
        return True
    return any(token in hay for token in _PAYMENTS_HINTS)


def generate_call(text: str) -> CallCoaching:
    source = text.strip()
    if not source:
        raise ValueError("call input is empty")
    title = extract_title(source, "Coaching call")
    turns = parse_turns(source)
    speakers = list(dict.fromkeys(turn.speaker for turn in turns))
    kind = _session_kind(source, speakers)
    left, right = _roles(speakers, turns)
    signals = _signals(turns, left, right, kind, source)
    notes = _notes(title, left, right, signals, kind, source)
    fix = _fix(signals, kind, source)
    return CallCoaching(
        example_data=is_example_data(source),
        source_note=SOURCE_NOTE,
        call_title=title,
        speakers=speakers or ["Speaker"],
        signals=signals,
        notes=notes,
        enablement_fix=fix,
    )


def _has_hint(blob: str, token: str) -> bool:
    if " " in token or "-" in token:
        return token in blob
    return re.search(rf"\b{re.escape(token)}\b", blob) is not None


def _session_kind(source: str, speakers: list[str]) -> str:
    hay = source.lower()
    speaker_blob = " ".join(speakers).lower()
    blob = f"{hay}\n{speaker_blob}"
    if any(_has_hint(blob, token) for token in _CLINICAL_HINTS):
        return "clinical"
    if any(_has_hint(blob, token) for token in _TRAINING_HINTS) and not any(
        _has_hint(hay, token) for token in _SALES_HINTS
    ):
        return "training"
    if any(_has_hint(hay, token) for token in _SALES_HINTS) or any(
        token in speaker_blob for token in ("account executive", "prospect")
    ):
        return "sales"
    return "unknown"


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
    return seller or "the speaker", buyer or "the other party"


def _signals(turns: list, seller: str, buyer: str, kind: str, source: str) -> list[str]:
    if kind in {"clinical", "training"}:
        return _training_signals(turns, seller, source)
    return _sales_signals(turns, seller, buyer)


def _sales_signals(turns: list, seller: str, buyer: str) -> list[str]:
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
    if _price_before_discovery(turns, seller):
        signals.append("Price or promo appeared before current-process discovery.")
    if not any(
        token in lowered
        for token in ("next step", "follow up", "calendar", "thursday", "tuesday")
    ):
        signals.append("No dated next step was confirmed.")
    ignored_pain = any(
        token in buyer_lowered
        for token in ("chargeback", "pain", "weekend", "problem", "issue")
    ) and not any(
        token in lowered
        for token in ("chargeback", "weekend", "that problem", "you mentioned", "payout")
    )
    if ignored_pain:
        signals.append("Buyer named a concrete problem that the seller did not pick up.")
    if not signals:
        signals.append("Discovery questions landed before any commercial talk.")
    return signals


def _training_signals(turns: list, lead: str, source: str) -> list[str]:
    lead_text = " ".join(turn.text for turn in turns if turn.speaker == lead)
    hay = source.lower()
    signals: list[str] = []
    questions = lead_text.count("?")
    if questions < 1:
        signals.append("The facilitator asked no check questions on the tape.")
    if not any(token in hay for token in ("teach", "checklist", "double-check", "show me")):
        signals.append("No teach-back or checklist was confirmed.")
    if not signals:
        signals.append("The tape shows a skills practice; coach the next observable step.")
    return signals


def _price_before_discovery(turns: list, seller: str) -> bool:
    saw_price = False
    saw_discovery = False
    for turn in turns:
        if turn.speaker != seller:
            continue
        lowered = turn.text.lower()
        if any(
            token in lowered
            for token in (
                "price",
                "pricing",
                "promo",
                "2.4%",
                "discount",
                "rate card",
            )
        ):
            saw_price = True
            if not saw_discovery:
                return True
        if any(
            token in lowered
            for token in (
                "current processor",
                "today how",
                "what happens when",
                "who else",
                "success look",
                "how do you",
            )
        ):
            saw_discovery = True
    return saw_price and not saw_discovery


def _notes(
    title: str,
    seller: str,
    buyer: str,
    signals: list[str],
    kind: str,
    source: str,
) -> list[AgentNote]:
    lead = signals[0]
    if kind in {"clinical", "training"}:
        return [
            AgentNote(
                "learner",
                "Practice the step on the tape",
                (
                    f"{seller} on '{title}': {lead} "
                    f"Next session, have {buyer} teach the same step back "
                    "while you tick the checklist that already appears in the transcript."
                ),
            ),
            AgentNote(
                "customer",
                "The other person needs the skill practiced",
                (
                    f"{buyer} showed up to practice a job step. "
                    "They need the step restated, then one observed attempt, "
                    "then a stop rule if the check fails."
                ),
            ),
            AgentNote(
                "coach",
                "Coach one behavior, not the whole call",
                (
                    f"Inspect the teach-back only. If {seller} skips the check "
                    "that is already on the tape, stop and rerun that step. "
                    "Do not add commercial coaching the transcript never earned."
                ),
            ),
        ]
    pitched = any("price" in signal.lower() and "before" in signal.lower() for signal in signals)
    if pitched:
        if _is_payments(source):
            next_drill = (
                f"Next live call, ask {buyer} three questions about how money moves today "
                "before you mention a rate. Write the answers where your manager can see them."
            )
        else:
            next_drill = (
                f"Next live call, ask {buyer} three questions about how they work today "
                "before you mention a price. Write the answers where your manager can see them."
            )
        learner = AgentNote(
            "learner",
            "You pitched before you earned the right",
            (
                f"{seller} on '{title}': {lead} "
                f"{next_drill}"
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
    learner = AgentNote(
        "learner",
        "You stayed in discovery",
        (
            f"{seller} on '{title}': {lead} "
            f"Keep asking {buyer} about the process they already named. "
            "Write the answers and the dated next step where your manager can see them."
        ),
    )
    customer = AgentNote(
        "customer",
        "The other person already told you what matters",
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
            f"Inspect the open. If {seller} keeps discovery ahead of product talk, "
            "protect that sequence. Do not invent a pitch problem the tape does not show."
        ),
    )
    return [learner, customer, coach]


def _fix(signals: list[str], kind: str, source: str) -> EnablementFix:
    hay = source.lower()
    if kind in {"clinical", "training"}:
        if any(token in hay for token in ("ehr", "skills lab", "skills-lab", "chart", "mar")):
            return EnablementFix(
                title="Skills-lab teach-back drill",
                problem="The session needs one observable teach-back, not a commercial close.",
                fix=(
                    "Run a 10-minute teach-back on the chart step already on the tape. "
                    "Observer ticks the skills-lab checklist."
                ),
                measure="Next skills-lab: learner completes the chart step aloud with zero missed checks.",
            )
        return EnablementFix(
            title="Teach-back on the skill in the tape",
            problem="The session needs one observable practice of the step already named.",
            fix="Pair learners for a 10-minute teach-back. Observer ticks the source checklist.",
            measure="Observer checklist on the next practice, not a CRM log.",
        )
    if any("Price" in signal or "price" in signal for signal in signals):
        if _is_payments(source):
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
        return EnablementFix(
            title="Discovery-before-price drill",
            problem="Sellers open with price, so the other person never feels heard.",
            fix=(
                "Ship a 10-minute paired drill: three current-process questions, "
                "one restatement of pain, then—and only then—price. "
                "Managers score a 4-item checklist."
            ),
            measure="On the next three recorded calls, price talk starts after minute six.",
        )
    if any("Talk ratio" in signal for signal in signals):
        return EnablementFix(
            title="Question quota card",
            problem="Sellers occupy the airtime and never collect inspectable facts.",
            fix="Give a pocket card: four open questions before any feature sentence.",
            measure="Written notes list four buyer facts after each first call.",
        )
    if any("next step" in signal.lower() for signal in signals):
        return EnablementFix(
            title="Dated next-step script",
            problem="Calls end without an owner and a date.",
            fix="Add a 60-second close: propose a date, get the other person to repeat it, write it down.",
            measure="100% of first calls have a dated next step written within an hour.",
        )
    return EnablementFix(
        title="Keep the written recap",
        problem="The discovery sequence worked; the notes still need to be inspectable.",
        fix=(
            "After a clean open, write the three answers and the dated next step "
            "where a manager can see them."
        ),
        measure="The recap lists process, pain, success, and the next date.",
    )
