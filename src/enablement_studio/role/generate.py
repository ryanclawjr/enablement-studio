from __future__ import annotations

import re
from dataclasses import dataclass

from enablement_studio.models import (
    PUBLIC_SOURCE_NOTE,
    SOURCE_NOTE,
    LearningObjective,
    ModuleBlock,
    PracticeActivity,
    QuizItem,
    RoleEnablement,
    SkillEdge,
    SkillGraph,
    SkillNode,
)
from enablement_studio.role.extract import extract_work_units
from enablement_studio.role.family import (
    EnablementFrame,
    JobFamily,
    classify_enablement_frame,
    classify_job_family,
)
from enablement_studio.role.title_swap import apply_title_swap_validity
from enablement_studio.textutil import (
    extract_title,
    is_example_data,
    is_public_posting,
    slug,
)

_LEVEL_VERBS = {
    "foundation": "explain",
    "core": "demonstrate",
    "performance": "run",
}
_SA_RE = re.compile(r"\bsa teams?\b|solution architect", re.I)
_LEADING_VERBS = frozenset(
    {
        "assess",
        "check",
        "close",
        "coach",
        "collect",
        "design",
        "diagnose",
        "demonstrate",
        "describe",
        "explain",
        "facilitate",
        "handle",
        "identify",
        "inspect",
        "leave",
        "log",
        "map",
        "measure",
        "move",
        "negotiate",
        "operate",
        "pack",
        "package",
        "pair",
        "perform",
        "pick",
        "prepare",
        "prototype",
        "record",
        "report",
        "retire",
        "revise",
        "run",
        "schedule",
        "score",
        "set",
        "stop",
        "teach",
        "tie",
        "train",
        "write",
    }
)
_NAME_TRAILING = re.compile(
    r"\b(?:and|or|the|a|an|to|for|from|they|then|with|of|in|on)$",
    flags=re.I,
)


@dataclass(frozen=True)
class SkillSeed:
    id: str
    name: str
    level: str
    keywords: tuple[str, ...]
    detail: str
    verb: str
    requires: tuple[str, ...] = ()


SELLER_CATALOG: tuple[SkillSeed, ...] = (
    SkillSeed(
        "payment-fundamentals",
        "Payment fundamentals",
        "foundation",
        ("payment", "payments", "interchange", "processor", "merchant", "card"),
        "Authorization, settlement, and how a merchant account actually works.",
        "explain",
    ),
    SkillSeed(
        "buyer-context",
        "Buyer and business context",
        "foundation",
        ("small-business", "bakery", "smb", "prospect", "business owner"),
        "Who the buyer is, what the business sells, and what 'good' looks like for them.",
        "explain",
    ),
    SkillSeed(
        "crm-hygiene",
        "CRM and pipeline hygiene",
        "foundation",
        ("crm", "salesforce", "pipeline", "forecast", "hubspot"),
        "Log next steps, stage, and evidence so coaching is possible.",
        "log",
    ),
    SkillSeed(
        "discovery",
        "Discovery",
        "core",
        ("discover", "discovery", "pain", "qualify", "qualification"),
        "Ask for current process, pain, stakeholders, and success criteria before pitching.",
        "demonstrate",
    ),
    SkillSeed(
        "value-mapping",
        "Value mapping",
        "core",
        ("value", "roi", "outcome", "business case", "justify"),
        "Connect a product capability to a buyer outcome the prospect already named.",
        "map",
    ),
    SkillSeed(
        "demo",
        "Targeted demonstration",
        "core",
        ("demo", "demonstrate", "walkthrough"),
        "Show only the path that proves the discovery notes.",
        "demonstrate",
        ("discovery",),
    ),
    SkillSeed(
        "objection-handling",
        "Objection handling",
        "core",
        ("objection", "concern", "pushback", "price", "pricing", "competitor"),
        "Label the objection, isolate it, and answer with evidence—not a new pitch.",
        "handle",
        ("value-mapping",),
    ),
    SkillSeed(
        "negotiation",
        "Commercial negotiation",
        "performance",
        ("negotiate", "negotiation", "discount", "legal", "procurement", "contract terms"),
        "Trade, do not give. Protect margin while keeping a mutual plan.",
        "negotiate",
        ("objection-handling",),
    ),
    SkillSeed(
        "close",
        "Mutual-plan close",
        "performance",
        ("close", "closing", "next step", "commit", "agreement"),
        "Leave with a dated next step both sides can see.",
        "close",
        ("discovery",),
    ),
    SkillSeed(
        "coaching",
        "Call coaching",
        "performance",
        ("coach", "coaching", "manager"),
        "Give one observable behavior to change on the next call.",
        "coach",
        ("discovery",),
    ),
)

