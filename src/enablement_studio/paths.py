from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def default_db_path() -> Path:
    override = os.environ.get("ENABLEMENT_DB")
    if override:
        return Path(override)
    root = repo_root()
    if root is not None:
        return root / "data" / "enablement.db"
    return Path.cwd() / "data" / "enablement.db"


def schema_path() -> Path:
    packaged = Path(__file__).resolve().parent / "store" / "schema.sql"
    if packaged.exists():
        return packaged
    root = repo_root()
    if root is not None:
        return root / "data" / "schema.sql"
    raise FileNotFoundError("schema.sql not found")


DEMO_FILES = {
    "role": "example_account_executive_job.txt",
    "call": "example_sales_call.txt",
    "critic": "example_new_hire_lesson.md",
}


def find_fixture(filename: str) -> Path:
    candidates = [
        Path.cwd() / "fixtures" / filename,
        Path(__file__).resolve().parent / "fixtures" / filename,
    ]
    root = repo_root()
    if root is not None:
        candidates.append(root / "fixtures" / filename)
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"fixture not found: {filename}")


def demo_text(product: str) -> str:
    try:
        filename = DEMO_FILES[product]
    except KeyError as exc:
        raise ValueError(f"unknown product: {product}") from exc
    return find_fixture(filename).read_text(encoding="utf-8")
