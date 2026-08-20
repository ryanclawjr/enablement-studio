from __future__ import annotations

import re
from dataclasses import dataclass

EXAMPLE_MARKERS = (
    "EXAMPLE DATA",
    "FICTIONAL",
    "EXAMPLE BUSINESS",
    "NOT A REAL",
    "NOT FROM A LIVE",
)

_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
    "you",
    "your",
    "will",
    "able",
}

_TITLE_RE = re.compile(
    r"(?im)^(?:job title|role|position|title|lesson|call)\s*[:\-]\s*(.+)$"
)
_HEADING_RE = re.compile(r"(?m)^#{1,3}\s+(.+)$")
_BULLET_RE = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+(.+)$")
_TURN_RE = re.compile(
    r"^(?P<speaker>[A-Za-z][A-Za-z0-9 ./'&-]{0,48})\s*:\s+(?P<line>.+)$"
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+-]{2,}")
_META_SPEAKERS = {
    "call",
    "title",
    "job title",
    "company",
    "lesson",
    "role",
    "position",
}
_ROSTER_SPEAKERS = {
    "account executive",
    "ae",
    "prospect",
    "customer",
    "buyer",
    "rep",
    "seller",
    "learner",
    "coach",
    "trainer",
    "nurse educator",
    "new hire",
    "educator",
    "facilitator",
    "preceptor",
}


PUBLIC_POSTING_MARKERS = (
    "PUBLIC POSTING",
    "PUBLIC JOB POSTING",
)


def is_example_data(text: str) -> bool:
    head = text[:1200].upper()
    return any(marker in head for marker in EXAMPLE_MARKERS)


def is_public_posting(text: str) -> bool:
    head = text[:1200].upper()
    return any(marker in head for marker in PUBLIC_POSTING_MARKERS)


def first_non_banner_line(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.lstrip("# ").upper()
        if any(marker in upper for marker in EXAMPLE_MARKERS):
            continue
        if upper.startswith("EXAMPLE"):
            continue
        return line.lstrip("# ").strip()
    return "Untitled source"


def extract_title(text: str, fallback: str) -> str:
    match = _TITLE_RE.search(text)
    if match:
        return _clean_title(match.group(1))
    heading = _HEADING_RE.search(text)
    if heading:
        candidate = _clean_title(heading.group(1))
        if not any(marker in candidate.upper() for marker in EXAMPLE_MARKERS):
            return candidate
    line = first_non_banner_line(text)
    if line and line.lower() != "untitled source":
        return _clean_title(line)
    return fallback


def _clean_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" -:")
    cleaned = re.sub(r"\s+\(example.*$", "", cleaned, flags=re.I)
    return cleaned[:120]


def extract_bullets(text: str) -> list[str]:
    seen: list[str] = []
    current: str | None = None
    for raw in text.splitlines():
        match = _BULLET_RE.match(raw)
        if match:
            if current:
                _push_unique(seen, current)
            current = re.sub(r"\s+", " ", match.group(1)).strip()
            continue
        stripped = raw.strip()
        if current and raw[:1] in {" ", "\t"} and stripped:
            current = f"{current} {stripped}"
            continue
        if current:
            _push_unique(seen, current)
            current = None
    if current:
        _push_unique(seen, current)
    return seen


def _push_unique(seen: list[str], item: str) -> None:
    if item and item not in seen:
        seen.append(item)


def extract_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = "intro"
    chunks: list[str] = []
    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            sections[current] = "\n".join(chunks).strip()
            current = heading.group(1).strip().lower()
            chunks = []
            continue
        chunks.append(line)
    sections[current] = "\n".join(chunks).strip()
    return {key: value for key, value in sections.items() if value}


def significant_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for word in _WORD_RE.findall(text.lower()):
        if word in _STOP:
            continue
        terms.add(word)
    return terms


def slug(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return compact[:48] or "item"


def clamp(score: int, low: int = 1, high: int = 5) -> int:
    return max(low, min(high, score))


@dataclass(frozen=True)
class SpeakerTurn:
    speaker: str
    text: str


def parse_turns(text: str) -> list[SpeakerTurn]:
    turns: list[SpeakerTurn] = []
    current: SpeakerTurn | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _TURN_RE.match(line)
        if match:
            speaker = match.group("speaker").strip()
            spoken = match.group("line").strip()
            if _is_metadata_line(speaker, spoken):
                continue
            if current is not None:
                turns.append(current)
            current = SpeakerTurn(speaker, spoken)
            continue
        if current is not None and not line.startswith("#"):
            current = SpeakerTurn(current.speaker, f"{current.text} {line}")
    if current is not None:
        turns.append(current)
    return turns


def _is_metadata_line(speaker: str, spoken: str) -> bool:
    label = speaker.lower()
    if label in _META_SPEAKERS:
        return True
    if label in _ROSTER_SPEAKERS and word_count(spoken) <= 4:
        return True
    return False


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))
