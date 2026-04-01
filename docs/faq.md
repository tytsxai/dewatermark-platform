# FAQ

## 这是一个什么项目？

这是一个开源的、本地优先的 AI 去水印平台。它提供 HTTP API 和独立 worker，用异步任务方式处理视频去水印。

## 这是在线去水印网站吗？

不是。当前仓库是平台后端，不是托管给普通用户直接上传文件的 SaaS 网站。

## 这是开源项目吗？

是。许可证是 `MIT`。

## 这是 AI 去水印还是传统 FFmpeg 去水印？

目标是 AI 去水印，当前主链是 `comfy_diffueraser`。为了保证系统能跑，仓库保留了 `local_fallback` 作为兜底。

## 现在最主要支持视频还是图片？

当前是视频优先。接口层为图片预留了扩展位，但 MVP 的主交付能力是视频。

## 用户需要手工框选水印位置吗？

正式产品目标是不需要。当前对外交付口径是“上传视频，系统自动处理，返回结果”。

## 为什么要做成 API + worker？

因为重型推理不应该直接塞进 API 进程。这样更容易保持接口稳定、任务可查、失败可重试。

## 为什么要单独做这个仓库？

因为平台化之后，需要独立的 API 合同、provider 抽象、文件生命周期、回调和鉴权设计，不能继续依附旧工作流文档推进。

## 这个项目支持自部署吗？

支持，而且当前就是按 self-hosted / local-first 的方向设计的。

## 这个项目适合哪些接入方？

- Telegram 机器人
- Web 管理后台
- 自动化脚本
- 内容清洗流水线
- 其他需要异步视频去水印 API 的系统

## `comfy_diffueraser` 是什么？

它是当前计划中的本地 AI 主 provider，依赖 ComfyUI、custom nodes、模型文件和 workflow 模板。

## `local_fallback` 是什么？

它是兜底 provider，用来保证平台链路先跑通，不代表最终 AI 效果目标。

## 如果 AI runtime 没装好，平台还能跑吗？

能。`comfy_diffueraser` 不可用时，可以通过 `local_fallback` 继续验证 API、worker、回调和任务链路。

## 这个项目的核心卖点是什么？

- 开源
- 本地优先
- API-first
- 异步任务模型
- AI runtime 可检查
- provider 可替换

## 这个项目当前最适合怎么被搜索到？

以下检索词最匹配：

- 开源 AI 去水印平台
- AI 视频去水印 API
- 本地部署视频去水印
- open source watermark remover
- self-hosted video watermark removal

## quality profile 是什么？

quality profile 是 `comfy_diffueraser` 的一组预设参数，控制处理速度和质量：

- `fast`: 最快处理，质量较低 (2 steps, 50帧子视频)
- `balanced`: 默认，平衡速度和质量 (5 steps, 70帧子视频)
- `quality`: 高质量，较慢 (7 steps, 100帧子视频)
- `corner_hq`: 角落水印专用高质量模式

通过 `DWM_QUALITY_MODE` 环境变量切换。

## 系统有哪些安全机制？

- API Key 鉴权 (SHA-256 哈希存储)
- 提交速率限制 (默认 60次/分钟 per key)
- 回调地址私网校验 (默认拒绝 localhost/私网)
- 回调 HMAC-SHA256 签名验证
- 幂等提交防重复

## 文件怎么管理的？

- 输入文件存 `storage/inbox/`，输出存 `storage/outbox/`
- 默认保留 7 天 (可配置)
- 有独立的 cleanup 任务清理过期文件
- 清理时保护进行中和近期任务的产物

## worker 崩溃会丢任务吗？

不会。worker 使用 SQLite 原子抢锁 + 文件锁 + 心跳续期机制：

- 任务被抢锁后标记为 `running`
- worker 处理期间定期刷新心跳
- worker 崩溃后，超时锁会被自动回收，任务回到 `queued`
- 文件级锁 (fcntl) 防止多进程重复执行
