from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import AuthorizedUser
from config import settings
from database import get_db
from errors import ApplicationError
from models import Exam, Result, ScanBatch
from schemas import APIResponse, ResultRead, ScanBatchData, StudentMetadata
from services.data_access import (
    get_exam_or_404,
    load_answer_key,
    resolve_student,
)
from services.file_processing import (
    FileProcessingError,
    StoredUpload,
    discard_upload,
    normalize_upload,
    processing_workspace,
    store_upload,
)
from services.omr_engine import OMRProcessingError, detect_answers, grade_answers


router = APIRouter(prefix="/exams", tags=["scanner"])
DatabaseSession = Annotated[Session, Depends(get_db)]
logger = logging.getLogger("omr_api.scanner")


@dataclass(frozen=True, slots=True)
class CachedScanResponse:
    data: dict[str, object]
    message: str


@dataclass(frozen=True, slots=True)
class ScanReadContext:
    exam_id: uuid.UUID
    total_questions: int
    options_per_question: int
    owner_subject: str
    answer_key: dict[int, str]
    cached_response: CachedScanResponse | None


@dataclass(frozen=True, slots=True)
class PendingScanResult:
    student_name: str | None
    student_roll_number: str | None
    student_class_name: str | None
    score: int
    total: int
    percentage: float
    answers: dict[str, str]
    breakdown: dict[str, object]
    source_file: str
    filename: str


@dataclass(frozen=True, slots=True)
class PersistedScanResponse:
    data: dict[str, object]
    message: str
    committed_new_results: bool


def _cached_scan_response(
    db: Session, exam_id: uuid.UUID, idempotency_key: str
) -> CachedScanResponse | None:
    batch = db.scalar(
        select(ScanBatch).where(
            ScanBatch.exam_id == exam_id,
            ScanBatch.idempotency_key == idempotency_key,
        )
    )
    if batch is None:
        return None
    return CachedScanResponse(
        data=dict(batch.response_data),
        message=batch.response_message,
    )


def _load_scan_context(
    db: Session,
    exam_id: uuid.UUID,
    user: AuthorizedUser,
    idempotency_key: str | None,
) -> ScanReadContext:
    try:
        exam = get_exam_or_404(db, exam_id, user)
        answer_key = load_answer_key(db, exam)
        cached_response = (
            _cached_scan_response(db, exam.id, idempotency_key)
            if idempotency_key is not None
            else None
        )
        return ScanReadContext(
            exam_id=exam.id,
            total_questions=exam.total_questions,
            options_per_question=exam.options_per_question,
            owner_subject=exam.created_by or user.subject,
            answer_key=answer_key,
            cached_response=cached_response,
        )
    finally:
        # All data that leaves this helper is plain Python data.  Ending the
        # read transaction here returns the pooled Neon connection before any
        # upload conversion or OMR work begins.
        db.rollback()


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Idempotency-Key cannot be blank")
    if len(normalized) > 255:
        raise HTTPException(
            status_code=422, detail="Idempotency-Key cannot exceed 255 characters"
        )
    if any(ord(character) < 33 or ord(character) > 126 for character in normalized):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must contain printable ASCII without whitespace",
        )
    return normalized


def _persist_pending_result(
    db: Session,
    *,
    exam_id: uuid.UUID,
    owner_subject: str,
    pending: PendingScanResult,
) -> Result:
    metadata = StudentMetadata(
        name=pending.student_name,
        roll_number=pending.student_roll_number,
        class_name=pending.student_class_name,
    )
    student = resolve_student(db, metadata, owner_subject=owner_subject)
    result = Result(
        exam_id=exam_id,
        student_id=student.id,
        student=student,
        score=pending.score,
        total=pending.total,
        percentage=pending.percentage,
        answers=dict(pending.answers),
        breakdown=dict(pending.breakdown),
        source_file=pending.source_file,
        filename=pending.filename,
        student_name=student.name,
        student_roll_number=student.roll_number,
        student_class_name=student.class_name,
    )
    db.add(result)
    db.flush()
    db.refresh(result)
    return result


