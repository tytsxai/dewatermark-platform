# Architecture

## 1. 一期架构

一期只用最简单能跑的结构：

```text
client
  -> api service
  -> job store
  -> local queue
  -> worker
  -> provider adapter
  -> output file
```

更具体一点：

```text
client
  -> FastAPI
  -> SQLite(jobs, callbacks, api_keys)
  -> worker polling loop
  -> provider adapter
  -> storage/inbox + storage/outbox
  -> .runtime/ComfyUI + custom_nodes + models
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

## 3. 建议技术栈

为了简单，先按这个落：

- API: FastAPI
- DB: SQLite
- Queue: SQLite polling 或最小内存队列加持久化表
- Worker: Python process
- Storage: 本地文件系统

如果后面需要增强，再替换成：

- DB: PostgreSQL
- Queue: Redis / Celery / RQ

但一期不要先把自己设计死。

## 4. 模块划分

### API Service

职责：

- 接收上传
- 创建 job
- 鉴权
- 查询状态
- 返回结果信息

### Worker

职责：

- 拉取待处理 job
- 调用 provider adapter
- 写回结果状态
- 发送回调
- 处理重试和降级
- 承载本地 AI runtime 的探测、启动和执行

### Provider Adapter

职责：

- 统一封装不同去水印后端
- 输出统一结果格式
- 处理 provider 级错误

当前 provider 分层已经明确：

- `comfy_diffueraser`
  - 本地 AI 主链
  - 依赖 ComfyUI runtime、custom nodes、models、workflow、API
- `local_fallback`
  - 兜底路径
  - 负责系统保活，不代表最终效果目标
- `cloud_inpaint`
  - 可选兼容路径

统一接口建议：

```python
class ProviderAdapter:
    name: str

    def probe(self) -> dict: ...

    def run(self, job: dict) -> dict: ...
```

### Storage

职责：

- 存输入文件
- 存输出文件
- 提供产物路径

## 5. 数据层最小设计

一期别搞太复杂，先有这三张表就够：

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
- `output_path`
- `callback_url`
- `callback_secret`
- `attempt_count`
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
- `created_at`

## 6. 队列与抢锁规则

一期用 SQLite 轮询就行，但规则必须明确：

1. worker 只拉 `queued` 状态任务
2. 抢到任务时写入 `claimed_at` 和 `lock_owner`
3. worker 启动时回收超时锁
4. 同一 job 任意时刻只允许一个 worker 执行

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

## 9. 关键工程约束

1. API 进程不直接承载重型推理。
2. worker 崩了不能把 API 一起带死。
3. provider 失败必须能返回统一错误码。
4. 任何路径都不能再依赖旧项目里的运行时目录。
5. API 和 worker 启动时都要做基础自检。
6. 本地 AI 主链必须具备 `doctor / probe` 门禁。
7. 用户正式交互不能要求手工提供水印位置。
8. `manual bbox / points / mask` 只允许保留为内部调试扩展位。
