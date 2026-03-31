from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import io
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from wm_platform.api_app import create_app
from wm_platform.config import load_settings
from wm_platform.comfy_runtime import build_comfyui_command
from wm_platform.dependencies import get_repository
from wm_platform.db import db_connection
from wm_platform.doctor import provider_doctor_report
from wm_platform.maintenance import run_file_cleanup
from wm_platform.models import JobCreate
from wm_platform.provider_runtime import ProviderRuntime
from wm_platform.rate_limit import reset_submit_rate_limiter
from wm_platform.repository import JobRepository
from wm_platform.runtime_contract import expected_model_entries, expected_repo_paths
from wm_platform.runtime_installer import RuntimeInstaller
from wm_platform.worker_service import CallbackWorkerService, WorkerService


def _upload_payload(files: dict) -> dict:
    return {
        "media_type": "video",
        "provider": "auto",
        "callback_url": "http://example.com/callback",
        "callback_secret": "secret",
    }


def _submit_job(api_client, auth_headers, idempotency_key: str) -> dict:
    file_bytes = io.BytesIO(b"\x01" * 16)
    files = {"file": ("video.mp4", file_bytes, "video/mp4")}
    headers = {**auth_headers, "Idempotency-Key": idempotency_key}
    response = api_client.post("/v1/jobs", headers=headers, files=files, data=_upload_payload({}))
    response.raise_for_status()
    return response.json()


def _prepare_video_file(settings_path: Path, name: str = "dummy.mp4") -> Path:
    target = settings_path / name
    target.write_bytes(b"fake-video-content")
    return target


def test_healthz(api_client):
    response = api_client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert body.get("status") in {"ok", "healthy", "alive"}


def test_auth_failure(api_client):
    response = api_client.post("/v1/jobs")
    assert response.status_code in {401, 403, 400}
    payload = response.json()
    assert payload.get("error_code") == "AUTH_ERROR"


def test_submit_job_and_idempotent(api_client, auth_headers, settings):
    file_bytes = io.BytesIO(b"\x00" * 16)
    files = {"file": ("video.mp4", file_bytes, "video/mp4")}
    headers = {**auth_headers, "Idempotency-Key": "idem-123"}
    data = _upload_payload({})

    first = api_client.post("/v1/jobs", headers=headers, files=files, data=data)
    assert first.status_code in {200, 201}
    first_body = first.json()
    assert first_body["status"] == "queued"

    file_bytes.seek(0)
    second = api_client.post("/v1/jobs", headers=headers, files=files, data=data)
    assert second.status_code == first.status_code
    assert second.json()["job_id"] == first_body["job_id"]