def _make_pending_result(
    *,
    metadata: StudentMetadata,
    detected_answers: Mapping[int, str],
    grading: Mapping[str, object],
    source_file: str,
    filename: str,
) -> PendingScanResult:
    return PendingScanResult(
        student_name=metadata.name,
        student_roll_number=metadata.roll_number,
        student_class_name=metadata.class_name,
        score=int(grading["score"]),
        total=int(grading["total"]),
        percentage=float(grading["percentage"]),
        answers={str(key): value for key, value in detected_answers.items()},
        breakdown={
            str(key): value
            for key, value in dict(grading["breakdown"]).items()  # type: ignore[arg-type]
        },
        source_file=source_file,
        filename=filename,
    )


def _cache_scan_batch(
    db: Session,
    *,
    exam_id: uuid.UUID,
    idempotency_key: str,
    response_data: dict[str, object],
    response_message: str,
) -> None:
    db.add(
        ScanBatch(
            exam_id=exam_id,
            idempotency_key=idempotency_key,
            response_data=response_data,
            response_message=response_message,
        )
    )


def _commit_transaction(db: Session) -> None:
    db.commit()


def _rollback_transaction(db: Session) -> None:
    db.rollback()


def _discard_uploads_safely(uploads: list[StoredUpload]) -> None:
    seen: set[Path] = set()
    for stored in uploads:
        if stored.path in seen:
            continue
        seen.add(stored.path)
        try:
            discard_upload(stored)
        except OSError:
            logger.exception("Unable to remove failed scan upload %s", stored.path)


async def _close_uploads(uploads: list[UploadFile]) -> None:
    for upload in uploads:
        try:
            await upload.close()
        except Exception:
            logger.exception("Unable to close scan upload %r", upload.filename)


def _scan_error(
    *,
    filename: str,
    message: str,
    stage: str,
    status_code: int,
    retryable: bool = False,
) -> dict[str, object]:
    return {
        "filename": filename,
        "message": message,
        "stage": stage,
        "status_code": status_code,
        "retryable": retryable,
    }


def _batch_data(
    results: list[ResultRead],
    errors: list[dict[str, object]],
    *,
    status: str,
) -> dict[str, object]:
    return ScanBatchData(
        results=results,
        errors=errors,
        processed_count=len(results),
        failed_count=len(errors),
        status=status,
    ).model_dump(mode="json")


def _exam_changed_error(
    errors: list[dict[str, object]], message: str
) -> ApplicationError:
    return ApplicationError(
        message,
        status_code=409,
        data=_batch_data(
            [],
            [
                *errors,
                _scan_error(
                    filename="batch",
                    message=message,
                    stage="database",
                    status_code=409,
                    retryable=True,
                ),
            ],
            status="failed",
        ),
    )


def _persist_scan_batch(
    db: Session,
    *,
    context: ScanReadContext,
    user: AuthorizedUser,
    pending_results: list[PendingScanResult],
    errors: list[dict[str, object]],
    idempotency_key: str | None,
) -> PersistedScanResponse:
    current_filename = "batch"
    try:
        if idempotency_key is not None:
            cached_response = _cached_scan_response(
                db, context.exam_id, idempotency_key
            )
            if cached_response is not None:
                db.rollback()
                return PersistedScanResponse(
                    data=cached_response.data,
                    message=cached_response.message,
                    committed_new_results=False,
                )

        exam = get_exam_or_404(db, context.exam_id, user)
        if (
            exam.total_questions != context.total_questions
            or exam.options_per_question != context.options_per_question
            or (exam.created_by or user.subject) != context.owner_subject
        ):
            raise _exam_changed_error(
                errors,
                "The exam changed while sheets were processing; retry the batch",
            )
        if load_answer_key(db, exam) != context.answer_key:
            raise _exam_changed_error(
                errors,
                "The answer key changed while sheets were processing; retry the batch",
            )

        persisted_results: list[ResultRead] = []
        for pending in pending_results:
            current_filename = pending.filename
            result = _persist_pending_result(
                db,
                exam_id=context.exam_id,
                owner_subject=context.owner_subject,
                pending=pending,
            )
            persisted_results.append(ResultRead.model_validate(result))

        status = "partial" if errors else "completed"
        response_data = _batch_data(persisted_results, errors, status=status)
        message = (
            f"{len(persisted_results)} sheet(s) processed successfully"
            if not errors
            else (
                f"{len(persisted_results)} sheet(s) processed; "
                f"{len(errors)} file(s) or sheet(s) failed"
            )
        )
        if idempotency_key is not None:
            _cache_scan_batch(
                db,
                exam_id=context.exam_id,
                idempotency_key=idempotency_key,
                response_data=response_data,
                response_message=message,
            )
        _commit_transaction(db)
        return PersistedScanResponse(
            data=response_data,
            message=message,
            committed_new_results=True,
        )
    except IntegrityError as exc:
        db.rollback()
        if idempotency_key is not None:
            try:
                cached_response = _cached_scan_response(
                    db, context.exam_id, idempotency_key
                )
            finally:
                # A retry lookup is also a transaction and must not pin a
                # connection after this helper returns.
                db.rollback()
            if cached_response is not None:
                return PersistedScanResponse(
                    data=cached_response.data,
                    message=cached_response.message,
                    committed_new_results=False,
                )
        database_error = _scan_error(
            filename=current_filename,
            message="Student metadata conflicts with an existing roll number",
            stage="database",
            status_code=409,
        )
        raise ApplicationError(
            "The scan batch could not be saved; no results were committed",
            status_code=409,
            data=_batch_data([], [*errors, database_error], status="failed"),
        ) from exc
    except Exception:
        db.rollback()
        raise


