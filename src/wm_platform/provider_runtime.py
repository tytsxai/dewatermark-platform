from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx
from wm_platform.config import Settings
from wm_platform.errors import AppError
from wm_platform.models import JobRecord, ProviderProbeResult
from wm_platform.runtime_contract import expected_model_entries, expected_repo_paths
from wm_platform.storage import build_output_path

AUTO_FALLBACK_ORDER = ["comfy_diffueraser", "cloud_inpaint", "local_fallback"]


class ProviderExecutionError(Exception):
    def __init__(self, provider_selected: str | None, error_code: str, error_message: str) -> None:
        super().__init__(error_message)
        self.provider_selected = provider_selected
        self.error_code = error_code
        self.error_message = error_message


@dataclass
class _BaseProvider:
    name: str
    settings: Settings

    def probe(self) -> ProviderProbeResult:
        raise NotImplementedError

    def run(self, job: JobRecord) -> dict[str, str]:
        raise NotImplementedError


class _UnavailableProvider(_BaseProvider):
    def __init__(self, name: str, settings: Settings, message: str) -> None:
        super().__init__(name=name, settings=settings)
        self._message = message

    def probe(self) -> ProviderProbeResult:
        return ProviderProbeResult(
            name=self.name,
            installed=False,
            runnable=False,
            message=self._message,
            details={"provider": self.name},
        )

    def run(self, job: JobRecord) -> dict[str, str]:
        raise AppError("PROVIDER_NOT_AVAILABLE", f"{self.name} is not available in MVP")


class _ComfyDiffuEraserProvider(_BaseProvider):
    def probe(self) -> ProviderProbeResult:
        installation_issues = self._missing_installation_bits()
        workflow_ready = self.settings.comfyui_diffueraser_workflow.exists()
        missing_models = self._missing_models()
        api_issue = self._api_issue()
        reasons = [*installation_issues]
        if not workflow_ready:
            reasons.append(f"missing workflow {self.settings.comfyui_diffueraser_workflow.name}")
        if missing_models:
            reasons.append(f"missing models: {', '.join(missing_models[:3])}")
        if api_issue:
            reasons.append(api_issue)
        details = {
            "api_url": self.settings.comfyui_api_url,
            "auto_start_comfyui": self.settings.auto_start_comfyui,
            "comfyui_dir": str(self.settings.comfyui_dir),
            "venv_python": str(self.settings.comfyui_venv_dir / "bin" / "python"),
            "custom_nodes_dir": str(self.settings.comfyui_custom_nodes_dir),
            "models_dir": str(self.settings.comfyui_models_dir),
            "workflow_path": str(self.settings.comfyui_diffueraser_workflow),
            "runtime_root": str(self.settings.runtime_root),
            "missing_installation_bits": installation_issues,
            "missing_models": missing_models,
            "workflow_ready": workflow_ready,
            "api_issue": api_issue,
            "automatic_ai_pipeline": "not_wired",
        }
        return ProviderProbeResult(
            name=self.name,
            installed=not installation_issues,
            runnable=not reasons,
            message="ready" if not reasons else "; ".join(reasons[:3]),
            details=details,
        )

    def run(self, job: JobRecord) -> dict[str, str]:
        raise AppError(
            "PROVIDER_NOT_AVAILABLE",
            "comfy_diffueraser is not wired for execution yet; probe/doctor only in current stage",
            503,
        )

    def _missing_installation_bits(self) -> list[str]:
        repo_paths = expected_repo_paths(self.settings)
        reasons: list[str] = []
        if not repo_paths:
            reasons.append("runtime lock file missing or empty")
        missing_paths = [path for path in repo_paths if not path.exists()]
        if missing_paths:
            labels = [path.name or str(path) for path in missing_paths[:3]]
            reasons.append(f"missing runtime paths: {', '.join(labels)}")
        if not (self.settings.comfyui_venv_dir / "bin" / "python").exists():
            reasons.append("missing ComfyUI venv")
        return reasons

    def _missing_models(self) -> list[str]:
        entries = expected_model_entries(self.settings)
        if not entries:
            return ["model manifest missing or empty"]
        missing: list[str] = []
        for entry in entries:
            if not bool(entry.get("required", False)):
                continue
            expected_path = (self.settings.repo_root / str(entry.get("expected_path", ""))).resolve()
            if not expected_path.exists():
                missing.append(str(entry.get("name", expected_path.name)))
        return missing

    def _api_issue(self) -> str | None:
        try:
            response = httpx.get(urljoin(self.settings.comfyui_api_url, "/system_stats"), timeout=2.0)
        except Exception:
            return "ComfyUI API unreachable"
        if response.status_code != 200:
            return f"ComfyUI API returned {response.status_code}"
        return None


