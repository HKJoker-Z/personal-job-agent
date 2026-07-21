"""add one primary resume per user

Revision ID: 20260721_05
Revises: 20260717_04
Create Date: 2026-07-21 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260721_05"
down_revision: Union[str, None] = "20260717_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(
            """
            WITH newest AS (
                SELECT id, row_number() OVER (
                    PARTITION BY user_id ORDER BY updated_at DESC, created_at DESC, id DESC
                ) AS position
                FROM resumes WHERE archived_at IS NULL
            )
            UPDATE resumes SET is_primary = TRUE
            FROM newest WHERE resumes.id = newest.id AND newest.position = 1
            """
        )
    else:
        connection.exec_driver_sql(
            """
            UPDATE resumes SET is_primary = 1
            WHERE id IN (
                SELECT candidate.id FROM resumes AS candidate
                WHERE candidate.archived_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM resumes AS newer
                    WHERE newer.user_id = candidate.user_id
                      AND newer.archived_at IS NULL
                      AND (
                        newer.updated_at > candidate.updated_at OR
                        (newer.updated_at = candidate.updated_at AND newer.created_at > candidate.created_at) OR
                        (newer.updated_at = candidate.updated_at AND newer.created_at = candidate.created_at AND newer.id > candidate.id)
                      )
                  )
            )
            """
        )
    op.create_index(
        "uq_resumes_user_primary_active",
        "resumes",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE AND archived_at IS NULL"),
        sqlite_where=sa.text("is_primary = 1 AND archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_resumes_user_primary_active", table_name="resumes")
    op.drop_column("resumes", "is_primary")
