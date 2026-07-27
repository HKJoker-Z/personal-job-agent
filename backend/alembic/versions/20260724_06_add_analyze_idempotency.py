"""add PostgreSQL-backed Analyze idempotency ledger

Revision ID: 20260724_06
Revises: 20260721_05
Create Date: 2026-07-24 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260724_06"
down_revision: Union[str, None] = "20260721_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analyze_idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_token", sa.Uuid(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("history_record_id", sa.Integer(), nullable=True),
        sa.Column("provider_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('processing','completed','failed','indeterminate')",
            name="analyze_idempotency_status_valid",
        ),
        sa.CheckConstraint(
            "attempt_count >= 1",
            name="analyze_idempotency_attempt_count_positive",
        ),
        sa.ForeignKeyConstraint(["history_record_id"], ["application_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key_hash",
            name="uq_analyze_idempotency_scope_key",
        ),
    )
    op.create_index(
        "ix_analyze_idempotency_expiry_status",
        "analyze_idempotency_records",
        ["expires_at", "status"],
    )
    op.create_index(
        "ix_analyze_idempotency_processing_lease",
        "analyze_idempotency_records",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analyze_idempotency_processing_lease",
        table_name="analyze_idempotency_records",
    )
    op.drop_index(
        "ix_analyze_idempotency_expiry_status",
        table_name="analyze_idempotency_records",
    )
    op.drop_table("analyze_idempotency_records")
