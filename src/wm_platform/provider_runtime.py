from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin

import httpx
from wm_platform.comfy_runtime import start_comfyui, wait_for_comfyui
from wm_platform.config import Settings
from wm_platform.errors import AppError
from wm_platform.models import JobRecord, ProviderProbeResult, RunMetadataRecord
from wm_platform.repository import JobRepository
from wm_platform.runtime_contract import expected_model_entries, expected_repo_paths
from wm_platform.storage import build_output_path

AUTO_FALLBACK_ORDER = ["comfy_diffueraser", "local_fallback"]
_PROBE_CACHE: dict[tuple[str, str, str, str], tuple[float, list[ProviderProbeResult]]] = {}

# Quality profiles 配置
QUALITY_PROFILES = {
    "fast": {
        "steps": 2,
        "subvideo_length": 50,
        "neighbor_length": 10,
        "mask_dilation_iter": 1,
        "ref_stride": 10,
    },
    "balanced": {
        "steps": 5,
        "subvideo_length": 70,
        "neighbor_length": 14,
        "mask_dilation_iter": 2,
        "ref_stride": 10,
    },
    "quality": {
        "steps": 7,
        "subvideo_length": 100,
        "neighbor_length": 20,
        "mask_dilation_iter": 3,
        "ref_stride": 10,
    },
}

