# Roadmap

## 阶段 0

先把文档钉死：

- 需求
- 架构
- API
- provider 路由规则

完成标志：

- 不再依赖旧系统文档推进

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

## 阶段 2

接第一个真实 provider：

- `local_fallback` 或 `comfy_diffueraser`

完成标志：

- 至少一个真实 provider 可跑

当前阶段状态更新：

- `local_fallback` 已可跑
- `comfy_diffueraser` 的 runtime contract / doctor / probe 已落地
- `comfy_diffueraser` 已接入 ComfyUI API 执行链
- 当前主要缺口已经收敛到模型就位和实际效果调优

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

## 阶段 4

补回调、清理、重试：

- callback retry
- cleanup job
- 错误码整理

完成标志：

- 一期具备持续运行基础

当前阶段状态更新：

- callback retry
- cleanup
- doctor
- runtime bootstrap CLI

以上已基本具备

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
