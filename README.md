# Dewatermark Platform | 开源 AI 去水印平台

Open source, local-first AI dewatermark platform for video workflows.

这是一个面向本地部署的异步去水印系统，目标是把“AI 视频去水印”做成独立、可接入、可扩展的 API 平台，而不是某个既有工作流里的临时脚本。

- GitHub: <https://github.com/tytsxai/dewatermark-platform>
- License: [MIT](./LICENSE)
- English README: [README.en.md](./README.en.md)
- AI index: [llms.txt](./llms.txt)

## 项目是什么

`Dewatermark Platform` 是一个开源 AI 去水印平台，当前聚焦：

- AI video watermark removal
- self-hosted watermark remover
- local-first dewatermark API
- async video dewatermark jobs
- ComfyUI-based video watermark removal pipeline

它解决的问题很直接：

1. 外部系统通过 HTTP API 提交视频去水印任务。
2. 平台用异步 job 模型执行任务，而不是把重型推理塞进 API 进程。
3. 本地 AI 主链优先跑 `comfy_diffueraser`，不可用时降级到 `local_fallback` 保证系统先跑通。

## 项目不是什么

它现在不是：

- SaaS 在线去水印网站
- 已经调优完成的商业级效果产品
- 需要用户手工框选水印区域的最终方案

这个仓库的目标从一开始就很明确：

- 独立 API
- 独立 worker
- 独立 runtime contract
- 独立文档和开源协作入口

## 为什么这个项目对 SEO 和 AI 索引友好

这个仓库现在按“让搜索引擎和 AI 都能更快理解项目”的方式组织：

- README 首页直接回答“它是什么、解决什么问题、适合谁”
- 文档按产品、架构、API、FAQ 分层
- 补充 `llms.txt` / `llms-full.txt` 给模型做低成本入口
- 中英文双 README，覆盖中文和英文检索词
- 保留明确关键词：`AI 去水印`、`video watermark removal`、`open source`、`self-hosted`、`ComfyUI`

## 核心能力

- 开源 AI 视频去水印平台
- 本地优先，适合私有化部署
- FastAPI + SQLite + worker 的最小可跑架构
- 异步任务提交、查询、取消、结果获取
- API Key 鉴权
- 幂等提交
- provider 路由与失败降级
- 回调通知与重试
- 本地 AI runtime `doctor / plan / install / health` 能力

当前 provider：

- `comfy_diffueraser`: 本地 AI 主链
- `local_fallback`: 兜底 provider，保证平台持续可跑

## 典型使用场景

- Telegram 机器人接入去水印能力
- 自有 Web 后台接异步去水印 API
- 内容清洗流水线接入本地 AI 去水印
- 私有化环境部署视频去水印服务
- 需要可控存储、可控回调、可控 runtime 的内部工具链

## 仓库结构

```text
apps/api/             API 入口
apps/worker/          worker 入口
docs/                 产品、架构、API、FAQ、路线图文档
src/wm_platform/      平台核心代码
storage/inbox/        上传输入目录
storage/outbox/       输出产物目录
workflows/            ComfyUI workflow / API prompt 模板
.runtime/             本地 AI runtime contract 与安装目录
```

## 快速开始

1. 安装依赖：

```sh
uv sync
```

2. 启动 API：

```sh
uv run dewatermark-api --host 0.0.0.0 --port 8000
```

3. 启动 worker：

```sh
uv run dewatermark-worker
```

4. 检查 provider 和本地 runtime 就绪情况：

```sh
uv run dewatermark-worker --doctor
```

5. 查看本地 AI runtime 安装计划：

```sh
uv run dewatermark-worker --runtime-plan
```

6. 只安装运行时骨架，不安装模型：

```sh
uv run dewatermark-worker --install-runtime --repos-only
```

7. 查看 ComfyUI 启动命令：

```sh
uv run dewatermark-worker --comfyui-plan
```

8. 启动并探活 ComfyUI：

```sh
uv run dewatermark-worker --start-comfyui
```

API 启动时会自动创建：

- `storage/app.db`
- `storage/inbox/`
- `storage/outbox/`

## 默认凭据

- Default tenant: `local-dev`
- Default API key: `dev-secret-key`
- Header: `X-API-Key`

## API 示例

