from __future__ import annotations

import re
from dataclasses import dataclass

from enablement_studio.models import (
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
from enablement_studio.textutil import (
    extract_bullets,
    extract_title,
    is_example_data,
    significant_terms,
    slug,
)

_LEVELS = ("foundation", "core", "performance")


@dataclass(frozen=True)
class SkillSeed:
    id: str
    name: str
    level: str
    keywords: tuple[str, ...]
    detail: str
    requires: tuple[str, ...] = ()


CATALOG: tuple[SkillSeed, ...] = (
    SkillSeed(
        "payment-fundamentals",
        "Payment fundamentals",
        "foundation",
        ("payment", "payments", "interchange", "processor", "merchant", "card"),
        "Authorization, settlement, and how a merchant account actually works.",
    ),
    SkillSeed(
        "buyer-context",
        "Buyer and business context",
        "foundation",
        ("small-business", "bakery", "owner", "smb", "prospect", "customer"),
        "Who the buyer is, what the business sells, and what 'good' looks like for them.",
    ),
    SkillSeed(
        "crm-hygiene",
        "CRM and pipeline hygiene",
        "foundation",
        ("crm", "salesforce", "pipeline", "forecast", "hubspot"),
        "Log next steps, stage, and evidence so coaching is possible.",
    ),
    SkillSeed(
        "discovery",
        "Discovery",
        "core",
        ("discover", "discovery", "needs", "pain", "qualify", "qualification"),
        "Ask for current process, pain, stakeholders, and success criteria before pitching.",
        ("buyer-context",),
    ),
    SkillSeed(
        "value-mapping",
        "Value mapping",
        "core",
        ("value", "roi", "outcome", "business case", "justify"),
        "Connect a product capability to a buyer outcome the prospect already named.",
        ("discovery",),
    ),
    SkillSeed(
        "demo",
        "Targeted demonstration",
        "core",
        ("demo", "demonstrate", "walkthrough", "product"),
        "Show only the path that proves the discovery notes.",
        ("discovery",),
    ),
    SkillSeed(
        "objection-handling",
        "Objection handling",
        "core",
        ("objection", "concern", "pushback", "price", "pricing", "competitor"),
        "Label the objection, isolate it, and answer with evidence—not a new pitch.",
        ("value-mapping",),
    ),
    SkillSeed(
        "negotiation",
        "Commercial negotiation",
        "performance",
        ("negotiat", "discount", "legal", "procurement", "terms"),
        "Trade, do not give. Protect margin while keeping a mutual plan.",
        ("objection-handling",),
    ),
    SkillSeed(
        "close",
        "Mutual-plan close",
        "performance",
        ("close", "closing", "next step", "commit", "agreement"),
        "Leave with a dated next step both sides can see.",
        ("discovery",),
    ),
    SkillSeed(
        "coaching",
        "Call coaching",
        "performance",
        ("coach", "coaching", "enablement", "manager"),
        "Give one observable behavior to change on the next call.",
        ("discovery",),
    ),
)


def generate_role(text: str) -> RoleEnablement:
    source = text.strip()
    if not source:
        raise ValueError("role input is empty")
    title = extract_title(source, "Role from source text")
    bullets = extract_bullets(source)
    terms = significant_terms(source)
    nodes, edges = _skill_graph(source, bullets, terms)
    objectives = _objectives(title, nodes)
    outline = _outline(title, nodes)
    practice = _practice(title, nodes, bullets)
    quiz = _quiz(title, nodes)
    return RoleEnablement(
        example_data=is_example_data(source),
        source_note=SOURCE_NOTE,
        role_title=title,
        skill_graph=SkillGraph(nodes=nodes, edges=edges),
        objectives=objectives,
        outline=outline,
        practice=practice,
        quiz=quiz,
    )


def _skill_graph(
    source: str, bullets: list[str], terms: set[str]
) -> tuple[list[SkillNode], list[SkillEdge]]:
    lowered = source.lower()
    matched: list[SkillSeed] = []
    for seed in CATALOG:
        if any(keyword in lowered for keyword in seed.keywords):
            matched.append(seed)
    if not matched:
        matched = [seed for seed in CATALOG if seed.level in {"foundation", "core"}][:4]

    extra_nodes: list[SkillNode] = []
    for bullet in bullets:
        if _bullet_covered(bullet, matched):
            continue
        name = _skill_name_from_bullet(bullet)
        if any(name.lower() == seed.name.lower() for seed in matched):
            continue
        extra_nodes.append(
            SkillNode(
                id=slug(name),
                name=name,
                level="core" if terms else "foundation",
                detail=bullet,
            )
        )
        if len(extra_nodes) == 2:
            break

    required_ids = {seed.id for seed in matched}
    for seed in matched:
        required_ids.update(seed.requires)
    seeds = [seed for seed in CATALOG if seed.id in required_ids]

    nodes = [
        SkillNode(id=seed.id, name=seed.name, level=seed.level, detail=seed.detail)
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


def _bullet_covered(bullet: str, matched: list[SkillSeed]) -> bool:
    lowered = bullet.lower()
    return any(any(keyword in lowered for keyword in seed.keywords) for seed in matched)


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


def _objectives(title: str, nodes: list[SkillNode]) -> list[LearningObjective]:
    catalog_ids = {seed.id for seed in CATALOG}
    focus = [
        node
        for node in nodes
        if node.id in catalog_ids and node.level in {"core", "performance"}
    ][:4]
    if len(focus) < 3:
        focus = [node for node in nodes if node.level in {"core", "performance"}][:4]
    if len(focus) < 3:
        focus = nodes[:3]
    verbs = {
        "foundation": "explain",
        "core": "demonstrate",
        "performance": "run",
    }
    objectives: list[LearningObjective] = []
    for index, node in enumerate(focus, start=1):
        verb = verbs[node.level]
        measure = {
            "foundation": "a 90-second teach-back scored on a 3-point rubric",
            "core": "a live role-play scored against a behavior checklist",
            "performance": "a recorded call review with one observable next-step",
        }[node.level]
        statement = (
            f"Given a realistic {title} scenario, the learner will {verb} "
            f"{node.name.lower()} in language a buyer can use."
        )
        objectives.append(
            LearningObjective(
                id=f"lo-{index}",
                statement=statement,
                skill_id=node.id,
                measure=measure,
            )
        )
    return objectives


def _catalog_core_name(nodes: list[SkillNode]) -> str:
    catalog_ids = {seed.id for seed in CATALOG}
    return next(
        (
            node.name.lower()
            for node in nodes
            if node.id in catalog_ids and node.level == "core"
        ),
        next((node.name.lower() for node in nodes if node.level == "core"), "the core skill"),
    )


def _outline(title: str, nodes: list[SkillNode]) -> list[ModuleBlock]:
    core = _catalog_core_name(nodes)
    return [
        ModuleBlock(
            "0–5",
            "Hook and outcome",
            f"Open with a missed {title} moment and name the one behavior this 30 minutes will change.",
        ),
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


def _practice(title: str, nodes: list[SkillNode], bullets: list[str]) -> PracticeActivity:
    skill = _catalog_core_name(nodes)
    context = bullets[0] if bullets else f"a typical {title} conversation"
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
        ],
        success_criteria=[
            "At least four open questions before any price or feature talk.",
            "Buyer can restate the problem in their own words.",
            "Next step has an owner and a date.",
        ],
    )


def _quiz(title: str, nodes: list[SkillNode]) -> list[QuizItem]:
    first = nodes[0].name if nodes else "the foundation skill"
    core = next((node.name for node in nodes if node.level == "core"), first)
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
            "Performance skills are measured in the work, not in the classroom.",
        ),
    ]
