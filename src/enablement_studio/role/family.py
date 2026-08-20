from __future__ import annotations

import re
from enum import Enum

_ENABLEMENT_TITLE = re.compile(
    r"enablement|l\s*&\s*d|learning and development|instructional design",
    re.I,
)
_ENABLEMENT_PHRASES = (
    "enablement business partner",
    "sales enablement",
    "enablement program",
    "enablement programs",
    "enablement initiatives",
    "technical enablement",
    "learning and development",
    "instructional design",
    "just-in-time learning",
    "skill and knowledge gap",
    "skill and knowledge gaps",
)
_SELLER_TITLE = re.compile(
    r"account executive|sales engineer|sales development|"
    r"solutions? engineer|field (?:sa|se)\b",
    re.I,
)
_FIELD_SA_TITLE = re.compile(r"solution architect", re.I)


class JobFamily(str, Enum):
    ENABLEMENT = "enablement"
    SELLER = "seller"


def classify_job_family(source: str, title: str = "") -> JobFamily:
    heading = title or ""
    hay = f"{heading}\n{source}".lower()
    if _ENABLEMENT_TITLE.search(heading):
        return JobFamily.ENABLEMENT
    if any(phrase in hay for phrase in _ENABLEMENT_PHRASES):
        return JobFamily.ENABLEMENT
    if _SELLER_TITLE.search(heading):
        return JobFamily.SELLER
    if _FIELD_SA_TITLE.search(heading) and "enablement" not in heading.lower():
        return JobFamily.SELLER
    return JobFamily.SELLER
