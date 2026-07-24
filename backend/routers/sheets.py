"""Router for generating and downloading printable OMR bubble sheets."""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import AuthorizedUser
from database import get_db
from services.data_access import get_exam_or_404
from services.sheet_generator import generate_omr_sheet


router = APIRouter(tags=["sheets"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/exams/{exam_id}/sheet")
def download_exam_sheet(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
    include_name: Annotated[bool, Query(description="Include student name grid")] = True,
    include_roll: Annotated[bool, Query(description="Include roll number grid")] = True,
) -> Response:
    """Generate and download a printable OMR sheet for an exam."""
    exam = get_exam_or_404(db, exam_id, user)

    sheet_bytes = generate_omr_sheet(
        total_questions=exam.total_questions,
        options_per_question=exam.options_per_question,
        exam_title=exam.name.upper(),
        include_name_grid=include_name,
        include_roll_grid=include_roll,
    )

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", exam.name).strip("-._") or "exam"

    return Response(
        content=sheet_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}-omr-sheet.png"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/sheets/preview")
def preview_sheet(
    user: AuthorizedUser,
    total_questions: Annotated[int, Query(ge=10, le=100)] = 20,
    options_per_question: Annotated[int, Query()] = 4,
    title: Annotated[str, Query(max_length=60)] = "OMR EXAMINATION SHEET",
    include_name: Annotated[bool, Query()] = True,
    include_roll: Annotated[bool, Query()] = True,
) -> Response:
    """Generate a preview OMR sheet without needing an existing exam."""
    if options_per_question not in (4, 5):
        raise HTTPException(status_code=422, detail="options_per_question must be 4 or 5")

    sheet_bytes = generate_omr_sheet(
        total_questions=total_questions,
        options_per_question=options_per_question,
        exam_title=title.upper(),
        include_name_grid=include_name,
        include_roll_grid=include_roll,
    )

    return Response(
        content=sheet_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": 'inline; filename="omr-sheet-preview.png"',
            "Cache-Control": "no-store",
        },
    )
