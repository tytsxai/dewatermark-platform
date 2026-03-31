# 去水印平台

一个独立的、本地优先的异步视频去水印平台。

[GitHub Repository](https://github.com/tytsxai/dewatermark-platform)

当前仓库已按开源项目方式整理，采用 [MIT License](./LICENSE)。

当前结论很明确：

- 原始方案适合“把视频去水印能力接入现有 OpenFang/shipinbot 工作流”
- 不适合直接当成“独立的通用去水印 API 平台”方案

所以这个仓库从一开始就按独立项目定义：

- 独立目录
- 独立仓库
- 独立 API
- 独立 worker
- 不和现有业务运行时路径混用

## 项目目标

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

## 开源说明

- License: `MIT`
- Issues / PR: welcome
- 当前阶段更适合单机、本地 AI 运行时、MVP 骨架和执行链演进
- 不承诺即开即用的商业级效果，重点是可跑、可查、可扩展

## 快速开始

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

API 启动时会自动创建 `storage/app.db`、`storage/inbox/`、`storage/outbox/`，并写入默认 API key。

## 默认凭据

- Default tenant: `local-dev`
- Default API key: `dev-secret-key`
- Header name: `X-API-Key`

## 存储布局

- `storage/inbox/`: uploaded inputs
- `storage/outbox/`: worker outputs
- `storage/app.db`: SQLite job store

## 调用示例

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

## 平台接口

- `GET /v1/jobs`: list jobs filtered by tenant and optional `status`, `provider`, `media_type`, `page`, `page_size`
- `GET /v1/jobs/{job_id}`: get status (existing)
- `GET /v1/jobs/{job_id}/result`: get `output_path`/`download_url` once job finishes
- `POST /v1/jobs/{job_id}/cancel`: cancel queued jobs only
- `GET /v1/providers`: check provider health and capabilities

## 环境变量

启动前可以复制 `.env.example`，或者直接设置以下环境变量。

- `DWM_DEFAULT_TENANT_ID` / `DWM_DEFAULT_API_KEY`: API key pair seeded on startup
- `DWM_STORAGE_ROOT`: storage directory that contains `inbox`, `outbox`, `app.db`
- `DWM_RUNTIME_ROOT`: AI runtime root directory, default `.runtime`
- `DWM_MAX_UPLOAD_BYTES`: upload size guard (default 512 MiB)
- `DWM_COMFYUI_API_URL`: local ComfyUI API address
- `DWM_AUTO_START_COMFYUI`: future Comfy auto-start switch, default off
- `DWM_COMFYUI_DIR` / `DWM_COMFYUI_VENV_DIR` / `DWM_COMFYUI_CUSTOM_NODES_DIR` / `DWM_COMFYUI_MODELS_DIR`: local AI runtime paths
- `DWM_LOCAL_FALLBACK_MODE`: `ffmpeg_copy` or `delogo`, controls how the local provider transforms video
- `DWM_LOCAL_FALLBACK_DELOGO_{X,Y,W,H}`: required together to enable delogo filter
- `DWM_ALLOW_PRIVATE_CALLBACK_URLS`: allow `localhost` / private IP callback targets when you explicitly need intranet callbacks
- `DWM_FILE_RETENTION_DAYS`: how long input/output files are considered recent
- `DWM_SUBMIT_RATE_LIMIT_COUNT` / `DWM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS`: per-API-key submit rate limit, default `60` requests per `60s`
- `DWM_PROVIDER_RUNTIME_DELAY_SECONDS`: simulated runtime delay for fake providers
- `DWM_CALLBACK_RETRY_COUNT` / `DWM_CALLBACK_RETRY_DELAY_SECONDS`: callback retry policy

`ffmpeg_copy` mode directly copies the input file into `storage/outbox/`. `delogo` requires FFmpeg on `PATH` (`brew install ffmpeg` or similar) plus the delogo coordinates.
`uv run dewatermark-worker --doctor` now also reports `sqlite3` / `git` / `ffmpeg` readiness.

当前推荐的本地 AI 运行时目录是仓库内的 `.runtime/ComfyUI`，不要把 Electron 客户端缓存目录误当成真正的 Comfy 推理运行时。

## 测试

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
- `comfy_diffueraser` API prompt 执行链

## AI 主链说明

当前主目标不是让用户手工给水印框，而是把 `comfy_diffueraser` 补成真正的本地 AI 主链。

- `comfy_diffueraser`：未来主方案，本地 AI 自动视频去水印
- `local_fallback`：当前兜底，保证系统持续可跑
- `local_fallback` 的 `ffmpeg_copy` 模式只负责保活，不会再把 ffmpeg 执行失败伪装成成功

当前仓库已经具备 `comfy_diffueraser` 的最小探测骨架：

- 检查 `ComfyUI` 目录
- 检查 `custom_nodes`
- 检查工作流模板
- 检查 `models`
- 检查 `ComfyUI API`

当前已经接入最小可执行链：

- 读取 `workflows/sam2_diffueraser_api.json` API prompt 模板
- 向 ComfyUI `/prompt` 提交任务
- 轮询 `/history/{prompt_id}`
- 从 `/view` 拉回导出视频并落到 `storage/outbox/`

当前默认工作流会直接基于输入视频生成 mask，不要求用户额外上传 mask。

## Runtime Contract

当前仓库已经内置 AI runtime contract，不再依赖旧工程临时抄路径：

- [lock.yaml](/Users/xiaomo/Desktop/去水印平台/.runtime/lock.yaml)
- [manifest.yaml](/Users/xiaomo/Desktop/去水印平台/.runtime/models/manifest.yaml)
- [sam2_diffueraser_api.json](/Users/xiaomo/Desktop/去水印平台/workflows/sam2_diffueraser_api.json)

这三份文件分别定义：

- 要 clone 的 ComfyUI / custom nodes 版本
- 必需模型清单
- 当前 AI 工作流 API 模板

后续真正安装本地 AI 运行时，应以这三份文件为准，而不是继续从旧仓库人工抄配置。

当前推荐顺序：

1. `--runtime-plan`
2. `--install-runtime --repos-only`
3. 手工补模型到 `.runtime/ComfyUI/models`
4. 启动 ComfyUI
5. 直接提交视频任务验证 `comfy_diffueraser`

`/v1/providers` 现在会把 `comfy_diffueraser` 的缺失项结构化返回，便于直接定位：

- 缺失 `ComfyUI` 主目录或 venv
- 缺失 `custom_nodes`
- 缺失关键模型
- 工作流模板是否存在
- `ComfyUI API` 是否可达

补充：

- `DWM_COMFYUI_SEGMENTATION_REPO` 默认是 `briaai/RMBG-2.0`
- 如果本地已有可用的 RMBG/BiRefNet 仓库路径，也可以把这个变量改成本地模型目录

## 已知限制

- 当前主能力聚焦视频，图片能力仍保留为后续扩展位
- 效果和吞吐主要受 ComfyUI、显存、模型文件、输入视频分辨率影响
- SQLite 适合单机 MVP，不适合高并发生产集群

## 贡献

提交代码前建议先看 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 许可证

本项目使用 [MIT License](./LICENSE)。
