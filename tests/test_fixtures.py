from __future__ import annotations

from pathlib import Path

from enablement_studio.paths import find_fixture


def test_fixtures_are_marked_example() -> None:
    names = (
        "example_account_executive_job.txt",
        "example_sales_call.txt",
        "example_new_hire_lesson.md",
    )
    for name in names:
        text = find_fixture(name).read_text(encoding="utf-8")
        assert "EXAMPLE DATA" in text
        assert "fictional" in text.lower()


def test_eval_fixture_is_public_posting_not_example() -> None:
    text = find_fixture("eval_stripe_sa_enablement_job.txt").read_text(encoding="utf-8")
    assert "PUBLIC POSTING" in text
    assert "EXAMPLE DATA" not in text
    assert "fictional" not in text.lower()
    assert "8115022" in text
    assert "Solution Architect Enablement Business Partner" in text
    lowered = text.lower()
    assert "apply now" not in lowered
    assert "$" not in text
    assert "salary" not in lowered
    for banned in ("LAPC", "Autonoma", "IDN", "SIGNIT"):
        assert banned not in text


_EVAL_EXAMPLE = (
    "eval_instructional_designer_job.txt",
    "eval_learning_experience_designer_job.txt",
    "eval_customer_education_lead_job.txt",
    "eval_director_training_job.txt",
    "eval_nurse_educator_job.txt",
    "eval_warehouse_sop.txt",
    "eval_ae_sales_enablement_hybrid_job.txt",
    "eval_ai_transformation_owner_job.txt",
    "eval_field_solution_architect_job.txt",
    "eval_clean_discovery_call.txt",
    "eval_ehr_skills_lab_call.txt",
    "eval_aligned_interchange_lesson.md",
    "eval_pallet_jack_lesson.md",
)


def test_eval_family_fixtures_are_example_data() -> None:
    for name in _EVAL_EXAMPLE:
        text = find_fixture(name).read_text(encoding="utf-8")
        assert "EXAMPLE DATA" in text, name
        lowered = text.lower()
        assert "apply now" not in lowered
        assert "$" not in text
        assert "salary" not in lowered
        for banned in ("LAPC", "Autonoma", "IDN", "SIGNIT"):
            assert banned not in text, f"{name}: {banned}"


def test_cwd_fixture_does_not_shadow_package(tmp_path: Path, monkeypatch) -> None:
    from enablement_studio.paths import demo_text, find_fixture

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    decoy = fixtures / "example_account_executive_job.txt"
    decoy.write_text("EXAMPLE DATA — cwd decoy, not Harborline.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    path = find_fixture("example_account_executive_job.txt")
    text = path.read_text(encoding="utf-8")
    assert "Harborline" in text
    assert "cwd decoy" not in text
    assert "Harborline" in demo_text("role")
    assert path != decoy


def test_repo_and_package_fixtures_match() -> None:
    repo = Path(__file__).resolve().parents[1]
    packaged = repo / "src/enablement_studio/fixtures"
    public = repo / "fixtures"
    for name in public.iterdir():
        if name.is_file():
            assert (packaged / name.name).read_text(encoding="utf-8") == name.read_text(
                encoding="utf-8"
            )
