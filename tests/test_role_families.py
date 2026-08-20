from __future__ import annotations

from enablement_studio.engine import generate
from enablement_studio.models import EngineName, Product, artifact_map
from enablement_studio.paths import find_fixture
from enablement_studio.role import generate_role
from enablement_studio.role.family import JobFamily, classify_job_family
from enablement_studio.store import Store

AE_STOCK = (
    "before presenting price",
    "offer a discount",
    "weekend cash",
    "buyer facts written in the crm",
    "sa teams they support",
)

LEARNER_JOBS = (
    "eval_instructional_designer_job.txt",
    "eval_learning_experience_designer_job.txt",
    "eval_customer_education_lead_job.txt",
    "eval_director_training_job.txt",
    "eval_nurse_educator_job.txt",
)


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


def test_instructional_designer_has_no_enablement_word() -> None:
    text = _read("eval_instructional_designer_job.txt")
    assert "enablement" not in text.lower()
    role = generate_role(text)
    assert classify_job_family(text, role.role_title) is JobFamily.ENABLEMENT
    assert role.skill_graph.nodes
    assert role.invalid is False
    blob = _blob(role)
    for phrase in AE_STOCK:
        assert phrase not in blob, phrase
    assert "sa teams they support" not in blob


def test_learner_facing_jobs_are_enablement_not_ae_dump() -> None:
    for name in LEARNER_JOBS:
        text = _read(name)
        role = generate_role(text)
        assert classify_job_family(text, role.role_title) is JobFamily.ENABLEMENT, name
        assert role.skill_graph.nodes, name
        assert role.invalid is False, name
        blob = _blob(role)
        for phrase in AE_STOCK:
            if phrase == "sa teams they support":
                continue
            assert phrase not in blob, f"{name}: {phrase}"
        assert "sa teams they support" not in blob, name
        assert "solution architect" not in blob, name


def test_warehouse_sop_is_unknown_invalid_without_ae_quiz() -> None:
    text = _read("eval_warehouse_sop.txt")
    role = generate_role(text)
    assert classify_job_family(text, role.role_title) is JobFamily.UNKNOWN
    assert role.invalid is True
    blob = _blob(role)
    for phrase in AE_STOCK:
        assert phrase not in blob, phrase
    assert "pallet" in blob or "pick" in blob or "pack" in blob


def test_ai_transformation_owner_is_unknown_invalid() -> None:
    text = _read("eval_ai_transformation_owner_job.txt")
    role = generate_role(text)
    assert classify_job_family(text, role.role_title) is JobFamily.UNKNOWN
    assert role.invalid is True
    blob = _blob(role)
    for phrase in AE_STOCK:
        assert phrase not in blob, phrase


def test_empty_graph_is_invalid() -> None:
    text = "EXAMPLE DATA\nJob title: Director, Training\nHello from a thin posting."
    role = generate_role(text)
    assert classify_job_family(text, role.role_title) is JobFamily.ENABLEMENT
    assert not role.skill_graph.nodes
    assert role.invalid is True


def test_hybrid_ae_enablement_is_not_empty_valid() -> None:
    thin = "EXAMPLE DATA\nJob title: Account Executive, Sales Enablement\n"
    thin_role = generate_role(thin)
    assert classify_job_family(thin, thin_role.role_title) is JobFamily.ENABLEMENT
    assert not (thin_role.skill_graph.nodes and thin_role.invalid is False)

    text = _read("eval_ae_sales_enablement_hybrid_job.txt")
    role = generate_role(text)
    assert classify_job_family(text, role.role_title) is JobFamily.ENABLEMENT
    assert role.skill_graph.nodes
    assert role.invalid is False
    blob = _blob(role)
    assert "before presenting price" not in blob
    assert "offer a discount" not in blob
    assert any(
        token in blob
        for token in ("onboarding", "gap", "package", "practice")
    )


def test_field_sa_may_stay_seller_without_price_quiz() -> None:
    text = _read("eval_field_solution_architect_job.txt")
    role = generate_role(text)
    assert classify_job_family(text, role.role_title) is JobFamily.SELLER
    assert role.invalid is False
    blob = _blob(role)
    assert "before presenting price" not in blob
    assert "offer a discount" not in blob
    assert "weekend cash" not in blob
    assert "discovery" in blob


def test_unknown_invalid_run_is_persisted(tmp_path) -> None:
    text = _read("eval_ai_transformation_owner_job.txt")
    role = generate_role(text)
    output, engine = generate(Product.ROLE, text)
    assert engine is EngineName.OFFLINE
    assert output.invalid is True
    store = Store(tmp_path / "test.db")
    run = store.save_run(
        project="eval",
        product=Product.ROLE,
        title=role.role_title,
        input_text=text,
        engine=engine,
        artifacts=artifact_map(role),
        invalid=role.invalid,
    )
    assert store.get_run(run.id).invalid is True