# Workflow 映射
WORKFLOW_MAP = {
    "fast": "sam2_diffueraser_api.json",
    "balanced": "sam2_diffueraser_balanced.json",
    "quality": "sam2_diffueraser_quality.json",
    "corner_hq": "corner_watermark_hq.json",
}


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
    def __init__(self, name: str, settings: Settings, repository: JobRepository | None = None) -> None:
        super().__init__(name=name, settings=settings)
        self.repository = repository
    def probe(self) -> ProviderProbeResult:
        installation_issues = self._missing_installation_bits()
        workflow_issue = self._workflow_issue()
        workflow_ready = workflow_issue is None
        missing_models = self._missing_models()
        api_issue = self._api_issue()
        reasons = [*installation_issues]
        if workflow_issue:
            reasons.append(workflow_issue)
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
            "workflow_issue": workflow_issue,
            "segmentation_repo": self.settings.comfyui_segmentation_repo,
            "api_issue": api_issue,
            "automatic_ai_pipeline": "wired",
        }
        return ProviderProbeResult(
            name=self.name,
            installed=not installation_issues,
            runnable=not reasons,
            message="ready" if not reasons else "; ".join(reasons[:3]),
            details=details,
        )

    def run(self, job: JobRecord) -> dict[str, str]:
        prompt = self._build_prompt(job)
        with httpx.Client(timeout=None) as client:
            device = self._ensure_comfyui_ready(client)
            prompt = self._inject_prompt_runtime_values(prompt, job, device)
            prompt_id = self._queue_prompt(client, prompt, job.job_id)
            artifact = self._wait_for_prompt_result(client, prompt_id)
            output_path = self._download_artifact(client, artifact, job)

            # 记录运行元数据
            self._record_run_metadata(job, device)
        return {"output_path": str(output_path)}

    def _record_run_metadata(self, job: JobRecord, device: str) -> None:
        """记录运行元数据到数据库"""
        if self.repository is None:
            return
        try:
            profile = self.settings.quality_mode
            profile_config = QUALITY_PROFILES.get(profile, QUALITY_PROFILES["balanced"])
            metadata = RunMetadataRecord(
                id=0,
                job_id=job.job_id,
                workflow_name=self.settings.comfyui_diffueraser_workflow.name,
                quality_profile=profile,
                steps=profile_config["steps"],
                subvideo_length=profile_config["subvideo_length"],
                neighbor_length=profile_config["neighbor_length"],
                mask_dilation_iter=profile_config["mask_dilation_iter"],
                device=device,
                seed=int(hashlib.sha256(job.job_id.encode("utf-8")).hexdigest()[:8], 16),
                scene_type=None,
                confidence_level=None,
                created_at=datetime.now(UTC).replace(microsecond=0),
            )
            self.repository.record_run_metadata(metadata)
        except Exception:
            # 元数据记录失败不影响主流程
            pass

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

    def _workflow_issue(self) -> str | None:
        if not self.settings.comfyui_diffueraser_workflow.exists():
            return f"missing workflow {self.settings.comfyui_diffueraser_workflow.name}"
        try:
            prompt = json.loads(self.settings.comfyui_diffueraser_workflow.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return f"invalid workflow json: {exc.msg}"
        if not isinstance(prompt, dict) or not prompt:
            return "workflow prompt is empty"
        if any(not isinstance(node, dict) or "class_type" not in node for node in prompt.values()):
            return "workflow prompt must use ComfyUI API export format"
        return None

    def _api_issue(self) -> str | None:
        try:
            response = httpx.get(urljoin(self.settings.comfyui_api_url, "/system_stats"), timeout=2.0)
        except Exception:
            return "ComfyUI API unreachable"
        if response.status_code != 200:
            return f"ComfyUI API returned {response.status_code}"
        return None

    def _build_prompt(self, job: JobRecord) -> dict[str, dict[str, object]]:
        workflow_issue = self._workflow_issue()
        if workflow_issue:
            raise AppError("PROVIDER_NOT_AVAILABLE", workflow_issue, 503)
        template = json.loads(self.settings.comfyui_diffueraser_workflow.read_text(encoding="utf-8"))
        if not isinstance(template, dict):
            raise AppError("PROVIDER_NOT_AVAILABLE", "workflow prompt is invalid", 503)

        # 应用 quality profile 参数
        profile = self.settings.quality_mode
        profile_config = QUALITY_PROFILES.get(profile, QUALITY_PROFILES["balanced"])

        replacements: dict[str, object] = {
            "__INPUT_VIDEO__": job.input_path,
            "__SEG_REPO__": self.settings.comfyui_segmentation_repo,
            "__OUTPUT_PREFIX__": f"video/{job.job_id}",
            "__VAE_MODEL__": self._resolve_model_input(
                roots=[self.settings.comfyui_models_dir / "vae"],
                candidates=["sd-vae-ft-mse.safetensors"],
                label="vae",
            ),
            "__LORA_MODEL__": self._resolve_model_input(
                roots=[self.settings.comfyui_models_dir / "loras"],
                candidates=["sd15/pcm_sd15_smallcfg_2step_converted.safetensors", "pcm_sd15_smallcfg_2step_converted.safetensors"],
                label="lora",
            ),
            "__CLIP_MODEL__": self._resolve_model_input(
                roots=[self.settings.comfyui_models_dir / "text_encoders", self.settings.comfyui_models_dir / "clip"],
                candidates=["clip_l.safetensors"],
                label="clip",
            ),
            "__PROPAINTER_MODEL__": self._resolve_model_input(
                roots=[self.settings.comfyui_models_dir / "DiffuEraser"],
                candidates=["propainter/ProPainter.pth", "ProPainter.pth"],
                label="propainter",
            ),
            "__FLOW_MODEL__": self._resolve_model_input(
                roots=[self.settings.comfyui_models_dir / "DiffuEraser"],
                candidates=["propainter/recurrent_flow_completion.pth", "recurrent_flow_completion.pth"],
                label="flow",
            ),
            "__FIX_RAFT_MODEL__": self._resolve_model_input(
                roots=[self.settings.comfyui_models_dir / "DiffuEraser"],
                candidates=["propainter/raft-things.pth", "raft-things.pth"],
                label="fix_raft",
            ),
            "__SEED__": int(hashlib.sha256(job.job_id.encode("utf-8")).hexdigest()[:8], 16),
        }
        prompt = self._replace_placeholders(copy.deepcopy(template), replacements)

        # 注入 quality profile 参数到 workflow 节点
        prompt = self._apply_quality_profile(prompt, profile_config)
        return prompt

    def _apply_quality_profile(
        self, prompt: dict[str, dict[str, object]], profile_config: dict[str, int]
    ) -> dict[str, dict[str, object]]:
        """应用 quality profile 参数到 workflow 节点"""
        # 修改 Propainter_Sampler 节点 (节点 5)
        if "5" in prompt and "inputs" in prompt["5"]:
            inputs = prompt["5"]["inputs"]
            if isinstance(inputs, dict):
                if "mask_dilation_iter" in inputs:
                    inputs["mask_dilation_iter"] = profile_config.get("mask_dilation_iter", inputs["mask_dilation_iter"])
                if "ref_stride" in inputs:
                    inputs["ref_stride"] = profile_config.get("ref_stride", inputs.get("ref_stride", 10))
                if "neighbor_length" in inputs:
                    inputs["neighbor_length"] = profile_config.get("neighbor_length", inputs["neighbor_length"])
                if "subvideo_length" in inputs:
                    inputs["subvideo_length"] = profile_config.get("subvideo_length", inputs["subvideo_length"])

        # 修改 DiffuEraser_Sampler 节点 (节点 9)
        if "9" in prompt and "inputs" in prompt["9"]:
            inputs = prompt["9"]["inputs"]
            if isinstance(inputs, dict):
                if "steps" in inputs:
                    inputs["steps"] = profile_config.get("steps", inputs["steps"])

        return prompt

    def _inject_prompt_runtime_values(
        self,
        prompt: dict[str, dict[str, object]],
        job: JobRecord,
        device: str,
    ) -> dict[str, dict[str, object]]:
        return self._replace_placeholders(
            prompt,
            {
                "__PROP_DEVICE__": device,
                "__INPUT_VIDEO__": job.input_path,
                "__OUTPUT_PREFIX__": f"video/{job.job_id}",
                "__SEG_REPO__": self.settings.comfyui_segmentation_repo,
            },
        )

    def _resolve_model_input(self, roots: list[Path], candidates: list[str], label: str) -> str:
        for root in roots:
            if not root.exists():
                continue
            for candidate in candidates:
                direct_path = root / candidate
                if direct_path.exists():
                    return direct_path.relative_to(root).as_posix()
            for candidate in candidates:
                candidate_name = Path(candidate).name
                matches = sorted(path for path in root.rglob(candidate_name) if path.is_file())
                if matches:
                    return matches[0].relative_to(root).as_posix()
        raise AppError("PROVIDER_NOT_AVAILABLE", f"missing required {label} model input", 503)

    def _replace_placeholders(self, payload: object, replacements: dict[str, object]) -> object:
        if isinstance(payload, str):
            return replacements.get(payload, payload)
        if isinstance(payload, list):
            return [self._replace_placeholders(item, replacements) for item in payload]
        if isinstance(payload, dict):
            return {key: self._replace_placeholders(value, replacements) for key, value in payload.items()}
        return payload

    def _ensure_comfyui_ready(self, client: httpx.Client) -> str:
        stats = self._system_stats(client)
        if stats is None and self.settings.auto_start_comfyui:
            start_comfyui(self.settings)
            health = wait_for_comfyui(self.settings)
            if not bool(health.get("ok")):
                raise AppError("PROVIDER_NOT_AVAILABLE", "ComfyUI API is unavailable after auto-start", 503)
            payload = health.get("payload")
            if isinstance(payload, dict):
                stats = payload
        if stats is None:
            raise AppError("PROVIDER_NOT_AVAILABLE", "ComfyUI API is unavailable", 503)

        devices = stats.get("devices")
        if isinstance(devices, list) and devices:
            device_type = str(devices[0].get("type", "")).lower()
            if device_type in {"cuda", "mps", "cpu"}:
                return device_type
        return "cpu"

    def _system_stats(self, client: httpx.Client) -> dict[str, object] | None:
        try:
            response = client.get(urljoin(self.settings.comfyui_api_url, "/system_stats"), timeout=2.0)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _queue_prompt(self, client: httpx.Client, prompt: dict[str, dict[str, object]], prompt_id: str) -> str:
        response = client.post(
            urljoin(self.settings.comfyui_api_url, "/prompt"),
            json={"prompt": prompt, "prompt_id": prompt_id, "client_id": prompt_id},
        )
        if response.status_code != 200:
            detail = response.text[:1000] if response.text else "queue prompt failed"
            raise AppError("PROVIDER_RUN_FAILED", f"ComfyUI prompt rejected: {detail}", 500)
        payload = response.json()
        queued_prompt_id = str(payload.get("prompt_id", prompt_id))
        if not queued_prompt_id:
            raise AppError("PROVIDER_RUN_FAILED", "ComfyUI prompt response missing prompt_id", 500)
        return queued_prompt_id

    def _wait_for_prompt_result(self, client: httpx.Client, prompt_id: str) -> dict[str, str]:
        deadline = time.monotonic() + max(600.0, float(self.settings.job_claim_timeout_seconds) * 3.0)
        while time.monotonic() < deadline:
            response = client.get(urljoin(self.settings.comfyui_api_url, f"/history/{prompt_id}"))
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict) and prompt_id in payload:
                    history_item = payload[prompt_id]
                    artifact = self._extract_artifact(history_item)
                    if artifact is not None:
                        return artifact
                    status = history_item.get("status", {})
                    if isinstance(status, dict) and status.get("completed"):
                        messages = status.get("messages") or []
                        detail = "; ".join(str(item) for item in messages) or "ComfyUI execution completed without video output"
                        if status.get("status_str") == "error":
                            raise AppError("PROVIDER_RUN_FAILED", f"ComfyUI execution failed: {detail}", 500)
                        raise AppError("PROVIDER_RUN_FAILED", detail, 500)
            time.sleep(1.0)
        raise AppError("PROVIDER_RUN_FAILED", "ComfyUI execution timed out", 500)

    def _extract_artifact(self, history_item: object) -> dict[str, str] | None:
        if not isinstance(history_item, dict):
            return None
        outputs = history_item.get("outputs", {})
        if not isinstance(outputs, dict):
            return None

        ordered_nodes = []
        if "11" in outputs:
            ordered_nodes.append(outputs["11"])
        ordered_nodes.extend(value for key, value in outputs.items() if key != "11")
        for node_output in ordered_nodes:
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images", []):
                if not isinstance(image, dict):
                    continue
                filename = str(image.get("filename", ""))
                if Path(filename).suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
                    continue
                return {
                    "filename": filename,
                    "subfolder": str(image.get("subfolder", "")),
                    "type": str(image.get("type", "output")),
                }
        return None

    def _download_artifact(self, client: httpx.Client, artifact: dict[str, str], job: JobRecord) -> Path:
        response = client.get(urljoin(self.settings.comfyui_api_url, "/view"), params=artifact)
        if response.status_code != 200:
            detail = response.text[:1000] if response.text else "artifact download failed"
            raise AppError("PROVIDER_RUN_FAILED", f"failed to fetch ComfyUI artifact: {detail}", 500)
        output_path = build_output_path(job.job_id, artifact["filename"], self.settings)
        # Atomic write: write to temp file first, then rename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp.{job.job_id}")
        try:
            temp_path.write_bytes(response.content)
            temp_path.rename(output_path)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise
        return output_path


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
        if mode == "ffmpeg_copy":
            shutil.copyfile(source_path, output_path)
            return {"output_path": str(output_path)}

        command = self._build_ffmpeg_command(Path(source_path), output_path)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
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
    @lru_cache(maxsize=4)
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
    def __init__(self, settings: Settings, repository: JobRepository | None = None) -> None:
        self.settings = settings
        self.repository = repository
        self.registry: dict[str, _BaseProvider] = {
            "comfy_diffueraser": _ComfyDiffuEraserProvider(
                name="comfy_diffueraser", settings=settings, repository=repository
            ),
            "local_fallback": _LocalFallbackProvider(name="local_fallback", settings=settings),
        }

    def probe_all(self) -> list[ProviderProbeResult]:
        cache_key = (
            str(self.settings.runtime_root),
            self.settings.comfyui_api_url,
            self.settings.local_fallback_mode,
            str(self.settings.comfyui_diffueraser_workflow),
        )
        now = time.monotonic()
        cached = _PROBE_CACHE.get(cache_key)
        if cached and (now - cached[0]) < max(0.0, self.settings.provider_probe_cache_seconds):
            return cached[1]

        probes = [self.registry[name].probe() for name in AUTO_FALLBACK_ORDER]
        _PROBE_CACHE[cache_key] = (now, probes)
        return probes

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
