"""Post-hydrate PRODUCT guards for the LLM path.

Role stock-lines live next to the title-swap test (same invalid flag).
Call and Critic domain misses fall back to offline so the user still gets
a usable run. engine.py calls apply_llm_guards instead of copying these ifs.
"""

from __future__ import annotations

from enablement_studio.models import (
    CallCoaching,
    LessonCritique,
    Product,
    ProductOutput,
    RoleEnablement,
)
from enablement_studio.role.title_swap import apply_title_swap_validity

_CLINICAL_SOURCE = (
    "ehr",
    "nurse",
    "skills lab",
    "skills-lab",
    "medication",
    "allergy",
    " mar",
    "chart",
)
_MONEY_COACH = (
    "how money moves",
    "rate card",
    "mention a rate",
    "discovery-before-rate",
    "promo pricing",
    "crm",
)
_WAREHOUSE_SOURCE = ("pallet", "warehouse", "pallet-jack", "pallet jack")
_BUYER_REWRITE = ("weekend cash", "cautious buyer", "small-business owner", "buyer")


def apply_llm_guards(
    product: Product, output: ProductOutput, source: str
) -> ProductOutput | None:
    match product:
        case Product.ROLE:
            if not isinstance(output, RoleEnablement):
                raise TypeError("role hydrate produced a non-role object")
            return apply_title_swap_validity(output, source)
        case Product.CALL:
            if not isinstance(output, CallCoaching):
                raise TypeError("call hydrate produced a non-call object")
            return output if call_fits_source(output, source) else None
        case Product.CRITIC:
            if not isinstance(output, LessonCritique):
                raise TypeError("critic hydrate produced a non-critic object")
            return output if critic_fits_source(output, source) else None
        case _:
            never: Product = product
            raise ValueError(f"unsupported product: {never}")


def call_fits_source(output: CallCoaching, source: str) -> bool:
    hay = source.lower()
    if not any(token in hay for token in _CLINICAL_SOURCE):
        return True
    blob = _call_blob(output)
    return not any(token in blob for token in _MONEY_COACH)


def critic_fits_source(output: LessonCritique, source: str) -> bool:
    hay = source.lower()
    if not any(token in hay for token in _WAREHOUSE_SOURCE):
        return True
    rewrite = output.rewrite.replacement.lower()
    return not any(token in rewrite for token in _BUYER_REWRITE)


def _call_blob(output: CallCoaching) -> str:
    parts = [
        output.call_title,
        output.enablement_fix.title,
        output.enablement_fix.problem,
        output.enablement_fix.fix,
        output.enablement_fix.measure,
        *output.signals,
    ]
    for note in output.notes:
        parts.extend([note.headline, note.body])
    return " ".join(parts).lower()
