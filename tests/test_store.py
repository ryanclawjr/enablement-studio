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


def test_save_run_retries_version_race(tmp_path: Path, job_text: str) -> None:
    store = Store(tmp_path / "test.db")
    first = generate_role(job_text)
    store.save_run(
        project="example",
        product=Product.ROLE,
        title=first.role_title,
        input_text=job_text,
        engine=EngineName.OFFLINE,
        artifacts=artifact_map(first),
    )
    calls = {"n": 0}
    real_next = Store.next_version

    def collide_once(project_id: int, product: Product) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            return 1
        return real_next(store, project_id, product)

    store.next_version = collide_once
    run = store.save_run(
        project="example",
        product=Product.ROLE,
        title=first.role_title,
        input_text=job_text,
        engine=EngineName.OFFLINE,
        artifacts=artifact_map(first),
    )
    assert run.version == 2


def test_save_run_reads_invalid_from_artifact_when_omitted(
    tmp_path: Path,
) -> None:
    from enablement_studio.paths import find_fixture

    text = find_fixture("eval_warehouse_sop.txt").read_text(encoding="utf-8")
    role = generate_role(text)
    assert role.invalid is True
    store = Store(tmp_path / "test.db")
    run = store.save_run(
        project="eval",
        product=Product.ROLE,
        title=role.role_title,
        input_text=text,
        engine=EngineName.OFFLINE,
        artifacts=artifact_map(role),
    )
    assert run.invalid is True
    assert store.get_run(run.id).invalid is True


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
