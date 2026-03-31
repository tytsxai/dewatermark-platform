# 去水印平台

一个独立的本地去水印服务仓库。

当前结论很明确：

- 原始方案适合“把视频去水印能力接入现有 OpenFang/shipinbot 工作流”
- 不适合直接当成“独立的通用去水印 API 平台”方案

所以这个仓库从一开始就按独立项目定义：

- 独立目录
- 独立仓库
- 独立 API
- 独立 worker
- 不和现有业务运行时路径混用

## 当前目标

先把需求和边界钉死，再开始编码。

MVP 先做：

- 本地部署
- 外部通过 HTTP API 提交任务
- 异步任务模型
- 视频去水印优先
- 保留图片去水印作为后续能力，但接口从第一天就预留
- 后端支持可插拔
- provider 路由和失败降级
- 幂等提交、状态查询、结果回调
- 本地可单机部署

当前默认 provider：

- `cloud_inpaint`
- `comfy_diffueraser`
- `local_fallback`

## 仓库结构

```text
docs/                 需求、审查、架构、API 文档
apps/api/             API 服务预留目录
apps/worker/          worker 服务预留目录
storage/inbox/        本地输入文件目录
storage/outbox/       本地产物目录
```

## 先看这些文档

- `docs/review.md`
- `docs/requirements.md`
- `docs/architecture.md`
- `docs/api.md`
- `docs/roadmap.md`
- `项目启动提示词.md`

## Local Workflow

1. Install dependencies:
   ```sh
   uv sync
   ```

2. Run the API:
   ```sh
   uv run python -m apps.api.main --host 0.0.0.0 --port 8000
   ```

3. Run a worker in another terminal:
   ```sh
   uv run python -m apps.worker.main
   ```

4. Inspect provider readiness:
   ```sh
   uv run dewatermark-worker --doctor
   ```

5. Inspect local AI runtime bootstrap plan:
   ```sh
   uv run dewatermark-worker --runtime-plan
   ```

6. Install only the local AI framework skeleton, not models:
   ```sh
   uv run dewatermark-worker --install-runtime --repos-only
   ```

7. Print the ComfyUI startup command:
   ```sh
   uv run dewatermark-worker --comfyui-plan
   ```

8. Start ComfyUI and wait for `/system_stats`:
   ```sh
   uv run dewatermark-worker --start-comfyui
   ```

9. Check ComfyUI health only:
   ```sh
   uv run dewatermark-worker --comfyui-health
   ```

The API startup creates `storage/app.db`, ensures `storage/inbox/` and `storage/outbox/`, and seeds the default API key.

## Default Credentials

- Default tenant: `local-dev`
- Default API key: `dev-secret-key`
- Header name: `X-API-Key`

## Storage Layout

- `storage/inbox/`: uploaded inputs
- `storage/outbox/`: worker outputs
- `storage/app.db`: SQLite job store

## Example Workflow

Submit a job:

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: first-job" \
  -F "media_type=video" \
  -F "provider=auto" \
  -F "file=@/absolute/path/to/local.mp4"
