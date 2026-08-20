"""Frozen copy of the v0 AE seller template. Used to prove the title-swap test."""

from __future__ import annotations

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


def canned_ae_template_role(
    title: str = "Solution Architect Enablement Business Partner",
) -> RoleEnablement:
    """Today's failure: paste any title onto discovery / price / CRM next-step."""
    return RoleEnablement(
        example_data=False,
        source_note=SOURCE_NOTE,
        role_title=title,
        skill_graph=SkillGraph(
            nodes=[
                SkillNode(
                    "buyer-context",
                    "Buyer and business context",
                    "foundation",
                    "Who the buyer is, what the business sells, and what 'good' looks like.",
                ),
                SkillNode(
                    "discovery",
                    "Discovery",
                    "core",
                    "Ask for current process, pain, stakeholders, and success criteria before pitching.",
                ),
                SkillNode(
                    "crm-hygiene",
                    "CRM and pipeline hygiene",
                    "foundation",
                    "Log next steps, stage, and evidence so coaching is possible.",
                ),
            ],
            edges=[SkillEdge("buyer-context", "discovery", "prerequisite")],
        ),
        objectives=[
            LearningObjective(
                "lo-1",
                f"Given a realistic {title} scenario, the learner will demonstrate "
                "discovery in language a buyer can use.",
                "discovery",
                "a live role-play scored against a behavior checklist",
            )
        ],
        outline=[
            ModuleBlock("0–5", "Hook and outcome", f"Open with a missed {title} moment."),
            ModuleBlock("5–15", "Model the skill", "Worked example of discovery."),
            ModuleBlock("15–25", "Guided practice", "Pairs run a 6-minute drill."),
            ModuleBlock("25–30", "Assessment and transfer", "Two-item check."),
        ],
        practice=PracticeActivity(
            title="12-minute discovery drill",
            scenario=(
                f"You are an {title}. The other person is a cautious buyer. "
                "Source cue: run a first conversation."
            ),
            instructions=[
                "Spend the first four minutes only on questions. No product claims.",
                "Map two buyer facts to discovery before you propose anything.",
                "Close on one dated next step the buyer repeats back.",
            ],
            success_criteria=[
                "At least four open questions before any price or feature talk.",
                "Buyer can restate the problem in their own words.",
                "Next step has an owner and a date.",
            ],
        ),
        quiz=[
            QuizItem(
                f"What should an {title} do before presenting price?",
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
                "Which artifact proves discovery happened?",
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
        ],
    )
