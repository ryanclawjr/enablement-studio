from __future__ import annotations

from dataclasses import replace

from enablement_studio.models import RoleEnablement
from enablement_studio.role.family import JobFamily, classify_job_family
from enablement_studio.textutil import extract_title

AE_SELLER_MARKERS = (
    "before presenting price",
    "buyer facts written in the crm",
    "current process, pain, and success criteria",
    "four open questions before any price",
    "cautious buyer",
)

SWAP_TITLE = "Account Executive"

# Offline already gates these nouns. After hydrate, the same lines are a miss
# unless the source actually has them — even when the five AE markers above
# are absent (a novel seller dump).
STOCK_LINE_GATES = (
    ("before presenting price", ("price", "pricing")),
    ("offer a discount", ("discount",)),
    ("weekend cash", ("weekend cash",)),
    ("cautious buyer", ("buyer", "cautious buyer")),
)


def role_body_text(role: RoleEnablement) -> str:
    """Skill graph, practice, and quiz — the title is ignored."""
    parts: list[str] = []
    for node in role.skill_graph.nodes:
        parts.extend([node.id, node.name, node.detail])
    for edge in role.skill_graph.edges:
        parts.extend([edge.source, edge.target, edge.relation])
    parts.extend(
        [
            role.practice.title,
            role.practice.scenario,
            *role.practice.instructions,
            *role.practice.success_criteria,
        ]
    )
    for item in role.quiz:
        parts.extend([item.question, item.answer, item.rationale, *item.choices])
    return " ".join(parts)


def title_swap(role: RoleEnablement, title: str = SWAP_TITLE) -> RoleEnablement:
    return replace(role, role_title=title)


def looks_like_ae_seller_module(role: RoleEnablement) -> bool:
    blob = role_body_text(role).lower()
    hits = sum(1 for marker in AE_SELLER_MARKERS if marker in blob)
    return hits >= 2


def fails_title_swap(role: RoleEnablement) -> bool:
    """True when swapping the title for Account Executive still yields a seller module."""
    return looks_like_ae_seller_module(title_swap(role))


def role_validity_blob(role: RoleEnablement) -> str:
    statements = " ".join(item.statement for item in role.objectives)
    return f"{role_body_text(role)} {statements}".lower()


def has_ungated_stock_lines(role: RoleEnablement, source: str) -> bool:
    blob = role_validity_blob(role)
    hay = source.lower()
    return any(
        line in blob and not any(noun in hay for noun in nouns)
        for line, nouns in STOCK_LINE_GATES
    )


def apply_title_swap_validity(role: RoleEnablement, source: str) -> RoleEnablement:
    # Family from THIS source. An LLM can title an ID job "Account Executive"
    # and would otherwise skip portability / stock-line checks.
    source_title = extract_title(source, "")
    family = classify_job_family(source, source_title)
    empty = not role.skill_graph.nodes
    unknown = family is JobFamily.UNKNOWN
    portable = family is not JobFamily.SELLER and fails_title_swap(role)
    seller_dump = family is not JobFamily.SELLER and looks_like_ae_seller_module(role)
    stock = has_ungated_stock_lines(role, source)
    invalid = empty or unknown or portable or seller_dump or stock
    if role.invalid == invalid:
        return role
    return replace(role, invalid=invalid)