def test_submit_job_rejects_reserved_provider(api_client, auth_headers):
    response = api_client.post(
        "/v1/jobs",
        headers={**auth_headers, "Idempotency-Key": "reserved-provider"},
        files={"file": ("video.mp4", io.BytesIO(b"\x00" * 16), "video/mp4")},
        data={
            "media_type": "video",
            "provider": "cloud_inpaint",
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_submit_job_rejects_private_callback_url(api_client, auth_headers):
    response = api_client.post(
        "/v1/jobs",
        headers={**auth_headers, "Idempotency-Key": "private-callback"},
        files={"file": ("video.mp4", io.BytesIO(b"\x00" * 16), "video/mp4")},
        data={
            "media_type": "video",
            "provider": "auto",
            "callback_url": "http://127.0.0.1:9000/callback",
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_worker_marks_job_succeeded(job_repo, settings):
    fallback_chain = JobRepository.default_fallback_chain("local_fallback")
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=fallback_chain,
        idempotency_key="worker-success",
        input_path=str(_prepare_video_file(settings.inbox_dir, "worker-sample.mp4")),
    )
    job = job_repo.create_job(payload)
    service = WorkerService(settings=settings, repository=job_repo, providers=ProviderRuntime(settings))
    assert service.run_once() is True
    updated = job_repo.get_job(job.job_id)
    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.output_path is not None
    assert Path(updated.output_path).exists()
    assert Path(updated.output_path).stat().st_size > 0


def test_provider_auto_chain():
    chain = json.loads(JobRepository.default_fallback_chain("auto"))
    assert chain == ["comfy_diffueraser", "local_fallback"]


def test_local_fallback_copy_mode_does_not_invoke_ffmpeg(job_repo, settings, monkeypatch):
    copy_settings = replace(settings, local_fallback_mode="ffmpeg_copy")
    provider = ProviderRuntime(copy_settings).registry["local_fallback"]
    job = job_repo.create_job(
        JobCreate(
            tenant_id=settings.default_tenant_id,
            media_type="video",
            provider_requested="local_fallback",
            fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
            input_path=str(_prepare_video_file(settings.inbox_dir, "copy-mode.mp4")),
        )
    )

    def _unexpected_run(*args, **kwargs):
        raise AssertionError("ffmpeg should not run in ffmpeg_copy mode")

    monkeypatch.setattr("wm_platform.provider_runtime.subprocess.run", _unexpected_run)
    result = provider.run(job)

    assert Path(result["output_path"]).exists()
    assert Path(result["output_path"]).read_bytes() == Path(job.input_path).read_bytes()


def test_callback_event_record(job_repo):
    job_id = "job-callback-demo"
    job_repo.record_callback_event(job_id, attempt_no=1, status="succeeded", response_code=200, response_body="ok")
    events = job_repo.get_callback_events(job_id)
    assert events
    assert events[-1]["status"] == "succeeded"
    assert events[-1]["attempt_no"] == 1


def test_job_worker_enqueues_callback_without_sending(job_repo, settings, monkeypatch):
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        input_path=str(_prepare_video_file(settings.inbox_dir, "callback-sample.mp4")),
        callback_url="http://callback.local/notify",
        callback_secret="secret",
    )
    job = job_repo.create_job(payload)

    attempts = {"count": 0}

    class _UnexpectedClient:
        def __init__(self, *args, **kwargs):
            attempts["count"] += 1
            raise AssertionError("job worker should not dispatch callbacks inline")

    monkeypatch.setattr("wm_platform.worker_service.httpx.Client", _UnexpectedClient)
    service = WorkerService(settings=settings, repository=job_repo, providers=ProviderRuntime(settings))
    assert service.run_once() is True

    outbox = job_repo.get_callback_outbox(job.job_id)
    assert len(outbox) == 1
    assert outbox[0].status == "pending"
    events = job_repo.get_callback_events(job.job_id)
    assert events == []
    assert attempts["count"] == 0


def test_callback_worker_retry_records_events(job_repo, settings, monkeypatch):
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        input_path=str(_prepare_video_file(settings.inbox_dir, "callback-sample.mp4")),
        callback_url="http://callback.local/notify",
        callback_secret="secret",
    )
    job = job_repo.create_job(payload)
    service = WorkerService(settings=settings, repository=job_repo, providers=ProviderRuntime(settings))
    assert service.run_once() is True

    attempts = {"count": 0}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary callback failure")
            return SimpleNamespace(status_code=200, text="ok")

    monkeypatch.setattr("wm_platform.worker_service.httpx.Client", _FakeClient)
    callback_service = CallbackWorkerService(settings=settings, repository=job_repo, lock_owner="callback-test")
    assert callback_service.run_once() is True
    assert callback_service.run_once() is True
    assert callback_service.run_once() is True

    events = job_repo.get_callback_events(job.job_id)
    assert len(events) == 3
    assert events[-1]["status"] == "succeeded"


def test_list_jobs_filters(api_client, auth_headers):
    job = _submit_job(api_client, auth_headers, "list-filter")
    response = api_client.get("/v1/jobs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert any(item["job_id"] == job["job_id"] for item in data["jobs"])

    filtered = api_client.get("/v1/jobs?status=queued&provider=auto&media_type=video&page=1&page_size=10", headers=auth_headers)
    assert filtered.status_code == 200
    filtered_jobs = filtered.json().get("jobs", [])
    assert any(item["job_id"] == job["job_id"] for item in filtered_jobs)


def test_list_jobs_pagination(api_client, auth_headers):
    for index in range(3):
        _submit_job(api_client, auth_headers, f"page-{index}")

    first_page = api_client.get("/v1/jobs?page=1&page_size=2", headers=auth_headers)
    second_page = api_client.get("/v1/jobs?page=2&page_size=2", headers=auth_headers)

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_data = first_page.json()
    second_data = second_page.json()
    assert len(first_data["jobs"]) == 2
    assert first_data["has_more"] is True
    assert second_data["page"] == 2
    assert second_data["page_size"] == 2
    assert len(second_data["jobs"]) == 1


def test_job_result_endpoint(api_client, auth_headers, job_repo, settings):
    fallback_chain = JobRepository.default_fallback_chain("local_fallback")
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=fallback_chain,
        idempotency_key="result-test",
        input_path=str(_prepare_video_file(settings.inbox_dir, "result-sample.mp4")),
    )
    job = job_repo.create_job(payload)
    service = WorkerService(settings=settings, repository=job_repo, providers=ProviderRuntime(settings))
    assert service.run_once() is True

    response = api_client.get(f"/v1/jobs/{job.job_id}/result", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["output_path"] is not None
    assert Path(body["output_path"]).exists()
    assert body.get("download_url") in {None, ""}


def test_job_result_endpoint_reports_missing_artifact(api_client, auth_headers, job_repo, settings):
    fallback_chain = JobRepository.default_fallback_chain("local_fallback")
    output_path = settings.outbox_dir / "missing.mp4"
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=fallback_chain,
        idempotency_key="result-missing",
        input_path=str(_prepare_video_file(settings.inbox_dir, "result-missing.mp4")),
    )
    job = job_repo.create_job(payload)
    with db_connection(settings) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = 'succeeded',
                output_path = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (str(output_path), datetime.now(UTC).isoformat(), job.job_id),
        )

    response = api_client.get(f"/v1/jobs/{job.job_id}/result", headers=auth_headers)
    assert response.status_code == 410
    assert response.json()["error_code"] == "ARTIFACT_MISSING"


