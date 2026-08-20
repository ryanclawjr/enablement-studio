from __future__ import annotations

import re

from enablement_studio.paths import find_fixture
from enablement_studio.role import (
    EnablementFrame,
    classify_enablement_frame,
    classify_job_family,
    generate_role,
)
from enablement_studio.role.extract import extract_work_units
from enablement_studio.role.family import JobFamily

_TITLE_RECOGNITION = re.compile(
    r"which move best lets a(?:n)?\s+|which move best lets someone",
    re.I,
)
_STOP = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "the",
    "to",
    "with",
    "of",
    "in",
    "on",
    "or",
}


def _read(name: str) -> str:
    return find_fixture(name).read_text(encoding="utf-8")


def _blob(role) -> str:
    parts = [role.role_title, role.practice.title, role.practice.scenario]
    parts.extend(role.practice.instructions)
    parts.extend(role.practice.success_criteria)
    for node in role.skill_graph.nodes:
        parts.extend([node.id, node.name, node.detail])
    for item in role.objectives:
        parts.append(item.statement)
    for item in role.quiz:
        parts.extend([item.question, item.answer, item.rationale, *item.choices])
    return " ".join(parts).lower()


def _name_grounded(name: str, source: str) -> bool:
    hay = re.sub(r"\s+", " ", source).lower()
    needle = re.sub(r"\s+", " ", name).lower()
    if needle in hay:
        return True
    words = [word for word in re.findall(r"[a-z0-9']+", needle) if word not in _STOP]
    if not words:
        return False
    if len(words) == 1:
        return words[0] in hay
    for size in range(len(words), 1, -1):
        for index in range(0, len(words) - size + 1):
            span = " ".join(words[index : index + size])
            if span in hay:
                return True
    return False


def _shares_practice_criterion(role) -> bool:
    criteria = [line.lower() for line in role.practice.success_criteria]
    for item in role.quiz:
        blob = f"{item.question} {item.answer} {item.rationale}".lower()
        if any(line in blob for line in criteria):
            return True
        for line in criteria:
            verbs = set(re.findall(r"[a-z]+", line)) & {
                "measure",
                "measures",
                "design",
                "diagnose",
                "package",
                "prepare",
                "coach",
                "teach",
                "demonstrate",
                "map",
                "handle",
                "close",
                "log",
                "run",
                "artifact",
                "criterion",
                "verbs",
            }
            if verbs and any(verb in blob for verb in verbs):
                return True
    return False


def test_harborline_extract_is_rich_enough_to_drop_catalog_fallback() -> None:
    text = _read("example_account_executive_job.txt")
    units = extract_work_units(text)
    blob = " ".join(units).lower()
    assert any("discovery" in unit.lower() for unit in units)
    assert "price" in blob or "objection" in blob
    assert "crm" in blob
    assert not any("no live customer" in unit.lower() for unit in units)
    role = generate_role(text)
    assert role.invalid is False
    assert any(node.id == "discovery" for node in role.skill_graph.nodes)


def test_skill_node_names_are_source_spans() -> None:
    names = (
        "example_account_executive_job.txt",
        "eval_stripe_sa_enablement_job.txt",
        "eval_nurse_educator_job.txt",
        "eval_instructional_designer_job.txt",
        "eval_warehouse_sop.txt",
    )
    for name in names:
        text = _read(name)
        role = generate_role(text)
        assert role.skill_graph.nodes, name
        for node in role.skill_graph.nodes:
            assert _name_grounded(node.name, text), f"{name}: {node.name!r}"


def test_harborline_disclaimer_is_not_a_skill_node() -> None:
    text = _read("example_account_executive_job.txt")
    role = generate_role(text)
    for node in role.skill_graph.nodes:
        blob = f"{node.id} {node.name} {node.detail}".lower()
        assert "no live customer book is required" not in node.name.lower()
        assert "no live customer book" not in blob


def test_quiz_is_application_not_title_recognition() -> None:
    names = (
        "example_account_executive_job.txt",
        "eval_stripe_sa_enablement_job.txt",
        "eval_nurse_educator_job.txt",
        "eval_instructional_designer_job.txt",
        "eval_warehouse_sop.txt",
        "eval_field_solution_architect_job.txt",
    )
    for name in names:
        role = generate_role(_read(name))
        questions = [item.question for item in role.quiz]
        recognition = [item for item in questions if _TITLE_RECOGNITION.search(item)]
        assert not recognition, f"{name}: {recognition}"
        assert _shares_practice_criterion(role), name


def test_enablement_frames_drive_practice_voice() -> None:
    designer_text = _read("eval_instructional_designer_job.txt")
    lxd_text = _read("eval_learning_experience_designer_job.txt")
    nurse_text = _read("eval_nurse_educator_job.txt")
    stripe_text = _read("eval_stripe_sa_enablement_job.txt")
    director = (
        "EXAMPLE DATA — fictional job posting.\n"
        "Job title: Director of Nursing Education\n"
        "- Coach new hires through a skills check\n"
        "- Record which steps still fail\n"
    )
    customer_ed = _read("eval_customer_education_lead_job.txt")

    assert classify_enablement_frame(designer_text) is EnablementFrame.DESIGNER
    assert classify_enablement_frame(lxd_text) is EnablementFrame.DESIGNER
    assert classify_enablement_frame(nurse_text) is EnablementFrame.EDUCATOR
    assert classify_enablement_frame(director) is EnablementFrame.EDUCATOR
    assert classify_enablement_frame(stripe_text) is EnablementFrame.PARTNER
    assert classify_enablement_frame(customer_ed) is EnablementFrame.EDUCATOR

    designer = generate_role(designer_text)
    nurse = generate_role(nurse_text)
    stripe = generate_role(stripe_text)
    director_role = generate_role(director)

    designer_blob = _blob(designer)
    nurse_blob = _blob(nurse)
    stripe_blob = _blob(stripe)
    director_blob = _blob(director_role)

    assert "sa teams they support" not in designer_blob
    assert "cautious buyer" not in designer_blob
    assert "designing instruction" in designer.practice.scenario.lower()
    assert "studio" in designer.practice.title.lower()

    assert "sa teams they support" not in nurse_blob
    assert "sa teams they support" not in director_blob
    assert "teaching" in nurse.practice.scenario.lower()
    assert "cautious buyer" not in nurse_blob

    assert "sa teams they support" in stripe_blob
    assert "storyboard" not in stripe.practice.title.lower()
    assert "storyboard studio" not in stripe_blob


def test_product_manager_without_enablement_work_is_unknown_invalid() -> None:
    text = (
        "EXAMPLE DATA — fictional job posting.\n"
        "Job title: Product Manager\n"
        "- Write the quarterly roadmap\n"
        "- Prioritize the backlog with engineering\n"
        "- Run sprint reviews\n"
    )
    role = generate_role(text)
    assert classify_job_family(text, role.role_title) is JobFamily.UNKNOWN
    assert role.invalid is True
