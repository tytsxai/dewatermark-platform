# Changelog

All notable changes to this project will be documented in this file. The format is based on Keep a Changelog; the project uses Semantic Versioning.

## [0.1.0] - 2026-05-19

First tagged release. This codifies the platform's MVP shape after several iterations on the README, docs structure, and runtime contract.

### Included

- **API + worker architecture** (FastAPI + SQLite + async worker), local-first / self-hostable.
- **Multi-provider routing** with `provider=auto` failover:
  - `comfy_diffueraser` — ComfyUI-based AI video watermark removal (primary)
  - `local_fallback` (`ffmpeg_copy` keep-alive, `delogo` minimal coords-based) (fallback)
- **Quality profiles**: `fast` / `balanced` / `quality` / `corner_hq` mapped onto Diffueraser parameters (steps, subvideo_length, neighbor_length, mask_dilation_iter, ref_stride).
- **AI runtime contract**: `doctor` / `runtime-plan` / `install-runtime` / `comfyui-plan` / `start-comfyui` subcommands to inspect and bootstrap the local ComfyUI environment without binding the deploy to a single host setup.
- **Job API surface**:
  - `POST /v1/jobs` (multipart upload, `Idempotency-Key` supported)
  - `GET /v1/jobs` / `GET /v1/jobs/{id}` / `GET /v1/jobs/{id}/result` / `POST /v1/jobs/{id}/cancel`
  - `GET /v1/providers`, `GET /healthz`
- **Auth + rate limiting**: per-API-key sliding-window rate limit, default tenant `local-dev` + key `dev-secret-key` for first-run usability.
- **Callbacks**: HMAC-SHA256-signed callback URL with configurable retry count + delay; private callback URLs blocked unless explicitly allowed.
- **File lifecycle**: storage root + retention days; `storage/inbox/` + `storage/outbox/` auto-created.
- **Observability fields**: workflow, profile, device, seed recorded on each run.
- **Discovery surfaces**: bilingual READMEs (`README.md` / `README.en.md`), `llms.txt`, structured docs under `docs/` covering FAQ / API / architecture / requirements / roadmap.

### Notes

This is the first version that the maintainer considers worth tagging. The internal design is stable enough that downstream tools can pin a version. Behavior between this tag and the most recent commit on `main` before tagging is identical.
