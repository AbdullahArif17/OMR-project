"""Add request_fingerprint to scan_batches.

Revision ID: 20260720_0002
Revises: 20260719_0001
Create Date: 2026-07-20
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_0002"
down_revision: str | Sequence[str] | None = "20260719_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scan_batches",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scan_batches", "request_fingerprint")
