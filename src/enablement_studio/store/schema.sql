-- Enablement Studio v0 schema
-- Local SQLite only. Applied on first run.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    product TEXT NOT NULL CHECK (product IN ('role', 'call', 'critic')),
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    input_text TEXT NOT NULL,
    engine TEXT NOT NULL CHECK (engine IN ('offline', 'llm')),
    invalid INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, product, version)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_project_product
    ON runs (project_id, product, version);

CREATE INDEX IF NOT EXISTS idx_artifacts_run
    ON artifacts (run_id, kind);
