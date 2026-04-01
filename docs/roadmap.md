# Roadmap

本文档记录开源 AI 去水印平台的阶段目标和当前推进状态，重点是先把独立 API、worker、provider 和本地 AI runtime 主链跑通。

## 阶段 0

先把文档钉死：

- 需求
- 架构
- API
- provider 路由规则

完成标志：

- 不再依赖旧系统文档推进

**状态: ✅ 已完成**

## 阶段 1

实现最小可跑骨架：

- FastAPI
- SQLite
- 本地文件存储
- worker polling
- 假 provider

完成标志：

- 可以提交任务
- 可以查状态
- 假任务可以跑通全链路

**状态: ✅ 已完成**

## 阶段 2

接第一个真实 provider：

- `local_fallback` 或 `comfy_diffueraser`

完成标志：

- 至少一个真实 provider 可跑

当前阶段状态更新：

- `local_fallback` 已可跑 (ffmpeg_copy + delogo)
- `comfy_diffueraser` 的 runtime contract / doctor / probe 已落地
- `comfy_diffueraser` 已接入 ComfyUI API 执行链
- 当前主要缺口已经收敛到模型就位和实际效果调优

**状态: ✅ 已完成**

## 阶段 3

补 provider 探测和自动降级：

- `/v1/providers`
- `provider=auto`
- fallback chain

完成标志：

- provider 故障时系统仍可返回清晰结果

当前阶段状态更新：

- 这部分已经完成
- `/v1/providers` 已返回结构化探测结果
- provider probe 缓存已实现 (默认 10s)

**状态: ✅ 已完成**

## 阶段 4

补回调、清理、重试：

- callback retry
- cleanup job
- 错误码整理

完成标志：

- 一期具备持续运行基础

当前阶段状态更新：

- callback outbox 模式已实现 (独立 worker 线程)
- callback retry 已实现 (可配置次数和间隔)
- HMAC-SHA256 签名验证已实现
- 私网地址校验已实现
- cleanup job 已实现 (可配置保留天数, dry_run + execute)
- doctor CLI 已实现
- runtime bootstrap CLI 已实现
- rate limiting 已实现 (滑动窗口, per API key)
- 文件锁 (fcntl) 防重复执行已实现
- 心跳续期已实现
- SQLite WAL + 指数退避重试已实现

**状态: ✅ 已完成**

## 阶段 5

补本地 AI 主链框架：

- `.runtime/lock.yaml`
- `.runtime/models/manifest.yaml`
- `workflows/sam2_diffueraser_api.json`
- ComfyUI runtime bootstrap
- ComfyUI `/system_stats` 探活

完成标志：

- 不装模型时，框架也能完成：
  - runtime plan
  - repo/bootstrap
  - ComfyUI 启动
  - API 探活

当前阶段状态更新：

- runtime lock (lock.yaml) 已实现
- model manifest (manifest.yaml) 已实现
- runtime installer (git clone, venv, pip) 已实现
- ComfyUI 自动启动 + 文件锁防竞争已实现
- quality profiles (fast / balanced / quality / corner_hq) 已实现
- workflow 动态参数注入已实现
- run metadata 记录已实现
- ComfyUI `/system_stats` 探活已实现

**状态: ✅ 已完成**

## 阶段 6

补本地 AI 主链模型与执行链：

- 下载必需模型
- `comfy_diffueraser` 变为 `runnable=true`
- 接入真正执行逻辑
- 逐步推进到自动 AI 视频去水印

完成标志：

- 用户只上传视频
- 系统自动处理
- 不要求用户提供水印位置

当前阶段状态更新：

- API prompt 模板已落地
- Worker 已能调用 ComfyUI `/prompt` / `/history` / `/view`
- `comfy_diffueraser` 在模型齐备、ComfyUI 可用时可直接执行
- 动态模型路径解析已实现 (VAE, LoRA, CLIP, ProPainter, Flow, Raft)
- 当前主要缺口: 模型下载和效果调优

**状态: 🔄 进行中 — 模型安装和效果调优**

## 阶段 7 (规划中)

效果优化与生产就绪：

- 模型效果评估与调优
- 多场景水印自动检测
- 性能优化 (批处理, 并发)
- 监控与告警
- Docker 容器化
- CI/CD pipeline

完成标志：

- 多场景水印自动检测可用
- 有明确的 SLA 和监控
- 可一键部署
