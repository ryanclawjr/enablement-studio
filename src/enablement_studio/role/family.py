from __future__ import annotations

import re
from enum import Enum

_ENABLEMENT_TITLE = re.compile(
    r"enablement|l\s*&\s*d|learning and development|"
    r"instructional design|learning experience|\blxd\b|"
    r"customer education|customer training|"
    r"nurse educator|clinical educator|clinical instructor|"
    r"nursing education|clinical education|patient educator|"
    r"director of education|"
    r"director,?\s*training|training director|head of training|"
    r"onboarding specialist|learning designer|curriculum designer",
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
    "learning experience",
    "customer education",
    "just-in-time learning",
    "skill and knowledge gap",
    "skill and knowledge gaps",
    "skills lab",
    "skills-lab",
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
    UNKNOWN = "unknown"


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
    return JobFamily.UNKNOWN