ENABLEMENT_CATALOG: tuple[SkillSeed, ...] = (
    SkillSeed(
        "gap-analysis",
        "Enablement gap analysis",
        "foundation",
        ("gap", "gaps", "needs assessment", "skill and knowledge"),
        "Find skill and knowledge gaps before building a program.",
        "diagnose",
    ),
    SkillSeed(
        "onboarding-design",
        "Onboarding design",
        "core",
        ("onboarding", "just-in-time", "learning resource", "learning resources"),
        "Design onboarding and ongoing learning for the audience.",
        "design",
        ("gap-analysis",),
    ),
    SkillSeed(
        "technical-packaging",
        "Technical packaging",
        "core",
        (
            "package",
            "packaging",
            "sales audience",
            "curation",
            "content creation",
            "enablement content",
            "go-to-market",
        ),
        "Turn technical product information into something the audience can use.",
        "package",
        ("gap-analysis",),
    ),
    SkillSeed(
        "launch-readiness",
        "Launch readiness",
        "core",
        ("launch", "readiness", "product release", "technical readiness"),
        "Get the audience technically ready before a product launch.",
        "prepare",
        ("technical-packaging",),
    ),
    SkillSeed(
        "impact-metrics",
        "Enablement impact metrics",
        "performance",
        ("metric", "metrics", "analytics", "impact", "impact metrics"),
        "Track whether the program changed productivity or readiness.",
        "measure",
        ("onboarding-design",),
    ),
    SkillSeed(
        "curriculum-design",
        "Curriculum and storyboard design",
        "core",
        (
            "curriculum",
            "storyboard",
            "needs analysis",
            "knowledge check",
            "facilitator guide",
            "learner journey",
            "learning experience",
        ),
        "Design the learning path and materials the audience will use.",
        "design",
    ),
    SkillSeed(
        "skills-practice",
        "Skills practice design",
        "core",
        ("skills lab", "skills-lab", "competency", "teach-back", "ehr", "medication"),
        "Design practice that matches the job skill.",
        "design",
    ),
)

CATALOG = SELLER_CATALOG


def generate_role(text: str) -> RoleEnablement:
    source = text.strip()
    if not source:
        raise ValueError("role input is empty")
    title = extract_title(source, "Role from source text")
    family = classify_job_family(source, title)
    frame = classify_enablement_frame(source, title)
    catalog = _catalog_for(family)
    units = extract_work_units(source)
    nodes, edges = _skill_graph(source, units, catalog)
    focus = _focus(nodes, catalog)
    audience = _audience_phrase(family, source, frame)
    objectives = _objectives(title, family, frame, focus, source, audience)
    outline = _outline(title, family, frame, focus, source)
    practice = _practice(title, family, frame, focus, units, source, audience)
    quiz = _quiz(title, family, focus, source, practice)
    result = RoleEnablement(
        example_data=is_example_data(source),
        source_note=PUBLIC_SOURCE_NOTE if is_public_posting(source) else SOURCE_NOTE,
        role_title=title,
        skill_graph=SkillGraph(nodes=nodes, edges=edges),
        objectives=objectives,
        outline=outline,
        practice=practice,
        quiz=quiz,
    )
    return apply_title_swap_validity(result, source)


def _catalog_for(family: JobFamily) -> tuple[SkillSeed, ...]:
    if family is JobFamily.ENABLEMENT:
        return ENABLEMENT_CATALOG
    if family is JobFamily.SELLER:
        return SELLER_CATALOG
    if family is JobFamily.UNKNOWN:
        return ()
    never: JobFamily = family
    raise ValueError(f"unsupported job family: {never}")


