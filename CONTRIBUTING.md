# Contributing

## Scope

This repository is a local async video dewatermark platform.

Please keep contributions aligned with the current direction:

- local-first deployment
- API + worker separation
- provider-based execution
- simple, runnable implementation over heavy abstraction

## Development

```sh
uv sync --extra dev
uv run pytest
```

Run services locally:

```sh
uv run python -m apps.api.main --host 0.0.0.0 --port 8000
uv run python -m apps.worker.main
```

## Pull Requests

- keep changes focused
- include tests for behavior changes
- avoid unrelated refactors
- document any new runtime dependency or model expectation

## Issues

When reporting a bug, include:

- input type and file size
- selected provider
- ComfyUI version / custom nodes / models status
- relevant logs from API, worker, and `--doctor`
