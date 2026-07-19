from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from config import settings
from database import SessionLocal
from models import Exam, Result, ScanBatch
from services.storage_maintenance import run_storage_maintenance


def test_storage_maintenance_removes_only_stale_unreferenced_data(client) -> None:
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=settings.storage_cleanup_grace_hours + 1)
    scans_root = settings.upload_dir / "scans"
    processing_root = settings.upload_dir / ".processing"
    scans_root.mkdir(parents=True, exist_ok=True)
    processing_root.mkdir(parents=True, exist_ok=True)

    referenced_name = f"{uuid.uuid4().hex}.png"
    orphan_name = f"{uuid.uuid4().hex}.png"
    recent_name = f"{uuid.uuid4().hex}.png"
    referenced_path = scans_root / referenced_name
    orphan_path = scans_root / orphan_name
    recent_path = scans_root / recent_name
    referenced_path.write_bytes(b"referenced")
    orphan_path.write_bytes(b"orphan")
    recent_path.write_bytes(b"recent")
    os.utime(referenced_path, (old_time.timestamp(), old_time.timestamp()))
    os.utime(orphan_path, (old_time.timestamp(), old_time.timestamp()))

    stale_workspace = processing_root / f"job-{uuid.uuid4().hex}"
    stale_workspace.mkdir()
    (stale_workspace / "render.png").write_bytes(b"temporary")
    os.utime(stale_workspace, (old_time.timestamp(), old_time.timestamp()))

    old_batch_id = uuid.uuid4()
    with SessionLocal() as db:
        exam = Exam(
            name="Retention exam",
            subject="Operations",
            total_questions=10,
            options_per_question=4,
            created_by="test-user",
        )
        db.add(exam)
        db.flush()
        db.add(
            Result(
                exam_id=exam.id,
                score=0,
                total=10,
                percentage=0,
                answers={},
                breakdown={},
                source_file=f"scans/{referenced_name}",
            )
        )
        db.add(
            ScanBatch(
                id=old_batch_id,
                exam_id=exam.id,
                idempotency_key="old-retry-key",
                response_data={"results": []},
                response_message="Old response",
                created_at=now
                - timedelta(hours=settings.idempotency_retention_hours + 1),
            )
        )
        db.commit()

    report = run_storage_maintenance(now=now)

    assert referenced_path.exists()
    assert recent_path.exists()
    assert not orphan_path.exists()
    assert not stale_workspace.exists()
    assert report.orphan_uploads_deleted == 1
    assert report.workspaces_deleted == 1
    assert report.idempotency_records_deleted == 1
    with SessionLocal() as db:
        assert db.get(ScanBatch, old_batch_id) is None