```

Check providers:

```sh
curl http://127.0.0.1:8000/v1/providers -H "X-API-Key: dev-secret-key"
```

Check job status:

```sh
curl http://127.0.0.1:8000/v1/jobs/<job_id> -H "X-API-Key: dev-secret-key"
```

## Platform Endpoints

- `GET /v1/jobs`: list jobs filtered by tenant and optional `status`, `provider`, `media_type`, `page`, `page_size`
- `GET /v1/jobs/{job_id}`: get status (existing)
- `GET /v1/jobs/{job_id}/result`: get `output_path`/`download_url` once job finishes
- `POST /v1/jobs/{job_id}/cancel`: cancel queued jobs only
- `GET /v1/providers`: check provider health and capabilities

## Environment Variables

Copy `.env.example` and adjust if needed before running, or set the variables listed below before starting API/worker.

- `DWM_DEFAULT_TENANT_ID` / `DWM_DEFAULT_API_KEY`: API key pair seeded on startup
- `DWM_STORAGE_ROOT`: storage directory that contains `inbox`, `outbox`, `app.db`
- `DWM_RUNTIME_ROOT`: AI runtime root directory, default `.runtime`
- `DWM_MAX_UPLOAD_BYTES`: upload size guard (default 512 MiB)
- `DWM_COMFYUI_API_URL`: local ComfyUI API address
- `DWM_AUTO_START_COMFYUI`: future Comfy auto-start switch, default off
- `DWM_COMFYUI_DIR` / `DWM_COMFYUI_VENV_DIR` / `DWM_COMFYUI_CUSTOM_NODES_DIR` / `DWM_COMFYUI_MODELS_DIR`: local AI runtime paths
- `DWM_LOCAL_FALLBACK_MODE`: `ffmpeg_copy` or `delogo`, controls how the local provider transforms video
- `DWM_LOCAL_FALLBACK_DELOGO_{X,Y,W,H}`: required together to enable delogo filter
- `DWM_FILE_RETENTION_DAYS`: how long input/output files are considered recent
- `DWM_SUBMIT_RATE_LIMIT_COUNT` / `DWM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS`: per-API-key submit rate limit, default `60` requests per `60s`
- `DWM_PROVIDER_RUNTIME_DELAY_SECONDS`: simulated runtime delay for fake providers
- `DWM_CALLBACK_RETRY_COUNT` / `DWM_CALLBACK_RETRY_DELAY_SECONDS`: callback retry policy

FFmpeg must be installed and on `PATH` for the local fallback provider to work (`brew install ffmpeg` or similar). If you only need a copy mode, leave the delogo variables unset.
`uv run dewatermark-worker --doctor` now also reports `sqlite3` / `git` / `ffmpeg` readiness.

当前推荐的本地 AI 运行时目录是仓库内的 `.runtime/ComfyUI`，不要把 Electron 客户端缓存目录误当成真正的 Comfy 推理运行时。

## Testing

```sh
uv run pytest
```

当前测试覆盖：

- `GET /healthz`
- 鉴权失败
- 提交任务与幂等返回
- worker 真正执行成功并写出文件
- `provider=auto` 降级链
- callback 重试事件落库
- `GET /v1/jobs` / `result` / `cancel`
- `comfy_diffueraser` probe 缺失运行时提示

## AI Provider Direction

当前主目标不是让用户手工给水印框，而是把 `comfy_diffueraser` 补成真正的本地 AI 主链。

- `comfy_diffueraser`：未来主方案，本地 AI 自动视频去水印
- `local_fallback`：当前兜底，保证系统持续可跑
- `cloud_inpaint`：当前占位，后续按需要接回

当前仓库已经具备 `comfy_diffueraser` 的最小探测骨架：

- 检查 `ComfyUI` 目录
- 检查 `custom_nodes`
- 检查工作流模板
- 检查 `models`
- 检查 `ComfyUI API`

但还没有接入真正执行链，所以它现在属于“doctor/probe 已落地，run 仍待接入”的状态。

## Runtime Contract

当前仓库已经内置 AI runtime contract，不再依赖旧工程临时抄路径：

- [lock.yaml](/Users/xiaomo/Desktop/去水印平台/.runtime/lock.yaml)
- [manifest.yaml](/Users/xiaomo/Desktop/去水印平台/.runtime/models/manifest.yaml)
- [sam2_diffueraser_api.json](/Users/xiaomo/Desktop/去水印平台/workflows/sam2_diffueraser_api.json)

这三份文件分别定义：

- 要 clone 的 ComfyUI / custom nodes 版本
- 必需模型清单
- 当前 AI 工作流模板占位

后续真正安装本地 AI 运行时，应以这三份文件为准，而不是继续从旧仓库人工抄配置。

当前推荐顺序：

1. `--runtime-plan`
2. `--install-runtime --repos-only`
3. 手工补模型到 `.runtime/ComfyUI/models`
4. 再处理 ComfyUI API 启动和真正执行链

`/v1/providers` 现在会把 `comfy_diffueraser` 的缺失项结构化返回，便于直接定位：

- 缺失 `ComfyUI` 主目录或 venv
- 缺失 `custom_nodes`
- 缺失关键模型
- 工作流模板是否存在
- `ComfyUI API` 是否可达