def test_cancel_job(api_client, auth_headers):
    job = _submit_job(api_client, auth_headers, "cancel-test")
    response = api_client.post(f"/v1/jobs/{job['job_id']}/cancel", headers=auth_headers)
    assert response.status_code in {200, 202}
    body = response.json()
    assert body["status"] == "canceled"


def test_cancel_job_reports_conflict_when_repository_observes_running(auth_headers):
    app = create_app()

    class _RaceRepository:
        def authenticate_api_key(self, api_key: str) -> str | None:
            return "local-dev" if api_key == "dev-secret-key" else None

        def cancel_job(self, job_id: str, tenant_id: str):
            return SimpleNamespace(job_id=job_id, status="running", updated_at=datetime.now(UTC))

    app.dependency_overrides[get_repository] = lambda: _RaceRepository()
    try:
        with TestClient(app) as client:
            response = client.post("/v1/jobs/job_race/cancel", headers=auth_headers)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error_code"] == "JOB_NOT_CANCELABLE"


def test_submit_job_rate_limit(settings, job_repo, auth_headers, monkeypatch):
    app = create_app()
    limited_settings = replace(settings, submit_rate_limit_count=1, submit_rate_limit_window_seconds=60.0)
    reset_submit_rate_limiter()
    monkeypatch.setattr("wm_platform.api_app.get_settings", lambda: limited_settings)
    app.dependency_overrides[get_repository] = lambda: job_repo
    try:
        with TestClient(app) as client:
            first = client.post(
                "/v1/jobs",
                headers={**auth_headers, "Idempotency-Key": "limited-1"},
                files={"file": ("video.mp4", io.BytesIO(b"\x01" * 16), "video/mp4")},
                data=_upload_payload({}),
            )
            second = client.post(
                "/v1/jobs",
                headers={**auth_headers, "Idempotency-Key": "limited-2"},
                files={"file": ("video.mp4", io.BytesIO(b"\x02" * 16), "video/mp4")},
                data=_upload_payload({}),
            )
    finally:
        app.dependency_overrides.clear()
        reset_submit_rate_limiter()

    assert first.status_code in {200, 201}
    assert second.status_code == 429
    assert second.json()["error_code"] == "RATE_LIMITED"


