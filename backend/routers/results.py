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
from schemas import APIResponse, ResultDetail, ResultListData, ResultRead, ResultUpdate, StudentMetadata
from services.data_access import ensure_exam_access, get_exam_or_404, load_answer_key, resolve_student
from services.omr_engine import grade_answers


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
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
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


@router.patch("/results/{result_id}", response_model=APIResponse[ResultDetail])
def update_result(
    result_id: uuid.UUID,
    payload: ResultUpdate,
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

    # Check if student metadata changed
    metadata_changed = False
    if payload.name is not None and payload.name != result.student_name:
        result.student_name = payload.name
        metadata_changed = True
    
    if payload.roll_number is not None and payload.roll_number != result.student_roll_number:
        result.student_roll_number = payload.roll_number
        metadata_changed = True

    if payload.class_name is not None and payload.class_name != result.student_class_name:
        result.student_class_name = payload.class_name
        metadata_changed = True

    if metadata_changed:
        # Re-resolve the student with the updated metadata
        metadata = StudentMetadata(
            name=result.student_name,
            roll_number=result.student_roll_number,
            class_name=result.student_class_name,
        )
        try:
            student = resolve_student(db, metadata)
            result.student_id = student.id
            result.student = student
        except Exception as e:
            # If resolve_student throws an IntegrityError or other error (e.g. duplicate roll number for a different student)
            # resolve_student actually handles duplicate roll numbers by reusing the existing student or updating it.
            # However, just in case, we bubble up a 409
            db.rollback()
            raise HTTPException(status_code=409, detail="Student metadata conflicts with an existing roll number") from e

    # --- answer override handling ---
    answers_changed = False
    if payload.answers is not None:
        exam = result.exam
        if exam is None:
            raise HTTPException(status_code=404, detail="Result's exam could not be loaded")

        # Validate that all provided answers are within the exam's option range
        valid_options = set("ABCDE"[: exam.options_per_question])
        for question, answer in payload.answers.items():
            if not (1 <= question <= exam.total_questions):
                raise HTTPException(
                    status_code=422,
                    detail=f"Question number {question} is out of range for this exam",
                )
            if answer not in valid_options:
                allowed = ", ".join(sorted(valid_options))
                raise HTTPException(
                    status_code=422,
                    detail=f"Question {question} has an invalid answer; must be one of: {allowed}",
                )

        try:
            answer_key = load_answer_key(db, exam)
        except HTTPException:
            raise HTTPException(
                status_code=422,
                detail="Cannot edit answers: no answer key is saved for this exam yet",
            )

        # Merge existing detected answers with overrides
        existing_answers: dict[int, str] = {}
        raw_breakdown = result.breakdown or {}
        if isinstance(raw_breakdown, dict):
            for raw_q, item in raw_breakdown.items():
                try:
                    q = int(raw_q)
                except (TypeError, ValueError):
                    continue
                student_answer = item.get("student") if isinstance(item, dict) else None
                if student_answer:
                    existing_answers[q] = str(student_answer).upper()

        final_answers: dict[int, str] = {
            q: existing_answers.get(q, "A") for q in range(1, exam.total_questions + 1)
        }
        final_answers.update(payload.answers)

        grading = grade_answers(final_answers, answer_key)
        result.answers = {str(q): a for q, a in final_answers.items()}
        result.breakdown = {str(k): v for k, v in grading["breakdown"].items()}
        result.score = int(grading["score"])
        result.total = int(grading["total"])
        result.percentage = float(grading["percentage"])
        answers_changed = True

    db.commit()
    db.refresh(result)

    return {
        "success": True,
        "data": ResultDetail.model_validate(result),
        "message": "Result updated successfully",
    }
