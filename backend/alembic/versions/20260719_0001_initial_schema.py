"""Create the initial Markwise schema.

Revision ID: 20260719_0001
Revises:
Create Date: 2026-07-19
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260719_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "exams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column(
            "options_per_question",
            sa.Integer(),
            server_default=sa.text("4"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "options_per_question IN (4, 5)",
            name="options_per_question_values",
        ),
        sa.CheckConstraint(
            "total_questions BETWEEN 10 AND 100",
            name="total_questions_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exams"),
    )
    op.create_index("ix_exams_created_by", "exams", ["created_by"], unique=False)

    op.create_table(
        "students",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("roll_number", sa.String(length=50), nullable=True),
        sa.Column("class", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_students"),
        sa.UniqueConstraint(
            "created_by", "roll_number", name="owner_roll_number"
        ),
    )
    op.create_index(
        "ix_students_created_by", "students", ["created_by"], unique=False
    )
    op.create_index(
        "ix_students_roll_number", "students", ["roll_number"], unique=False
    )

    op.create_table(
        "answer_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False),
        sa.Column("correct_answer", sa.String(length=1), nullable=False),
        sa.CheckConstraint(
            "length(correct_answer) = 1",
            name="correct_answer_one_character",
        ),
        sa.CheckConstraint(
            "question_number >= 1",
            name="question_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name="fk_answer_keys_exam_id_exams",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_answer_keys"),
        sa.UniqueConstraint("exam_id", "question_number", name="exam_question"),
    )
    op.create_index(
        "ix_answer_keys_exam_id", "answer_keys", ["exam_id"], unique=False
    )

    op.create_table(
        "results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("answers", JSON_DOCUMENT, nullable=False),
        sa.Column("breakdown", JSON_DOCUMENT, nullable=False),
        sa.Column("source_file", sa.String(length=500), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column("student_name", sa.String(length=255), nullable=True),
        sa.Column("student_roll_number", sa.String(length=50), nullable=True),
        sa.Column("student_class_name", sa.String(length=50), nullable=True),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("percentage >= 0 AND percentage <= 100", name="percentage_range"),
        sa.CheckConstraint("score <= total", name="score_not_above_total"),
        sa.CheckConstraint("score >= 0", name="score_nonnegative"),
        sa.CheckConstraint("total > 0", name="total_positive"),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name="fk_results_exam_id_exams",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_results_student_id_students",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_results"),
    )
    op.create_index(
        "ix_results_exam_scanned",
        "results",
        ["exam_id", "scanned_at"],
        unique=False,
    )
    op.create_index(
        "ix_results_student_id", "results", ["student_id"], unique=False
    )

    op.create_table(
        "scan_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("response_data", JSON_DOCUMENT, nullable=False),
        sa.Column("response_message", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name="fk_scan_batches_exam_id_exams",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scan_batches"),
        sa.UniqueConstraint(
            "exam_id", "idempotency_key", name="scan_batch_exam_idempotency"
        ),
    )


def downgrade() -> None:
    op.drop_table("scan_batches")
    op.drop_index("ix_results_student_id", table_name="results")
    op.drop_index("ix_results_exam_scanned", table_name="results")
    op.drop_table("results")
    op.drop_index("ix_answer_keys_exam_id", table_name="answer_keys")
    op.drop_table("answer_keys")
    op.drop_index("ix_students_roll_number", table_name="students")
    op.drop_index("ix_students_created_by", table_name="students")
    op.drop_table("students")
    op.drop_index("ix_exams_created_by", table_name="exams")
    op.drop_table("exams")
