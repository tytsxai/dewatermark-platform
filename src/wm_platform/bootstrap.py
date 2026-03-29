from __future__ import annotations

from wm_platform.config import Settings, load_settings
from wm_platform.db import init_db
from wm_platform.repository import JobRepository
from wm_platform.storage import ensure_storage_dirs


def bootstrap(settings: Settings | None = None) -> tuple[Settings, JobRepository]:
    resolved_settings = settings or load_settings()
    ensure_storage_dirs(resolved_settings)
    init_db(resolved_settings)
    repository = JobRepository(resolved_settings)
    repository.seed_api_key(resolved_settings.default_tenant_id, resolved_settings.default_api_key)
    return resolved_settings, repository
