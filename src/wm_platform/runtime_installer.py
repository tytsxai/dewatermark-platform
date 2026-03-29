from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from wm_platform.config import Settings
from wm_platform.runtime_contract import load_runtime_lock


class RuntimeInstaller:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = load_runtime_lock(settings)

    def _run(self, command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
        )

    def _ensure_repo(self, name: str, spec: dict[str, Any]) -> list[str]:
        target = (self.settings.repo_root / str(spec["target"])).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        messages: list[str] = []
        git_dir = target / ".git"
        if target.exists() and not git_dir.exists():
            if any(target.iterdir()):
                raise RuntimeError(f"target exists and is not a git repo: {target}")
            target.rmdir()
        if not target.exists():
            result = self._run(["git", "clone", str(spec["url"]), str(target)])
            if result.returncode != 0:
                raise RuntimeError(f"clone {name} failed: {result.stderr.strip()}")
            messages.append(f"cloned {name}")
        fetch = self._run(["git", "fetch", "--all", "--tags"], cwd=target)
        if fetch.returncode != 0:
            raise RuntimeError(f"fetch {name} failed: {fetch.stderr.strip()}")
        checkout = self._run(["git", "checkout", str(spec["ref"])], cwd=target)
        if checkout.returncode != 0:
            raise RuntimeError(f"checkout {name} failed: {checkout.stderr.strip()}")
        messages.append(f"pinned {name} to {str(spec['ref'])[:12]}")
        return messages

    def _ensure_runtime_venv(self) -> list[str]:
        venv_dir = self.settings.comfyui_venv_dir
        python_version = str(self.lock.get("runtime", {}).get("python", "3.12"))
        messages: list[str] = []
        if shutil.which("uv") is None:
            raise RuntimeError("uv not found")
        if not venv_dir.exists():
            install_python = self._run(["uv", "python", "install", python_version])
            if install_python.returncode != 0:
                raise RuntimeError(f"install python {python_version} failed: {install_python.stderr.strip()}")
            create_venv = self._run(["uv", "venv", str(venv_dir), "--python", python_version])
            if create_venv.returncode != 0:
                raise RuntimeError(f"create venv failed: {create_venv.stderr.strip()}")
            messages.append(f"created runtime venv {venv_dir}")
        return messages

    def _install_python_packages(self) -> list[str]:
        venv_python = self.settings.comfyui_venv_dir / "bin" / "python"
        comfy_requirements = self.settings.comfyui_dir / "requirements.txt"
        messages: list[str] = []
        if shutil.which("uv") is None:
            raise RuntimeError("uv not found")
        if venv_python.exists() and comfy_requirements.exists():
            install = self._run(["uv", "pip", "install", "--python", str(venv_python), "-r", str(comfy_requirements)])
            if install.returncode != 0:
                raise RuntimeError(f"install comfy requirements failed: {install.stderr.strip()}")
            messages.append("installed ComfyUI requirements")
        for requirement in self.settings.comfyui_dir.glob("custom_nodes/*/requirements.txt"):
            install = self._run(["uv", "pip", "install", "--python", str(venv_python), "-r", str(requirement)])
            if install.returncode != 0:
                raise RuntimeError(f"install node requirements failed {requirement.parent.name}: {install.stderr.strip()}")
            messages.append(f"installed node requirements {requirement.parent.name}")
        compat = self._run(["uv", "pip", "install", "--python", str(venv_python), "numpy<2"])
        if compat.returncode != 0:
            raise RuntimeError(f"pin numpy<2 failed: {compat.stderr.strip()}")
        messages.append("pinned numpy<2")
        diffueraser = self._run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(venv_python),
                "diffusers>=0.35,<0.36",
                "transformers>=4.56,<5",
                "peft>=0.18",
                "accelerate>=1.13",
                "huggingface-hub<1",
                "matplotlib",
            ]
        )
        if diffueraser.returncode != 0:
            raise RuntimeError(f"install diffueraser compatible deps failed: {diffueraser.stderr.strip()}")
        messages.append("pinned diffueraser compatible deps and matplotlib")
        return messages

    def plan(self) -> dict[str, object]:
        return {
            "python": str(self.lock.get("runtime", {}).get("python", "3.12")),
            "runtime_root": str(self.settings.runtime_root),
            "repositories": self.lock.get("repositories", {}),
            "venv_dir": str(self.settings.comfyui_venv_dir),
        }

    def install(self, *, include_python_packages: bool = True) -> list[str]:
        messages: list[str] = []
        messages.extend(self._ensure_runtime_venv())
        repositories = self.lock.get("repositories", {})
        if "comfyui" in repositories:
            messages.extend(self._ensure_repo("comfyui", repositories["comfyui"]))
        self.settings.comfyui_custom_nodes_dir.mkdir(parents=True, exist_ok=True)
        for name, spec in repositories.items():
            if name == "comfyui":
                continue
            if isinstance(spec, dict):
                messages.extend(self._ensure_repo(str(name), spec))
        if include_python_packages:
            messages.extend(self._install_python_packages())
        else:
            messages.append("skipped python package installation")
        return messages