def test_provider_probe_shape(api_client, auth_headers):
    response = api_client.get("/v1/providers", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    providers = data["providers"]
    assert isinstance(providers, list)
    for provider in providers:
        assert "name" in provider
        assert "installed" in provider
        assert "runnable" in provider
        assert "message" in provider
        assert "details" in provider


def test_provider_probe_is_cached(settings, monkeypatch):
    calls = {"count": 0}

    def _fake_get(*args, **kwargs):
        calls["count"] += 1
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr("wm_platform.provider_runtime.httpx.get", _fake_get)
    runtime = ProviderRuntime(replace(settings, provider_probe_cache_seconds=60.0))
    runtime.probe_all()
    runtime.probe_all()
    assert calls["count"] <= 1


def test_db_connection_enables_wal(settings):
    with db_connection(settings) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert str(journal_mode).lower() == "wal"
    assert int(foreign_keys) == 1


def test_comfy_probe_reports_missing_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("DWM_RUNTIME_ROOT", str(tmp_path / ".runtime"))
    monkeypatch.setenv("DWM_COMFYUI_DIR", str(tmp_path / "ComfyUI"))
    monkeypatch.setenv("DWM_COMFYUI_CUSTOM_NODES_DIR", str(tmp_path / "ComfyUI" / "custom_nodes"))
    monkeypatch.setenv("DWM_COMFYUI_MODELS_DIR", str(tmp_path / "ComfyUI" / "models"))
    monkeypatch.setenv("DWM_COMFYUI_WORKFLOWS_DIR", str(tmp_path / "workflows"))
    monkeypatch.setenv("DWM_COMFYUI_DIFFUERASER_WORKFLOW", str(tmp_path / "workflows" / "sam2_diffueraser_api.json"))
    settings = load_settings()
    probe_map = {item.name: item for item in ProviderRuntime(settings).probe_all()}
    comfy = probe_map["comfy_diffueraser"]
    assert comfy.installed is False
    assert comfy.runnable is False
    assert "missing" in comfy.message.lower() or "unreachable" in comfy.message.lower()
    assert comfy.details is not None
    assert comfy.details["automatic_ai_pipeline"] == "wired"
    assert comfy.details["workflow_ready"] is False


def test_comfy_workflow_template_uses_api_prompt_format(settings):
    payload = json.loads(settings.comfyui_diffueraser_workflow.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["1"]["class_type"] == "VHS_LoadVideoPath"
    assert payload["11"]["class_type"] == "SaveVideo"


def test_comfy_provider_runs_with_api_prompt(job_repo, settings, monkeypatch, tmp_path):
    comfy_dir = tmp_path / "ComfyUI"
    comfy_dir.mkdir()
    (comfy_dir / "main.py").write_text("print('comfy')\n", encoding="utf-8")
    comfy_venv = tmp_path / ".venv" / "bin"
    comfy_venv.mkdir(parents=True)
    (comfy_venv / "python").write_text("", encoding="utf-8")

    models_dir = comfy_dir / "models"
    (models_dir / "vae").mkdir(parents=True)
    (models_dir / "loras" / "sd15").mkdir(parents=True)
    (models_dir / "clip").mkdir(parents=True)
    (models_dir / "DiffuEraser" / "propainter").mkdir(parents=True)
    (models_dir / "vae" / "sd-vae-ft-mse.safetensors").write_bytes(b"vae")
    (models_dir / "loras" / "sd15" / "pcm_sd15_smallcfg_2step_converted.safetensors").write_bytes(b"lora")
    (models_dir / "clip" / "clip_l.safetensors").write_bytes(b"clip")
    (models_dir / "DiffuEraser" / "propainter" / "ProPainter.pth").write_bytes(b"propainter")
    (models_dir / "DiffuEraser" / "propainter" / "recurrent_flow_completion.pth").write_bytes(b"flow")
    (models_dir / "DiffuEraser" / "propainter" / "raft-things.pth").write_bytes(b"raft")

    workflow_path = tmp_path / "sam2_diffueraser_api.json"
    workflow_path.write_text(settings.comfyui_diffueraser_workflow.read_text(encoding="utf-8"), encoding="utf-8")

    comfy_settings = replace(
        settings,
        comfyui_dir=comfy_dir,
        comfyui_venv_dir=tmp_path / ".venv",
        comfyui_models_dir=models_dir,
        comfyui_diffueraser_workflow=workflow_path,
        comfyui_api_url="http://127.0.0.1:8188",
    )

    job = job_repo.create_job(
        JobCreate(
            tenant_id=settings.default_tenant_id,
            media_type="video",
            provider_requested="comfy_diffueraser",
            fallback_chain_json=JobRepository.default_fallback_chain("comfy_diffueraser"),
            input_path=str(_prepare_video_file(settings.inbox_dir, "comfy-provider.mp4")),
        )
    )

    captured_prompt: dict[str, object] = {}

    class _Response:
        def __init__(self, status_code=200, payload=None, text="", content=b""):
            self.status_code = status_code
            self._payload = payload
            self.text = text
            self.content = content

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.text or f"http {self.status_code}")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, timeout=None, params=None):
            if url.endswith("/system_stats"):
                return _Response(payload={"devices": [{"type": "cpu"}]})
            if f"/history/{job.job_id}" in url:
                return _Response(
                    payload={
                        job.job_id: {
                            "outputs": {
                                "11": {
                                    "images": [
                                        {
                                            "filename": "video_00001_.mp4",
                                            "subfolder": "video",
                                            "type": "output",
                                        }
                                    ]
                                }
                            },
                            "status": {"status_str": "success", "completed": True, "messages": []},
                        }
                    }
                )
            if url.endswith("/view"):
                assert params == {"filename": "video_00001_.mp4", "subfolder": "video", "type": "output"}
                return _Response(content=b"fake-comfy-video")
            raise AssertionError(f"unexpected GET {url}")

        def post(self, url, json=None):
            assert url.endswith("/prompt")
            captured_prompt.update(json or {})
            return _Response(payload={"prompt_id": job.job_id})

    monkeypatch.setattr("wm_platform.provider_runtime.httpx.Client", _FakeClient)
    provider = ProviderRuntime(comfy_settings).registry["comfy_diffueraser"]
    result = provider.run(job)

    assert Path(result["output_path"]).exists()
    assert Path(result["output_path"]).read_bytes() == b"fake-comfy-video"
    assert captured_prompt["prompt_id"] == job.job_id
    prompt = captured_prompt["prompt"]
    assert prompt["1"]["inputs"]["video"] == job.input_path
    assert prompt["4"]["inputs"]["device"] == "cpu"
    assert prompt["6"]["inputs"]["vae"] == "sd-vae-ft-mse.safetensors"
    assert prompt["6"]["inputs"]["lora"] == "sd15/pcm_sd15_smallcfg_2step_converted.safetensors"
    assert prompt["7"]["inputs"]["clip_name"] == "clip_l.safetensors"
    assert prompt["11"]["inputs"]["filename_prefix"] == f"video/{job.job_id}"


