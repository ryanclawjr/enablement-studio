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
from enablement_studio.role.family import JobFamily, classify_job_family
from enablement_studio.role.title_swap import apply_title_swap_validity
from enablement_studio.textutil import (
    extract_bullets,
    extract_title,
    is_example_data,
    is_public_posting,
    significant_terms,
    slug,
)

_LEVELS = ("foundation", "core", "performance")
_LEVEL_VERBS = {
    "foundation": "explain",
    "core": "demonstrate",
    "performance": "run",
}
_OBJECTIVE_OBJECTS = {
    "discovery": "discovery",
    "demo": "a targeted demonstration",
    "value-mapping": "value to a buyer outcome",
    "objection-handling": "objections",
    "gap-analysis": "enablement gap analysis",
    "onboarding-design": "SA onboarding",
    "technical-packaging": "technical content for a sales audience",
    "launch-readiness": "launch readiness",
    "impact-metrics": "enablement impact",
}


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
        ("small-business", "bakery", "owner", "smb", "prospect", "customer"),
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
        ("negotiate", "negotiation", "discount", "legal", "procurement", "terms"),
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
        "SA onboarding design",
        "core",
        ("onboarding", "just-in-time", "learning resource", "learning resources"),
        "Design onboarding and ongoing learning for the SA audience.",
        "design",
        ("gap-analysis",),
    ),
    SkillSeed(
        "technical-packaging",
        "Technical packaging for a sales audience",
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
        "Turn technical product information into something a sales audience can use.",
        "package",
        ("gap-analysis",),
    ),
    SkillSeed(
        "launch-readiness",
        "Launch readiness",
        "core",
        ("launch", "readiness", "product release", "technical readiness"),
        "Get SA teams technically ready before a product launch.",
        "prepare",
        ("technical-packaging",),
    ),
    SkillSeed(
        "impact-metrics",
        "Enablement impact metrics",
        "performance",
        ("metric", "metrics", "analytics", "impact", "measurable"),
        "Track whether enablement changed productivity or readiness.",
        "measure",
        ("onboarding-design",),
    ),
)

CATALOG = SELLER_CATALOG


def generate_role(text: str) -> RoleEnablement:
    source = text.strip()
    if not source:
        raise ValueError("role input is empty")
    title = extract_title(source, "Role from source text")
    family = classify_job_family(source, title)
    catalog = _catalog_for(family)
    bullets = extract_bullets(source)
    terms = significant_terms(source)
    nodes, edges = _skill_graph(source, bullets, terms, catalog)
    focus = _focus(nodes, catalog)
    objectives = _objectives(title, family, focus)
    outline = _outline(title, family, focus)
    practice = _practice(title, family, focus, bullets)
    quiz = _quiz(title, family, focus)
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
    never: JobFamily = family
    raise ValueError(f"unsupported job family: {never}")


