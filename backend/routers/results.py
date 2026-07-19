from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth import AuthorizedUser
from database import get_db
from models import Result
from schemas import APIResponse, ResultDetail, ResultListData, ResultRead
from services.data_access import ensure_exam_access, get_exam_or_404


router = APIRouter(tags=["results"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def _result_query_for_exam(exam_id: uuid.UUID):
    return (
        select(Result)
        .where(Result.exam_id == exam_id)
        .options(selectinload(Result.student))
        .order_by(Result.scanned_at.desc())
    )


def _summary(results: list[Result]) -> dict[str, float | int]:
    if not results:
        return {
            "average_score": 0.0,
            "highest_score": 0,
            "lowest_score": 0,
            "pass_rate": 0.0,
            "total_scans": 0,
        }
    scores = [result.score for result in results]
    passed = sum(result.percentage >= 60 for result in results)
    return {
        "average_score": round(sum(scores) / len(scores), 2),
        "highest_score": max(scores),
        "lowest_score": min(scores),
        "pass_rate": round((passed / len(results)) * 100, 2),
        "total_scans": len(results),
    }


def _grade(percentage: float) -> str:
    if percentage >= 90:
        return "A"
    if percentage >= 80:
        return "B"
    if percentage >= 60:
        return "C"
    if percentage >= 40:
        return "D"
    return "F"


def _csv_safe(value: object | None) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@router.get(
    "/exams/{exam_id}/results",
    response_model=APIResponse[ResultListData],
)
def list_exam_results(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    exam = get_exam_or_404(db, exam_id, user)
    results = list(db.scalars(_result_query_for_exam(exam.id)).all())
    data = {
        "results": [ResultRead.model_validate(result) for result in results],
        "summary": _summary(results),
    }
    return {"success": True, "data": data, "message": "Results retrieved"}


@router.get("/exams/{exam_id}/results/export")
def export_exam_results(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> StreamingResponse:
    exam = get_exam_or_404(db, exam_id, user)
    results = list(db.scalars(_result_query_for_exam(exam.id)).all())
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Roll No",
            "Name",
            "Class",
            "Score",
            "Total",
            "Percentage",
            "Grade",
            "Source File",
            "Scanned At",
        ]
    )
    for result in results:
        scanned_at = result.scanned_at
        if scanned_at.tzinfo is None:
            scanned_at = scanned_at.replace(tzinfo=timezone.utc)
        writer.writerow(
            [
                _csv_safe(result.student_roll_number),
                _csv_safe(result.student_name),
                _csv_safe(result.student_class_name),
                result.score,
                result.total,
                f"{result.percentage:.2f}",
                _grade(result.percentage),
                _csv_safe(result.filename),
                scanned_at.isoformat(),
            ]
        )
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", exam.name).strip("-._") or "exam"
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}-results.csv"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.get("/results/{result_id}", response_model=APIResponse[ResultDetail])
def get_result(
    result_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    result = db.scalar(
        select(Result)
        .where(Result.id == result_id)
        .options(selectinload(Result.student), selectinload(Result.exam))
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    ensure_exam_access(result.exam, user)
    return {
        "success": True,
        "data": ResultDetail.model_validate(result),
        "message": "Result retrieved",
    }
