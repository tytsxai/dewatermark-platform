# Project Overview

## 项目定位

`Dewatermark Platform` 是一个开源、本地优先、面向 API 集成的 AI 去水印平台。

更准确地说，它是：

- open source AI watermark remover platform
- self-hosted video dewatermark API
- local-first async processing system
- ComfyUI-capable AI runtime integration layer

## 要解决的核心问题

很多“去水印能力”实际都被写成：

- 某个项目里的内部脚本
- 某条工作流里的临时步骤
- 强依赖人工框水印位置的半自动工具

这个仓库想解决的是更平台化的问题：

1. 外部系统怎样稳定提交去水印任务。
2. 重型推理怎样和 API 服务解耦。
3. 本地 AI runtime 怎样做就绪检查、安装和观测。
4. provider 不可用时怎样优雅降级。

## 当前产品口径

当前口径非常明确：

- 视频优先
- 本地部署优先
- 异步任务模型
- API + worker 分离
- AI 主链优先尝试 `comfy_diffueraser`
- `local_fallback` 用于兜底保活

## 适合谁

- 想做私有化视频去水印服务的开发者
- 要把去水印能力接到机器人、Web 后台或内部工具的团队
- 需要可控存储、可控回调、可控本地运行时的场景

## 不适合谁

- 只是想找一个在线网页去水印网站的普通终端用户
- 期待零配置、开箱即用、商业级效果的用户
- 需要大规模分布式 GPU 调度的团队

## 当前能力边界

已具备：

- HTTP API
- 异步 job
- 状态查询
- 结果查询
- 取消接口
- provider 健康探测
- 回调与重试
- 本地 runtime `doctor / plan / install / health`

当前重点不在：

- Web 管理后台
- 用户系统
- 复杂计费
- 集群调度
- 图片去水印正式交付

## 核心关键词

为了方便搜索引擎和 AI 模型理解，这个项目长期使用以下稳定关键词：

- 开源 AI 去水印平台
- 开源视频去水印 API
- 本地部署去水印系统
- self-hosted watermark remover
- open source AI watermark removal
- ComfyUI video watermark removal
