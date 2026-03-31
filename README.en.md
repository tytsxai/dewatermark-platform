# Dewatermark Platform

Open source, local-first AI dewatermark platform for asynchronous video watermark removal.

This repository is a self-hosted watermark remover platform built around:

- FastAPI API service
- worker-based async job execution
- local file storage
- provider routing and fallback
- ComfyUI-based AI runtime integration

## What It Is

`Dewatermark Platform` is an open source AI watermark removal platform focused on video workflows. It is designed for developers and teams who need a local, controllable, API-first system instead of a hosted consumer website.

Typical keywords this project targets:

- open source AI watermark remover
- video watermark removal API
- self-hosted dewatermark platform
- local-first AI video processing
- ComfyUI watermark removal pipeline

## Current Scope

- Video-first MVP
- Async job submission and status tracking
- Provider health checks
- Callback support
- Idempotent submissions
- Local AI runtime doctor / plan / install / health commands

Current providers:

- `comfy_diffueraser` for the intended AI-first path
- `local_fallback` for keeping the system runnable

## Quick Start

```sh
uv sync
uv run dewatermark-api --host 0.0.0.0 --port 8000
uv run dewatermark-worker
```

Check runtime readiness:

```sh
uv run dewatermark-worker --doctor
```

## API Example

```sh
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: first-job" \
  -F "media_type=video" \
  -F "provider=auto" \
  -F "file=@/absolute/path/to/local.mp4"
```

## Documentation

- [Chinese README](./README.md)
- [Docs Index](./docs/index.md)
- [Overview](./docs/overview.md)
- [FAQ](./docs/faq.md)
- [Architecture](./docs/architecture.md)
- [API](./docs/api.md)
- [Requirements](./docs/requirements.md)
- [Roadmap](./docs/roadmap.md)
- [LLM Index](./llms.txt)

## Status

This project is not a polished SaaS product. It is an open source platform repository focused on making an AI dewatermark system runnable, inspectable, and extensible.
