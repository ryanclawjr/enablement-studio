from __future__ import annotations

from pathlib import Path

from enablement_studio.models import EngineName, Product, artifact_map
from enablement_studio.role import generate_role
from enablement_studio.store import Store


def test_schema_creates_required_tables(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    names = set(store.iter_table_names())
    assert {"projects", "runs", "artifacts"} <= names


def test_schema_files_match() -> None:
    repo = Path(__file__).resolve().parents[1]
    packaged = (repo / "src/enablement_studio/store/schema.sql").read_text(encoding="utf-8")
    checked_in = (repo / "data/schema.sql").read_text(encoding="utf-8")
    assert packaged == checked_in
    assert "version INTEGER NOT NULL" in checked_in
    assert "invalid INTEGER NOT NULL DEFAULT 0" in checked_in


def test_save_run_increments_version(tmp_path: Path, job_text: str) -> None:
    store = Store(tmp_path / "test.db")
    first = generate_role(job_text)
    run_a = store.save_run(
        project="example",
        product=Product.ROLE,
        title=first.role_title,
        input_text=job_text,
        engine=EngineName.OFFLINE,
        artifacts=artifact_map(first),
    )
    run_b = store.save_run(
        project="example",
        product=Product.ROLE,
        title=first.role_title,
        input_text=job_text,
        engine=EngineName.OFFLINE,
        artifacts=artifact_map(first),
    )
    assert run_a.version == 1
    assert run_b.version == 2
    assert run_a.id != run_b.id
    loaded = store.get_run(run_a.id)
    assert "skill_graph" in loaded.artifacts
    assert "result" in loaded.artifacts
    listed = store.list_runs(project="example", product=Product.ROLE)
    assert [item.id for item in listed] == [run_a.id, run_b.id]
