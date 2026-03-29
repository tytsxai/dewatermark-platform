from __future__ import annotations

from wm_platform.config import Settings
from wm_platform.provider_runtime import ProviderRuntime
from wm_platform.runtime_contract import expected_model_entries, expected_repo_paths


def provider_doctor_report(settings: Settings) -> dict[str, object]:
    probes = [item.model_dump() for item in ProviderRuntime(settings).probe_all()]
    return {
        "storage_root": str(settings.storage_root),
        "comfyui_api_url": settings.comfyui_api_url,
        "comfyui_dir": str(settings.comfyui_dir),
        "comfyui_custom_nodes_dir": str(settings.comfyui_custom_nodes_dir),
        "comfyui_models_dir": str(settings.comfyui_models_dir),
        "comfyui_workflow": str(settings.comfyui_diffueraser_workflow),
        "runtime_root": str(settings.runtime_root),
        "runtime_lock_file": str(settings.runtime_root / "lock.yaml"),
        "runtime_model_manifest": str(settings.runtime_root / "models" / "manifest.yaml"),
        "expected_repo_paths": [str(path) for path in expected_repo_paths(settings)],
        "expected_model_entries": expected_model_entries(settings),
        "providers": probes,
    }
