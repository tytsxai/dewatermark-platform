from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from wm_platform.config import Settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    status TEXT NOT NULL,
    provider_requested TEXT NOT NULL,
    provider_selected TEXT,
    fallback_chain_json TEXT NOT NULL,
    idempotency_key TEXT,
    input_path TEXT NOT NULL,
    input_signature TEXT,
    output_path TEXT,
    callback_url TEXT,
    callback_secret TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    claimed_at TEXT,
    lock_owner TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_priority_created
ON jobs(status, priority DESC, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_jobs_idempotency
ON jobs(tenant_id, idempotency_key, input_signature, input_path);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_jobs_tenant_idem_signature
ON jobs(tenant_id, idempotency_key, input_signature)
WHERE idempotency_key IS NOT NULL AND input_signature IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_jobs_tenant_idem_path
ON jobs(tenant_id, idempotency_key, input_path)
WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS api_keys (
    tenant_id TEXT PRIMARY KEY,
    api_key_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS callback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    status TEXT NOT NULL,
    response_code INTEGER,
    response_body TEXT,
    created_at TEXT NOT NULL
);
"""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def init_db(settings: Settings) -> None:
    ensure_parent_dir(settings.db_path)
    with sqlite3.connect(settings.db_path) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


@contextmanager
def db_connection(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(settings.db_path, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
