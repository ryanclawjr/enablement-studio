from __future__ import annotations

import re

from enablement_studio.models import (
    SOURCE_NOTE,
    AlignmentScores,
    CritiqueFinding,
    LessonCritique,
    Rewrite,
)
from enablement_studio.textutil import (
    clamp,
    extract_sections,
    extract_title,
    is_example_data,
    significant_terms,
)

_OBJECTIVE_KEYS = ("objective", "objectives", "outcome", "learners will", "you will")
_ACTIVITY_KEYS = ("activity", "practice", "exercise", "role-play", "role play", "drill")
_ASSESS_KEYS = ("assessment", "quiz", "knowledge check", "check for understanding", "test")
_BLOOM = {
    "explain",
    "describe",
    "demonstrate",
    "apply",
    "run",
    "score",
    "practice",
    "teach",
    "map",
    "close",
}


def generate_critic(text: str) -> LessonCritique:
    source = text.strip()
    if not source:
        raise ValueError("critic input is empty")
    title = extract_title(source, "Lesson outline")
    sections = extract_sections(source)
    objective_text = _section(sections, _OBJECTIVE_KEYS) or _first_match(source, _OBJECTIVE_KEYS)
    activity_text = _section(sections, _ACTIVITY_KEYS) or _first_match(source, _ACTIVITY_KEYS)
    assess_text = _section(sections, _ASSESS_KEYS) or _first_match(source, _ASSESS_KEYS)

    objective_terms = significant_terms(objective_text)
    activity_terms = significant_terms(activity_text)
    assess_terms = significant_terms(assess_text)
    bloom_in_objective = objective_terms & _BLOOM

    objective_score = _objective_score(objective_text, bloom_in_objective)
    activity_score = _alignment_score(objective_terms, activity_terms, activity_text)
    assess_score = _alignment_score(objective_terms, assess_terms, assess_text)
    overall = clamp(round((objective_score + activity_score + assess_score) / 3))
    scores = AlignmentScores(objective_score, activity_score, assess_score, overall)

    findings = _findings(objective_text, activity_text, assess_text, scores)
    rewrite = _rewrite(title, objective_text, activity_text, assess_text, scores)
    return LessonCritique(
        example_data=is_example_data(source),
        source_note=SOURCE_NOTE,
        lesson_title=title,
        scores=scores,
        findings=findings,
        rewrite=rewrite,
    )


def _section(sections: dict[str, str], keys: tuple[str, ...]) -> str:
    for name, body in sections.items():
        if any(key in name for key in keys):
            return body
    return ""


def _first_match(text: str, keys: tuple[str, ...]) -> str:
    lowered = text.lower()
    for key in keys:
        index = lowered.find(key)
        if index != -1:
            return text[index : index + 400]
    return ""


def _objective_score(objective_text: str, bloom: set[str]) -> int:
    if not objective_text:
        return 1
    score = 2
    if re.search(r"will (be able to )?\w+", objective_text, flags=re.I):
        score += 1
    if bloom:
        score += 1
    if len(objective_text.split()) >= 12:
        score += 1
    return clamp(score)


def _alignment_score(objective_terms: set[str], other_terms: set[str], other_text: str) -> int:
    if not other_text:
        return 1
    if not objective_terms:
        return 2
    overlap = len(objective_terms & other_terms)
    if overlap == 0:
        return 1
    if overlap <= 2:
        return 2
    if overlap <= 5:
        return 3
    return 5


def _findings(
    objective_text: str,
    activity_text: str,
    assess_text: str,
    scores: AlignmentScores,
) -> list[CritiqueFinding]:
    findings: list[CritiqueFinding] = []
    if scores.objective_clarity <= 2:
        findings.append(
            CritiqueFinding(
                "objective",
                "high",
                "The objective is missing or not measurable. Write a verb, a condition, and a measure.",
            )
        )
    elif objective_text:
        findings.append(
            CritiqueFinding(
                "objective",
                "low",
                "The objective is usable. Keep the verb; add a live measure if one is missing.",
            )
        )
    if scores.activity_alignment <= 2:
        findings.append(
            CritiqueFinding(
                "activity",
                "high",
                "The activity does not practice the objective verb. Replace social or logistics tasks with a skill drill.",
            )
        )
    if scores.assessment_alignment <= 2:
        findings.append(
            CritiqueFinding(
                "assessment",
                "high",
                "The check does not measure the same performance as the objective.",
            )
        )
    if activity_text and assess_text and scores.overall >= 4:
        findings.append(
            CritiqueFinding(
                "alignment",
                "low",
                "Objective, activity, and assessment already point at the same performance.",
            )
        )
    return findings


def _rewrite(
    title: str,
    objective_text: str,
    activity_text: str,
    assess_text: str,
    scores: AlignmentScores,
) -> Rewrite:
    named = [
        ("activity", scores.activity_alignment, activity_text),
        ("assessment", scores.assessment_alignment, assess_text),
        ("objective", scores.objective_clarity, objective_text),
    ]
    target, score, _original = min(named, key=lambda item: item[1])
    verb = "explain"
    match = re.search(r"will (?:be able to )?(\w+)", objective_text, flags=re.I)
    if match:
        verb = match.group(1).lower()
    topic = _topic(objective_text) or title
    if target == "activity":
        replacement = (
            f"## Activity (rewrite)\n"
            f"Paired teach-back (8 minutes): one learner {verb}s {topic} "
            "to a skeptical small-business owner. The partner only asks "
            "'what does that mean for my weekend cash?' Swap roles. "
            "Facilitator scores a 3-item rubric: accuracy, plain language, one next question."
        )
        reason = "The original activity does not practice the objective verb."
    elif target == "assessment":
        replacement = (
            f"## Assessment (rewrite)\n"
            f"1. In 90 seconds, {verb} {topic} to a buyer who has never heard the term.\n"
            "2. Name the buyer cue that tells you they understood.\n"
            "3. What is the one next question you will ask on a live call?"
        )
        reason = "The original check measures logistics, not the skill in the objective."
    else:
        replacement = (
            f"## Learning objective (rewrite)\n"
            f"Given a first conversation with a small-business owner, the learner will "
            f"{verb} {topic} in plain language, as measured by a 90-second teach-back "
            "scored on accuracy, clarity, and one relevant follow-up question."
        )
        reason = "The objective needs a condition, a verb, and an observable measure."
    return Rewrite(target=target, reason=reason, replacement=replacement)


def _topic(objective_text: str) -> str:
    match = re.search(
        r"(interchange|authorization|settlement|discovery|pipeline|objection[^.]*)",
        objective_text,
        flags=re.I,
    )
    if match:
        return match.group(1).lower()
    words = [word for word in re.findall(r"[A-Za-z]{4,}", objective_text) if word.lower() not in {"will", "able", "this", "that"}]
    if words:
        return " ".join(words[:6]).lower()
    return "the target skill"
