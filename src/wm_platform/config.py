from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    storage_root: Path
    inbox_dir: Path
    outbox_dir: Path
    db_path: Path
    runtime_root: Path
    default_tenant_id: str
    default_api_key: str
    max_upload_bytes: int
    worker_poll_interval_seconds: float
    job_claim_timeout_seconds: int
    job_claim_heartbeat_seconds: float
    callback_retry_count: int
    callback_retry_delay_seconds: float
    submit_rate_limit_count: int
    submit_rate_limit_window_seconds: float
    provider_probe_cache_seconds: float
    provider_runtime_delay_seconds: float
    comfyui_api_url: str
    auto_start_comfyui: bool
    comfyui_dir: Path
    comfyui_venv_dir: Path
    comfyui_custom_nodes_dir: Path
    comfyui_models_dir: Path
    comfyui_workflows_dir: Path
    comfyui_diffueraser_workflow: Path
    comfyui_segmentation_repo: str
    local_fallback_mode: str
    local_fallback_delogo_x: int | None
    local_fallback_delogo_y: int | None
    local_fallback_delogo_w: int | None
    local_fallback_delogo_h: int | None
    file_retention_days: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    repo_root = _repo_root()
    storage_root = Path(os.getenv("DWM_STORAGE_ROOT", repo_root / "storage")).expanduser().resolve()
    inbox_dir = Path(os.getenv("DWM_INBOX_DIR", storage_root / "inbox")).expanduser().resolve()
    outbox_dir = Path(os.getenv("DWM_OUTBOX_DIR", storage_root / "outbox")).expanduser().resolve()
    db_path = Path(os.getenv("DWM_DB_PATH", storage_root / "app.db")).expanduser().resolve()
    runtime_root = Path(os.getenv("DWM_RUNTIME_ROOT", repo_root / ".runtime")).expanduser().resolve()
    comfyui_dir = Path(
        os.getenv("DWM_COMFYUI_DIR", runtime_root / "ComfyUI")
    ).expanduser().resolve()
    comfyui_venv_dir = Path(os.getenv("DWM_COMFYUI_VENV_DIR", runtime_root / ".venv")).expanduser().resolve()
    comfyui_custom_nodes_dir = Path(
        os.getenv("DWM_COMFYUI_CUSTOM_NODES_DIR", comfyui_dir / "custom_nodes")
    ).expanduser().resolve()
    comfyui_models_dir = Path(os.getenv("DWM_COMFYUI_MODELS_DIR", comfyui_dir / "models")).expanduser().resolve()
    comfyui_workflows_dir = Path(
        os.getenv("DWM_COMFYUI_WORKFLOWS_DIR", repo_root / "workflows")
    ).expanduser().resolve()
    comfyui_diffueraser_workflow = Path(
        os.getenv("DWM_COMFYUI_DIFFUERASER_WORKFLOW", comfyui_workflows_dir / "sam2_diffueraser_api.json")
    ).expanduser().resolve()
    delogo_x = os.getenv("DWM_LOCAL_FALLBACK_DELOGO_X")
    delogo_y = os.getenv("DWM_LOCAL_FALLBACK_DELOGO_Y")
    delogo_w = os.getenv("DWM_LOCAL_FALLBACK_DELOGO_W")
    delogo_h = os.getenv("DWM_LOCAL_FALLBACK_DELOGO_H")

    return Settings(
        repo_root=repo_root,
        storage_root=storage_root,
        inbox_dir=inbox_dir,
        outbox_dir=outbox_dir,
        db_path=db_path,
        runtime_root=runtime_root,
        default_tenant_id=os.getenv("DWM_DEFAULT_TENANT_ID", "local-dev"),
        default_api_key=os.getenv("DWM_DEFAULT_API_KEY", "dev-secret-key"),
        max_upload_bytes=int(os.getenv("DWM_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))),
        worker_poll_interval_seconds=float(os.getenv("DWM_WORKER_POLL_INTERVAL_SECONDS", "1.0")),
        job_claim_timeout_seconds=int(os.getenv("DWM_JOB_CLAIM_TIMEOUT_SECONDS", "300")),
        job_claim_heartbeat_seconds=float(os.getenv("DWM_JOB_CLAIM_HEARTBEAT_SECONDS", "30.0")),
        callback_retry_count=int(os.getenv("DWM_CALLBACK_RETRY_COUNT", "3")),
        callback_retry_delay_seconds=float(os.getenv("DWM_CALLBACK_RETRY_DELAY_SECONDS", "1.0")),
        submit_rate_limit_count=int(os.getenv("DWM_SUBMIT_RATE_LIMIT_COUNT", "60")),
        submit_rate_limit_window_seconds=float(os.getenv("DWM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS", "60.0")),
        provider_probe_cache_seconds=float(os.getenv("DWM_PROVIDER_PROBE_CACHE_SECONDS", "10.0")),
        provider_runtime_delay_seconds=float(os.getenv("DWM_PROVIDER_RUNTIME_DELAY_SECONDS", "0.2")),
        comfyui_api_url=os.getenv("DWM_COMFYUI_API_URL", "http://127.0.0.1:8188"),
        auto_start_comfyui=_env_bool("DWM_AUTO_START_COMFYUI", False),
        comfyui_dir=comfyui_dir,
        comfyui_venv_dir=comfyui_venv_dir,
        comfyui_custom_nodes_dir=comfyui_custom_nodes_dir,
        comfyui_models_dir=comfyui_models_dir,
        comfyui_workflows_dir=comfyui_workflows_dir,
        comfyui_diffueraser_workflow=comfyui_diffueraser_workflow,
        comfyui_segmentation_repo=os.getenv("DWM_COMFYUI_SEGMENTATION_REPO", "briaai/RMBG-2.0"),
        local_fallback_mode=os.getenv("DWM_LOCAL_FALLBACK_MODE", "ffmpeg_copy"),
        local_fallback_delogo_x=int(delogo_x) if delogo_x is not None else None,
        local_fallback_delogo_y=int(delogo_y) if delogo_y is not None else None,
        local_fallback_delogo_w=int(delogo_w) if delogo_w is not None else None,
        local_fallback_delogo_h=int(delogo_h) if delogo_h is not None else None,
        file_retention_days=int(os.getenv("DWM_FILE_RETENTION_DAYS", "7")),
    )
