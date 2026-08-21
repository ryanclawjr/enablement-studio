from __future__ import annotations

from enablement_studio.models import EngineName, Product, artifact_map
from enablement_studio.role import generate_role
from enablement_studio.session import (
    SQLITE_HEADER,
    close_ephemeral_store,
    dump_store,
    open_ephemeral_store,
)


def _save_role(store, job_text: str):
    role = generate_role(job_text)
    return store.save_run(
        project="default",
        product=Product.ROLE,
        title=role.role_title,
        input_text=job_text,
        engine=EngineName.OFFLINE,
        artifacts=artifact_map(role),
    )


def test_dumped_store_blob_reopened_via_open_ephemeral_store_reads_saved_run(
    job_text: str,
) -> None:
    store = open_ephemeral_store()
    try:
        saved = _save_role(store, job_text)
        blob = dump_store(store)
    finally:
        close_ephemeral_store(store)

    assert blob.startswith(SQLITE_HEADER)
    reopened = open_ephemeral_store(blob)
    try:
        loaded = reopened.get_run(saved.id)
        assert loaded.id == 1
        assert loaded.title == saved.title
        assert "skill_graph" in loaded.artifacts
        assert loaded.input_text == job_text
    finally:
        close_ephemeral_store(reopened)


def test_dump_store_blob_is_a_standalone_database_after_wal(job_text: str) -> None:
    store = open_ephemeral_store()
    try:
        with store.connect() as connection:
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
            assert str(mode[0]).lower() == "wal"
        saved = _save_role(store, job_text)
        blob = dump_store(store)
    finally:
        close_ephemeral_store(store)

    assert blob.startswith(SQLITE_HEADER)
    reopened = open_ephemeral_store(blob)
    try:
        assert reopened.get_run(saved.id).id == 1
        assert reopened.list_runs()[0].version == 1
    finally:
        close_ephemeral_store(reopened)


def test_open_ephemeral_store_skips_nonsqlite_blob() -> None:
    store = open_ephemeral_store(b"not a database at all")
    try:
        assert store.list_runs() == []
    finally:
        close_ephemeral_store(store)


def test_open_ephemeral_store_skips_utf8_mangled_sqlite_blob(job_text: str) -> None:
    store = open_ephemeral_store()
    try:
        _save_role(store, job_text)
        blob = dump_store(store)
    finally:
        close_ephemeral_store(store)

    mangled = blob.decode("utf-8", errors="replace").encode("utf-8")
    assert mangled != blob
    assert mangled.startswith(SQLITE_HEADER)

    recovered = open_ephemeral_store(mangled)
    try:
        assert recovered.list_runs() == []
    finally:
        close_ephemeral_store(recovered)


def test_open_ephemeral_store_skips_header_corrupted_sqlite_blob(job_text: str) -> None:
    store = open_ephemeral_store()
    try:
        _save_role(store, job_text)
        blob = dump_store(store)
    finally:
        close_ephemeral_store(store)

    corrupted = b"\x00\x00\x00\x00\x00\x00\x00\x00" + blob[8:]
    recovered = open_ephemeral_store(corrupted)
    try:
        assert recovered.list_runs() == []
    finally:
        close_ephemeral_store(recovered)
