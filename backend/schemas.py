from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


T = TypeVar("T")


def _attach_utc_to_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: str


class ExamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    total_questions: int = Field(ge=10, le=100)
    options_per_question: int = Field(default=4)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Exam name cannot be blank")
        return value

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("options_per_question")
    @classmethod
    def validate_options(cls, value: int) -> int:
        if value not in {4, 5}:
            raise ValueError("options_per_question must be either 4 or 5")
        return value


class ExamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    subject: str | None
    total_questions: int
    options_per_question: int
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _attach_utc_to_naive(value)


class ManualAnswerKeyRequest(BaseModel):
    answers: dict[int, str]


class AnswerKeyData(BaseModel):
    exam_id: uuid.UUID
    answers: dict[int, str]


class StudentMetadata(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    roll_number: str | None = Field(default=None, max_length=50)
    class_name: str | None = Field(default=None, max_length=50)

    @field_validator("name", "roll_number", "class_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    roll_number: str | None
    class_name: str | None


class BreakdownItem(BaseModel):
    student: str | None
    correct: str
    result: bool


class ResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    student: StudentRead | None = Field(validation_alias="student_data")
    score: int
    total: int
    percentage: float
    answers: dict[int, str]
    breakdown: dict[int, BreakdownItem]
    source_file: str | None
    scanned_at: datetime
    filename: str | None = None

    @field_validator("scanned_at")
    @classmethod
    def normalize_scanned_at(cls, value: datetime) -> datetime:
        return _attach_utc_to_naive(value)


class ResultDetail(ResultRead):
    exam: ExamRead


class ResultSummary(BaseModel):
    average_score: float
    highest_score: int
    lowest_score: int
    pass_rate: float
    total_scans: int


class ResultListData(BaseModel):
    results: list[ResultRead]
    summary: ResultSummary


class ScanError(BaseModel):
    filename: str
    message: str
    stage: Literal[
        "upload",
        "normalization",
        "detection",
        "database",
        "processing",
        "idempotency",
    ] = "processing"
    status_code: int = Field(default=422, ge=400, le=599)
    retryable: bool = False


class ScanBatchData(BaseModel):
    results: list[ResultRead]
    errors: list[ScanError]
    processed_count: int
    failed_count: int
    status: Literal["completed", "partial", "failed"] = "completed"


class DeleteData(BaseModel):
    id: uuid.UUID
    deleted: bool


class ErrorResponse(BaseModel):
    success: bool = False
    data: Any = None
    message: str


class AdminLoginRequest(BaseModel):
    # The admin console authenticates with a shared password only; no email.
    password: str = Field(min_length=1, max_length=1024)


class AdminUserRead(BaseModel):
    id: uuid.UUID
    email: str = "admin@markwise"
    name: str = "Administrator"
    role: str = "admin"
    is_active: bool = True
    created_at: datetime


class TokenData(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: AdminUserRead