def test_provider_doctor_report_contains_probe_data(settings):
    report = provider_doctor_report(settings)
    assert "providers" in report
    assert "comfyui_dir" in report
    assert "expected_repo_paths" in report
    assert "system_dependencies" in report
    providers = report["providers"]
    assert isinstance(providers, list)
    assert any(item["name"] == "comfy_diffueraser" for item in providers)
    system_dependencies = report["system_dependencies"]
    assert system_dependencies["sqlite3"]["available"] is True
    assert "git" in system_dependencies
    assert "ffmpeg" in system_dependencies


def test_get_job_reports_job_not_found(api_client, auth_headers):
    response = api_client.get("/v1/jobs/job_missing", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "JOB_NOT_FOUND"


def test_runtime_contract_files_are_visible(settings):
    repo_paths = expected_repo_paths(settings)
    model_entries = expected_model_entries(settings)
    assert repo_paths
    assert model_entries
    assert any(entry["name"] == "propainter" for entry in model_entries)


def test_runtime_installer_plan_contains_repositories(settings):
    plan = RuntimeInstaller(settings).plan()
    assert plan["python"] == "3.12"
    repositories = plan["repositories"]
    assert isinstance(repositories, dict)
    assert "comfyui" in repositories


def test_comfyui_command_points_to_runtime(settings):
    command = build_comfyui_command(settings)
    assert command[0].endswith(".runtime/.venv/bin/python")
    assert command[1].endswith(".runtime/ComfyUI/main.py")


def test_create_job_returns_existing_record_on_idempotency_conflict(job_repo, settings):
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        idempotency_key="dup-key",
        input_path=str(settings.inbox_dir / "same.mp4"),
        input_signature="same-signature",
    )
    first = job_repo.create_job(payload)
    second = job_repo.create_job(payload)

    assert second.job_id == first.job_id


