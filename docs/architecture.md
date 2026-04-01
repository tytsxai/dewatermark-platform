# Architecture

本文档描述开源 AI 去水印平台的架构，目标是保持 `API + worker + provider runtime` 边界清晰，优先保证系统能跑和能扩展。

## 1. 当前架构

```text
client
  -> FastAPI (API 进程)
  -> SQLite (jobs, api_keys, callback_events, callback_outbox, run_metadata)
  -> worker polling loop (独立进程)
  -> provider adapter (comfy_diffueraser / local_fallback)
  -> storage/inbox + storage/outbox
  -> .runtime/ComfyUI + custom_nodes + models
  -> callback outbox worker (独立线程)
```

更具体的数据流：

```text
client --[POST /v1/jobs + file]--> API
  API: 鉴权 → 速率限制 → 幂等检查 → 文件落盘 → 创建 job → 返回 job_id

worker: 轮询 SQLite → 抢锁 (claimed_at + lock_owner + 文件锁) → 心跳续期
  → provider 降级链执行 → 标记 succeeded/failed → enqueue callback

callback worker: 独立线程轮询 callback_outbox → POST 回调 → 签名验证 → 重试
```

## 2. 为什么先这样

你现在最需要的是：

- 先把独立系统边界立住
- 先把 API 打通
- 先把 provider 抽象打通

不是一上来就搞复杂分布式。

所以一期默认这样：

- API 单独进程
- worker 单独进程
- 本地文件存储
- 本地数据库
- 本地队列
- callback outbox worker 独立线程

## 3. 建议技术栈

为了简单，先按这个落：

- API: FastAPI
- DB: SQLite (WAL 模式, busy_timeout 30s, 指数退避重试)
- Queue: SQLite polling (带抢锁 + 心跳 + 文件锁)
- Worker: Python process (多线程: 主 worker + callback worker)
- Storage: 本地文件系统
- Rate Limiting: 内存滑动窗口 (per API key)

如果后面需要增强，再替换成：

- DB: PostgreSQL
- Queue: Redis / Celery / RQ

但一期不要先把自己设计死。

## 4. 模块划分

### API Service

职责：

- 接收上传 (multipart/form-data)
- 创建 job
- 鉴权 (X-API-Key → tenant_id)
- 速率限制 (滑动窗口, per key)
- 幂等检查 (Idempotency-Key)
- 查询状态
- 返回结果信息
- provider 健康探测

### Worker

职责：

- 拉取待处理 job (SQLite polling)
- 文件级锁防重复执行 (fcntl)
- 心跳续期 (每 30s 或 claim_timeout 的 1/3)
- 调用 provider adapter
- 写回结果状态
- 发送回调 (enqueue to callback_outbox)
- 处理重试和降级
- 承载本地 AI runtime 的探测、启动和执行

### Callback Worker (独立线程)

职责：

- 独立轮询 `callback_outbox` 表
- POST 回调到调用方
- HMAC-SHA256 签名验证 (X-Signature, X-Timestamp)
- 自动重试 (可配置次数和间隔)
- 回调失败不影响 job 最终状态

### Provider Adapter

职责：

- 统一封装不同去水印后端
- 输出统一结果格式
- 处理 provider 级错误

当前 provider 分层已经明确：

- `comfy_diffueraser`
  - 本地 AI 主链
  - 依赖 ComfyUI runtime、custom nodes、models、workflow、API
  - 支持 quality profiles (fast / balanced / quality / corner_hq)
  - 支持 workflow 动态参数注入 (steps, subvideo_length, neighbor_length, mask_dilation_iter, ref_stride)
  - 支持动态模型路径解析 (VAE, LoRA, CLIP, ProPainter, Flow, Raft)
  - ComfyUI 自动启动 + 文件锁防竞争
  - 运行元数据记录 (run_metadata 表)
- `local_fallback`
  - 兜底路径
  - 负责系统保活，不代表最终效果目标
  - 支持 `ffmpeg_copy` 和 `delogo` 两种模式

统一接口建议：

```python
class ProviderAdapter:
    name: str

    def probe(self) -> dict: ...

    def run(self, job: dict) -> dict: ...
```

### Storage

职责：

- 存输入文件 (`storage/inbox/`)
- 存输出文件 (`storage/outbox/`)
- 提供产物路径
- 文件生命周期管理 (可配置保留天数 + cleanup)

## 5. 数据层最小设计

一期别搞太复杂，先有这五张表就够：

### jobs