def keyword_in(hay: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in hay
    return re.search(rf"\b{re.escape(keyword)}s?\b", hay) is not None


def source_mentions(source: str, *needles: str) -> bool:
    hay = source.lower()
    return any(needle in hay for needle in needles)


def _has_sa(source: str) -> bool:
    return _SA_RE.search(source) is not None


def _audience_phrase(
    family: JobFamily, source: str, frame: EnablementFrame | None
) -> str:
    if family is JobFamily.SELLER:
        hay = source.lower()
        if source_mentions(source, "buyer", "prospect"):
            return "in language a buyer can use"
        if "operator" in hay:
            return "in language operators can use"
        return "in language the other person can use"
    if family is JobFamily.ENABLEMENT:
        return f"for {_audience_noun(source, frame)}"
    if family is JobFamily.UNKNOWN:
        hay = source.lower()
        if any(token in hay for token in ("warehouse", "pallet", "pallet jack")):
            return "for warehouse associates"
        return "for the people they support"
    never: JobFamily = family
    raise ValueError(f"unsupported job family: {never}")


def _seller_counterpart(source: str) -> str:
    if source_mentions(source, "buyer", "prospect"):
        return "a cautious buyer"
    if "operator" in source.lower():
        return "an operator"
    return "the other person"


def _seller_fact_noun(source: str) -> str:
    if source_mentions(source, "buyer", "prospect"):
        return "buyer facts"
    if "operator" in source.lower():
        return "operator facts"
    return "facts already named"


def _audience_noun(source: str, frame: EnablementFrame | None) -> str:
    hay = source.lower()
    if frame is EnablementFrame.PARTNER:
        if _has_sa(source):
            return "the SA teams they support"
        return "the field team they enable"
    if frame is EnablementFrame.EDUCATOR:
        if any(token in hay for token in ("nurse", "ehr", "clinical", "medication", "nursing")):
            return "the clinicians they train"
        if "customer education" in hay or "customers going live" in hay:
            return "the customers they educate"
        return "the practitioners they teach"
    if frame is EnablementFrame.DESIGNER:
        return "the learners they design for"
    if frame is None:
        if any(token in hay for token in ("warehouse", "pallet")):
            return "warehouse associates"
        return "the people they support"
    never: EnablementFrame = frame
    raise ValueError(f"unsupported enablement frame: {never}")


def _focus_object(node: SkillNode, source: str) -> str:
    hay = source.lower()
    sa = _has_sa(source)
    objects = {
        "discovery": "discovery",
        "demo": "a targeted demonstration",
        "value-mapping": "value to a buyer outcome",
        "objection-handling": "objections",
        "gap-analysis": "enablement gap analysis",
        "onboarding-design": "SA onboarding" if sa else "onboarding",
        "technical-packaging": (
            "technical content for a sales audience"
            if sa or "sales audience" in hay
            else "technical content for the audience"
        ),
        "launch-readiness": "launch readiness",
        "impact-metrics": "enablement impact",
        "curriculum-design": "the curriculum",
        "skills-practice": "skills practice",
    }
    return objects.get(node.id, node.name.lower())


def _skill_graph(
    source: str,
    units: list[str],
    catalog: tuple[SkillSeed, ...],
) -> tuple[list[SkillNode], list[SkillEdge]]:
    if not units:
        return [], []

    nodes: list[SkillNode] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()
    for unit in units:
        seed = _best_seed(unit, catalog)
        if seed is not None and seed.id not in used_ids:
            name = _grounded_name(unit, seed, source)
            node = SkillNode(
                id=seed.id,
                name=name,
                level=seed.level,
                detail=f"{seed.verb} — {_seed_detail(seed, source)}",
            )
            used_ids.add(seed.id)
        else:
            verb, _raw_name = _skill_from_bullet(unit, "core")
            name = _short_unit_name(unit)
            node_id = slug(name)
            if node_id in used_ids or name.lower() in used_names:
                continue
            node = SkillNode(
                id=node_id,
                name=name,
                level="core",
                detail=f"{verb} — {unit}",
            )
            used_ids.add(node_id)
        if node.name.lower() in used_names:
            continue
        used_names.add(node.name.lower())
        nodes.append(node)

    edges = _graph_edges(nodes, units, catalog)
    return nodes, edges


def _best_seed(unit: str, catalog: tuple[SkillSeed, ...]) -> SkillSeed | None:
    head = _short_unit_name(unit).lower()
    lowered = unit.lower()
    scored: list[tuple[int, int, SkillSeed]] = []
    for seed in catalog:
        head_hits = [keyword for keyword in seed.keywords if keyword_in(head, keyword)]
        all_hits = [keyword for keyword in seed.keywords if keyword_in(lowered, keyword)]
        hits = head_hits or all_hits
        if not hits:
            continue
        bonus = 100 if head_hits else 0
        scored.append((bonus + max(len(keyword) for keyword in hits), len(hits), seed))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return scored[0][2]


def _grounded_name(unit: str, seed: SkillSeed, source: str) -> str:
    labeled = _seed_name(seed, source)
    if _phrase_in(labeled, source):
        return labeled
    if _phrase_in(seed.name, source):
        return seed.name
    return _short_unit_name(unit)


def _phrase_in(phrase: str, source: str) -> bool:
    hay = re.sub(r"\s+", " ", source).lower()
    needle = re.sub(r"\s+", " ", phrase).lower()
    return bool(needle) and needle in hay


def _short_unit_name(unit: str) -> str:
    cleaned = re.sub(r"^(?:must|should|will|able to|you will)\s+", "", unit, flags=re.I)
    cleaned = re.sub(r"[.]+$", "", cleaned).strip()
    cleaned = re.split(
        r"\s+(?:that|who|then|without|so that|using)\s+",
        cleaned,
        maxsplit=1,
        flags=re.I,
    )[0]
    cleaned = cleaned.split(";")[0].strip().rstrip(" ,;:")
    if "," in cleaned and len(cleaned) > 72:
        cleaned = cleaned.split(",", 1)[0].strip().rstrip(" ,;:")
    return _readable_skill_name(cleaned)


def _graph_edges(
    nodes: list[SkillNode],
    units: list[str],
    catalog: tuple[SkillSeed, ...],
) -> list[SkillEdge]:
    edges: list[SkillEdge] = []
    seen: set[tuple[str, str, str]] = set()
    ids = {node.id for node in nodes}
    for index, node in enumerate(nodes[:-1]):
        nxt = nodes[index + 1]
        relation = _sequence_relation(units[index] if index < len(units) else "")
        key = (node.id, nxt.id, relation)
        if key not in seen:
            seen.add(key)
            edges.append(SkillEdge(node.id, nxt.id, relation))
    seed_by_id = {seed.id: seed for seed in catalog}
    for node in nodes:
        seed = seed_by_id.get(node.id)
        if seed is None:
            continue
        for parent in seed.requires:
            if parent in ids and node.id in ids:
                key = (parent, node.id, "prerequisite")
                if key not in seen:
                    seen.add(key)
                    edges.append(SkillEdge(parent, node.id, "prerequisite"))
    return edges


def _sequence_relation(unit: str) -> str:
    lowered = unit.lower()
    if re.search(r"\bonly after\b|\bafter the\b", lowered):
        return "after"
    if re.search(r"\bbefore (?:any|the next|you|presenting)\b", lowered):
        return "before"
    return "then"


def _seed_name(seed: SkillSeed, source: str) -> str:
    if seed.id == "onboarding-design" and _has_sa(source):
        return "SA onboarding design"
    if seed.id == "technical-packaging" and (
        _has_sa(source) or "sales audience" in source.lower()
    ):
        return "Technical packaging for a sales audience"
    return seed.name


def _seed_detail(seed: SkillSeed, source: str) -> str:
    if seed.id == "gap-analysis":
        return "Enablement gap analysis from the skill and knowledge gaps in the source."
    if seed.id == "onboarding-design" and _has_sa(source):
        return "SA onboarding design for the SA audience named in the source."
    if seed.id == "technical-packaging":
        return (
            "Technical packaging of product information for a sales audience."
            if _has_sa(source) or "sales audience" in source.lower()
            else "Technical packaging of product information for the audience."
        )
    if seed.id == "launch-readiness":
        if _has_sa(source):
            return "Launch readiness: get SA teams technically ready before a product launch."
        return "Launch readiness from the source release work."
    if seed.id == "impact-metrics":
        return "Enablement impact metrics from the source measurement work."
    return seed.detail


def _skill_from_bullet(bullet: str, level: str) -> tuple[str, str]:
    cleaned = re.sub(r"^(?:must|should|will|able to)\s+", "", bullet, flags=re.I)
    cleaned = re.sub(r"[.]+$", "", cleaned).strip()
    if not cleaned:
        return _LEVEL_VERBS[level], "Source skill"
    first = cleaned.split(None, 1)[0].lower()
    verb = first if first in _LEADING_VERBS else _LEVEL_VERBS[level]
    return verb, _readable_skill_name(cleaned)


def _readable_skill_name(cleaned: str) -> str:
    name = cleaned
    if len(name) > 80:
        name = name[:80].rsplit(" ", 1)[0]
        name = _NAME_TRAILING.sub("", name).strip()
    if not name:
        name = cleaned[:80].strip()
    return name[0].upper() + name[1:]


def _verb_complement(verb: str, node: SkillNode, source: str) -> str:
    focus_object = _focus_object(node, source)
    if focus_object == verb or focus_object.startswith(f"{verb} "):
        return focus_object
    return f"{verb} {focus_object}"


def _article(title: str) -> str:
    return "an" if title[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def _cap(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def _focus(
    nodes: list[SkillNode], catalog: tuple[SkillSeed, ...]
) -> list[tuple[str, SkillNode]]:
    verb_by_id = {seed.id: seed.verb for seed in catalog}
    picked = [
        node
        for node in nodes
        if node.id in verb_by_id and node.level in {"core", "performance"}
    ][:4]
    if len(picked) < 3:
        picked = [node for node in nodes if node.level in {"core", "performance"}][:4]
    if len(picked) < 3:
        picked = nodes[:3]
    pairs: list[tuple[str, SkillNode]] = []
    for node in picked:
        verb = verb_by_id.get(node.id) or _verb_from_detail(node) or _LEVEL_VERBS[node.level]
        pairs.append((verb, node))
    return pairs


def _verb_from_detail(node: SkillNode) -> str | None:
    prefix = node.detail.split(" — ", 1)[0].strip().lower()
    if prefix.isalpha():
        return prefix
    return None


def _objectives(
    title: str,
    family: JobFamily,
    frame: EnablementFrame | None,
    focus: list[tuple[str, SkillNode]],
    source: str,
    audience: str,
) -> list[LearningObjective]:
    measures = _objective_measures(family, frame)
    if family not in {JobFamily.ENABLEMENT, JobFamily.SELLER, JobFamily.UNKNOWN}:
        never: JobFamily = family
        raise ValueError(f"unsupported job family: {never}")
    objectives: list[LearningObjective] = []
    for index, (verb, node) in enumerate(focus, start=1):
        complement = _verb_complement(verb, node, source)
        statement = (
            f"Given a realistic {title} scenario, the learner will {complement} "
            f"{audience}."
        )
        objectives.append(
            LearningObjective(
                id=f"lo-{index}",
                statement=statement,
                skill_id=node.id,
                measure=measures[node.level],
            )
            )
    return objectives


def _objective_measures(
    family: JobFamily, frame: EnablementFrame | None
) -> dict[str, str]:
    if family is JobFamily.SELLER:
        return {
            "foundation": "a 90-second teach-back scored on a 3-point rubric",
            "core": "a live role-play scored against a behavior checklist",
            "performance": "a recorded call review with one observable next-step",
        }
    if family is JobFamily.UNKNOWN:
        return {
            "foundation": "a 90-second teach-back scored on a 3-point rubric",
            "core": "a live practice scored against a behavior checklist",
            "performance": "an on-the-job check with one observable next-step",
        }
    if family is not JobFamily.ENABLEMENT:
        never: JobFamily = family
        raise ValueError(f"unsupported job family: {never}")
    if frame is EnablementFrame.DESIGNER:
        return {
            "foundation": "a scored needs-analysis or design brief a manager can inspect",
            "core": "an instructional artifact scored against a checklist",
            "performance": "a revision from learner performance data",
        }
    if frame is EnablementFrame.EDUCATOR:
        return {
            "foundation": "a teach-back scored on a 3-point rubric",
            "core": "a live skills-lab or facilitation scored against a checklist",
            "performance": "a recorded coaching moment with one observable next-step",
        }
    if frame is EnablementFrame.PARTNER:
        return {
            "foundation": "a scored gap-analysis brief a manager can inspect",
            "core": "a packaged enablement artifact scored against a checklist",
            "performance": "an impact metric with a baseline and a review date",
        }
    never_frame: EnablementFrame | None = frame
    raise ValueError(f"unsupported enablement frame: {never_frame}")


def _outline(
    title: str,
    family: JobFamily,
    frame: EnablementFrame | None,
    focus: list[tuple[str, SkillNode]],
    source: str,
) -> list[ModuleBlock]:
    core = focus[0][1].name.lower() if focus else "the core skill"
    hook = _outline_hook(title, family, frame, source)
    return [
        ModuleBlock("0–5", "Hook and outcome", hook),
        ModuleBlock(
            "5–15",
            "Model the skill",
            f"Worked example of {core}: good / better / best, with the checklist on screen.",
        ),
        ModuleBlock(
            "15–25",
            "Guided practice",
            "Pairs run a 6-minute drill. Observer ticks the checklist; facilitator spot-coaches.",
        ),
        ModuleBlock(
            "25–30",
            "Assessment and transfer",
            "Two-item check plus a written commitment for the next live opportunity.",
        ),
    ]


def _outline_hook(
    title: str,
    family: JobFamily,
    frame: EnablementFrame | None,
    source: str,
) -> str:
    if family is JobFamily.SELLER:
        return (
            f"Open with a missed {title} moment and name the one behavior "
            "this 30 minutes will change."
        )
    if family is JobFamily.UNKNOWN:
        return (
            f"Open with a missed {title} moment and name the one behavior "
            "this 30 minutes will change."
        )
    if family is not JobFamily.ENABLEMENT:
        never: JobFamily = family
        raise ValueError(f"unsupported job family: {never}")
    if frame is EnablementFrame.PARTNER and _has_sa(source) and "launch" in source.lower():
        return (
            f"Open with an SA who cannot package a launch, then name the one "
            f"{title} behavior this 30 minutes will change."
        )
    if frame is EnablementFrame.DESIGNER:
        return (
            f"Open with a {title} module that skipped the source design step, "
            "then name the one behavior this 30 minutes will change."
        )
    if frame is EnablementFrame.EDUCATOR:
        return (
            f"Open with a missed teach-back for {title}, then name the one "
            "behavior this 30 minutes will change."
        )
    if frame is EnablementFrame.PARTNER:
        return (
            f"Open with a missed {title} moment and name the one behavior "
            "this 30 minutes will change."
        )
    never_frame: EnablementFrame | None = frame
    raise ValueError(f"unsupported enablement frame: {never_frame}")


def _practice(
    title: str,
    family: JobFamily,
    frame: EnablementFrame | None,
    focus: list[tuple[str, SkillNode]],
    units: list[str],
    source: str,
    audience: str,
) -> PracticeActivity:
    skill = focus[0][1].name.lower() if focus else "the core skill"
    verbs = list(dict.fromkeys(verb for verb, _ in focus))
    verb_list = ", ".join(verbs) if verbs else "practice"
    context = units[0] if units else f"a typical {title} conversation"
    if family is JobFamily.ENABLEMENT:
        return _practice_enablement(
            title, frame, focus, skill, verb_list, context, source
        )
    if family is JobFamily.SELLER:
        counterpart = _seller_counterpart(source)
        fact_noun = _seller_fact_noun(source)
        restater = "Buyer" if source_mentions(source, "buyer", "prospect") else "The other person"
        return PracticeActivity(
            title=f"12-minute {skill} drill",
            scenario=(
                f"You are {_article(title)} {title}. The other person is {counterpart}. "
                f"Source cue (example or user text): {context}"
            ),
            instructions=[
                "Spend the first four minutes only on questions. No product claims.",
                f"Map two {fact_noun} to {skill} before you propose anything.",
                "Close on one dated next step the other person repeats back.",
                f"Observer checks the learner can {verb_list}.",
            ],
            success_criteria=[
                "At least four open questions before any price or feature talk."
                if source_mentions(source, "price", "pricing")
                else "At least four open questions before any product claim.",
                f"{restater} can restate the problem in their own words.",
                "Next step has an owner and a date.",
                f"Verbs on the checklist: {verb_list}.",
            ],
        )
    if family is JobFamily.UNKNOWN:
        return PracticeActivity(
            title=f"12-minute {skill} drill",
            scenario=(
                f"You are working the {title} procedure. "
                f"Source cue: {context}"
            ),
            instructions=[
                f"{_cap(_verb_complement(verb, node, source))} from this source cue."
                for verb, node in focus[:3]
            ]
            or ["Practice the next step named in the source."],
            success_criteria=[
                f"The drill measures these verbs: {verb_list}.",
                "The practice stays in the domain of the source.",
                f"Audience: {audience}.",
            ],
        )
    never: JobFamily = family
    raise ValueError(f"unsupported job family: {never}")


def _practice_enablement(
    title: str,
    frame: EnablementFrame | None,
    focus: list[tuple[str, SkillNode]],
    skill: str,
    verb_list: str,
    context: str,
    source: str,
) -> PracticeActivity:
    audience = _audience_noun(source, frame)
    instructions = [
        f"{_cap(_verb_complement(verb, node, source))} from this source cue."
        for verb, node in focus[:3]
    ] or ["Build one learning artifact from the source cue."]
    if frame is EnablementFrame.DESIGNER:
        return PracticeActivity(
            title=f"12-minute {skill} studio",
            scenario=(
                f"You are {_article(title)} {title} designing instruction for {audience}. "
                f"Source cue: {context}"
            ),
            instructions=instructions,
            success_criteria=[
                f"The drill measures these verbs: {verb_list}.",
                "The output is an instructional design artifact, not a buyer pitch.",
                (
                    "Needs analysis, storyboard, or a knowledge check is visible."
                    if source_mentions(
                        source, "storyboard", "needs analysis", "knowledge check"
                    )
                    else f"The artifact practices the source verbs: {verb_list}."
                ),
            ],
        )
    if frame is EnablementFrame.EDUCATOR:
        return PracticeActivity(
            title=f"12-minute {skill} teaching drill",
            scenario=(
                f"You are {_article(title)} {title} teaching {audience}. "
                f"Source cue: {context}"
            ),
            instructions=instructions,
            success_criteria=[
                f"The drill measures these verbs: {verb_list}.",
                "The output is a teaching or coaching artifact, not a buyer pitch.",
                f"The artifact practices the source verbs: {verb_list}.",
            ],
        )
    if frame is EnablementFrame.PARTNER:
        sa = _has_sa(source)
        return PracticeActivity(
            title=f"12-minute {skill} drill",
            scenario=(
                f"You are {_article(title)} {title} supporting {audience}. "
                f"Source cue: {context}"
            ),
            instructions=instructions,
            success_criteria=[
                f"The drill measures these verbs: {verb_list}.",
                (
                    "The output is an enablement artifact for SAs, not a buyer pitch."
                    if sa
                    else "The output is an enablement artifact for the field team, not a buyer pitch."
                ),
                (
                    "Onboarding design, technical packaging, or launch readiness is visible."
                    if sa or source_mentions(source, "onboarding", "packaging", "launch")
                    else f"The artifact practices the source verbs: {verb_list}."
                ),
            ],
        )
    never: EnablementFrame | None = frame
    raise ValueError(f"unsupported enablement frame: {never}")


def _stock_choices(source: str) -> list[str]:
    choices = ["Send a logo slide deck and wait"]
    if source_mentions(source, "discount"):
        choices.append("Offer a discount to create urgency")
    else:
        choices.append("Skip practice and read the policy aloud")
    if source_mentions(source, "budget"):
        choices.append("Confirm budget authority only")
    else:
        choices.append("End early and skip the check")
    return choices


def _quiz(
    title: str,
    family: JobFamily,
    focus: list[tuple[str, SkillNode]],
    source: str,
    practice: PracticeActivity,
) -> list[QuizItem]:
    if family not in {JobFamily.ENABLEMENT, JobFamily.SELLER, JobFamily.UNKNOWN}:
        never: JobFamily = family
        raise ValueError(f"unsupported job family: {never}")
    items = _quiz_scenarios(family, focus, source)
    items.append(_quiz_criterion_item(focus, source, practice))
    if len(items) < 3:
        items.append(_quiz_transfer_item(focus))
    return items


def _quiz_scenarios(
    family: JobFamily, focus: list[tuple[str, SkillNode]], source: str
) -> list[QuizItem]:
    items: list[QuizItem] = []
    if family is JobFamily.SELLER and source_mentions(source, "price", "pricing"):
        noun = "chargeback pain" if "chargeback" in source.lower() else "the named pain"
        answer = "Ask for current process, pain, and success criteria"
        items.append(
            QuizItem(
                (
                    f"The other person asks what it costs after naming {noun}. "
                    "What is the next move before presenting price?"
                ),
                [
                    answer,
                    "Confirm budget authority only",
                    "Send a one-pager and wait",
                    "Offer a discount to create urgency"
                    if source_mentions(source, "discount")
                    else "Send a logo slide deck and wait",
                ],
                answer,
                "Discovery before commercial talk is measured in this module.",
            )
        )
    for verb, node in focus[:3]:
        if len(items) >= 3:
            break
        answer = _next_move_answer(verb, node, source)
        items.append(
            QuizItem(
                f"{_scenario_stem(node)} What is the next move?",
                [answer, *_plausible_moves(source, family, answer)],
                answer,
                f"The graph measures the verb {verb}.",
            )
        )
    if not items:
        items.append(
            QuizItem(
                "The source names the next work. What is the next move?",
                [
                    "The next step named in the source",
                    *_plausible_moves(source, family, "The next step named in the source"),
                ],
                "The next step named in the source",
                "Skills come from this source, not a generic seller template.",
            )
        )
    return items


def _quiz_criterion_item(
    focus: list[tuple[str, SkillNode]],
    source: str,
    practice: PracticeActivity,
) -> QuizItem:
    verbs = [verb for verb, _ in focus]
    criterion = practice.success_criteria[0] if practice.success_criteria else (
        "The practice stays in the domain of the source."
    )
    for line in practice.success_criteria:
        if any(verb in line.lower() for verb in verbs):
            criterion = line
            break
    stem = _scenario_stem(focus[0][1]) if focus else "The practice drill finished."
    return QuizItem(
        f"{stem} Which success criterion was met?",
        [
            criterion,
            "Attendance at the webinar",
            "A smile sheet score of 4.5",
            "Number of slides reviewed",
        ],
        criterion,
        f"Practice already named this criterion: {criterion}",
    )


def _quiz_transfer_item(focus: list[tuple[str, SkillNode]]) -> QuizItem:
    verb_list = (
        ", ".join(dict.fromkeys(verb for verb, _ in focus)) if focus else "practice"
    )
    return QuizItem(
        "The live opportunity is next. Which transfer move fits this module?",
        [
            "Guided practice with a checklist",
            "Company history",
            "A recorded keynote",
            "A policy acknowledgment",
        ],
        "Guided practice with a checklist",
        f"Practice is where the skill graph becomes behavior. Verbs: {verb_list}.",
    )


def _scenario_stem(node: SkillNode) -> str:
    text = node.name.strip().rstrip(".")
    return f"{_cap(text)} is the live situation."


def _next_move_answer(verb: str, node: SkillNode, source: str) -> str:
    name = node.name.strip()
    first = name.split(None, 1)[0].lower() if name else ""
    if first == verb or first in _LEADING_VERBS:
        return name
    return _cap(_verb_complement(verb, node, source))


def _plausible_moves(source: str, family: JobFamily, exclude: str) -> list[str]:
    if family is JobFamily.SELLER:
        pool = [
            "Send a logo slide deck and wait",
            "Skip discovery and pitch the full catalog",
            "End early and skip the check",
        ]
        if source_mentions(source, "discount"):
            pool.insert(1, "Offer a discount to create urgency")
    elif family is JobFamily.ENABLEMENT:
        pool = [
            "Send a logo slide deck and wait",
            "Skip practice and read the policy aloud",
            "End early and skip the check",
        ]
    elif family is JobFamily.UNKNOWN:
        pool = _stock_choices(source)
    else:
        never: JobFamily = family
        raise ValueError(f"unsupported job family: {never}")
    return [item for item in pool if item != exclude][:3]