def test_stale_worker_cannot_overwrite_running_job_or_dispatch_callback(job_repo, settings, monkeypatch):
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        input_path=str(_prepare_video_file(settings.inbox_dir, "stale-claim.mp4")),
        callback_url="http://callback.local/notify",
        callback_secret="secret",
    )
    job = job_repo.create_job(payload)
    claimed = job_repo.claim_next_job(lock_owner="new-owner")
    assert claimed is not None

    service = WorkerService(settings=settings, repository=job_repo, providers=SimpleNamespace())
    service.lock_owner = "old-owner"
    monkeypatch.setattr(
        service.providers,
        "run_with_fallback",
        lambda _: ("local_fallback", str(settings.outbox_dir / "stale-claim.mp4")),
        raising=False,
    )

    callback_attempts = {"count": 0}

    class _UnexpectedClient:
        def __init__(self, *args, **kwargs):
            callback_attempts["count"] += 1
            raise AssertionError("callback should not be dispatched by stale worker")

    monkeypatch.setattr("wm_platform.worker_service.httpx.Client", _UnexpectedClient)
    service._process_job(claimed)

    current = job_repo.get_job(job.job_id)
    assert current is not None
    assert current.status == "running"
    assert current.lock_owner == "new-owner"
    assert callback_attempts["count"] == 0
    assert job_repo.get_callback_events(job.job_id) == []
    assert job_repo.get_callback_outbox(job.job_id) == []


def test_callback_retry_count_respects_single_attempt(job_repo, settings, monkeypatch):
    once_settings = replace(settings, callback_retry_count=1, callback_retry_delay_seconds=0.0)
    once_repo = JobRepository(once_settings)
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        input_path=str(_prepare_video_file(settings.inbox_dir, "retry-once.mp4")),
        callback_url="http://callback.local/notify",
    )
    job = once_repo.create_job(payload)

    attempts = {"count": 0}

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            attempts["count"] += 1
            raise RuntimeError("callback down")

    service = WorkerService(settings=once_settings, repository=once_repo, providers=ProviderRuntime(once_settings))
    assert service.run_once() is True

    monkeypatch.setattr("wm_platform.worker_service.httpx.Client", _FailingClient)
    callback_service = CallbackWorkerService(settings=once_settings, repository=once_repo, lock_owner="callback-once")
    assert callback_service.run_once() is True

    events = once_repo.get_callback_events(job.job_id)
    outbox = once_repo.get_callback_outbox(job.job_id)
    assert attempts["count"] == 1
    assert len(events) == 1
    assert events[0]["status"] == "failed"
    assert outbox[0].status == "failed"


