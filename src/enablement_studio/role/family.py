from __future__ import annotations

import re
from enum import Enum

from enablement_studio.role.extract import extract_work_units
from enablement_studio.textutil import extract_title

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


class EnablementFrame(str, Enum):
    """Practice theory inside enablement. Not a fourth JobFamily."""

    DESIGNER = "designer"
    EDUCATOR = "educator"
    PARTNER = "partner"


_DESIGNER_TITLE = re.compile(
    r"instructional design(?:er)?|learning experience designer|\blxd\b|"
    r"learning designer|curriculum designer",
    re.I,
)
_EDUCATOR_TITLE = re.compile(
    r"nurse educator|clinical educator|clinical instructor|"
    r"nursing education|clinical education|patient educator|"
    r"customer education|customer training|"
    r"director of nursing education|head of nursing education|"
    r"facilitator",
    re.I,
)
_PARTNER_TITLE = re.compile(
    r"enablement business partner|sales enablement|enablement partner|"
    r"\benablement\b|onboarding specialist",
    re.I,
)
_DESIGNER_MARKERS = (
    "storyboard",
    "needs analysis",
    "curriculum",
    "facilitator guide",
    "learner journey",
    "knowledge check",
    "learning experience",
    "instructional design",
)
_EDUCATOR_MARKERS = (
    "train the trainer",
    "train-the-trainer",
    "train the trainers",
    "skills lab",
    "skills-lab",
    "teach-back",
    "coach new hires",
    "coach facilitators",
    "patient educator",
    "nurse educator",
    "clinical educator",
    "office hours",
    "medication",
    "ehr",
)
_PARTNER_MARKERS = (
    "skill and knowledge gap",
    "skill and knowledge gaps",
    "sales audience",
    "technical readiness",
    "enablement program",
    "enablement programs",
    "enablement initiatives",
    "enablement content",
    "sa teams",
    "go-to-market",
    "package technical",
    "technical packaging",
    "prior to launch",
    "launch readiness",
)


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


def classify_enablement_frame(source: str, title: str = "") -> EnablementFrame | None:
    heading = title or extract_title(source, "")
    if classify_job_family(source, heading) is not JobFamily.ENABLEMENT:
        return None
    title_frame = _frame_from_title(heading)
    bullet_scores = _frame_scores(_bullet_hay(source))
    bullet_frame = _winner(bullet_scores)
    if bullet_frame is not None:
        tied = _tied(bullet_scores)
        if not tied:
            return bullet_frame
        if title_frame is not None:
            return title_frame
        return bullet_frame
    if title_frame is not None:
        return title_frame
    source_frame = _winner(_frame_scores(f"{heading}\n{source}".lower()))
    if source_frame is not None:
        return source_frame
    return EnablementFrame.PARTNER


def _frame_from_title(title: str) -> EnablementFrame | None:
    if _DESIGNER_TITLE.search(title):
        return EnablementFrame.DESIGNER
    if _EDUCATOR_TITLE.search(title):
        return EnablementFrame.EDUCATOR
    if _PARTNER_TITLE.search(title):
        return EnablementFrame.PARTNER
    return None


def _bullet_hay(source: str) -> str:
    return " ".join(extract_work_units(source)).lower()


def _frame_scores(hay: str) -> dict[EnablementFrame, int]:
    lowered = hay.lower()
    return {
        EnablementFrame.DESIGNER: sum(1 for item in _DESIGNER_MARKERS if item in lowered),
        EnablementFrame.EDUCATOR: sum(1 for item in _EDUCATOR_MARKERS if item in lowered),
        EnablementFrame.PARTNER: sum(1 for item in _PARTNER_MARKERS if item in lowered),
    }


def _winner(scores: dict[EnablementFrame, int]) -> EnablementFrame | None:
    best = max(scores.values())
    if best <= 0:
        return None
    leaders = [frame for frame, score in scores.items() if score == best]
    if len(leaders) != 1:
        return None
    return leaders[0]


def _tied(scores: dict[EnablementFrame, int]) -> bool:
    best = max(scores.values())
    return best > 0 and sum(1 for score in scores.values() if score == best) > 1
