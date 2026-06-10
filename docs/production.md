# Production Readiness Runbook | 生产运行手册

本文档面向单机自托管部署。目标是让 `Dewatermark Platform` 能以小步、可回滚、可验证的方式上线，并把当前已经实现的能力和仍需外部配套的边界讲清楚。

## 1. 上线前门槛

上线前必须满足：

- `uv run pytest` 全量通过。
- `uv run dewatermark-worker --doctor` 可运行，并保存输出作为上线前快照。
- `GET /healthz` 返回 API 和 DB 正常。
- `GET /v1/providers` 中至少一个目标 provider 是 `runnable=true`。
- `DWM_ENV=production` 时必须设置非默认 `DWM_DEFAULT_API_KEY`。
- `DWM_STORAGE_ROOT`、`DWM_DB_PATH`、`.runtime` 路径位于可持久化磁盘。
- 已配置数据库和文件目录备份。
- 已准备回滚版本、旧进程停止方式和旧数据恢复方式。

当前没有 `openspec/` 目录；涉及新功能、数据模型、接口或部署架构变更时，应先补项目内 OpenSpec 约定再实施。

## 2. 推荐生产配置

最小生产环境变量：

```sh
export DWM_ENV=production
export DWM_DEFAULT_TENANT_ID="tenant-main"
export DWM_DEFAULT_API_KEY="replace-with-a-long-random-secret"
export DWM_STORAGE_ROOT="/srv/dewatermark/storage"
export DWM_DB_PATH="/srv/dewatermark/storage/app.db"
export DWM_RUNTIME_ROOT="/srv/dewatermark/runtime"
export DWM_COMFYUI_API_URL="http://127.0.0.1:8188"
export DWM_ALLOW_PRIVATE_CALLBACK_URLS=false
export DWM_SUBMIT_RATE_LIMIT_COUNT=60
export DWM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS=60
export DWM_FILE_RETENTION_DAYS=7
```

生产模式保护：

- 当 `DWM_ENV=production` 且 `DWM_DEFAULT_API_KEY=dev-secret-key` 时，API/worker 启动会失败。
- 生产默认拒绝 localhost、私网、链路本地、保留地址和组播地址作为 callback 目标。
- 需要本地调试私网 callback 时，只在开发环境设置 `DWM_ALLOW_PRIVATE_CALLBACK_URLS=true`。

## 3. 启动与进程模型

API 和 worker 必须分进程运行：

```sh
uv run dewatermark-api --host 127.0.0.1 --port 8000
uv run dewatermark-worker --log-level INFO
```

推荐用 systemd、supervisord、launchd 或容器编排托管进程。托管配置至少要包含：

- 自动重启。
- stdout/stderr 日志采集。
- 明确的工作目录和环境变量文件。
- 停止 API 和 worker 的独立命令。
- 部署前后执行 `--doctor` 和 `/healthz` 检查。

## 4. 健康检查

API 存活：

```sh
curl -fsS http://127.0.0.1:8000/healthz
```

Provider 和生产安全检查：

```sh
uv run dewatermark-worker --doctor
curl -fsS -H "X-API-Key: $DWM_DEFAULT_API_KEY" http://127.0.0.1:8000/v1/providers
```

`--doctor` 输出包含：

- `system_dependencies`: SQLite、git、ffmpeg。
- `providers`: `comfy_diffueraser` 和 `local_fallback` 的安装、运行和缺失项。
- `production_safety`: 生产配置风险，如默认开发 key、生产放开私网 callback、关闭限流、保留时间过短。

## 5. 数据一致性

当前数据层是 SQLite WAL：

- job claim 使用事务写入 `running + claimed_at + lock_owner`。
- worker 处理期间心跳刷新 `claimed_at`。
- 文件锁防止同一 job 被多进程重复执行。
- stale claim 会在 worker 轮询时回收。
- callback 使用 outbox 表，回调失败不会回滚 job 最终状态。
- `Idempotency-Key` 写入在 SQLite `BEGIN IMMEDIATE` 临界区内按租户串行化，避免并发请求用同一幂等键创建多条不同任务。

