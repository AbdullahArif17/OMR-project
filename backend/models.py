from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


json_type = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    """An account that can sign in and own exams/results.

    ``id`` is what lands in ``created_by``/``owner_subject`` on the other
    tables, replacing the Supabase ``sub`` claim used previously.  Accounts are
    created by an admin (or the startup bootstrap), never by public signup.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('teacher', 'admin')", name="role_values"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="teacher", server_default="teacher"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class RefreshToken(Base):
    """A hashed, revocable refresh token for one login session.

    Only the SHA-256 of the opaque token is stored, so a database leak cannot
    be replayed.  Rotation revokes the previous row and inserts a new one; a
    reused (already-rotated) token is treated as compromise.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        CheckConstraint(
            "total_questions BETWEEN 10 AND 100",
            name="total_questions_range",
        ),
        CheckConstraint(
            "options_per_question IN (4, 5)",
            name="options_per_question_values",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(100))
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    options_per_question: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, server_default="4"
    )
    created_by: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    answer_keys: Mapped[list[AnswerKey]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", passive_deletes=True
    )
    results: Mapped[list[Result]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", passive_deletes=True
    )


class AnswerKey(Base):
    __tablename__ = "answer_keys"
    __table_args__ = (
        UniqueConstraint("exam_id", "question_number", name="exam_question"),
        CheckConstraint("question_number >= 1", name="question_number_positive"),
        CheckConstraint(
            "length(correct_answer) = 1", name="correct_answer_one_character"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(1), nullable=False)

    exam: Mapped[Exam] = relationship(back_populates="answer_keys")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("created_by", "roll_number", name="owner_roll_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    roll_number: Mapped[str | None] = mapped_column(String(50), index=True)
    class_name: Mapped[str | None] = mapped_column("class", String(50))

    results: Mapped[list[Result]] = relationship(back_populates="student")


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (
        Index("ix_results_exam_scanned", "exam_id", "scanned_at"),
        CheckConstraint("score >= 0", name="score_nonnegative"),
        CheckConstraint("total > 0", name="total_positive"),
        CheckConstraint("score <= total", name="score_not_above_total"),
        CheckConstraint(
            "percentage >= 0 AND percentage <= 100",
            name="percentage_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exams.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str | None] = mapped_column(String(500))
    student_name: Mapped[str | None] = mapped_column(String(255))
    student_roll_number: Mapped[str | None] = mapped_column(String(50))
    student_class_name: Mapped[str | None] = mapped_column(String(50))
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    exam: Mapped[Exam] = relationship(back_populates="results")
    student: Mapped[Student | None] = relationship(back_populates="results")

    @property
    def student_data(self) -> dict[str, Any] | None:
        if self.student_id is None:
            return None
        return {
            "id": self.student_id,
            "name": self.student_name,
            "roll_number": self.student_roll_number,
            "class_name": self.student_class_name,
        }


class ScanBatch(Base):
    """A committed scan response keyed by a client-provided retry token.

    The record is inserted in the same transaction as its results.  That makes
    an ``Idempotency-Key`` retry either observe the complete original batch or
    no batch at all; a partially committed response cannot be cached.
    """

    __tablename__ = "scan_batches"
    __table_args__ = (
        UniqueConstraint(
            "exam_id",
            "idempotency_key",
            name="scan_batch_exam_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exams.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 of the batch request payload (files + metadata).  Lets a reused
    # Idempotency-Key be rejected when the request body changed, instead of
    # silently returning the original batch and dropping the new upload.
    request_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    response_data: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    response_message: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
