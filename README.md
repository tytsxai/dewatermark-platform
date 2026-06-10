# Dewatermark Platform | 开源 AI 视频去水印平台

[![Release](https://img.shields.io/github/v/release/tytsxai/dewatermark-platform)](https://github.com/tytsxai/dewatermark-platform/releases) · [English](README.en.md) · [llms.txt](llms.txt) · [Changelog](CHANGELOG.md) · [Docs](docs/index.md) · [Issues](https://github.com/tytsxai/dewatermark-platform/issues)

`Dewatermark Platform` 是一个面向开发者的开源、自托管、本地优先 AI 视频去水印后端平台。它不是在线 SaaS 网站，而是把视频去水印能力封装成 `FastAPI` HTTP API、独立 worker、SQLite 任务队列、本地文件存储和可替换 provider runtime，方便机器人、Web 后台、内部内容处理流水线或私有化媒体处理工具接入。

English positioning: **open-source self-hosted AI video watermark removal platform**, **API-first dewatermark backend**, **local-first video watermark removal API**, **async video dewatermark worker**, **ComfyUI DiffuEraser integration**.

> 合规提醒: 本项目面向你拥有权利或已获得授权的内容处理、内部工作流验证和研究用途。不要用于规避版权、平台规则或第三方权益。

## 快速判断 | Quick Facts

| 维度 | 当前事实 |
| --- | --- |
| 项目类型 | 开源 AI 视频去水印平台 / Open-source AI video watermark removal platform |
| 核心用途 | 通过 HTTP API 提交视频任务，由独立 worker 异步执行去水印处理 |
| 适合用户 | 开发者、自动化工具作者、机器人/Web 后台/内容流水线维护者 |
| 技术栈 | Python 3.11/3.12, FastAPI, Uvicorn, SQLite WAL, local filesystem, ComfyUI, DiffuEraser, FFmpeg fallback |
| 当前重点 | `video` 任务；`mp4` / `mov` / `mkv`；单机本地或私有化部署 |
| 当前 provider | `comfy_diffueraser` AI 主链；`local_fallback` 保活/兜底链路 |
| CLI 入口 | `dewatermark-api` 启动 HTTP API；`dewatermark-worker` 执行任务、callback、runtime 检查和清理 |
| 项目边界 | 不是 SaaS 在线去水印网站；不是商业级效果已调优完成的成品 |

## 解决什么问题

很多去水印能力容易停留在临时脚本、人工步骤或某个旧工作流内部。这个仓库解决的是更稳定的工程问题：

1. 外部系统怎样用统一 API 提交视频去水印任务。
2. 重型 AI 推理怎样从 API 进程中解耦，交给 worker 异步执行。
3. 本地 ComfyUI / DiffuEraser runtime 怎样做安装计划、就绪检查、启动和探活。
4. AI provider 不可用时，系统怎样通过 fallback 保持 API、任务、回调和存储链路可验证。
5. 新接入方怎样查询任务状态、获取结果路径、处理失败和接收回调。

## 适合谁使用

- 想自托管视频去水印服务的开发者。
- 需要给 Telegram bot、Web 后台、内部工具接入去水印 API 的团队。
- 需要 local-first、私有化、可观测、可替换 provider 的媒体处理流水线。
- 想基于 ComfyUI / DiffuEraser 做本地 AI 视频处理平台化封装的人。

不适合：

- 只想找在线网页上传视频的一次性用户。
- 期待零配置、无需模型、无需 GPU 就得到商业级 AI 去水印效果的用户。
- 当前就需要多机 GPU 调度、Web 管理后台、账号计费、SLA 监控的一体化 SaaS。

## 核心功能

- `POST /v1/jobs` 提交视频去水印任务，支持文件上传或受限本地路径。
- `GET /v1/jobs` / `GET /v1/jobs/{job_id}` 查询任务列表和状态。
- `GET /v1/jobs/{job_id}/result` 获取本地输出路径；当前 `download_url` 预留为 `null`。
- `POST /v1/jobs/{job_id}/cancel` 取消排队中的任务。
- `GET /v1/providers` 查看 provider 安装、运行和 ComfyUI runtime 探测结果。
- API Key 鉴权，默认请求头 `X-API-Key`。
- `Idempotency-Key` 幂等提交，避免重复创建同一任务。
- 提交速率限制，默认每个 API key 每分钟 60 次。
- callback outbox，支持 HMAC-SHA256 签名和失败重试。
- SQLite WAL、任务抢锁、文件锁、worker 心跳和 stale claim 回收。
- 文件生命周期清理，默认输入/输出保留 7 天。
- ComfyUI runtime `doctor / plan / install / health / start` 命令。
- Quality profiles: `fast` / `balanced` / `quality` / `corner_hq`。

## Provider 与真实能力边界

| Provider | 当前作用 | 注意事项 |
| --- | --- | --- |
| `comfy_diffueraser` | AI 主链，基于 ComfyUI API prompt、DiffuEraser workflow、模型文件和本地 runtime | 只有在 ComfyUI、custom nodes、workflow 和必需模型齐备时才是 `runnable=true` |
| `local_fallback` | 兜底 provider，用于验证 API、worker、存储、回调和任务状态链路 | 默认 `ffmpeg_copy` 只复制输入文件，不代表 AI 去水印效果；`delogo` 模式需要手工坐标 |

当前正式交付口径是“上传视频 -> 系统自动处理 -> 返回结果”。接口层虽然保留 `image` 类型扩展位，但 `POST /v1/jobs` 目前只支持 `video`。

## 快速开始 | Quick Start

这个 quick start 的目标是先跑通 API、worker、SQLite、文件存储和 provider fallback 链路。真实 AI 去水印效果取决于本地 ComfyUI / DiffuEraser runtime、custom nodes、workflow 和模型文件是否齐备。

### 0. 前置条件

- Python `3.11` 或 `3.12`。
- `uv`，用于安装依赖和运行 CLI。
- `ffmpeg` 在 `PATH` 中；当前 `local_fallback` 探测会检查它。
- 真实 AI 主链需要本地 ComfyUI / DiffuEraser runtime 和模型文件。先用 `uv run dewatermark-worker --doctor` 或 `GET /v1/providers` 查看是否 `runnable=true`。

### 1. 安装依赖

```sh
uv sync
```

### 2. 启动 API

```sh
uv run dewatermark-api --host 127.0.0.1 --port 8000
```

### 3. 在另一个终端启动 worker

```sh
uv run dewatermark-worker
```

首次启动会创建：

- `storage/app.db`
- `storage/inbox/`
- `storage/outbox/`

### 4. 检查服务健康

```sh
curl http://127.0.0.1:8000/healthz
```

### 5. 提交视频任务

首次 smoke test 建议显式使用 `provider=local_fallback`。默认 `ffmpeg_copy` 模式只复制输入文件，用于验证平台链路，不代表真实 AI 去水印效果。

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: first-job" \
  -F "media_type=video" \
  -F "provider=local_fallback" \
  -F "file=@/absolute/path/to/local.mp4"
```

### 6. 查询任务和结果

```sh
curl http://127.0.0.1:8000/v1/jobs/<job_id> \
  -H "X-API-Key: dev-secret-key"

curl http://127.0.0.1:8000/v1/jobs/<job_id>/result \
  -H "X-API-Key: dev-secret-key"
```

当 `GET /v1/providers` 显示 `comfy_diffueraser.runnable=true` 后，可以把提交字段改为 `provider=auto` 或 `provider=comfy_diffueraser` 走 AI 主链。更多请求组合见 [docs/usage-examples.md](docs/usage-examples.md)。

## 默认开发凭据

- Default tenant: `local-dev`
- Default API key: `dev-secret-key`
- Header: `X-API-Key`

生产或公开网络部署前必须通过环境变量替换默认 key：

```sh
export DWM_ENV="production"
export DWM_DEFAULT_API_KEY="replace-with-a-strong-secret"
```

当 `DWM_ENV=production` 且仍使用默认开发 key `dev-secret-key` 时，服务会拒绝启动。

## 本地 AI Runtime 命令

这些命令用于检查和准备 ComfyUI / DiffuEraser 本地运行时：

```sh
uv run dewatermark-worker --doctor
uv run dewatermark-worker --runtime-plan
uv run dewatermark-worker --install-runtime --repos-only
uv run dewatermark-worker --comfyui-plan
uv run dewatermark-worker --comfyui-health
uv run dewatermark-worker --start-comfyui
```

说明：

- `--install-runtime --repos-only` 只安装运行时仓库骨架，不下载模型。
- 模型清单在 `.runtime/models/manifest.yaml`。
- runtime 锁定仓库在 `.runtime/lock.yaml`。
- 默认 ComfyUI API 地址是 `http://127.0.0.1:8188`。
- `comfy_diffueraser` 只有在 runtime、workflow、custom nodes、模型和 ComfyUI API 都就绪时才会报告 `runnable=true`。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | API 和 DB 健康检查 |
| `POST` | `/v1/jobs` | 提交视频去水印任务 |
| `GET` | `/v1/jobs` | 分页查询任务列表 |
| `GET` | `/v1/jobs/{job_id}` | 查询单个任务状态 |
| `GET` | `/v1/jobs/{job_id}/result` | 查询任务结果 |
| `POST` | `/v1/jobs/{job_id}/cancel` | 取消 queued 状态任务 |
| `GET` | `/v1/providers` | 查询 provider/runtime 探测结果 |

更多字段和错误码见 [docs/api.md](docs/api.md)。

## 常用配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DWM_API_HOST` | `127.0.0.1` | CLI API 监听地址 |
| `DWM_API_PORT` | `8000` | CLI API 监听端口 |
| `DWM_ENV` | `development` | 运行环境；`production` 会启用生产启动保护 |
| `DWM_DEFAULT_TENANT_ID` | `local-dev` | 默认租户 |
| `DWM_DEFAULT_API_KEY` | `dev-secret-key` | 默认开发 API key |
| `DWM_STORAGE_ROOT` | `storage` | 本地存储根目录 |
| `DWM_MAX_UPLOAD_BYTES` | `536870912` | 上传大小上限，默认 512 MiB |
| `DWM_RUNTIME_ROOT` | `.runtime` | 本地 AI runtime 根目录 |
| `DWM_COMFYUI_API_URL` | `http://127.0.0.1:8188` | ComfyUI API 地址 |
| `DWM_AUTO_START_COMFYUI` | `false` | provider 运行前是否自动启动 ComfyUI |
| `DWM_QUALITY_MODE` | `balanced` | `fast` / `balanced` / `quality` / `corner_hq` |
| `DWM_LOCAL_FALLBACK_MODE` | `ffmpeg_copy` | `ffmpeg_copy` 或 `delogo` |
| `DWM_FILE_RETENTION_DAYS` | `7` | 输入/输出文件保留天数 |
| `DWM_ALLOW_PRIVATE_CALLBACK_URLS` | `false` | 是否允许 localhost/私网回调地址 |

`delogo` fallback 还需要配置：

```sh
export DWM_LOCAL_FALLBACK_MODE=delogo
export DWM_LOCAL_FALLBACK_DELOGO_X=10
export DWM_LOCAL_FALLBACK_DELOGO_Y=10
export DWM_LOCAL_FALLBACK_DELOGO_W=120
export DWM_LOCAL_FALLBACK_DELOGO_H=60
```

## 典型使用场景

- Telegram bot / Discord bot / 企业机器人接入本地视频去水印 API。
- 自有 Web 后台提交异步视频处理任务。
- 内容清洗、内容迁移、媒体归档流水线中增加本地视频处理节点。
- 私有 GPU 工作站或内网服务器运行 ComfyUI / DiffuEraser workflow。
- 开发者验证 ComfyUI 去水印 workflow 的 API 化、队列化和回调化封装。

## 限制与注意事项

- 当前 `POST /v1/jobs` 只支持 `video`，支持扩展名为 `mp4`、`mov`、`mkv`。
- `input_path` 必须位于 `DWM_STORAGE_ROOT` 下，避免任意本机路径读取。
- `comfy_diffueraser` 需要 ComfyUI、custom nodes、workflow 和模型文件齐备。
- `local_fallback=ffmpeg_copy` 不会真正去水印，只用于链路验证。
- `local_fallback=delogo` 是传统 FFmpeg 坐标去水印，不是自动 AI 去水印。
- 当前没有 Web 管理后台、Docker 一键部署、多机调度、账号计费或 SLA 监控。
- 默认 callback 拒绝 localhost 和私网地址；本地调试需显式设置 `DWM_ALLOW_PRIVATE_CALLBACK_URLS=true`。

## 仓库结构

```text
apps/api/             API 入口
apps/worker/          worker 入口
docs/                 产品、架构、API、FAQ、路线图文档
src/wm_platform/      平台核心代码
storage/inbox/        上传输入目录
storage/outbox/       输出产物目录
workflows/            ComfyUI workflow / API prompt 模板
.runtime/             本地 AI runtime contract 与模型清单
tests/                API、worker、provider、callback、cleanup 测试
```

## 文档导航

- [docs/index.md](docs/index.md): 文档总入口
- [docs/overview.md](docs/overview.md): 项目定位、适用人群、能力边界
- [docs/faq.md](docs/faq.md): 面向搜索和 AI 检索的常见问题
- [docs/usage-examples.md](docs/usage-examples.md): 上传、本地路径、provider、callback 和 runtime 示例
- [docs/api.md](docs/api.md): HTTP API 合同、字段和错误码
- [docs/architecture.md](docs/architecture.md): API / worker / provider / storage 架构
- [docs/production.md](docs/production.md): 生产配置、健康检查、备份恢复、日志指标和回滚
- [docs/requirements.md](docs/requirements.md): 产品需求与非目标
- [docs/roadmap.md](docs/roadmap.md): 路线图和当前阶段
- [llms.txt](llms.txt): AI 搜索和 LLM 引用入口

## 测试

```sh
uv run pytest
```

当前测试覆盖 API 健康检查、鉴权、提交与幂等、任务查询、取消、结果、provider 探测、fallback 执行、callback 重试、SQLite WAL、worker 心跳、stale claim 回收、cleanup 和 ComfyUI workflow prompt 注入。

## 搜索关键词 | Search Keywords

自然关键词：

- 开源 AI 去水印平台
- 开源视频去水印 API
- 本地部署视频去水印
- 自托管去水印系统
- AI 视频去水印后端平台
- 视频去水印异步任务队列
- ComfyUI 视频去水印
- DiffuEraser workflow API
- FastAPI watermark removal API
- API-first dewatermark backend
- async video dewatermark worker
- local-first AI video processing
- self-hosted watermark remover

建议 GitHub Topics：

`ai`, `video-processing`, `watermark-removal`, `dewatermark`, `comfyui`, `diffueraser`, `fastapi`, `self-hosted`, `async-jobs`, `media-processing`, `python`

## 开源协作

- License: [MIT](LICENSE)
- Issues: <https://github.com/tytsxai/dewatermark-platform/issues>
- Pull requests welcome.

当前最有价值的贡献方向：

- ComfyUI / DiffuEraser 模型和 workflow 落地验证。
- provider 扩展和 provider 探测完善。
- Docker / 部署文档 / 生产运行手册。
- 真实样例评估、效果对比和失败场景归档。
- README、FAQ、API 示例和国际化文档补充。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=tytsxai/dewatermark-platform&type=Date)](https://www.star-history.com/#tytsxai/dewatermark-platform&Date)