def _known_upload_size(upload: UploadFile) -> int | None:
    size = getattr(upload, "size", None)
    return size if isinstance(size, int) and size >= 0 else None


def _stored_upload_size(stored: StoredUpload) -> int:
    return stored.path.stat().st_size


def _metadata_item(value: Any, index: int) -> StudentMetadata:
    if value is None:
        return StudentMetadata()
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=422,
            detail=f"Metadata item {index + 1} must be an object",
        )
    normalized = dict(value)
    if "class_name" not in normalized and "class" in normalized:
        normalized["class_name"] = normalized.pop("class")
    try:
        return StudentMetadata.model_validate(normalized)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        message = first_error.get("msg", "invalid metadata")
        raise HTTPException(
            status_code=422,
            detail=f"Metadata item {index + 1} is invalid: {message}",
        ) from exc


def _parse_metadata_json(raw: str) -> list[StudentMetadata]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422, detail="metadata must be valid JSON"
        ) from exc
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=422, detail="metadata must be a JSON array"
        )
    return [_metadata_item(value, index) for index, value in enumerate(parsed)]


def _value_at(values: list[str] | None, index: int) -> str | None:
    if values is None or index >= len(values):
        return None
    return values[index]


def _build_top_level_metadata(
    upload_count: int,
    *,
    metadata: str | None,
    student_metadata: str | None,
    student_names: list[str] | None,
    roll_numbers: list[str] | None,
    classes: list[str] | None,
    class_names: list[str] | None,
) -> list[StudentMetadata]:
    raw_metadata = metadata if metadata is not None else student_metadata
    if raw_metadata is not None:
        items = _parse_metadata_json(raw_metadata)
        if len(items) > upload_count:
            raise HTTPException(
                status_code=422,
                detail="metadata contains more entries than uploaded files",
            )
        return items + [StudentMetadata() for _ in range(upload_count - len(items))]

    legacy_lengths = [
        len(values)
        for values in (student_names, roll_numbers, classes, class_names)
        if values is not None
    ]
    if legacy_lengths and max(legacy_lengths) > upload_count:
        raise HTTPException(
            status_code=422,
            detail="Student metadata fields contain more entries than uploaded files",
        )
    selected_classes = class_names if class_names is not None else classes
    return [
        StudentMetadata(
            name=_value_at(student_names, index),
            roll_number=_value_at(roll_numbers, index),
            class_name=_value_at(selected_classes, index),
        )
        for index in range(upload_count)
    ]


def _display_stem(filename: str) -> str:
    without_page = filename.split("#page-", 1)[0]
    archive_member = without_page.rsplit(":", 1)[-1]
    stem = Path(archive_member).stem.replace("_", " ").replace("-", " ").strip()
    return stem or "Scanned student"


