from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

from config import Settings, settings
from database import SessionLocal
from models import Result, ScanBatch


logger = logging.getLogger("omr_api.storage")
GENERATED_SCAN_NAME = re.compile(r"^[0-9a-f]{32}\.(?:jpe?g|png|pdf|zip)$")
PROCESSING_JOB_NAME = re.compile(r"^job-[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class StorageMaintenanceReport:
    workspaces_deleted: int = 0
    orphan_uploads_deleted: int = 0
    idempotency_records_deleted: int = 0


def _is_older_than(path: Path, cutoff: datetime) -> bool:
    modified_at = datetime.fromtimestamp(path.lstat().st_mtime, tz=timezone.utc)
    return modified_at < cutoff


def _remove_stale_workspaces(processing_root: Path, cutoff: datetime) -> int:
    if not processing_root.is_dir():
        return 0
    deleted = 0
    for candidate in processing_root.iterdir():
        if not PROCESSING_JOB_NAME.fullmatch(candidate.name):
            continue
        try:
            if not _is_older_than(candidate, cutoff):
                continue
            if candidate.is_symlink():
                candidate.unlink()
            elif candidate.is_dir():
                shutil.rmtree(candidate)
            else:
                continue
            deleted += 1
        except OSError:
            logger.exception("Unable to remove stale processing workspace %s", candidate)
    return deleted


def _remove_orphan_uploads(
    scans_root: Path,
    *,
    upload_root: Path,
    referenced_paths: set[str],
    cutoff: datetime,
) -> int:
    if not scans_root.is_dir():
        return 0
    deleted = 0
    for candidate in scans_root.iterdir():
        if not GENERATED_SCAN_NAME.fullmatch(candidate.name):
            continue
        relative_path = candidate.relative_to(upload_root).as_posix()
        if relative_path in referenced_paths:
            continue
        try:
            if not _is_older_than(candidate, cutoff):
                continue
            if candidate.is_file() or candidate.is_symlink():
                candidate.unlink()
                deleted += 1
        except OSError:
            logger.exception("Unable to remove orphaned scan upload %s", candidate)
    return deleted


def run_storage_maintenance(
    *,
    configured: Settings = settings,
    now: datetime | None = None,
) -> StorageMaintenanceReport:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    storage_cutoff = current_time - timedelta(
        hours=configured.storage_cleanup_grace_hours
    )
    idempotency_cutoff = current_time - timedelta(
        hours=configured.idempotency_retention_hours
    )

    with SessionLocal() as db:
        referenced_paths = {
            path
            for path in db.scalars(
                select(Result.source_file)
                .where(Result.source_file.is_not(None))
                .distinct()
            ).all()
            if path
        }
        deletion = db.execute(
            delete(ScanBatch).where(ScanBatch.created_at < idempotency_cutoff)
        )
        idempotency_deleted = max(deletion.rowcount or 0, 0)
        db.commit()

    upload_root = configured.upload_dir.resolve()
    processing_root = upload_root / ".processing"
    scans_root = upload_root / "scans"
    upload_root.mkdir(parents=True, exist_ok=True)
    workspaces_deleted = _remove_stale_workspaces(
        processing_root, storage_cutoff
    )
    orphan_uploads_deleted = _remove_orphan_uploads(
        scans_root,
        upload_root=upload_root,
        referenced_paths=referenced_paths,
        cutoff=storage_cutoff,
    )
    report = StorageMaintenanceReport(
        workspaces_deleted=workspaces_deleted,
        orphan_uploads_deleted=orphan_uploads_deleted,
        idempotency_records_deleted=idempotency_deleted,
    )
    logger.info(
        "Storage maintenance complete workspaces=%d orphan_uploads=%d idempotency_records=%d",
        report.workspaces_deleted,
        report.orphan_uploads_deleted,
        report.idempotency_records_deleted,
    )
    return report


if __name__ == "__main__":
    maintenance_report = run_storage_maintenance()
    print(
        "Storage maintenance complete: "
        f"{maintenance_report.workspaces_deleted} workspace(s), "
        f"{maintenance_report.orphan_uploads_deleted} orphan upload(s), and "
        f"{maintenance_report.idempotency_records_deleted} idempotency record(s) removed"
    )