- `job_id`
- `tenant_id`
- `media_type`
- `status`
- `provider_requested`
- `provider_selected`
- `fallback_chain_json`
- `idempotency_key`
- `input_path`
- `input_signature`
- `output_path`
- `callback_url`
- `callback_secret`
- `priority`
- `attempt_count`
- `duration_ms`
- `error_code`
- `error_message`
- `created_at`
- `updated_at`
- `claimed_at`
- `lock_owner`

### api_keys

- `tenant_id`
- `api_key_hash`
- `status`
- `created_at`

### callback_events

- `id`
- `job_id`
- `attempt_no`
- `status`
- `response_code`
- `response_body`
- `created_at`

### callback_outbox

- `id`
- `job_id`
- `tenant_id`
- `callback_url`
- `callback_secret`
- `payload_json`
- `status`
- `attempt_count`
- `max_attempts`
- `next_attempt_at`
- `last_error`
- `last_response_code`
- `last_response_body`
- `claimed_at`
- `lock_owner`
- `created_at`
- `updated_at`

### run_metadata

- `id`
- `job_id`
- `workflow_name`
- `quality_profile`
- `steps`
- `subvideo_length`
- `neighbor_length`
- `mask_dilation_iter`
- `device`
- `seed`
- `scene_type`
- `confidence_level`
- `created_at`

## 6. 队列与抢锁规则

一期用 SQLite 轮询就行，但规则必须明确：

1. worker 只拉 `queued` 状态任务 (按 priority DESC, created_at ASC)
2. 抢到任务时写入 `claimed_at` 和 `lock_owner` (原子操作)
3. worker 启动时回收超时锁 (stale claim → queued)
4. 同一 job 任意时刻只允许一个 worker 执行
5. **文件级锁**: 每个 job 有独立的 `.lock` 文件 (fcntl)，防止多进程重复执行
6. **心跳续期**: worker 处理 job 期间定期刷新 `claimed_at`，防止被误回收

这四条不先定死，后面重复执行会很恶心。

## 7. Provider 选择原则

一期不要把 provider 逻辑写死在业务代码里。

至少拆成：

- provider registry
- routing policy
- fallback policy

否则后面加第四个后端时又要拆。

建议 provider 注册信息至少包含：

- `name`
- `media_types`
- `installed`
- `runnable`
- `priority`
- `details`

### Quality Profiles

`comfy_diffueraser` 支持四种 quality profile，通过 `DWM_QUALITY_MODE` 环境变量控制：

| Profile | Steps | Subvideo | Neighbor | Mask Dilation | Ref Stride |
|---------|-------|----------|----------|---------------|------------|
| fast | 2 | 50 | 10 | 1 | 10 |
| balanced | 5 | 70 | 14 | 2 | 10 |
| quality | 7 | 100 | 20 | 3 | 10 |
| corner_hq | 7 | 100 | 20 | 3 | 10 |

每个 profile 对应不同的 workflow 文件：
- `fast` → `sam2_diffueraser_api.json`
- `balanced` → `sam2_diffueraser_balanced.json`
- `quality` → `sam2_diffueraser_quality.json`
- `corner_hq` → `corner_watermark_hq.json`

### Provider Probe 缓存

`/v1/providers` 接口的探测结果会被缓存，缓存 key 包含 runtime_root、comfyui_api_url、local_fallback_mode、quality_mode 等。缓存时间由 `DWM_PROVIDER_PROBE_CACHE_SECONDS` 控制 (默认 10s)。

## 8. 配置规则

一期统一放到一个配置文件或环境变量里：

- API 监听地址
- SQLite 路径
- storage 路径
- provider 启用开关
- 文件大小限制
- 视频时长限制
- 回调重试次数
- `.runtime` 根目录
- ComfyUI API URL
- ComfyUI 路径 / venv / custom_nodes / models
- workflow 模板路径
- quality mode (fast / balanced / quality / corner_hq)

## 9. 关键工程约束

1. API 进程不直接承载重型推理。
2. worker 崩了不能把 API 一起带死。
3. provider 失败必须能返回统一错误码。
4. 任何路径都不能再依赖旧项目里的运行时目录。
5. API 和 worker 启动时都要做基础自检。
6. 本地 AI 主链必须具备 `doctor / probe` 门禁。
7. 用户正式交互不能要求手工提供水印位置。
8. `manual bbox / points / mask` 只允许保留为内部调试扩展位。
9. SQLite 连接使用 WAL 模式 + busy_timeout 30s + 指数退避重试。
10. ComfyUI 启动使用文件锁 (fcntl) 防止多 worker 竞争。
11. 回调地址默认拒绝 localhost 和私网 IP (可通过 `DWM_ALLOW_PRIVATE_CALLBACK_URLS` 放开)。
12. 提交接口有速率限制 (默认 60 次/分钟 per API key)。