提交任务：

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: first-job" \
  -F "media_type=video" \
  -F "provider=auto" \
  -F "file=@/absolute/path/to/local.mp4"
```

查询 provider 状态：

```sh
curl http://127.0.0.1:8000/v1/providers -H "X-API-Key: dev-secret-key"
```

查询任务：

```sh
curl http://127.0.0.1:8000/v1/jobs/<job_id> -H "X-API-Key: dev-secret-key"
```

## 核心接口

- `POST /v1/jobs`: 提交去水印任务
- `GET /v1/jobs`: 列表查询
- `GET /v1/jobs/{job_id}`: 查询任务状态
- `GET /v1/jobs/{job_id}/result`: 获取结果路径或下载地址
- `POST /v1/jobs/{job_id}/cancel`: 取消任务
- `GET /v1/providers`: 查看 provider 健康与能力
- `GET /healthz`: 服务健康检查

## 运行时与环境变量

启动前可以复制 `.env.example`，或直接设置环境变量。

- `DWM_DEFAULT_TENANT_ID` / `DWM_DEFAULT_API_KEY`
- `DWM_STORAGE_ROOT`
- `DWM_RUNTIME_ROOT`
- `DWM_MAX_UPLOAD_BYTES`
- `DWM_COMFYUI_API_URL`
- `DWM_AUTO_START_COMFYUI`
- `DWM_COMFYUI_DIR`
- `DWM_COMFYUI_VENV_DIR`
- `DWM_COMFYUI_CUSTOM_NODES_DIR`
- `DWM_COMFYUI_MODELS_DIR`
- `DWM_LOCAL_FALLBACK_MODE`
- `DWM_LOCAL_FALLBACK_DELOGO_{X,Y,W,H}`
- `DWM_ALLOW_PRIVATE_CALLBACK_URLS`
- `DWM_FILE_RETENTION_DAYS`
- `DWM_SUBMIT_RATE_LIMIT_COUNT`
- `DWM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS`
- `DWM_PROVIDER_RUNTIME_DELAY_SECONDS`
- `DWM_CALLBACK_RETRY_COUNT`
- `DWM_CALLBACK_RETRY_DELAY_SECONDS`

`local_fallback` 有两个现实用途：

- `ffmpeg_copy`: 用于保活和链路验证
- `delogo`: 用于最小可用的本地 FFmpeg 去水印尝试

## 文档导航

- [docs/index.md](./docs/index.md): 文档总入口
- [docs/overview.md](./docs/overview.md): 项目概览与定位
- [docs/faq.md](./docs/faq.md): 常见问题，适合搜索和 AI 检索
- [docs/api.md](./docs/api.md): API 草案和接口语义
- [docs/architecture.md](./docs/architecture.md): 架构与模块边界
- [docs/requirements.md](./docs/requirements.md): 产品需求与能力边界
- [docs/roadmap.md](./docs/roadmap.md): 路线图
- [docs/review.md](./docs/review.md): 历史方案审查

## FAQ 摘要

### 这是开源 AI 去水印平台吗？

是。这个仓库是一个开源、本地优先、可自部署的 AI 去水印平台，当前重点是视频去水印。

### 这是网页在线去水印站点吗？

不是。当前是 API + worker + 本地 runtime 的平台仓库，不是面向普通用户的托管网站。

### 当前真正的 AI 主链是什么？

`comfy_diffueraser`。`local_fallback` 只是兜底，不代表最终效果目标。

### 支持图片去水印吗？

接口层预留了 `image`，但当前 MVP 重点是 `video`。

### 适合怎么部署？

最适合单机、本地 GPU、私有化环境，或者作为内部工作流的去水印服务节点。

## 开源协作

- Issues / PRs welcome
- 文档、runtime contract、provider 接入都可以贡献
- 当前最有价值的贡献方向：
  - 模型与 workflow 落地
  - provider 扩展
  - 文档完善
  - 真实效果评估

## 测试

```sh
uv run pytest
```

当前测试覆盖：

- 健康检查
- 鉴权失败
- 提交任务与幂等
- worker 执行成功并写出文件
- `provider=auto` 降级链
- callback 重试
- `GET /v1/jobs` / `result` / `cancel`
- `comfy_diffueraser` probe 与 ComfyUI API 执行链
