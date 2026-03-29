from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from wm_platform.db import db_connection
from wm_platform.dependencies import get_repository, get_settings, get_tenant_id, init_runtime
from wm_platform.errors import AppError, error_payload
from wm_platform.models import (
    CancelJobResponse,
    JobCreate,
    JobListResponse,
    JobResponse,
    JobResultResponse,
    JobSubmitResponse,
    ProviderProbeResult,
)
from wm_platform.provider_runtime import ProviderRuntime
from wm_platform.repository import JobRepository
from wm_platform.storage import save_upload_file, validate_local_input_path

AllowedProvider = Literal["auto", "cloud_inpaint", "comfy_diffueraser", "local_fallback"]
ALLOWED_PROVIDERS: set[str] = {"auto", "cloud_inpaint", "comfy_diffueraser", "local_fallback"}
ALLOWED_MEDIA_TYPES: set[str] = {"video", "image"}
ALLOWED_STATUSES: set[str] = {"queued", "running", "succeeded", "failed", "canceled"}


def create_app() -> FastAPI:
    app = FastAPI(title="Dewatermark Platform API", version="0.1.0")

    @app.on_event("startup")
    def _startup() -> None:
        init_runtime()

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_payload(exc.error_code, exc.error_message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_payload("VALIDATION_ERROR", str(exc.errors()[0].get("msg", "request validation failed"))),
        )

    @app.exception_handler(ValidationError)
    async def _handle_model_validation_error(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content=error_payload("VALIDATION_ERROR", str(exc)))

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content=error_payload("INTERNAL_ERROR", str(exc)))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        settings = get_settings()
        with db_connection(settings) as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "db": "ok"}

    @app.post("/v1/jobs", response_model=JobSubmitResponse)
    def submit_job(
        media_type: str = Form(...),
        provider: str = Form(default="auto"),
        callback_url: str | None = Form(default=None),
        callback_secret: str | None = Form(default=None),
        input_path: str | None = Form(default=None),
        priority: int = Form(default=0),
        file: UploadFile | None = File(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        tenant_id: str = Depends(get_tenant_id),
        repository: JobRepository = Depends(get_repository),
    ) -> JobSubmitResponse:
        settings = get_settings()
        if media_type != "video":
            raise AppError("MEDIA_TYPE_NOT_SUPPORTED", "only video is supported in MVP", 400)
        if provider not in ALLOWED_PROVIDERS:
            raise AppError("VALIDATION_ERROR", "provider is invalid", 400)
        if (file is None and not input_path) or (file is not None and input_path):
            raise AppError("VALIDATION_ERROR", "provide exactly one of file or input_path", 400)

        if file is not None:
            final_input_path, input_signature = save_upload_file(file, settings)
        else:
            validated_path, input_signature = validate_local_input_path(input_path or "", settings)
            final_input_path = validated_path

        existing = repository.find_idempotent_job(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            input_signature=input_signature,
            input_path=str(final_input_path),
        )
        if existing is not None:
            return JobSubmitResponse(
                job_id=existing.job_id,
                status=existing.status,
                provider_requested=existing.provider_requested,
                created_at=existing.created_at,
            )

        payload = JobCreate(
            tenant_id=tenant_id,
            media_type="video",
            provider_requested=provider,  # type: ignore[arg-type]
            fallback_chain_json=repository.default_fallback_chain(provider_requested=provider),
            idempotency_key=idempotency_key,
            input_path=str(final_input_path),
            input_signature=input_signature,
            callback_url=callback_url,
            callback_secret=callback_secret,
            priority=priority,
        )
        created = repository.create_job(payload)
        return JobSubmitResponse(
            job_id=created.job_id,
            status=created.status,
            provider_requested=created.provider_requested,
            created_at=created.created_at,
        )

    @app.get("/v1/jobs/{job_id}", response_model=JobResponse)
    def get_job(
        job_id: str,
        tenant_id: str = Depends(get_tenant_id),
        repository: JobRepository = Depends(get_repository),
    ) -> JobResponse:
        job = repository.get_job(job_id)
        if job is None or job.tenant_id != tenant_id:
            raise AppError("FILE_NOT_FOUND", "job not found", 404)
        return JobResponse.from_record(job)

    @app.get("/v1/jobs", response_model=JobListResponse)
    def list_jobs(
        status: str | None = None,
        provider: str | None = None,
        media_type: str | None = None,
        tenant_id: str = Depends(get_tenant_id),
        repository: JobRepository = Depends(get_repository),
    ) -> JobListResponse:
        if status is not None and status not in ALLOWED_STATUSES:
            raise AppError("VALIDATION_ERROR", "status is invalid", 400)
        if provider is not None and provider not in ALLOWED_PROVIDERS:
            raise AppError("VALIDATION_ERROR", "provider is invalid", 400)
        if media_type is not None and media_type not in ALLOWED_MEDIA_TYPES:
            raise AppError("VALIDATION_ERROR", "media_type is invalid", 400)

        records = repository.list_jobs(
            tenant_id=tenant_id,
            status=status,
            provider=provider,
            media_type=media_type,
        )
        return JobListResponse(jobs=[JobResponse.from_record(item) for item in records])

    @app.get("/v1/jobs/{job_id}/result", response_model=JobResultResponse)
    def get_job_result(
        job_id: str,
        tenant_id: str = Depends(get_tenant_id),
        repository: JobRepository = Depends(get_repository),
    ) -> JobResultResponse:
        job = repository.get_job(job_id)
        if job is None or job.tenant_id != tenant_id:
            raise AppError("FILE_NOT_FOUND", "job not found", 404)
        return JobResultResponse(
            job_id=job.job_id,
            status=job.status,
            output_path=job.output_path,
            download_url=None,
        )

    @app.post("/v1/jobs/{job_id}/cancel", response_model=CancelJobResponse)
    def cancel_job(
        job_id: str,
        tenant_id: str = Depends(get_tenant_id),
        repository: JobRepository = Depends(get_repository),
    ) -> CancelJobResponse:
        job = repository.cancel_job(job_id=job_id, tenant_id=tenant_id)
        if job is None:
            raise AppError("FILE_NOT_FOUND", "job not found", 404)
        if job.status != "canceled":
            raise AppError("VALIDATION_ERROR", f"job in status '{job.status}' cannot be canceled", 409)
        return CancelJobResponse(job_id=job.job_id, status=job.status, updated_at=job.updated_at)

    @app.get("/v1/providers")
    def list_providers(_: str = Depends(get_tenant_id)) -> dict[str, list[ProviderProbeResult]]:
        providers = ProviderRuntime(get_settings()).probe_all()
        return {"providers": providers}

    return app