def _suffix_roll_number(roll_number: str, sheet_number: int) -> str:
    suffix = f"-{sheet_number}"
    return roll_number[: 50 - len(suffix)] + suffix


def _metadata_for_expanded_sheet(
    base: StudentMetadata,
    *,
    filename: str,
    expanded_index: int,
) -> StudentMetadata:
    default_name = _display_stem(filename)
    if expanded_index == 0:
        return StudentMetadata(
            name=base.name or default_name,
            roll_number=base.roll_number,
            class_name=base.class_name,
        )
    sheet_number = expanded_index + 1
    base_name = base.name or default_name
    suffix = f" ({sheet_number})"
    return StudentMetadata(
        name=base_name[: 255 - len(suffix)] + suffix,
        roll_number=(
            _suffix_roll_number(base.roll_number, sheet_number)
            if base.roll_number
            else None
        ),
        class_name=base.class_name,
    )


@router.post("/{exam_id}/scan", response_model=APIResponse[ScanBatchData])
async def scan_student_sheets(
    exam_id: uuid.UUID,
    db: DatabaseSession,
    user: AuthorizedUser,
    files: Annotated[list[UploadFile] | None, File()] = None,
    file: Annotated[list[UploadFile] | None, File()] = None,
    metadata: Annotated[str | None, Form()] = None,
    student_metadata: Annotated[str | None, Form()] = None,
    student_names: Annotated[list[str] | None, Form()] = None,
    roll_numbers: Annotated[list[str] | None, Form()] = None,
    classes: Annotated[list[str] | None, Form()] = None,
    class_names: Annotated[list[str] | None, Form()] = None,
    idempotency_key_header: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> dict[str, object]:
    uploads = [*(files or []), *(file or [])]
    if not uploads:
        raise HTTPException(status_code=422, detail="At least one sheet file is required")
    if len(uploads) > settings.max_files_per_request:
        await _close_uploads(uploads)
        raise HTTPException(
            status_code=422,
            detail=f"A maximum of {settings.max_files_per_request} files is allowed",
        )

    known_batch_size = sum(_known_upload_size(upload) or 0 for upload in uploads)
    if known_batch_size > settings.max_batch_size_bytes:
        await _close_uploads(uploads)
        message = (
            f"The combined uploads exceed the {settings.max_batch_size_mb} MB "
            "batch limit"
        )
        raise ApplicationError(
            message,
            status_code=413,
            data=_batch_data(
                [],
                [
                    _scan_error(
                        filename="batch",
                        message=message,
                        stage="upload",
                        status_code=413,
                    )
                ],
                status="failed",
            ),
        )

    try:
        idempotency_key = _normalize_idempotency_key(idempotency_key_header)
        metadata_items = _build_top_level_metadata(
            len(uploads),
            metadata=metadata,
            student_metadata=student_metadata,
            student_names=student_names,
            roll_numbers=roll_numbers,
            classes=classes,
            class_names=class_names,
        )
        scan_context = await run_in_threadpool(
            _load_scan_context, db, exam_id, user, idempotency_key
        )
    except Exception:
        await _close_uploads(uploads)
        raise
    if scan_context.cached_response is not None:
        await _close_uploads(uploads)
        return {
            "success": True,
            "data": scan_context.cached_response.data,
            "message": scan_context.cached_response.message,
        }

    pending_results: list[PendingScanResult] = []
    errors: list[dict[str, object]] = []
    failure_statuses: set[int] = set()
    normalized_count = 0
    stored_byte_count = 0
    stored_uploads: list[StoredUpload] = []
    retained_source_files: set[str] = set()
    transaction_committed = False

    try:
        with processing_workspace() as workspace:
            for upload_index, upload in enumerate(uploads):
                upload_name = Path(
                    upload.filename or f"upload-{upload_index + 1}"
                ).name
                if normalized_count >= settings.max_files_per_request:
                    await upload.close()
                    errors.append(
                        _scan_error(
                            filename=upload_name,
                            message=(
                                "The expanded sheet limit has been reached; "
                                "this upload was not processed"
                            ),
                            stage="normalization",
                            status_code=422,
                        )
                    )
                    failure_statuses.add(422)
                    continue

                stored: StoredUpload | None = None
                try:
                    stored = await store_upload(upload, category="scans")
                    stored_uploads.append(stored)
                    stored_byte_count += await run_in_threadpool(
                        _stored_upload_size, stored
                    )
                    if stored_byte_count > settings.max_batch_size_bytes:
                        message = (
                            f"The combined uploads exceed the "
                            f"{settings.max_batch_size_mb} MB batch limit"
                        )
                        raise ApplicationError(
                            message,
                            status_code=413,
                            data=_batch_data(
                                [],
                                [
                                    *errors,
                                    _scan_error(
                                        filename=upload_name,
                                        message=message,
                                        stage="upload",
                                        status_code=413,
                                    ),
                                ],
                                status="failed",
                            ),
                        )
                    sheets = await run_in_threadpool(
                        partial(
                            normalize_upload,
                            stored,
                            workspace=workspace,
                            allow_zip=True,
                            max_sheets=(
                                settings.max_files_per_request - normalized_count
                            ),
                        )
                    )
                    if not sheets:
                        raise FileProcessingError(
                            "The upload did not contain any processable sheets",
                            status_code=422,
                        )
                    if normalized_count + len(sheets) > settings.max_files_per_request:
                        raise FileProcessingError(
                            f"Expanded uploads exceed the "
                            f"{settings.max_files_per_request} sheet limit",
                            status_code=422,
                        )
                except ApplicationError as exc:
                    if exc.status_code == 413 and exc.data is not None:
                        raise
                    errors.append(
                        _scan_error(
                            filename=upload_name,
                            message=exc.message,
                            stage="upload" if stored is None else "normalization",
                            status_code=exc.status_code,
                        )
                    )
                    failure_statuses.add(exc.status_code)
                    continue

                normalized_count += len(sheets)
                successful_for_upload = 0
                for expanded_index, sheet in enumerate(sheets):
                    display_filename = sheet.filename[:500]
                    sheet_metadata = _metadata_for_expanded_sheet(
                        metadata_items[upload_index],
                        filename=display_filename,
                        expanded_index=expanded_index,
                    )
                    try:
                        detected_answers = await run_in_threadpool(
                            detect_answers,
                            sheet.path,
                            scan_context.total_questions,
                            scan_context.options_per_question,
                        )
                        grading = grade_answers(
                            detected_answers, scan_context.answer_key
                        )
                    except OMRProcessingError as exc:
                        errors.append(
                            _scan_error(
                                filename=display_filename,
                                message=str(exc),
                                stage="detection",
                                status_code=422,
                            )
                        )
                        failure_statuses.add(422)
                        continue

                    successful_for_upload += 1
                    retained_source_files.add(sheet.source_relative_path)
                    pending_results.append(
                        _make_pending_result(
                            metadata=sheet_metadata,
                            detected_answers=detected_answers,
                            grading=grading,
                            source_file=sheet.source_relative_path,
                            filename=display_filename,
                        )
                    )

                if successful_for_upload == 0 and stored is not None:
                    await run_in_threadpool(_discard_uploads_safely, [stored])

        if not pending_results:
            response_data = _batch_data([], errors, status="failed")
            raise ApplicationError(
                "No sheets could be processed",
                status_code=(
                    next(iter(failure_statuses))
                    if len(failure_statuses) == 1
                    else 422
                ),
                data=response_data,
            )

        unretained_uploads = [
            stored
            for stored in stored_uploads
            if stored.relative_path not in retained_source_files
        ]
        if unretained_uploads:
            await run_in_threadpool(_discard_uploads_safely, unretained_uploads)

        persisted = await run_in_threadpool(
            partial(
                _persist_scan_batch,
                db,
                context=scan_context,
                user=user,
                pending_results=pending_results,
                errors=errors,
                idempotency_key=idempotency_key,
            )
        )
        transaction_committed = persisted.committed_new_results
        return {
            "success": True,
            "data": persisted.data,
            "message": persisted.message,
        }
    except Exception:
        if not transaction_committed:
            await run_in_threadpool(_rollback_transaction, db)
        raise
    finally:
        await _close_uploads(uploads)
        if not transaction_committed:
            await run_in_threadpool(_discard_uploads_safely, stored_uploads)
