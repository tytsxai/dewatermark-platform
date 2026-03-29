from __future__ import annotations

from datetime import UTC, datetime, timedelta

from wm_platform.config import Settings
from wm_platform.repository import JobRepository


def run_file_cleanup(settings: Settings, repository: JobRepository, execute: bool = False) -> dict[str, int | str]:
    retention_days = max(0, settings.file_retention_days)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    cutoff_timestamp = cutoff.timestamp()

    report: dict[str, int | str] = {
        "mode": "execute" if execute else "dry_run",
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "candidate_files": 0,
        "deleted_files": 0,
        "failed_files": 0,
    }

    for directory in (settings.inbox_dir, settings.outbox_dir):
        for path in directory.iterdir():
            if not path.is_file() or path.name == ".gitkeep":
                continue
            if path.stat().st_mtime >= cutoff_timestamp:
                continue
            report["candidate_files"] += 1
            if not execute:
                continue
            try:
                path.unlink()
                report["deleted_files"] += 1
            except OSError:
                report["failed_files"] += 1

    db_summary = repository.cleanup_expired_files(cutoff)
    report["candidate_jobs"] = db_summary["candidate_jobs"]
    report["candidate_db_files"] = db_summary["candidate_files"]
    return report
