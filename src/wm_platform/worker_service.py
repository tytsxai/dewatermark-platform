from __future__ import annotations

import hashlib
import hmac
import json
import logging
import socket
import time
from datetime import UTC, datetime

import httpx

from wm_platform.config import Settings
from wm_platform.models import CallbackPayload, JobRecord
from wm_platform.provider_runtime import ProviderExecutionError, ProviderRuntime
from wm_platform.repository import JobRepository

logger = logging.getLogger(__name__)


class WorkerService:
    def __init__(self, settings: Settings, repository: JobRepository, providers: ProviderRuntime) -> None:
        self.settings = settings
        self.repository = repository
        self.providers = providers
        self.lock_owner = f"{socket.gethostname()}:{int(time.time())}"
        self._running = True

    def run_forever(self) -> None:
        logger.info("worker started lock_owner=%s db=%s", self.lock_owner, self.settings.db_path)
        while self._running:
            processed = self.run_once()
            if not processed:
                time.sleep(max(0.0, self.settings.worker_poll_interval_seconds))

    def run_once(self) -> bool:
        reclaimed = self.repository.reset_stale_claims(self.settings.job_claim_timeout_seconds)
        if reclaimed:
            logger.warning("reclaimed %d stale running jobs", reclaimed)

        job = self.repository.claim_next_job(lock_owner=self.lock_owner)
        if not job:
            return False

        self._process_job(job)
        return True

    def stop(self) -> None:
        self._running = False

    def _process_job(self, job: JobRecord) -> None:
        started_at = time.monotonic()
        logger.info("processing job=%s provider_requested=%s", job.job_id, job.provider_requested)

        try:
            provider_name, output_path = self.providers.run_with_fallback(job)
            duration_ms = self._duration_ms(started_at)
            updated = self.repository.mark_job_succeeded(
                job_id=job.job_id,
                lock_owner=self.lock_owner,
                provider_selected=provider_name,
                output_path=output_path,
                duration_ms=duration_ms,
            )
            if updated is None:
                logger.warning("skip success finalize for stale claim job_id=%s", job.job_id)
                return
            logger.info(
                "job succeeded job_id=%s provider=%s duration_ms=%s output_path=%s",
                job.job_id,
                provider_name,
                duration_ms,
                output_path,
            )
        except ProviderExecutionError as exc:
            duration_ms = self._duration_ms(started_at)
            updated = self.repository.mark_job_failed(
                job_id=job.job_id,
                lock_owner=self.lock_owner,
                provider_selected=exc.provider_selected,
                error_code=exc.error_code,
                error_message=exc.error_message,
                duration_ms=duration_ms,
            )
            if updated is None:
                logger.warning("skip failure finalize for stale claim job_id=%s", job.job_id)
                return
            logger.error(
                "job failed job_id=%s provider=%s error_code=%s error=%s duration_ms=%s",
                job.job_id,
                exc.provider_selected,
                exc.error_code,
                exc.error_message,
                duration_ms,
            )
        except Exception as exc:
            duration_ms = self._duration_ms(started_at)
            updated = self.repository.mark_job_failed(
                job_id=job.job_id,
                lock_owner=self.lock_owner,
                provider_selected=None,
                error_code="INTERNAL_ERROR",
                error_message=f"worker exception: {exc}",
                duration_ms=duration_ms,
            )
            if updated is None:
                logger.warning("skip exception finalize for stale claim job_id=%s", job.job_id)
                return
            logger.exception("unhandled worker exception job_id=%s duration_ms=%s", job.job_id, duration_ms)

        self._dispatch_callback(updated)

    def _dispatch_callback(self, job: JobRecord) -> None:
        if not job.callback_url:
            return

        payload = CallbackPayload(
            job_id=job.job_id,
            status=job.status,
            provider=job.provider_selected,
            output_path=job.output_path,
            error_code=job.error_code,
            error_message=job.error_message,
        ).model_dump()
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        max_attempts = max(1, self.settings.callback_retry_count)

        for attempt in range(1, max_attempts + 1):
            headers = {"Content-Type": "application/json"}
            timestamp = str(int(datetime.now(UTC).timestamp()))
            if job.callback_secret:
                signature = self._build_signature(job.callback_secret, timestamp, body)
                headers["X-Timestamp"] = timestamp
                headers["X-Signature"] = signature

            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(job.callback_url, content=body, headers=headers)
                if 200 <= response.status_code < 300:
                    self.repository.record_callback_event(
                        job_id=job.job_id,
                        attempt_no=attempt,
                        status="succeeded",
                        response_code=response.status_code,
                        response_body=response.text[:1000],
                    )
                    return

                self.repository.record_callback_event(
                    job_id=job.job_id,
                    attempt_no=attempt,
                    status="failed",
                    response_code=response.status_code,
                    response_body=response.text[:1000],
                )
            except Exception as exc:
                self.repository.record_callback_event(
                    job_id=job.job_id,
                    attempt_no=attempt,
                    status="failed",
                    response_code=None,
                    response_body=str(exc)[:1000],
                )

            if attempt < max_attempts:
                time.sleep(max(0.0, self.settings.callback_retry_delay_seconds))

    @staticmethod
    def _build_signature(secret: str, timestamp: str, body: str) -> str:
        message = f"{timestamp}.{body}".encode("utf-8")
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