当前边界：

- 单机 SQLite 适合本地或单节点私有化部署。
- 多 API/worker 节点共享同一个 SQLite 文件不是推荐生产形态。
- 需要多机或更高并发时，先迁移到 PostgreSQL/Redis 队列，再放大部署。

## 6. 备份与恢复

必须备份：

- `DWM_DB_PATH`
- `DWM_STORAGE_ROOT/inbox`
- `DWM_STORAGE_ROOT/outbox`
- `.runtime/lock.yaml`
- `.runtime/models/manifest.yaml`
- 生产环境变量文件或密钥管理记录

SQLite 在线备份建议使用 `.backup`，避免直接复制正在写入的数据库：

```sh
sqlite3 "$DWM_DB_PATH" ".backup '/backup/dewatermark/app-$(date +%Y%m%d%H%M%S).db'"
rsync -a "$DWM_STORAGE_ROOT/inbox/" /backup/dewatermark/inbox/
rsync -a "$DWM_STORAGE_ROOT/outbox/" /backup/dewatermark/outbox/
```

恢复顺序：

1. 停止 API 和 worker。
2. 恢复 SQLite 备份到 `DWM_DB_PATH`。
3. 恢复 `inbox/` 和 `outbox/`。
4. 启动 API。
5. 运行 `/healthz`。
6. 启动 worker。
7. 运行 `--doctor` 和一条小样本任务。

## 7. 日志与可观测性

当前已具备：

- API 未处理异常会写 `logger.exception`，对外返回统一 `INTERNAL_ERROR`。
- worker 记录启动、任务成功/失败、stale claim 回收和心跳丢失。
- callback worker 记录重试、最终成功/失败事件。
- `jobs` 表保存状态、provider、耗时、错误码和错误消息。
- `callback_events` 表保存回调尝试历史。
- `run_metadata` 表保存 ComfyUI workflow、quality profile、设备和关键参数。
- `--doctor` 提供运行时和 provider 快照。

上线后至少关注：

- queued job 数量和最长排队时间。
- running job 数量和是否超过 `DWM_JOB_CLAIM_TIMEOUT_SECONDS`。
- succeeded/failed 比例。
- `PROVIDER_NOT_AVAILABLE` 和 `PROVIDER_RUN_FAILED` 数量。
- callback outbox 中 `failed` 和长期 `pending` 数量。
- storage 剩余空间。
- ComfyUI API 是否可达。

当前没有内置 Prometheus `/metrics`。需要正式指标系统时，先基于 SQLite 查询和日志采集落地外部监控，再评估是否新增原生 metrics 接口。

## 8. 清理与容量

默认文件保留 `DWM_FILE_RETENTION_DAYS=7` 天。先 dry-run：

```sh
uv run dewatermark-worker --cleanup
```

确认候选文件后再执行：

```sh
uv run dewatermark-worker --cleanup --execute-cleanup
```

清理只处理非 `queued/running` 任务的过期输入/输出文件，并跳过仍受保护的路径。

## 9. 回滚

代码回滚：

1. 停止 worker，避免新任务继续写状态。
2. 停止 API。
3. 切回上一版本代码。
4. 恢复上一版本依赖环境。
5. 如果本次变更改过数据结构，先恢复上线前数据库备份。
6. 启动 API，检查 `/healthz`。
7. 启动 worker，检查 `--doctor`。

本次仓库当前没有破坏性 schema migration。未来如果引入数据迁移，必须提供：

- migration 前备份命令。
- migration 后验证 SQL。
- rollback SQL 或恢复备份步骤。
- 新旧 worker/API 是否兼容的说明。

## 10. 仍需确认的生产边界

当前实现适合单机私有化上线验证，但还不应承诺：

- 多机高并发调度。
- SaaS 级租户隔离和配额。
- Web 管理后台。
- 一键 Docker 生产部署。
- 商业 SLA 监控。
- 所有视频场景的 AI 去水印效果。

这些能力应作为后续规格变更处理，而不是在当前上线中静默捆绑。
