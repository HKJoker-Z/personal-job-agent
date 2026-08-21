"""add Version 2.1.0 application snapshots

Revision ID: 20260820_08
Revises: 20260730_07
Create Date: 2026-08-20 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_08"
down_revision: Union[str, None] = "20260730_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.alter_column("job_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.add_column(sa.Column("company_name", sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("job_title", sa.String(500), nullable=True))
        batch_op.add_column(
            sa.Column("job_description", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("resume_snapshot", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source_analysis_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_applications_source_analysis_id_application_records",
            "application_records",
            ["source_analysis_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_applications_source_analysis_id", ["source_analysis_id"]
        )
        batch_op.create_index(
            "uq_applications_owner_source_analysis",
            ["owner_user_id", "source_analysis_id"],
            unique=True,
            postgresql_where=sa.text("source_analysis_id IS NOT NULL"),
            sqlite_where=sa.text("source_analysis_id IS NOT NULL"),
        )
    with op.batch_alter_table("applications") as batch_op:
        batch_op.alter_column(
            "job_description", existing_type=sa.Text(), server_default=None
        )


def downgrade() -> None:
    op.execute("DELETE FROM applications WHERE job_id IS NULL")
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_index("uq_applications_owner_source_analysis")
        batch_op.drop_index("ix_applications_source_analysis_id")
        batch_op.drop_constraint(
            "fk_applications_source_analysis_id_application_records",
            type_="foreignkey",
        )
        batch_op.drop_column("source_analysis_id")
        batch_op.drop_column("resume_snapshot")
        batch_op.drop_column("job_description")
        batch_op.drop_column("job_title")
        batch_op.drop_column("company_name")
        batch_op.alter_column("job_id", existing_type=sa.Uuid(), nullable=False)
