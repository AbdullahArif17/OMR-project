from __future__ import annotations

import csv
import io
import uuid
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import AuthorizedUser
from database import get_db
from models import AnswerKey
from schemas import APIResponse, AnswerKeyData, ManualAnswerKeyRequest
from services.data_access import (
    get_exam_or_404,
    replace_answer_key,
    validate_complete_answer_key,
)
from services.file_processing import (
    IMAGE_SUFFIXES,
    PDF_SUFFIXES,
    discard_upload,
    normalize_upload,
    processing_workspace,
    read_limited_upload,
    store_upload,
)
from services.omr_engine import OMRProcessingError, detect_answers


router = APIRouter(prefix="/exams", tags=["answer keys"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def _response_data(exam_id: uuid.UUID, answers: dict[int, str]) -> dict[str, object]:
    return {"exam_id": exam_id, "answers": dict(sorted(answers.items()))}


@router.post(
    "/{exam_id}/answer-key/manual",
    response_model=APIResponse[AnswerKeyData],
)
def save_manual_answer_key(
    exam_id: uuid.UUID,
    payload: ManualAnswerKeyRequest,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    exam = get_exam_or_404(db, exam_id, user)
    answers = validate_complete_answer_key(exam, payload.answers)
    replace_answer_key(db, exam, answers)
    return {
        "success": True,
        "data": _response_data(exam.id, answers),
        "message": "Answer key saved",
    }


@router.post(
    "/{exam_id}/answer-key/csv",
    response_model=APIResponse[AnswerKeyData],
)
async def save_csv_answer_key(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
    file: UploadFile = File(...),
) -> dict[str, object]:
    exam = get_exam_or_404(db, exam_id, user)
    raw_csv = await read_limited_upload(file, allowed_suffixes=frozenset({".csv"}))
    try:
        csv_text = raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="CSV file must use UTF-8 encoding"
        ) from exc

    reader = csv.DictReader(io.StringIO(csv_text, newline=""))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file has no header row")
    normalized_headers = {
        header.strip().lower(): header for header in reader.fieldnames if header
    }
    if "question" not in normalized_headers or "answer" not in normalized_headers:
        raise HTTPException(
            status_code=400,
            detail="CSV headers must include question and answer",
        )

    answers: dict[int, str] = {}
    for row_number, row in enumerate(reader, start=2):
        if row.get(None):
            raise HTTPException(
                status_code=400,
                detail=f"CSV row {row_number} contains unexpected extra columns",
            )
        raw_question = (row.get(normalized_headers["question"]) or "").strip()
        raw_answer = (row.get(normalized_headers["answer"]) or "").strip()
        if not raw_question and not raw_answer:
            continue
        try:
            question = int(raw_question)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"CSV row {row_number} has an invalid question number",
            ) from exc
        if question in answers:
            raise HTTPException(
                status_code=400,
                detail=f"CSV contains duplicate question {question}",
            )
        answers[question] = raw_answer

    validated_answers = validate_complete_answer_key(exam, answers)
    replace_answer_key(db, exam, validated_answers)
    return {
        "success": True,
        "data": _response_data(exam.id, validated_answers),
        "message": "CSV answer key saved",
    }


@router.post(
    "/{exam_id}/answer-key/scan",
    response_model=APIResponse[AnswerKeyData],
)
async def save_scanned_answer_key(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
    file: UploadFile = File(...),
) -> dict[str, object]:
    exam = get_exam_or_404(db, exam_id, user)
    stored = await store_upload(
        file,
        category="answer-keys",
        allowed_suffixes=IMAGE_SUFFIXES | PDF_SUFFIXES,
    )
    try:
        with processing_workspace() as workspace:
            sheets = await run_in_threadpool(
                partial(
                    normalize_upload,
                    stored,
                    workspace=workspace,
                    allow_zip=False,
                    max_sheets=1,
                )
            )
            if len(sheets) != 1:
                raise HTTPException(
                    status_code=422,
                    detail="A master answer key upload must contain exactly one image or PDF page",
                )
            try:
                detected = await run_in_threadpool(
                    detect_answers,
                    sheets[0].path,
                    exam.total_questions,
                    exam.options_per_question,
                )
            except OMRProcessingError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            answers = validate_complete_answer_key(exam, detected.answers)
            replace_answer_key(db, exam, answers)
    finally:
        discard_upload(stored)
    return {
        "success": True,
        "data": _response_data(exam.id, answers),
        "message": "Scanned answer key saved",
    }


@router.get(
    "/{exam_id}/answer-key",
    response_model=APIResponse[AnswerKeyData],
)
def get_answer_key(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
) -> dict[str, object]:
    exam = get_exam_or_404(db, exam_id, user)
    rows = db.scalars(
        select(AnswerKey)
        .where(AnswerKey.exam_id == exam.id)
        .order_by(AnswerKey.question_number)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Answer key not found")
    answers = {row.question_number: row.correct_answer for row in rows}
    return {
        "success": True,
        "data": _response_data(exam.id, answers),
        "message": "Answer key retrieved",
    }
