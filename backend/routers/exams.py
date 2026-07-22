from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import AuthorizedUser
from database import get_db
from models import Exam, Result
from schemas import APIResponse, DeleteData, ExamCreate, ExamRead
from services.data_access import get_exam_or_404
from services.file_processing import discard_scan_uploads


router = APIRouter(prefix="/exams", tags=["exams"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=APIResponse[ExamRead],
    status_code=status.HTTP_201_CREATED,
)
def create_exam(
    payload: ExamCreate,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    exam = Exam(
        name=payload.name,
        subject=payload.subject,
        total_questions=payload.total_questions,
        options_per_question=payload.options_per_question,
    )
    try:
        db.add(exam)
        db.commit()
        db.refresh(exam)
    except Exception:
        db.rollback()
        raise
    return {"success": True, "data": exam, "message": "Exam created"}


@router.get("", response_model=APIResponse[list[ExamRead]])
def list_exams(
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    statement = select(Exam)
    exams = db.scalars(statement.order_by(Exam.created_at.desc())).all()
    return {"success": True, "data": exams, "message": "Exams retrieved"}


@router.get("/{exam_id}", response_model=APIResponse[ExamRead])
def get_exam(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    exam = get_exam_or_404(db, exam_id, user)
    return {"success": True, "data": exam, "message": "Exam retrieved"}


@router.delete("/{exam_id}", response_model=APIResponse[DeleteData])
def delete_exam(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    exam = get_exam_or_404(db, exam_id, user)
    source_files = {
        source_file
        for source_file in db.scalars(
            select(Result.source_file).where(Result.exam_id == exam.id)
        ).all()
        if source_file
    }
    try:
        db.delete(exam)
        db.commit()
    except Exception:
        db.rollback()
        raise
    discard_scan_uploads(source_files)
    return {
        "success": True,
        "data": {"id": exam_id, "deleted": True},
        "message": "Exam deleted",
    }
