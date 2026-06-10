# Project Overview | 项目概览

`Dewatermark Platform` 是一个开源、自托管、本地优先的 AI 视频去水印平台。它把视频去水印能力封装成稳定的 API、异步 worker、provider runtime 和本地存储边界，方便其他系统接入。

English positioning: **open-source AI video watermark removal platform**, **self-hosted dewatermark API**, **local-first async media processing**, **ComfyUI DiffuEraser integration**.

## 项目定位

这个项目不是一个临时脚本，也不是在线去水印网站。它的定位是：

- 给外部系统调用的 HTTP API。
- 与 API 进程解耦的 worker 异步执行模型。
- 可观测、可替换的 provider 层。
- 可检查、可安装、可启动、可探活的本地 AI runtime。
- 适合私有化或本地 GPU 工作站部署的媒体处理节点。

## 要解决的核心问题

很多“去水印能力”实际被写成：

- 某个项目里的内部脚本。
- 某条工作流里的临时步骤。
- 需要人工框选水印区域的半自动工具。

本项目解决的是平台化接入问题：

1. 外部系统如何稳定提交视频去水印任务。
2. 重型推理如何不阻塞 API 进程。
3. 本地 ComfyUI / DiffuEraser 运行时如何做安装计划和就绪检查。
4. provider 不可用时如何通过 fallback 维持任务链路可验证。
5. 调用方如何查询状态、取消任务、获取结果和接收回调。

## 适合谁

- 想做私有化视频去水印服务的开发者。
- 要把去水印能力接到机器人、Web 后台或内部工具的团队。
- 需要可控存储、可控回调、可控本地运行时的内容处理场景。
- 想验证 ComfyUI / DiffuEraser workflow API 化和队列化的人。

## 不适合谁

- 只是想找在线网页去水印网站的普通终端用户。
- 期待零配置、开箱即用、商业级效果的用户。
- 当前就需要大规模分布式 GPU 调度、账号计费或 Web 管理后台的团队。

## 当前能力边界

已具备：

- HTTP API (FastAPI)
- 独立 worker
- SQLite polling queue
- SQLite WAL + busy timeout + retry
- 本地文件存储
- API Key 鉴权
- 提交速率限制
- 幂等提交
- 任务列表、状态、结果、取消接口
- provider 健康探测
- `comfy_diffueraser` ComfyUI API 执行链
- `local_fallback` 的 `ffmpeg_copy` / `delogo` 模式
- callback outbox、HMAC-SHA256 签名和失败重试
- worker 文件锁、心跳续期和 stale claim 回收
- runtime `doctor / plan / install / health / start`
- quality profiles: `fast` / `balanced` / `quality` / `corner_hq`
- 文件生命周期清理

当前重点不在：

- Web 管理后台
- 用户系统
- 复杂计费
- 集群调度
- Docker 一键部署
- 图片去水印正式交付
- 多场景效果承诺和 SLA 监控

## Provider 边界

| Provider | 当前定位 | 真实限制 |
| --- | --- | --- |
| `comfy_diffueraser` | AI 主 provider，接 ComfyUI API prompt 和 DiffuEraser workflow | 需要本地 runtime、custom nodes、workflow 和必需模型都就绪 |
| `local_fallback` | 兜底 provider，保证系统链路能跑 | 默认 `ffmpeg_copy` 不会去水印；`delogo` 需要手工坐标 |

## 核心关键词

- 开源 AI 视频去水印平台
- 本地部署视频去水印 API
- 自托管去水印系统
- ComfyUI 视频去水印
- DiffuEraser workflow API
- FastAPI watermark removal API
- self-hosted watermark remover
- local-first AI video processing
