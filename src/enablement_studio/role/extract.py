"""Work-unit extraction for Role. Catalogs label these spans; they do not invent them."""

from __future__ import annotations

import re

from enablement_studio.textutil import extract_bullets

_YOU_WILL_SPAN = re.compile(r"(?i)\byou will\s+([^.!?]+)")
_DISCLAIMER = re.compile(
    r"example data|example copy|not from a live|no live customer|"
    r"this posting is example|fictional job|not an application|"
    r"do not treat company names|example business|public posting|"
    r"sanitized copy|not sourced from|this is example",
    re.I,
)
_CREDENTIAL = re.compile(
    r"^(experience|ability|track record|proven|demonstrated|comfort|written)\b",
    re.I,
)


def is_disclaimer_span(text: str) -> bool:
    return _DISCLAIMER.search(text) is not None


def is_credential_span(text: str) -> bool:
    return _CREDENTIAL.match(text.strip()) is not None


def is_work_unit(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned.split()) < 3:
        return False
    if is_disclaimer_span(cleaned):
        return False
    if is_credential_span(cleaned):
        return False
    return True


def extract_work_units(source: str) -> list[str]:
    """Bullets, numbered SOP steps, and you-will / responsibility lines, in source order."""
    candidates: list[tuple[int, str]] = []
    for bullet in extract_bullets(source):
        cleaned = _clean_span(bullet)
        if is_work_unit(cleaned):
            candidates.append((_span_pos(source, cleaned), cleaned))
    for span in _you_will_spans(source):
        cleaned = _clean_span(span)
        if is_work_unit(cleaned):
            candidates.append((_span_pos(source, cleaned), cleaned))
    candidates.sort(key=lambda item: item[0])
    units: list[str] = []
    seen: set[str] = set()
    for _pos, text in candidates:
        key = text.lower()
        if key in seen:
            continue
        if any(key in item.lower() or item.lower() in key for item in units):
            continue
        seen.add(key)
        units.append(text)
    return units


def _clean_span(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _you_will_spans(source: str) -> list[str]:
    collapsed = re.sub(r"[ \t]*\n[ \t]*", " ", source)
    return [match.group(1).strip() for match in _YOU_WILL_SPAN.finditer(collapsed)]


def _span_pos(source: str, text: str) -> int:
    hay = re.sub(r"\s+", " ", source).lower()
    needle = text.lower()
    idx = hay.find(needle[:48] if len(needle) > 48 else needle)
    return idx if idx >= 0 else len(hay)
