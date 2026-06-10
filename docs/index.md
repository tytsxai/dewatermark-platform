# Documentation Index | 文档总入口

这个目录是 `Dewatermark Platform` 的文档入口，面向三类读者：

- 第一次进入仓库的开发者。
- 需要接入 API / worker 的工程人员。
- 需要理解项目事实的传统搜索引擎和 AI 搜索引擎。

Project summary: **open-source self-hosted AI video watermark removal platform**, built with **FastAPI**, an **async worker**, **SQLite**, local storage, provider fallback, and **ComfyUI / DiffuEraser** runtime integration.

## 先读什么

| 文档 | 适合读者 | 内容 |
| --- | --- | --- |
| [README.md](../README.md) | 所有人 | 项目定位、快速开始、核心功能、限制和关键词 |
| [overview.md](overview.md) | 评估项目价值的人 | 项目是什么、适合谁、当前能力边界 |
| [faq.md](faq.md) | 搜索/问答读者 | 高频问题、限制、provider 解释、使用场景 |
| [api.md](api.md) | 接入方 | HTTP API、字段、错误码、回调语义 |
| [architecture.md](architecture.md) | 维护者 | API / worker / provider / storage / callback 架构 |
| [production.md](production.md) | 运维/上线负责人 | 生产配置、健康检查、备份恢复、日志指标和回滚 |
| [requirements.md](requirements.md) | 产品和工程负责人 | 需求边界、一期目标、非目标 |
| [roadmap.md](roadmap.md) | 贡献者 | 已完成阶段和后续计划 |

## 建议阅读顺序

1. [README.md](../README.md)
2. [overview.md](overview.md)
3. [faq.md](faq.md)
4. [api.md](api.md)
5. [architecture.md](architecture.md)
6. [production.md](production.md)
7. [roadmap.md](roadmap.md)

## 当前最重要的事实

- 当前提交接口只支持 `video`，支持 `mp4` / `mov` / `mkv`。
- `comfy_diffueraser` 是 AI 主链，需要 ComfyUI、custom nodes、workflow 和模型文件齐备。
- `local_fallback` 是兜底链路，默认 `ffmpeg_copy` 只复制文件，不代表 AI 去水印效果。
- 项目是 API + worker 平台仓库，不是面向普通用户的在线 SaaS 网站。
- 默认开发 key 是 `dev-secret-key`；`DWM_ENV=production` 时如果仍使用该 key，服务会拒绝启动。

## 历史与审查

- [review.md](review.md): 对历史方案的审查和为什么单开仓库。
