# Usage Examples | 使用示例

本文档给出 `Dewatermark Platform` 当前真实可用的 HTTP API 和 CLI 示例，便于开发者接入，也便于搜索引擎和 AI 搜索理解项目的实际使用方式。

English summary: **FastAPI video watermark removal API examples**, **self-hosted dewatermark worker usage**, **ComfyUI DiffuEraser provider checks**, and **local fallback smoke tests**.

## 1. 启动 API 和 Worker

```sh
uv sync
uv run dewatermark-api --host 127.0.0.1 --port 8000
```

另一个终端启动 worker：

```sh
uv run dewatermark-worker
```

健康检查：

```sh
curl http://127.0.0.1:8000/healthz
```

## 2. 上传文件并验证链路

首次接入建议显式使用 `provider=local_fallback`。默认 `DWM_LOCAL_FALLBACK_MODE=ffmpeg_copy` 只复制输入文件，用来验证 API、worker、SQLite、存储、任务状态和结果查询链路，不代表真实 AI 去水印效果。

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: smoke-test-001" \
  -F "media_type=video" \
  -F "provider=local_fallback" \
  -F "file=@/absolute/path/to/local.mp4"
```

返回的 `job_id` 用于后续查询。

## 3. 查询任务状态和结果

```sh
curl http://127.0.0.1:8000/v1/jobs/<job_id> \
  -H "X-API-Key: dev-secret-key"

curl http://127.0.0.1:8000/v1/jobs/<job_id>/result \
  -H "X-API-Key: dev-secret-key"
```

当前结果接口返回本地 `output_path`，`download_url` 预留为 `null`。

## 4. 使用本地 input_path

`input_path` 必须位于 `DWM_STORAGE_ROOT` 下，默认是仓库内的 `storage/`，避免任意本机路径读取。`file` 和 `input_path` 二选一。

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: local-path-001" \
  -F "media_type=video" \
  -F "provider=local_fallback" \
  -F "input_path=/absolute/path/to/dewatermark-platform/storage/inbox/sample.mp4"
```

## 5. 查看 Provider 和 AI Runtime 状态

```sh
curl http://127.0.0.1:8000/v1/providers \
  -H "X-API-Key: dev-secret-key"

uv run dewatermark-worker --doctor
uv run dewatermark-worker --runtime-plan
uv run dewatermark-worker --comfyui-health
```

当 `comfy_diffueraser` 的 `runnable=true` 时，可以用 AI 主链：

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: ai-path-001" \
  -F "media_type=video" \
  -F "provider=comfy_diffueraser" \
  -F "file=@/absolute/path/to/local.mp4"
```

`provider=auto` 会按当前实现先尝试 `comfy_diffueraser`，不可用时降级到 `local_fallback`。

## 6. Callback 示例

默认 callback URL 拒绝 localhost、私网、链路本地、保留地址和组播地址。生产环境应使用可访问的公网或内网网关地址。

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: callback-001" \
  -F "media_type=video" \
  -F "provider=local_fallback" \
  -F "callback_url=https://example.com/dewatermark/callback" \
  -F "callback_secret=replace-with-callback-secret" \
  -F "file=@/absolute/path/to/local.mp4"
```

本地调试私网 callback 时，需要显式放开：

```sh
export DWM_ALLOW_PRIVATE_CALLBACK_URLS=true
```

不要在公开生产环境中打开这个开关。

## 7. delogo Fallback 示例

`delogo` 是传统 FFmpeg 坐标去水印，不是自动 AI 去水印。它需要明确的水印区域坐标：

```sh
export DWM_LOCAL_FALLBACK_MODE=delogo
export DWM_LOCAL_FALLBACK_DELOGO_X=10
export DWM_LOCAL_FALLBACK_DELOGO_Y=10
export DWM_LOCAL_FALLBACK_DELOGO_W=120
export DWM_LOCAL_FALLBACK_DELOGO_H=60
```

然后按普通任务方式提交 `provider=local_fallback`。

## 8. 生产前最小检查

在启动 API 和 worker 的环境里先设置生产变量：

```sh
export DWM_ENV=production
export DWM_DEFAULT_API_KEY="replace-with-a-long-random-secret"
```

然后执行最小检查：

```sh
uv run pytest
uv run dewatermark-worker --doctor
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS -H "X-API-Key: $DWM_DEFAULT_API_KEY" http://127.0.0.1:8000/v1/providers
```

生产或公开网络部署前必须替换默认开发 key。更多配置、备份和回滚要求见 [production.md](production.md)。