class _LocalFallbackProvider(_BaseProvider):
    def probe(self) -> ProviderProbeResult:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return ProviderProbeResult(
                name=self.name,
                installed=False,
                runnable=False,
                message="ffmpeg not found in PATH",
                details={"mode": self.settings.local_fallback_mode, "ffmpeg_path": None},
            )

        mode = self.settings.local_fallback_mode.strip().lower()
        if mode == "ffmpeg_copy":
            return ProviderProbeResult(
                name=self.name,
                installed=True,
                runnable=True,
                message="ffmpeg copy mode",
                details={"mode": "ffmpeg_copy", "ffmpeg_path": ffmpeg_path},
            )

        if mode == "delogo":
            if not self._has_complete_delogo_config():
                return ProviderProbeResult(
                    name=self.name,
                    installed=True,
                    runnable=False,
                    message="delogo mode requires x/y/w/h coordinates",
                    details={"mode": "delogo", "ffmpeg_path": ffmpeg_path},
                )
            if not self._ffmpeg_supports_delogo():
                return ProviderProbeResult(
                    name=self.name,
                    installed=True,
                    runnable=False,
                    message="ffmpeg delogo filter not available",
                    details={"mode": "delogo", "ffmpeg_path": ffmpeg_path},
                )
            return ProviderProbeResult(
                name=self.name,
                installed=True,
                runnable=True,
                message="ffmpeg delogo mode",
                details={
                    "mode": "delogo",
                    "ffmpeg_path": ffmpeg_path,
                    "x": self.settings.local_fallback_delogo_x,
                    "y": self.settings.local_fallback_delogo_y,
                    "w": self.settings.local_fallback_delogo_w,
                    "h": self.settings.local_fallback_delogo_h,
                },
            )

        return ProviderProbeResult(
            name=self.name,
            installed=True,
            runnable=False,
            message=f"unsupported local_fallback_mode: {self.settings.local_fallback_mode}",
            details={"mode": self.settings.local_fallback_mode, "ffmpeg_path": ffmpeg_path},
        )

    def run(self, job: JobRecord) -> dict[str, str]:
        source_path = job.input_path
        output_path = build_output_path(job.job_id, source_path, self.settings)
        mode = self.settings.local_fallback_mode.strip().lower()
        command = self._build_ffmpeg_command(Path(source_path), output_path)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            if mode == "ffmpeg_copy":
                shutil.copyfile(source_path, output_path)
                return {"output_path": str(output_path)}
            stderr = (completed.stderr or "").strip()
            detail = stderr.splitlines()[-1] if stderr else "ffmpeg failed"
            raise AppError("PROVIDER_RUN_FAILED", f"local_fallback ffmpeg error: {detail}", 500)
        return {"output_path": str(output_path)}

    def _build_ffmpeg_command(self, source_path: Path, output_path: Path) -> list[str]:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise AppError("PROVIDER_NOT_AVAILABLE", "ffmpeg is not available in PATH", 503)

        mode = self.settings.local_fallback_mode.strip().lower()
        base_command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
        ]
        if mode == "ffmpeg_copy":
            return [
                *base_command,
                "-c",
                "copy",
                str(output_path),
            ]

        if mode == "delogo":
            if not self._has_complete_delogo_config():
                raise AppError("PROVIDER_NOT_AVAILABLE", "delogo mode requires x/y/w/h coordinates", 503)
            if not self._ffmpeg_supports_delogo():
                raise AppError("PROVIDER_NOT_AVAILABLE", "ffmpeg delogo filter not available", 503)
            vf = (
                f"delogo=x={self.settings.local_fallback_delogo_x}:"
                f"y={self.settings.local_fallback_delogo_y}:"
                f"w={self.settings.local_fallback_delogo_w}:"
                f"h={self.settings.local_fallback_delogo_h}"
            )
            return [
                *base_command,
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "copy",
                str(output_path),
            ]

        raise AppError(
            "PROVIDER_NOT_AVAILABLE",
            f"unsupported local_fallback_mode: {self.settings.local_fallback_mode}",
            503,
        )

    def _has_complete_delogo_config(self) -> bool:
        return all(
            value is not None
            for value in (
                self.settings.local_fallback_delogo_x,
                self.settings.local_fallback_delogo_y,
                self.settings.local_fallback_delogo_w,
                self.settings.local_fallback_delogo_h,
            )
        )

    @staticmethod
    def _ffmpeg_supports_delogo() -> bool:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return False
        completed = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return False
        return " delogo " in completed.stdout


class ProviderRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry: dict[str, _BaseProvider] = {
            "comfy_diffueraser": _ComfyDiffuEraserProvider(name="comfy_diffueraser", settings=settings),
            "cloud_inpaint": _UnavailableProvider(
                name="cloud_inpaint",
                settings=settings,
                message="provider not wired in MVP",
            ),
            "local_fallback": _LocalFallbackProvider(name="local_fallback", settings=settings),
        }

    def probe_all(self) -> list[ProviderProbeResult]:
        return [self.registry[name].probe() for name in AUTO_FALLBACK_ORDER]

    def run_with_fallback(self, job: JobRecord) -> tuple[str, str]:
        chain = self._resolve_fallback_chain(job)
        last_provider: str | None = None
        unavailable_count = 0
        failed_messages: list[str] = []

        for provider_name in chain:
            provider = self.registry.get(provider_name)
            if provider is None:
                unavailable_count += 1
                failed_messages.append(f"{provider_name}: not registered")
                continue

            last_provider = provider_name
            probe = provider.probe()
            if not probe.runnable:
                unavailable_count += 1
                failed_messages.append(f"{provider_name}: {probe.message or 'not runnable'}")
                continue

            try:
                result = provider.run(job)
                output_path = result.get("output_path")
                if not output_path:
                    raise AppError("PROVIDER_RUN_FAILED", f"{provider_name} returned empty output_path")
                return provider_name, output_path
            except AppError as exc:
                failed_messages.append(f"{provider_name}: {exc.error_message}")
            except Exception as exc:
                failed_messages.append(f"{provider_name}: {exc}")

        if unavailable_count == len(chain):
            raise ProviderExecutionError(
                provider_selected=last_provider,
                error_code="PROVIDER_NOT_AVAILABLE",
                error_message="all providers unavailable",
            )

        detail = "; ".join(failed_messages[-3:])
        raise ProviderExecutionError(
            provider_selected=last_provider,
            error_code="PROVIDER_RUN_FAILED",
            error_message=f"all providers failed: {detail}",
        )

    def _resolve_fallback_chain(self, job: JobRecord) -> list[str]:
        if job.provider_requested == "auto":
            return AUTO_FALLBACK_ORDER.copy()
        try:
            parsed = json.loads(job.fallback_chain_json)
            if isinstance(parsed, list) and parsed:
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        return [job.provider_requested]
