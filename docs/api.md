# API Draft

## 1. Submit Job

`POST /v1/jobs`

用途：

- 创建去水印任务

请求字段：

- `media_type`
  - `video`
  - `image`
- `provider`
  - `auto`
  - `comfy_diffueraser`
  - `local_fallback`
- `callback_url`
- `callback_secret`
- `input_path`
- `priority`

请求头：

- `X-API-Key`
- `Idempotency-Key`

说明：

- 一期至少支持 `multipart/form-data` 上传文件
- 如果传 `input_path`，只允许本机可信路径
- 如果传文件上传，服务端负责落盘到 `storage/inbox/`
- 如果传 `callback_url`，默认只允许公网 `http/https` 地址；`localhost` 和私网 IP 默认拒绝

成功响应示例：

```json
{
  "job_id": "job_123",
  "status": "queued",
  "provider": "auto"
}
```

返回字段建议至少包括：

- `job_id`
- `status`
- `provider_requested`
- `created_at`

## 2. Get Job

`GET /v1/jobs/{job_id}`

返回字段至少包括：

- `job_id`
- `status`
- `media_type`
- `provider`
- `provider_requested`
- `output_path`
- `attempt_count`
- `error_code`
- `error_message`

## 3. List Jobs

`GET /v1/jobs`

一期只做最简单过滤：

- `status`
- `provider`
- `media_type`
- `page`，默认 `1`
- `page_size`，默认 `50`，最大 `200`

响应至少包括：

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
- `download_url`

一期允许 `download_url` 为空，本地先用 `output_path`。

## 5. Cancel Job

`POST /v1/jobs/{job_id}/cancel`

一期行为：

- `queued` 可以取消
- `running` 默认先返回不支持或标记取消中

先把接口留好，内部实现可以后补。

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

这个接口很关键，因为本地去水印系统最怕“看起来接上了，实际上 provider 不能跑”。

对于 `comfy_diffueraser`，当前建议 `details` 至少包含：

- `api_url`
- `runtime_root`
- `workflow_path`
- `missing_installation_bits`
- `missing_models`
- `api_issue`

## 8. Callback Payload

回调 body 建议固定为：

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

如果设置了 `callback_secret`，建议同时带：

- `X-Signature`
- `X-Timestamp`

## 9. 错误响应

一期统一响应结构：

```json
{
  "error_code": "VALIDATION_ERROR",
  "error_message": "media_type is required"
}
```

## 10. 当前口径补充

- 当前最终产品目标是“用户只上传视频，系统自动完成 AI 去水印”
- 任何要求用户手工提供水印位置的方案，都不算正式完成
- 当前 API 可以保留调试扩展位，但对外交付能力必须以自动处理为准