def test_worker_renews_claim_while_processing(job_repo, settings, monkeypatch):
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        input_path=str(_prepare_video_file(settings.inbox_dir, "heartbeat.mp4")),
    )
    job = job_repo.create_job(payload)
    claimed = job_repo.claim_next_job(lock_owner="heartbeat-owner")
    assert claimed is not None

    heartbeat_settings = replace(settings, job_claim_heartbeat_seconds=0.01, job_claim_timeout_seconds=1)
    service = WorkerService(settings=heartbeat_settings, repository=job_repo, providers=SimpleNamespace())
    service.lock_owner = "heartbeat-owner"

    heartbeat_calls = {"count": 0}
    original_renew = job_repo.renew_job_claim

    def _renew(job_id: str, lock_owner: str) -> bool:
        heartbeat_calls["count"] += 1
        return original_renew(job_id, lock_owner)

    monkeypatch.setattr(job_repo, "renew_job_claim", _renew)
    monkeypatch.setattr(
        service.providers,
        "run_with_fallback",
        lambda _: (time.sleep(0.05), ("local_fallback", str(settings.outbox_dir / "heartbeat.mp4")))[1],
        raising=False,
    )
    service._process_job(claimed)

    updated = job_repo.get_job(job.job_id)
    assert updated is not None
    assert updated.status == "succeeded"
    assert heartbeat_calls["count"] >= 1


def test_run_forever_only_sleeps_when_queue_is_empty(settings, monkeypatch):
    service = WorkerService(settings=settings, repository=SimpleNamespace(), providers=SimpleNamespace())
    outcomes = iter([True, False])
    sleep_calls: list[float] = []

    def _fake_run_once() -> bool:
        result = next(outcomes)
        if not result:
            service.stop()
        return result

    monkeypatch.setattr(service, "run_once", _fake_run_once)
    monkeypatch.setattr(service.callback_service, "run_forever", lambda: None)
    monkeypatch.setattr("wm_platform.worker_service.time.sleep", lambda seconds: sleep_calls.append(seconds))
    service.run_forever()

    assert sleep_calls == [max(0.0, settings.worker_poll_interval_seconds)]


def test_save_upload_file_removes_partial_file_on_size_limit(settings):
    from wm_platform.storage import save_upload_file

    limited_settings = replace(settings, max_upload_bytes=4)
    upload = SimpleNamespace(filename="video.mp4", file=io.BytesIO(b"12345"))

    with pytest.raises(Exception):
        save_upload_file(upload, limited_settings)

    leftovers = [path for path in settings.inbox_dir.iterdir() if path.name != ".gitkeep"]
    assert leftovers == []


def test_callback_payload_is_frozen_at_enqueue(job_repo, settings, monkeypatch):
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        input_path=str(_prepare_video_file(settings.inbox_dir, "frozen-callback.mp4")),
        callback_url="http://callback.local/notify",
    )
    job = job_repo.create_job(payload)
    service = WorkerService(settings=settings, repository=job_repo, providers=ProviderRuntime(settings))
    assert service.run_once() is True

    outbox = job_repo.get_callback_outbox(job.job_id)
    assert len(outbox) == 1
    frozen_payload = outbox[0].payload_json
    with db_connection(settings) as connection:
        connection.execute(
            "UPDATE jobs SET error_message = ? WHERE job_id = ?",
            ("mutated-after-enqueue", job.job_id),
        )

    sent_bodies: list[str] = []

    class _SuccessClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            sent_bodies.append(kwargs["content"])
            return SimpleNamespace(status_code=200, text="ok")

    monkeypatch.setattr("wm_platform.worker_service.httpx.Client", _SuccessClient)
    callback_service = CallbackWorkerService(settings=settings, repository=job_repo, lock_owner="callback-frozen")
    assert callback_service.run_once() is True
    assert sent_bodies == [frozen_payload]


def test_cleanup_stats(job_repo, settings):
    fallback_chain = JobRepository.default_fallback_chain("local_fallback")
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=fallback_chain,
        idempotency_key="cleanup-test",
        input_path=str(_prepare_video_file(settings.inbox_dir, "cleanup-sample.mp4")),
    )
    job = job_repo.create_job(payload)
    cutoff = datetime.now(UTC) - timedelta(days=settings.file_retention_days + 1)
    with db_connection(settings) as connection:
        connection.execute(
            "UPDATE jobs SET status = 'succeeded', updated_at = ?, created_at = ? WHERE job_id = ?",
            (cutoff.isoformat(), cutoff.isoformat(), job.job_id),
        )

    output_path = settings.outbox_dir / f"{job.job_id}.mp4"
    output_path.write_bytes(b"output")
    os.utime(payload.input_path, (cutoff.timestamp(), cutoff.timestamp()))
    os.utime(output_path, (cutoff.timestamp(), cutoff.timestamp()))
    with db_connection(settings) as connection:
        connection.execute(
            "UPDATE jobs SET output_path = ?, updated_at = ? WHERE job_id = ?",
            (str(output_path), cutoff.isoformat(), job.job_id),
        )

    report = run_file_cleanup(settings=settings, repository=job_repo, execute=True)
    assert report["candidate_jobs"] >= 1

    updated = job_repo.get_job(job.job_id)
    assert updated is not None
    assert updated.input_path == ""
    assert updated.output_path is None
    assert not Path(payload.input_path).exists()
    assert not output_path.exists()


