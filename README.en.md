# Dewatermark Platform

`Dewatermark Platform` is an open-source, self-hosted, local-first AI video watermark removal platform. It exposes a FastAPI HTTP API, a separate async worker, SQLite-backed job state, local file storage, provider fallback, and ComfyUI / DiffuEraser runtime integration.

It is designed for developers and teams who need a controllable video dewatermark API for bots, web back offices, internal automation, or private media-processing workflows. It is not a hosted consumer SaaS website.

> Responsible use: use this project only for content you own, have permission to process, or are evaluating in a lawful research/internal workflow.

## Quick Facts

| Topic | Current status |
| --- | --- |
| Project type | Open-source AI video watermark removal platform |
| Main use case | Submit video jobs over HTTP and process them asynchronously in a worker |
| Audience | Developers, automation builders, bot/web-backend maintainers, private media workflow teams |
| Stack | Python 3.11/3.12, FastAPI, Uvicorn, SQLite WAL, local filesystem, ComfyUI, DiffuEraser, FFmpeg fallback |
| Current focus | Video jobs; `mp4` / `mov` / `mkv`; local or private deployment |
| Providers | `comfy_diffueraser` as the AI-first provider; `local_fallback` for runnable fallback |
| Not included yet | Hosted SaaS UI, Docker one-click deployment, multi-node GPU scheduling, production SLA monitoring |

## What Problem It Solves

Many watermark-removal workflows remain temporary scripts or manual steps inside a larger project. This repository turns the workflow into a platform boundary:

- HTTP API for job submission and status queries.
- Worker-based async execution so heavy AI inference does not block the API process.
- Provider routing and fallback between the ComfyUI AI path and a local fallback path.
- Runtime readiness commands for ComfyUI, DiffuEraser workflows, custom nodes, and model files.
- Callback delivery with retry and optional HMAC-SHA256 signatures.

## Core Features

- `POST /v1/jobs` to submit video dewatermark jobs.
- `GET /v1/jobs` and `GET /v1/jobs/{job_id}` to query job state.
- `GET /v1/jobs/{job_id}/result` to retrieve local output path information.
- `POST /v1/jobs/{job_id}/cancel` to cancel queued jobs.
- `GET /v1/providers` to inspect provider/runtime readiness.
- API key authentication through `X-API-Key`.
- Idempotent submission through `Idempotency-Key`.
- Submit rate limiting, defaulting to 60 requests per minute per API key.
- SQLite WAL, job claims, file locks, worker heartbeat, stale claim recovery.
- Callback outbox with retries and HMAC-SHA256 signing.
- File retention cleanup, defaulting to 7 days.
- Quality profiles: `fast`, `balanced`, `quality`, `corner_hq`.

## Provider Scope

| Provider | Purpose | Important limitation |
| --- | --- | --- |
| `comfy_diffueraser` | Main AI provider using ComfyUI API prompts, DiffuEraser workflow files, custom nodes, and required models | It is runnable only when the local ComfyUI runtime and model files are present |
| `local_fallback` | Keeps API, worker, storage, callback, and job-state flows testable | Default `ffmpeg_copy` only copies the input file; `delogo` requires manual coordinates and is not AI removal |

The formal product direction is: upload a video, process it automatically, return a result. The API model reserves `image`, but `POST /v1/jobs` currently accepts `video` only.

## Quick Start

```sh
uv sync
uv run dewatermark-api --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
uv run dewatermark-worker
```

Health check:

```sh
curl http://127.0.0.1:8000/healthz
```

Submit a video job:

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: first-job" \
  -F "media_type=video" \
  -F "provider=auto" \
  -F "file=@/absolute/path/to/local.mp4"
```

Query status:

```sh
curl http://127.0.0.1:8000/v1/jobs/<job_id> \
  -H "X-API-Key: dev-secret-key"
```

## Local AI Runtime Commands

```sh
uv run dewatermark-worker --doctor
uv run dewatermark-worker --runtime-plan
uv run dewatermark-worker --install-runtime --repos-only
uv run dewatermark-worker --comfyui-plan
uv run dewatermark-worker --comfyui-health
uv run dewatermark-worker --start-comfyui
```

Notes:

- `.runtime/lock.yaml` pins runtime repositories.
- `.runtime/models/manifest.yaml` lists expected model files.
- The default ComfyUI API endpoint is `http://127.0.0.1:8188`.
- Set `DWM_ENV=production` and replace the default development API key before exposing the service. Startup fails in production if `DWM_DEFAULT_API_KEY` is still `dev-secret-key`.

## Documentation

- [Chinese README](README.md)
- [Docs Index](docs/index.md)
- [Overview](docs/overview.md)
- [FAQ](docs/faq.md)
- [API](docs/api.md)
- [Architecture](docs/architecture.md)
- [Production Runbook](docs/production.md)
- [Requirements](docs/requirements.md)
- [Roadmap](docs/roadmap.md)
- [LLM Index](llms.txt)

## Search Keywords

`open source AI watermark remover`, `video watermark removal API`, `self-hosted dewatermark platform`, `local-first AI video processing`, `ComfyUI DiffuEraser workflow`, `async video watermark removal worker`, `FastAPI watermark removal API`.

## Test

```sh
uv run pytest
```
