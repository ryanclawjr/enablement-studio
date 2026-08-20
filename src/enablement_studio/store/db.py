from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from enablement_studio.models import EngineName, Product, SavedRun
from enablement_studio.paths import default_db_path, schema_path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_schema(self) -> None:
        sql = schema_path().read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(sql)
            _ensure_run_columns(connection)

    def get_or_create_project(self, name: str) -> int:
        created = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO projects (name, created_at) VALUES (?, ?)",
                (name, created),
            )
            row = connection.execute(
                "SELECT id FROM projects WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            raise RuntimeError(f"failed to load project {name!r}")
        return int(row["id"])

    def next_version(self, project_id: int, product: Product) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM runs "
                "WHERE project_id = ? AND product = ?",
                (project_id, product.value),
            ).fetchone()
        current = row["version"] if row is not None else None
        return int(current or 0) + 1

    def save_run(
        self,
        *,
        project: str,
        product: Product,
        title: str,
        input_text: str,
        engine: EngineName,
        artifacts: dict[str, Any],
        invalid: bool | None = None,
    ) -> SavedRun:
        if invalid is None:
            result = artifacts.get("result")
            invalid = bool(isinstance(result, dict) and result.get("invalid"))
        project_id = self.get_or_create_project(project)
        created = utc_now()
        try:
            return self._insert_run(
                project_id=project_id,
                project=project,
                product=product,
                title=title,
                input_text=input_text,
                engine=engine,
                artifacts=artifacts,
                invalid=invalid,
                version=self.next_version(project_id, product),
                created=created,
            )
        except sqlite3.IntegrityError:
            try:
                return self._insert_run(
                    project_id=project_id,
                    project=project,
                    product=product,
                    title=title,
                    input_text=input_text,
                    engine=engine,
                    artifacts=artifacts,
                    invalid=invalid,
                    version=self.next_version(project_id, product),
                    created=created,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "could not save run; version already exists"
                ) from exc

    def _insert_run(
        self,
        *,
        project_id: int,
        project: str,
        product: Product,
        title: str,
        input_text: str,
        engine: EngineName,
        artifacts: dict[str, Any],
        invalid: bool,
        version: int,
        created: str,
    ) -> SavedRun:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (
                    project_id, product, version, title, input_text, engine,
                    invalid, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    product.value,
                    version,
                    title,
                    input_text,
                    engine.value,
                    1 if invalid else 0,
                    created,
                ),
            )
            run_id = int(cursor.lastrowid)
            for kind, content in artifacts.items():
                connection.execute(
                    """
                    INSERT INTO artifacts (run_id, kind, content_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, kind, json.dumps(content, ensure_ascii=True), created),
                )
        return self.get_run(run_id)

    def get_run(self, run_id: int) -> SavedRun:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT runs.*, projects.name AS project_name
                FROM runs
                JOIN projects ON projects.id = runs.project_id
                WHERE runs.id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"run {run_id} not found")
            artifact_rows = connection.execute(
                "SELECT kind, content_json FROM artifacts WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        artifacts = {
            str(item["kind"]): json.loads(item["content_json"]) for item in artifact_rows
        }
        return _row_to_run(row, artifacts)

    def list_runs(
        self, *, project: str | None = None, product: Product | None = None
    ) -> list[SavedRun]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if project:
            clauses.append("projects.name = ?")
            params.append(project)
        if product:
            clauses.append("runs.product = ?")
            params.append(product.value)
        sql = f"""
            SELECT runs.*, projects.name AS project_name
            FROM runs
            JOIN projects ON projects.id = runs.project_id
            WHERE {' AND '.join(clauses)}
            ORDER BY runs.id ASC
        """
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [_row_to_run(row, {}) for row in rows]

    def iter_table_names(self) -> Iterator[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        for row in rows:
            yield str(row["name"])


def _row_to_run(row: sqlite3.Row, artifacts: dict[str, Any]) -> SavedRun:
    return SavedRun(
        id=int(row["id"]),
        project=str(row["project_name"]),
        product=Product(row["product"]),
        version=int(row["version"]),
        title=str(row["title"]),
        input_text=str(row["input_text"]),
        engine=EngineName(row["engine"]),
        created_at=str(row["created_at"]),
        artifacts=artifacts,
        invalid=bool(row["invalid"]) if "invalid" in row.keys() else False,
    )


def _ensure_run_columns(connection: sqlite3.Connection) -> None:
    columns = {info[1] for info in connection.execute("PRAGMA table_info(runs)")}
    if "invalid" not in columns:
        connection.execute(
            "ALTER TABLE runs ADD COLUMN invalid INTEGER NOT NULL DEFAULT 0"
        )
