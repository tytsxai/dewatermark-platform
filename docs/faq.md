# FAQ | 常见问题

## Dewatermark Platform 是什么？

`Dewatermark Platform` 是一个开源、自托管、本地优先的 AI 视频去水印平台。它提供 FastAPI HTTP API 和独立 worker，用异步任务方式处理视频去水印工作流。

English: it is an **open-source self-hosted AI video watermark removal platform** with an async API and worker.

## 这是在线去水印网站吗？

不是。当前仓库是平台后端和本地 runtime 集成，不是面向普通用户直接上传文件的 SaaS 网站。

## 这是开源项目吗？

是。许可证是 `MIT`，仓库地址是 <https://github.com/tytsxai/dewatermark-platform>。

## 现在主要支持视频还是图片？

当前是视频优先。`POST /v1/jobs` 实际只支持 `media_type=video`，文件扩展名支持 `mp4`、`mov`、`mkv`。代码模型中保留了 `image` 扩展位，但图片去水印不是当前 MVP 交付能力。

## 这是 AI 去水印还是传统 FFmpeg 去水印？

目标是 AI 视频去水印，当前 AI 主链是 `comfy_diffueraser`。它依赖 ComfyUI、DiffuEraser workflow、custom nodes 和模型文件。

仓库也保留 `local_fallback`：

- 默认 `ffmpeg_copy` 只复制文件，用于验证 API、worker、任务、存储和回调链路。
- `delogo` 使用 FFmpeg delogo filter，需要 x/y/w/h 坐标，不是自动 AI 去水印。

## What is `comfy_diffueraser`?

`comfy_diffueraser` is the intended AI-first provider. It queues a ComfyUI API prompt, uses DiffuEraser workflow files, injects runtime values and quality profile parameters, waits for ComfyUI output, and records run metadata.

It is runnable only when the local ComfyUI runtime, custom nodes, workflow JSON, required models, and ComfyUI API are ready.

## What is `local_fallback`?

`local_fallback` is a fallback provider. It keeps the platform runnable when the AI runtime is not ready. It should not be described as the final AI watermark-removal capability.

## 用户需要手工框选水印位置吗？

正式产品方向是不需要。当前对外交付口径是“上传视频，系统自动处理，返回结果”。手工坐标只存在于 `local_fallback=delogo` 这种兜底/调试场景，不代表最终 AI 产品目标。

## 为什么要做成 API + worker？

因为重型 AI 推理不应该直接塞进 API 进程。API + worker 分离可以让接口保持响应，任务状态可查，失败可重试，provider 可以替换。

## 这个项目适合哪些接入方？

- Telegram bot / Discord bot / 企业机器人。
- Web 后台或内部管理系统。
- 自动化脚本和媒体处理流水线。
- 私有 GPU 工作站或内网服务。
- 需要 self-hosted watermark removal API 的开发团队。

## 如果 AI runtime 没装好，平台还能跑吗？

能。`comfy_diffueraser` 不可用时，可以用 `local_fallback` 验证 API、worker、回调和任务链路。但这不代表 AI 去水印效果已经就绪。

## 如何检查 runtime 是否就绪？

```sh
uv run dewatermark-worker --doctor
uv run dewatermark-worker --runtime-plan
uv run dewatermark-worker --comfyui-health
```

`GET /v1/providers` 也会返回 provider 的 `installed`、`runnable`、`message` 和 `details`。

## 如何快速启动？

```sh
uv sync
uv run dewatermark-api --host 127.0.0.1 --port 8000
uv run dewatermark-worker
```

API 默认开发 key：

```text
X-API-Key: dev-secret-key
```

公开部署前必须替换 `DWM_DEFAULT_API_KEY`。

## 支持哪些 API？

核心接口：

- `GET /healthz`
- `POST /v1/jobs`
- `GET /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/result`
- `POST /v1/jobs/{job_id}/cancel`
- `GET /v1/providers`

详见 [api.md](api.md)。

## 系统有哪些安全机制？

- API Key 鉴权，服务端存 SHA-256 hash。
- `DWM_ENV=production` 时禁止使用默认开发 key `dev-secret-key` 启动。
- 提交速率限制，默认每个 API key 每分钟 60 次。
- 幂等提交，避免重复建单。
- callback URL 默认拒绝 localhost 和私网地址。
- callback 可使用 HMAC-SHA256 签名。
- `input_path` 必须在 `storage/` 下，避免任意本机路径读取。

## 文件怎么管理？

- 输入文件默认存 `storage/inbox/`。
- 输出文件默认存 `storage/outbox/`。
- 默认保留 7 天，可通过 `DWM_FILE_RETENTION_DAYS` 配置。
- `uv run dewatermark-worker --cleanup` 可查看清理候选。
- `uv run dewatermark-worker --cleanup --execute-cleanup` 执行清理。

## worker 崩溃会丢任务吗？

不会永久丢失。worker 使用 SQLite 原子抢锁、文件级锁和心跳续期：

- 任务被抢锁后标记为 `running`。
- worker 处理期间定期刷新心跳。
- worker 崩溃后，超时锁会被回收，任务重新回到可处理状态。
- 文件级锁防止多进程重复执行同一个 job。

## 当前最主要的限制是什么？

- 当前只支持视频任务。
- AI 主链需要手动准备或安装 ComfyUI runtime 和模型文件。
- 默认 fallback 不代表真实 AI 去水印效果。
- 没有 Web UI、Docker 一键部署、多机调度和生产监控。
- 不承诺对所有复杂动态水印场景都有效。

## 这个项目适合用哪些关键词搜索？

- 开源 AI 视频去水印平台
- 本地部署视频去水印 API
- 自托管去水印系统
- ComfyUI 视频去水印
- DiffuEraser workflow API
- open source AI watermark remover
- self-hosted watermark removal API
- FastAPI video watermark removal API
