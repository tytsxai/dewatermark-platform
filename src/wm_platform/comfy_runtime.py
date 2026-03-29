from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx

from wm_platform.config import Settings


def comfy_python(settings: Settings) -> Path:
    return settings.comfyui_venv_dir / "bin" / "python"


def comfy_main(settings: Settings) -> Path:
    return settings.comfyui_dir / "main.py"


def build_comfyui_command(settings: Settings) -> list[str]:
    return [
        str(comfy_python(settings)),
        str(comfy_main(settings)),
        "--listen",
        "127.0.0.1",
        "--port",
        str(_port_from_api_url(settings.comfyui_api_url)),
        "--output-directory",
        str(settings.outbox_dir),
        "--disable-auto-launch",
    ]


def comfyui_health(settings: Settings) -> dict[str, object]:
    url = f"{settings.comfyui_api_url.rstrip('/')}/system_stats"
    try:
        response = httpx.get(url, timeout=2.0)
        response.raise_for_status()
        payload = response.json()
        return {
            "ok": True,
            "url": url,
            "status_code": response.status_code,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "error": str(exc),
        }


def wait_for_comfyui(settings: Settings, timeout_seconds: float = 60.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        health = comfyui_health(settings)
        if bool(health.get("ok")):
            return health
        time.sleep(1.0)
    return comfyui_health(settings)


def start_comfyui(settings: Settings) -> subprocess.Popen[str]:
    command = build_comfyui_command(settings)
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, text=True)


def _port_from_api_url(api_url: str) -> int:
    stripped = api_url.rsplit(":", 1)
    if len(stripped) == 2 and stripped[1].isdigit():
        return int(stripped[1])
    return 8188
