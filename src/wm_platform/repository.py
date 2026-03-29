from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from wm_platform.config import Settings
from wm_platform.db import db_connection, sha256_text
from wm_platform.models import JobCreate, JobRecord


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _parse_job(row: Any) -> JobRecord:
    return JobRecord.model_validate(
        {
            "job_id": row["job_id"],
            "tenant_id": row["tenant_id"],
            "media_type": row["media_type"],
            "status": row["status"],
            "provider_requested": row["provider_requested"],
            "provider_selected": row["provider_selected"],
            "fallback_chain_json": row["fallback_chain_json"],
            "idempotency_key": row["idempotency_key"],
            "input_path": row["input_path"],
            "input_signature": row["input_signature"],
            "output_path": row["output_path"],
            "callback_url": row["callback_url"],
            "callback_secret": row["callback_secret"],
            "priority": row["priority"],
            "attempt_count": row["attempt_count"],
            "duration_ms": row["duration_ms"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "claimed_at": row["claimed_at"],
            "lock_owner": row["lock_owner"],
        }
    )


class JobRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def seed_api_key(self, tenant_id: str, api_key: str) -> None:
        now = utc_now().isoformat()
        with db_connection(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO api_keys (tenant_id, api_key_hash, status, created_at)
                VALUES (?, ?, 'active', ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                  api_key_hash = excluded.api_key_hash,
                  status = 'active'
                """,
                (tenant_id, sha256_text(api_key), now),
            )

    def authenticate_api_key(self, api_key: str) -> str | None:
        with db_connection(self.settings) as connection:
            row = connection.execute(
                """
                SELECT tenant_id
                FROM api_keys
                WHERE api_key_hash = ? AND status = 'active'
                """,
                (sha256_text(api_key),),
            ).fetchone()
        return row["tenant_id"] if row else None

    def create_job(self, payload: JobCreate) -> JobRecord:
        now = utc_now().isoformat()
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        with db_connection(self.settings) as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_id, tenant_id, media_type, status, provider_requested,
                        provider_selected, fallback_chain_json, idempotency_key,
                        input_path, input_signature, output_path, callback_url, callback_secret,
                        priority, attempt_count, duration_ms, error_code, error_message,
                        created_at, updated_at, claimed_at, lock_owner
                    )
                    VALUES (?, ?, ?, 'queued', ?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?, 0, NULL, NULL, NULL, ?, ?, NULL, NULL)
                    """,
                    (
                        job_id,
                        payload.tenant_id,
                        payload.media_type,
                        payload.provider_requested,
                        payload.fallback_chain_json,
                        payload.idempotency_key,
                        payload.input_path,
                        payload.input_signature,
                        payload.callback_url,
                        payload.callback_secret,
                        payload.priority,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self._find_idempotent_job_row(
                    connection=connection,
                    tenant_id=payload.tenant_id,
                    idempotency_key=payload.idempotency_key,
                    input_signature=payload.input_signature,
                    input_path=payload.input_path,
                )
                if existing is not None:
                    return _parse_job(existing)
                raise
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _parse_job(row)

    def find_idempotent_job(
        self,
        tenant_id: str,
        idempotency_key: str | None,
        input_signature: str | None,
        input_path: str,
    ) -> JobRecord | None:
        if not idempotency_key:
            return None

        with db_connection(self.settings) as connection:
            row = self._find_idempotent_job_row(
                connection=connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                input_signature=input_signature,
                input_path=input_path,
            )
        return _parse_job(row) if row else None

    def _find_idempotent_job_row(
        self,
        connection,
        tenant_id: str,
        idempotency_key: str | None,
        input_signature: str | None,
        input_path: str,
    ) -> Any | None:
        if not idempotency_key:
            return None
        return connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE tenant_id = ?
              AND idempotency_key = ?
              AND (
                (input_signature IS NOT NULL AND input_signature = ?)
                OR input_path = ?
              )
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant_id, idempotency_key, input_signature, input_path),
        ).fetchone()

    def get_job(self, job_id: str) -> JobRecord | None:
        with db_connection(self.settings) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _parse_job(row) if row else None

    def list_jobs(
        self,
        tenant_id: str,
        status: str | None = None,
        provider: str | None = None,
        media_type: str | None = None,
    ) -> list[JobRecord]:
        conditions = ["tenant_id = ?"]
        params: list[str] = [tenant_id]
        if status:
            conditions.append("status = ?")
            params.append(status)
        if provider:
            conditions.append("(provider_requested = ? OR provider_selected = ?)")
            params.extend([provider, provider])
        if media_type:
            conditions.append("media_type = ?")
            params.append(media_type)

        where_clause = " AND ".join(conditions)
        with db_connection(self.settings) as connection:
            rows = connection.execute(
                f"SELECT * FROM jobs WHERE {where_clause} ORDER BY created_at DESC",
                params,
            ).fetchall()
        return [_parse_job(row) for row in rows]

    def reset_stale_claims(self, worker_timeout_seconds: int) -> int:
        cutoff = (utc_now() - timedelta(seconds=worker_timeout_seconds)).isoformat()
        with db_connection(self.settings) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'queued',
                    claimed_at = NULL,
                    lock_owner = NULL,
                    updated_at = ?
                WHERE status = 'running' AND claimed_at < ?
                """,
                (utc_now().isoformat(), cutoff),
            )
        return int(cursor.rowcount or 0)

    def claim_next_job(self, lock_owner: str) -> JobRecord | None:
        now = utc_now().isoformat()
        with db_connection(self.settings) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE status = 'queued'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
            ).fetchone()
            if row is None:
                return None

            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    claimed_at = ?,
                    lock_owner = ?,
                    attempt_count = attempt_count + 1,
                    updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                """,
                (now, lock_owner, now, row["job_id"]),
            )
            if cursor.rowcount == 0:
                return None

            claimed_row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (row["job_id"],)).fetchone()
        return _parse_job(claimed_row)

    def cancel_job(self, job_id: str, tenant_id: str) -> JobRecord | None:
        now = utc_now().isoformat()
        with db_connection(self.settings) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'canceled',
                    claimed_at = NULL,
                    lock_owner = NULL,
                    updated_at = ?
                WHERE job_id = ? AND tenant_id = ? AND status = 'queued'
                """,
                (now, job_id, tenant_id),
            )
            if cursor.rowcount == 0:
                updated_row = connection.execute(
                    """
                    SELECT *
                    FROM jobs
                    WHERE job_id = ? AND tenant_id = ?
                    """,
                    (job_id, tenant_id),
                ).fetchone()
            else:
                updated_row = connection.execute(
                    "SELECT * FROM jobs WHERE job_id = ? AND tenant_id = ?",
                    (job_id, tenant_id),
                ).fetchone()
        return _parse_job(updated_row)

    def cleanup_expired_files(self, older_than: datetime) -> dict[str, int]:
        with db_connection(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT job_id, input_path, output_path
                FROM jobs
                WHERE updated_at <= ?
                """,
                (older_than.isoformat(),),
            ).fetchall()
        return {
            "candidate_jobs": len(rows),
            "candidate_files": sum(1 for row in rows for path in (row["input_path"], row["output_path"]) if path),
        }

    def mark_job_succeeded(
        self,
        job_id: str,
        lock_owner: str,
        provider_selected: str,
        output_path: str,
        duration_ms: int,
    ) -> JobRecord | None:
        now = utc_now().isoformat()
        with db_connection(self.settings) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'succeeded',
                    provider_selected = ?,
                    output_path = ?,
                    duration_ms = ?,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = ?,
                    claimed_at = NULL,
                    lock_owner = NULL
                WHERE job_id = ? AND status = 'running' AND lock_owner = ?
                """,
                (provider_selected, output_path, duration_ms, now, job_id, lock_owner),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _parse_job(row)

    def mark_job_failed(
        self,
        job_id: str,
        lock_owner: str,
        provider_selected: str | None,
        error_code: str,
        error_message: str,
        duration_ms: int | None = None,
    ) -> JobRecord | None:
        now = utc_now().isoformat()
        with db_connection(self.settings) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    provider_selected = COALESCE(?, provider_selected),
                    duration_ms = ?,
                    error_code = ?,
                    error_message = ?,
                    updated_at = ?,
                    claimed_at = NULL,
                    lock_owner = NULL
                WHERE job_id = ? AND status = 'running' AND lock_owner = ?
                """,
                (provider_selected, duration_ms, error_code, error_message, now, job_id, lock_owner),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _parse_job(row)

    def record_callback_event(
        self,
        job_id: str,
        attempt_no: int,
        status: str,
        response_code: int | None,
        response_body: str | None,
    ) -> None:
        with db_connection(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO callback_events (job_id, attempt_no, status, response_code, response_body, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, attempt_no, status, response_code, response_body, utc_now().isoformat()),
            )

    def get_callback_events(self, job_id: str) -> list[dict[str, Any]]:
        with db_connection(self.settings) as connection:
            rows = connection.execute(
                "SELECT * FROM callback_events WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "attempt_no": row["attempt_no"],
                "status": row["status"],
                "response_code": row["response_code"],
                "response_body": row["response_body"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def default_fallback_chain(provider_requested: str) -> str:
        if provider_requested == "auto":
            chain = ["comfy_diffueraser", "cloud_inpaint", "local_fallback"]
        else:
            chain = [provider_requested]
        return json.dumps(chain)