def keyword_in(hay: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in hay
    return re.search(rf"\b{re.escape(keyword)}s?\b", hay) is not None


def _skill_graph(
    source: str,
    bullets: list[str],
    terms: set[str],
    catalog: tuple[SkillSeed, ...],
) -> tuple[list[SkillNode], list[SkillEdge]]:
    lowered = source.lower()
    matched: list[SkillSeed] = []
    for seed in catalog:
        if any(keyword_in(lowered, keyword) for keyword in seed.keywords):
            matched.append(seed)
    if not matched and catalog is SELLER_CATALOG:
        matched = [seed for seed in catalog if seed.level in {"foundation", "core"}][:4]

    extra_nodes: list[SkillNode] = []
    if _want_extras(matched, catalog):
        for bullet in bullets:
            if _is_requirement_bullet(bullet) or _bullet_covered(bullet, matched):
                continue
            name = _skill_name_from_bullet(bullet)
            if any(name.lower() == seed.name.lower() for seed in matched):
                continue
            level = "core" if terms else "foundation"
            verb = _LEVEL_VERBS[level]
            extra_nodes.append(
                SkillNode(
                    id=slug(name),
                    name=name,
                    level=level,
                    detail=f"{verb} — {bullet}",
                )
            )
            if len(extra_nodes) == 2:
                break

    required_ids = {seed.id for seed in matched}
    for seed in matched:
        required_ids.update(seed.requires)
    seeds = [seed for seed in catalog if seed.id in required_ids]

    nodes = [
        SkillNode(
            id=seed.id,
            name=seed.name,
            level=seed.level,
            detail=f"{seed.verb} — {seed.detail}",
        )
        for seed in seeds
    ]
    nodes.extend(extra_nodes)
    nodes = _dedupe_nodes(nodes)

    edges: list[SkillEdge] = []
    ids = {node.id for node in nodes}
    for seed in seeds:
        for parent in seed.requires:
            if parent in ids and seed.id in ids:
                edges.append(SkillEdge(parent, seed.id, "prerequisite"))
    if extra_nodes:
        anchors = [node.id for node in nodes if node.level == "foundation"]
        parent = anchors[0] if anchors else nodes[0].id
        for extra in extra_nodes:
            if extra.id in ids:
                edges.append(SkillEdge(parent, extra.id, "supports"))
    return nodes, edges


def _want_extras(matched: list[SkillSeed], catalog: tuple[SkillSeed, ...]) -> bool:
    if catalog is ENABLEMENT_CATALOG and len(matched) >= 4:
        return False
    return True


def _is_requirement_bullet(bullet: str) -> bool:
    return bool(
        re.match(
            r"^(experience|ability|track record|proven|demonstrated|comfort|written)\b",
            bullet,
            flags=re.I,
        )
    )


def _bullet_covered(bullet: str, matched: list[SkillSeed]) -> bool:
    lowered = bullet.lower()
    return any(
        any(keyword_in(lowered, keyword) for keyword in seed.keywords)
        for seed in matched
    )


def _skill_name_from_bullet(bullet: str) -> str:
    cleaned = re.sub(r"^(?:must|should|will|able to)\s+", "", bullet, flags=re.I)
    cleaned = re.sub(r"[.]+$", "", cleaned)
    if len(cleaned) > 48:
        cleaned = cleaned[:45].rsplit(" ", 1)[0]
    return cleaned[0].upper() + cleaned[1:]


def _dedupe_nodes(nodes: list[SkillNode]) -> list[SkillNode]:
    seen: dict[str, SkillNode] = {}
    for node in nodes:
        seen.setdefault(node.id, node)
    ordered = sorted(seen.values(), key=lambda item: (_LEVELS.index(item.level), item.name))
    return ordered


def _article(title: str) -> str:
    return "an" if title[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


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
    title: str, family: JobFamily, focus: list[tuple[str, SkillNode]]
) -> list[LearningObjective]:
    if family is JobFamily.ENABLEMENT:
        audience = "for the SA teams they support"
    elif family is JobFamily.SELLER:
        audience = "in language a buyer can use"
    else:
        never: JobFamily = family
        raise ValueError(f"unsupported job family: {never}")
    measures = {
        "foundation": "a 90-second teach-back scored on a 3-point rubric",
        "core": "a live role-play scored against a behavior checklist",
        "performance": "a recorded call review with one observable next-step",
    }
    if family is JobFamily.ENABLEMENT:
        measures = {
            "foundation": "a scored gap-analysis brief a manager can inspect",
            "core": "a packaged enablement artifact scored against a checklist",
            "performance": "an impact metric with a baseline and a review date",
        }
    objectives: list[LearningObjective] = []
    for index, (verb, node) in enumerate(focus, start=1):
        focus_object = _OBJECTIVE_OBJECTS.get(node.id, node.name.lower())
        statement = (
            f"Given a realistic {title} scenario, the learner will {verb} "
            f"{focus_object} {audience}."
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


def _outline(
    title: str, family: JobFamily, focus: list[tuple[str, SkillNode]]
) -> list[ModuleBlock]:
    core = focus[0][1].name.lower() if focus else "the core skill"
    if family is JobFamily.ENABLEMENT:
        hook = (
            f"Open with an SA who cannot package a launch, then name the one "
            f"{title} behavior this 30 minutes will change."
        )
    elif family is JobFamily.SELLER:
        hook = (
            f"Open with a missed {title} moment and name the one behavior "
            "this 30 minutes will change."
        )
    else:
        never: JobFamily = family
        raise ValueError(f"unsupported job family: {never}")
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


def _practice(
    title: str,
    family: JobFamily,
    focus: list[tuple[str, SkillNode]],
    bullets: list[str],
) -> PracticeActivity:
    skill = focus[0][1].name.lower() if focus else "the core skill"
    verbs = list(dict.fromkeys(verb for verb, _ in focus))
    verb_list = ", ".join(verbs) if verbs else "practice"
    context = bullets[0] if bullets else f"a typical {title} conversation"
    if family is JobFamily.ENABLEMENT:
        instructions = [
                    f"{verb.capitalize()} {_OBJECTIVE_OBJECTS.get(node.id, node.name.lower())} from this source cue."
            for verb, node in focus[:3]
        ]
        if not instructions:
            instructions = ["Build one enablement artifact from the source cue."]
        return PracticeActivity(
            title=f"12-minute {skill} drill",
            scenario=(
                f"You are {_article(title)} {title} supporting solution architects. "
                f"Source cue: {context}"
            ),
            instructions=instructions,
            success_criteria=[
                f"The drill measures these verbs: {verb_list}.",
                "The output is an enablement artifact for SAs, not a buyer pitch.",
                "Onboarding design, technical packaging, or launch readiness is visible.",
            ],
        )
    if family is JobFamily.SELLER:
        return PracticeActivity(
            title=f"12-minute {skill} drill",
            scenario=(
                f"You are {_article(title)} {title}. The other person is a cautious buyer. "
                f"Source cue (example or user text): {context}"
            ),
            instructions=[
                "Spend the first four minutes only on questions. No product claims.",
                f"Map two buyer facts to {skill} before you propose anything.",
                "Close on one dated next step the buyer repeats back.",
                f"Observer checks the learner can {verb_list}.",
            ],
            success_criteria=[
                "At least four open questions before any price or feature talk.",
                "Buyer can restate the problem in their own words.",
                "Next step has an owner and a date.",
                f"Verbs on the checklist: {verb_list}.",
            ],
        )
    never: JobFamily = family
    raise ValueError(f"unsupported job family: {never}")


def _quiz(
    title: str, family: JobFamily, focus: list[tuple[str, SkillNode]]
) -> list[QuizItem]:
    if family is JobFamily.ENABLEMENT:
        items: list[QuizItem] = []
        for verb, node in focus[:3]:
            answer = f"{verb.capitalize()} from SA evidence in the field"
            items.append(
                QuizItem(
                    f"Which move best lets {_article(title)} {title} {verb} {_OBJECTIVE_OBJECTS.get(node.id, node.name.lower())}?",
                    [
                        answer,
                        "Offer a discount to create urgency",
                        "Send a logo slide deck and wait",
                        "Confirm budget authority only",
                    ],
                    answer,
                    f"The module measures the verb {verb} on {_OBJECTIVE_OBJECTS.get(node.id, node.name.lower())}.",
                )
            )
        items.append(
            QuizItem(
                "Which artifact proves enablement impact metrics happened?",
                [
                    "A recorded call with one observable next-step",
                    "Attendance at the webinar",
                    "A metric that measures adoption or launch readiness",
                    "A longer meeting",
                ],
                "A metric that measures adoption or launch readiness",
                "Impact is measured in the work, not in seat time.",
            )
        )
        return items
    if family is JobFamily.SELLER:
        first = focus[0][1].name if focus else "the foundation skill"
        core = next(
            (node.name for verb, node in focus if node.level == "core"),
            first,
        )
        verb_list = (
            ", ".join(dict.fromkeys(verb for verb, _ in focus)) if focus else "demonstrate"
        )
        return [
            QuizItem(
                f"What should {_article(title)} {title} do before presenting price?",
                [
                    "Confirm budget authority only",
                    "Ask for current process, pain, and success criteria",
                    "Send a one-pager and wait",
                    "Offer a discount to create urgency",
                ],
                "Ask for current process, pain, and success criteria",
                "Discovery before commercial talk is the first enablement rule in this module.",
            ),
            QuizItem(
                f"Which artifact proves {core.lower()} happened?",
                [
                    "A slide deck with the logo",
                    "A talk track memorized word-for-word",
                    "Buyer facts written in the CRM with a dated next step",
                    "A longer meeting",
                ],
                "Buyer facts written in the CRM with a dated next step",
                "If it is not written down, coaching cannot inspect it.",
            ),
            QuizItem(
                "A good 30-minute module spends most of its time on:",
                [
                    "Company history",
                    "Guided practice with a checklist",
                    "A recorded keynote",
                    "A policy acknowledgment",
                ],
                "Guided practice with a checklist",
                "Practice is where the skill graph becomes behavior.",
            ),
            QuizItem(
                f"Which measure fits a performance-level {title} objective?",
                [
                    "Attendance at the webinar",
                    "A smile sheet score of 4.5",
                    "A recorded call with one observable next-step",
                    "Number of slides reviewed",
                ],
                "A recorded call with one observable next-step",
                f"Performance skills are measured in the work. Verbs: {verb_list}.",
            ),
        ]
    never: JobFamily = family
    raise ValueError(f"unsupported job family: {never}")
