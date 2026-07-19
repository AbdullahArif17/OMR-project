from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from schemas import ExamRead, ResultRead


def test_response_timestamps_attach_utc_to_naive_sqlite_values() -> None:
    naive = datetime(2026, 7, 19, 12, 30)
    exam = ExamRead(
        id=uuid.uuid4(),
        name="Timezone Exam",
        subject=None,
        total_questions=10,
        options_per_question=4,
        created_by="teacher",
        created_at=naive,
    )
    result = ResultRead(
        id=uuid.uuid4(),
        exam_id=exam.id,
        student=None,
        score=10,
        total=10,
        percentage=100,
        answers={1: "A"},
        breakdown={1: {"student": "A", "correct": "A", "result": True}},
        source_file=None,
        scanned_at=naive,
    )

    assert exam.created_at.tzinfo is timezone.utc
    assert result.scanned_at.tzinfo is timezone.utc
    assert '"created_at":"2026-07-19T12:30:00Z"' in exam.model_dump_json()
    assert '"scanned_at":"2026-07-19T12:30:00Z"' in result.model_dump_json()


def test_response_timestamps_preserve_aware_postgres_values() -> None:
    source_timezone = timezone(timedelta(hours=5, minutes=30))
    source = datetime(2026, 7, 19, 12, 30, tzinfo=source_timezone)
    exam = ExamRead(
        id=uuid.uuid4(),
        name="Aware Exam",
        subject=None,
        total_questions=10,
        options_per_question=4,
        created_by="teacher",
        created_at=source,
    )

    assert exam.created_at.utcoffset() == timedelta(hours=5, minutes=30)
