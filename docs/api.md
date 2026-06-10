# Dewatermark API | HTTP API 合同

本文档描述 `Dewatermark Platform` 当前已经实现的 HTTP API，重点覆盖异步任务提交、状态查询、结果获取、provider 探测和回调语义。

关键词：

- AI 去水印 API
- video watermark removal API
- async dewatermark jobs
- self-hosted dewatermark service

## 0. 鉴权

所有 `/v1/*` 接口都需要 `X-API-Key` 请求头。

```
X-API-Key: dev-secret-key
```

API Key 在服务端以 SHA-256 哈希存储，不会明文保存。

生产部署必须设置：

```sh
export DWM_ENV=production
export DWM_DEFAULT_API_KEY="replace-with-a-long-random-secret"
```

当 `DWM_ENV=production` 且仍使用默认开发 key `dev-secret-key` 时，服务启动会失败。

## 0.1 速率限制

`POST /v1/jobs` 接口有速率限制：

- 默认: 60 次/分钟 per API key
- 可通过 `DWM_SUBMIT_RATE_LIMIT_COUNT` 和 `DWM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS` 配置
- 超出限制返回 `429 RATE_LIMITED`

## 1. Submit Job

`POST /v1/jobs`

用途：

- 创建去水印任务

请求字段：

- `media_type`
  - `video` (当前提交接口唯一支持的类型)
  - `image` (模型层预留，提交接口当前会返回 `MEDIA_TYPE_NOT_SUPPORTED`)
- `provider`
  - `auto` (默认, 先尝试 comfy_diffueraser, 失败降级 local_fallback)
  - `comfy_diffueraser`
  - `local_fallback`
- `callback_url`
- `callback_secret`
- `input_path` (必须位于 `DWM_STORAGE_ROOT` 下, 与 file 二选一)
- `priority` (默认 0, 越高越优先)

请求头：

- `X-API-Key`
- `Idempotency-Key` (可选, 用于幂等提交)

说明：

- 当前支持 `multipart/form-data` 上传文件
- 如果传 `input_path`，只允许 `DWM_STORAGE_ROOT` 下的本机文件路径
- 如果传文件上传，服务端负责落盘到 `storage/inbox/`
- 如果传 `callback_url`，默认只允许公网 `http/https` 地址；`localhost` 和私网 IP 默认拒绝
- 幂等: 相同 `Idempotency-Key` + 相同输入和参数 → 返回已有 job，不重复创建
- 如果幂等键已使用但参数不同 → 返回 `409 IDEMPOTENCY_CONFLICT`
- 幂等写入在数据库写事务内按租户串行化，避免并发请求用同一 key 创建多条不同 job

成功响应示例：

```json
{
  "job_id": "job_123",
  "status": "queued",
  "provider_requested": "auto",
  "created_at": "2026-01-01T00:00:00"
}
```

返回字段包括：

- `job_id`
- `status`
- `provider_requested`
- `created_at`

## 2. Get Job

`GET /v1/jobs/{job_id}`

返回字段包括：

- `job_id`
- `status`
- `media_type`
- `provider_requested`
- `provider_selected` (实际执行的 provider)
- `output_path`
- `attempt_count`
- `error_code`
- `error_message`
- `created_at`
- `updated_at`

## 3. List Jobs

`GET /v1/jobs`

当前支持过滤：

- `status`
- `provider`
- `media_type`
- `page`，默认 `1`
- `page_size`，默认 `50`，最大 `200`

响应包括：

- `jobs`
- `page`
- `page_size`
- `has_more`

## 4. Get Job Result

`GET /v1/jobs/{job_id}/result`

返回：

- `job_id`
- `status`
- `output_path`
- `download_url` (当前为 null, 本地先用 output_path)

当前允许 `download_url` 为空，本地先用 `output_path`。

如果 job 成功但产物文件已被删除 → 返回 `410 ARTIFACT_MISSING`。

## 5. Cancel Job

`POST /v1/jobs/{job_id}/cancel`

当前行为：

- `queued` 可以取消并返回 `canceled`
- `running` 返回 `409 JOB_NOT_CANCELABLE`
- 其他不可取消状态返回对应错误

## 6. Health

`GET /healthz`

返回：

- API 是否存活
- DB 是否可用

## 7. Providers Health

`GET /v1/providers`

返回每个 provider 的探测结果：

- `installed`
- `runnable`
- `message`
- `details`

这个接口很关键，因为本地去水印系统最怕"看起来接上了，实际上 provider 不能跑"。

对于 `comfy_diffueraser`，`details` 包含：

- `api_url`
- `auto_start_comfyui`
- `comfyui_dir`
- `venv_python`
- `custom_nodes_dir`
- `models_dir`
- `workflow_path`
- `workflow_name`
- `quality_profile` (当前使用的 quality profile)
- `runtime_root`
- `missing_installation_bits`
- `missing_models`
- `workflow_ready`
- `workflow_issue`
- `segmentation_repo`
- `api_issue`
- `automatic_ai_pipeline`

探测结果会被缓存 (默认 10s)，缓存 key 包含 runtime_root、comfyui_api_url、local_fallback_mode、quality_mode 等。

## 8. Callback Payload

回调 body 固定为：

```json
{
  "job_id": "job_123",
  "status": "succeeded",
  "provider": "comfy_diffueraser",
  "output_path": "/abs/path/to/output.mp4",
  "error_code": null,
  "error_message": null
}
```

如果设置了 `callback_secret`，回调头里带：

- `X-Signature` (HMAC-SHA256 签名)
- `X-Timestamp`

签名算法: `HMAC-SHA256("{timestamp}.{body}", secret)`

## 9. 错误响应

错误响应结构：

```json
{
  "error_code": "VALIDATION_ERROR",
  "error_message": "media_type is required"
}
```

错误码列表：

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| `VALIDATION_ERROR` | 400 | 请求参数校验失败 |
| `AUTH_ERROR` | 401 | API Key 缺失或无效 |
| `JOB_NOT_FOUND` | 404 | Job 不存在或无权访问 |
| `JOB_NOT_CANCELABLE` | 409 | Job 状态不允许取消 |
| `IDEMPOTENCY_CONFLICT` | 409 | 幂等键已使用但参数不同 |
| `RATE_LIMITED` | 429 | 提交频率超限 |
| `ARTIFACT_MISSING` | 410 | Job 成功但产物文件已删除 |
| `PROVIDER_NOT_AVAILABLE` | 503 | Provider 不可用 |
| `PROVIDER_RUN_FAILED` | 500 | Provider 执行失败 |
| `INTERNAL_ERROR` | 500 | 内部服务器错误 |

## 10. 当前口径补充

- 当前最终产品目标是"用户只上传视频，系统自动完成 AI 去水印"
- 任何要求用户手工提供水印位置的方案，都不算正式完成
- 当前 API 可以保留调试扩展位，但对外交付能力必须以自动处理为准

## 11. Quality Profiles (高级)

`comfy_diffueraser` 支持通过 `DWM_QUALITY_MODE` 环境变量切换 quality profile:

| 值 | 用途 |
|----|------|
| `fast` | 最快处理, 质量较低 |
| `balanced` | 默认, 平衡速度和质量 |
| `quality` | 高质量, 较慢 |
| `corner_hq` | 角落水印专用高质量模式 |

每个 profile 使用不同的 workflow 文件和参数组合 (steps, subvideo_length, neighbor_length, mask_dilation_iter, ref_stride)。
