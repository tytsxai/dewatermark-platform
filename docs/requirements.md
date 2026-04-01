# Product Requirements

本文档定义 `Dewatermark Platform` 的产品边界和一期交付口径，避免项目重新滑回“旧工作流里的临时去水印脚本”。

## 1. 项目定位

这是一个独立的本地去水印系统。

目标不是服务某一个固定工作流，而是提供统一 API，让不同平台都能接入：

- 电报机器人
- Web 后台
- 自动化脚本
- 现有内容发布系统
- 未来其他第三方系统

## 2. 一期目标

一期只追求能跑、能接、能查、能回调。

MVP 必须满足：

1. 支持通过 HTTP API 提交去水印任务
2. 支持视频任务
3. 任务异步执行
4. 支持状态查询
5. 支持结果下载地址或本地路径返回
6. 支持回调通知
7. 支持指定 provider 或自动选择 provider
8. 单机本地可部署
9. 支持幂等提交
10. 支持 provider 可观测探测

补一条当前已经明确的产品口径：

- 用户正式交互必须是“上传视频 -> 系统自动处理 -> 返回结果”
- 不接受“要求用户手工提供水印位置”作为正式方案
- `manual bbox / points / mask` 只允许作为内部调试或过渡能力，不算一期对外交付目标

## 3. 一期不做

先不做这些：

- 用户系统
- 复杂计费系统
- Web 管理后台
- 分布式调度
- 多机集群
- 自动扩缩容
- 高级审核系统

这些不是不要，是现在不做。

## 4. 能力边界

### 一期必须支持

- `video`
- provider 路由
- 失败降级
- 本地文件输入
- HTTP 文件上传
- 回调
- 幂等键
- 基础任务重试

### 一期必须明确但允许分阶段完成

- 本地 AI 主链目标是 `comfy_diffueraser`
- `comfy_diffueraser` 必须独立成 worker / service，不进入 API 主进程
- 必须具备 `doctor / probe` 门禁：
  - ComfyUI 本体
  - custom nodes
  - 模型文件
  - workflow 模板
  - ComfyUI API
- provider 必须可替换，模型和工作流必须允许后续迭代

### 一期接口预留，但可先返回未实现

- `image`
- 批量任务
- 结果二次压缩
- 水印区域手工标注

说明：

- “水印区域手工标注”不是当前产品目标，只是保留内部调试扩展位

## 5. 一期输入约束

先把边界写死，别让一期被无限扩展：

- 单文件任务
- 默认只收常见视频格式：`mp4`、`mov`、`mkv`
- 单文件大小先限制在可配置范围内
- 单任务视频时长先限制在可配置范围内
- 一期默认不处理音频分离、字幕提取、超分辨率
- 一期不承诺对所有动态复杂遮挡场景都有效

这些不是永久限制，只是为了先把系统跑起来。

## 6. 核心对象

### Job

字段至少包括：

- `job_id`
- `tenant_id`
- `media_type`
- `status`
- `provider`
- `fallback_chain`
- `idempotency_key`
- `priority`
- `input_path`
- `output_path`
- `callback_url`
- `callback_secret`
- `attempt_count`
- `duration_ms`
- `error_code`
- `error_message`
- `created_at`
- `updated_at`

### Provider

一期先支持两类：

- `comfy_diffueraser`
- `local_fallback`

三者职责现在已经明确：

- `comfy_diffueraser`
  - 本地 AI 主方案
  - 最终目标是自动检测 / 自动去水印
- `local_fallback`
  - 兜底保活
  - 不能代表最终 AI 能力

### Status

统一状态定义：

- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`

## 7. 核心流程

### 提交流程

1. 调用方上传文件或传入本地文件路径
2. API 创建 job
3. job 进入队列
4. worker 按 provider 策略执行
5. 成功后输出结果文件
6. 更新 job 状态
7. 如有回调则通知调用方

### 路由流程

支持三种模式：

1. `provider=comfy_diffueraser`
2. `provider=local_fallback`
3. `provider=auto`

`auto` 的一期默认策略：

1. 先尝试 `comfy_diffueraser`
2. 失败则降级到 `local_fallback`

这个顺序后续可配置，但现在先固定，保持简单。

补充口径：

- `auto` 的产品含义不是“优先让用户补水印框”，而是“优先尝试自动 AI 主链”
- 当前如果 `comfy_diffueraser` 尚未就绪，系统可以继续降级，但这不改变最终产品目标

### 幂等流程

一期要求支持 `Idempotency-Key`：

1. 相同调用方
2. 相同 `Idempotency-Key`
3. 相同输入摘要或相同本地路径

满足时直接返回已有 job，不重复创建。

## 8. 鉴权和调用约束

一期最小实现：

- API Key 鉴权
- 每个调用方一个 key
- 请求头使用 `X-API-Key`

一期先不做复杂 RBAC。

## 9. 回调规则

一期必须明确：

- 回调使用 `POST`
- 回调 body 至少包含 `job_id`、`status`、`provider`、`output_path`、`error_code`
- 如果设置了 `callback_secret`，回调头里带签名
- 回调失败自动重试，至少 3 次
- 回调失败不能影响 job 最终状态写入
- 生产默认只允许公网 `http/https` 回调地址；`localhost` 和私网 IP 需要显式放开

## 10. 文件管理

最小规则必须先定死：

1. 输入文件放 `storage/inbox/`
2. 输出文件放 `storage/outbox/`
3. 失败中间文件默认不保留
4. 输入和输出默认保留 7 天
5. 清理由独立清理任务处理

## 11. 错误码约定

一期至少区分这几类：

- `VALIDATION_ERROR`
- `AUTH_ERROR`
- `PROVIDER_NOT_AVAILABLE`
- `PROVIDER_RUN_FAILED`
- `CALLBACK_FAILED`
- `FILE_NOT_FOUND`
- `FILE_TOO_LARGE`
- `MEDIA_TYPE_NOT_SUPPORTED`
- `INTERNAL_ERROR`

先把错误码打平，别一开始做复杂分层。

## 12. 可观测性

一期至少记录：

- job 数量
- 各状态数量
- 各 provider 成功率
- 各 provider 平均耗时
- 错误码分布

先做日志和基础指标，不追求大而全。

## 13. 非功能要求

一期至少满足：

1. API 服务和 worker 可以独立启动和重启
2. worker 异常退出后，未完成任务不会永久丢失
3. 单个 provider 卡死时，不把 API 一起拖死
4. 所有关键状态变更都写日志
5. 任何实现都不能依赖 OpenFang 或 shipinbot 运行时路径

## 14. 验收标准

只有满足下面这些，才算一期能跑：

1. 本地能启动 API 服务
2. 本地能启动 worker
3. 能提交视频去水印任务
4. 能查到任务状态
5. 能得到输出结果
6. provider 失败时能按预期降级
7. API 不依赖 OpenFang 或 shipinbot 才能运行
8. 相同幂等键不会重复建单
9. 回调失败会自动重试
10. `/v1/providers` 能正确返回 provider 可用性

## 15. 当前明确结论

当前仓库不再以旧文档作为主方案。

旧文档只保留两个价值：

- 作为视频链接入经验参考
- 作为 provider 能力核验参考

同时再补一条当前阶段结论：

- 当前项目的最终方向已经锁定为"本地 AI 自动视频去水印平台"
- 当前框架层已基本具备：
  - API (FastAPI, 鉴权, 速率限制, 幂等, 错误处理)
  - worker (SQLite polling, 文件锁, 心跳续期, 异常恢复)
  - provider probe / doctor / runtime install
  - ComfyUI runtime contract (自动启动, 文件锁防竞争, health check)
  - callback outbox 模式 (HMAC 签名, 自动重试, 独立线程)
  - quality profiles (fast / balanced / quality / corner_hq)
  - run metadata 记录 (workflow, profile, device, seed 等)
  - SQLite 高可用 (WAL, busy_timeout, 指数退避重试)
  - 文件生命周期管理 (可配置保留天数, cleanup job)
  - runtime installer (git clone, venv, pip, 依赖安装)
- 当前尚未完成的核心项已经收敛为：
  - `comfy_diffueraser` 模型安装
  - 自动 AI 效果与性能调优

## 16. 已实现能力清单

以下能力已在代码中实现并可用：

### 核心 API
- [x] `POST /v1/jobs` — 文件上传 + 本地路径 + 幂等 + 速率限制
- [x] `GET /v1/jobs` — 分页 + 过滤 (status, provider, media_type)
- [x] `GET /v1/jobs/{job_id}` — 状态查询
- [x] `GET /v1/jobs/{job_id}/result` — 结果查询 + 410 产物缺失处理
- [x] `POST /v1/jobs/{job_id}/cancel` — 取消 queued 任务
- [x] `GET /v1/providers` — provider 健康探测 + 缓存
- [x] `GET /healthz` — API + DB 健康检查

### Worker
- [x] SQLite polling + 原子抢锁
- [x] 文件级锁 (fcntl) 防重复执行
- [x] 心跳续期 (防超时回收)
- [x] 超时锁回收 (stale claim → queued)
- [x] 异常恢复 (worker 崩溃不丢任务)
- [x] 独立 callback worker 线程

### Provider
- [x] `comfy_diffueraser` — ComfyUI API 执行链 + quality profiles + 动态模型解析
- [x] `local_fallback` — ffmpeg_copy + delogo 模式
- [x] `provider=auto` 降级链
- [x] provider probe 缓存

### Callback
- [x] callback outbox 表 + 独立 worker
- [x] HMAC-SHA256 签名 (X-Signature, X-Timestamp)
- [x] 自动重试 (可配置次数和间隔)
- [x] 私网地址校验 (默认拒绝 localhost/私网)
- [x] callback_events 审计日志

### Runtime
- [x] doctor 报告 (系统依赖 + provider 探测)
- [x] runtime installer (git clone, venv, pip)
- [x] ComfyUI 自动启动 + 文件锁防竞争
- [x] ComfyUI health check + wait
- [x] runtime lock (lock.yaml) + model manifest (manifest.yaml)

### 其他
- [x] 速率限制 (滑动窗口, per API key)
- [x] 文件生命周期管理 (可配置保留天数)
- [x] run metadata 记录 (workflow, profile, device, seed)
- [x] SQLite WAL + busy_timeout + 指数退避重试
- [x] 统一错误码体系
