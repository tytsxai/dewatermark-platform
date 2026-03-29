from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from wm_platform.config import Settings


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_runtime_lock(settings: Settings) -> dict[str, Any]:
    return _read_yaml(settings.runtime_root / "lock.yaml")


def load_model_manifest(settings: Settings) -> dict[str, Any]:
    return _read_yaml(settings.runtime_root / "models" / "manifest.yaml")


def expected_repo_paths(settings: Settings) -> list[Path]:
    lock = load_runtime_lock(settings)
    repositories = lock.get("repositories", {})
    paths: list[Path] = []
    for spec in repositories.values():
        if isinstance(spec, dict) and spec.get("target"):
            paths.append((settings.repo_root / str(spec["target"])).resolve())
    return paths


def expected_model_entries(settings: Settings) -> list[dict[str, Any]]:
    manifest = load_model_manifest(settings)
    entries = manifest.get("models", [])
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict)]