def test_cleanup_preserves_shared_file_referenced_by_running_job(job_repo, settings):
    shared_input = _prepare_video_file(settings.inbox_dir, "shared-running.mp4")
    old_job = job_repo.create_job(
        JobCreate(
            tenant_id=settings.default_tenant_id,
            media_type="video",
            provider_requested="local_fallback",
            fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
            input_path=str(shared_input),
        )
    )
    running_job = job_repo.create_job(
        JobCreate(
            tenant_id=settings.default_tenant_id,
            media_type="video",
            provider_requested="local_fallback",
            fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
            input_path=str(shared_input),
        )
    )
    old_output = settings.outbox_dir / f"{old_job.job_id}.mp4"
    old_output.write_bytes(b"artifact")
    cutoff = datetime.now(UTC) - timedelta(days=settings.file_retention_days + 1)
    old_ts = cutoff.timestamp()
    os.utime(shared_input, (old_ts, old_ts))

    with db_connection(settings) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = 'succeeded',
                output_path = ?,
                updated_at = ?,
                created_at = ?
            WHERE job_id = ?
            """,
            (str(old_output), cutoff.isoformat(), cutoff.isoformat(), old_job.job_id),
        )
        connection.execute(
            """
            UPDATE jobs
            SET status = 'running',
                claimed_at = ?,
                lock_owner = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (datetime.now(UTC).isoformat(), "worker-1", datetime.now(UTC).isoformat(), running_job.job_id),
        )
    old_output.unlink()

    report = run_file_cleanup(settings=settings, repository=job_repo, execute=True)
    old_job_after = job_repo.get_job(old_job.job_id)
    running_job_after = job_repo.get_job(running_job.job_id)

    assert report["cleared_db_references"] >= 1
    assert shared_input.exists()
    assert old_job_after is not None
    assert old_job_after.input_path == str(shared_input)
    assert old_job_after.output_path is None
    assert running_job_after is not None
    assert running_job_after.input_path == str(shared_input)


def test_callback_stale_claim_is_reclaimed(job_repo, settings):
    payload = JobCreate(
        tenant_id=settings.default_tenant_id,
        media_type="video",
        provider_requested="local_fallback",
        fallback_chain_json=JobRepository.default_fallback_chain("local_fallback"),
        input_path=str(_prepare_video_file(settings.inbox_dir, "callback-stale.mp4")),
        callback_url="http://callback.local/notify",
    )
    job = job_repo.create_job(payload)
    service = WorkerService(settings=settings, repository=job_repo, providers=ProviderRuntime(settings))
    assert service.run_once() is True
    outbox = job_repo.get_callback_outbox(job.job_id)
    assert len(outbox) == 1

    stale_at = datetime.now(UTC) - timedelta(seconds=settings.job_claim_timeout_seconds + 1)
    with db_connection(settings) as connection:
        connection.execute(
            """
            UPDATE callback_outbox
            SET status = 'delivering',
                claimed_at = ?,
                lock_owner = ?
            WHERE id = ?
            """,
            (stale_at.isoformat(), "stale-lock", outbox[0].id),
        )

    assert job_repo.reset_stale_callback_claims(settings.job_claim_timeout_seconds) == 1
    refreshed = job_repo.get_callback_outbox(job.job_id)[0]
    assert refreshed.status == "pending"
    assert refreshed.lock_owner is None
