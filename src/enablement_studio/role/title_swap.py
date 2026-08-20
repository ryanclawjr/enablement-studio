from __future__ import annotations

from dataclasses import replace

from enablement_studio.models import RoleEnablement
from enablement_studio.role.family import JobFamily, classify_job_family

AE_SELLER_MARKERS = (
    "before presenting price",
    "buyer facts written in the crm",
    "current process, pain, and success criteria",
    "four open questions before any price",
    "cautious buyer",
)

SWAP_TITLE = "Account Executive"


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


def apply_title_swap_validity(role: RoleEnablement, source: str) -> RoleEnablement:
    family = classify_job_family(source, role.role_title)
    invalid = family is not JobFamily.SELLER and fails_title_swap(role)
    if role.invalid == invalid:
        return role
    return replace(role, invalid=invalid)
