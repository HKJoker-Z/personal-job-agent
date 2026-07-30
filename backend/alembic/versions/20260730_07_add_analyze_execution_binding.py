"""add Analyze execution fingerprint binding

Revision ID: 20260730_07
Revises: 20260724_06
Create Date: 2026-07-30 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_07"
down_revision: Union[str, None] = "20260724_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_execution_contract(operations: object, *, table_name: str | None) -> None:
    add_column = getattr(operations, "add_column")
    create_check_constraint = getattr(operations, "create_check_constraint")
    column_args = (table_name,) if table_name is not None else ()
    constraint_args = (table_name,) if table_name is not None else ()

    add_column(
        *column_args,
        sa.Column("execution_fingerprint", sa.LargeBinary(length=32), nullable=True),
    )
    add_column(
        *column_args,
        sa.Column("execution_contract_version", sa.String(length=64), nullable=True),
    )
    add_column(
        *column_args,
        sa.Column("normalization_source", sa.String(length=32), nullable=True),
    )
    add_column(
        *column_args,
        sa.Column("normalization_policy_version", sa.String(length=64), nullable=True),
    )
    add_column(
        *column_args,
        sa.Column("skill_dictionary_version", sa.String(length=64), nullable=True),
    )
    add_column(
        *column_args,
        sa.Column("execution_bound_at", sa.DateTime(timezone=True), nullable=True),
    )
    create_check_constraint(
        "analyze_idempotency_execution_fingerprint_size",
        *constraint_args,
        "execution_fingerprint IS NULL OR length(execution_fingerprint) = 32",
    )
    create_check_constraint(
        "analyze_idempotency_execution_source_valid",
        *constraint_args,
        (
            "normalization_source IS NULL OR "
            "normalization_source IN ('local','java','fallback_local')"
        ),
    )
    create_check_constraint(
        "analyze_idempotency_execution_values_nonblank",
        *constraint_args,
        """
        (execution_contract_version IS NULL OR length(trim(execution_contract_version)) > 0)
        AND (normalization_source IS NULL OR length(trim(normalization_source)) > 0)
        AND (normalization_policy_version IS NULL OR length(trim(normalization_policy_version)) > 0)
        AND (skill_dictionary_version IS NULL OR length(trim(skill_dictionary_version)) > 0)
        """,
    )
    create_check_constraint(
        "analyze_idempotency_execution_metadata_consistent",
        *constraint_args,
        """
        (
            execution_fingerprint IS NULL
            AND execution_contract_version IS NULL
            AND normalization_source IS NULL
            AND normalization_policy_version IS NULL
            AND skill_dictionary_version IS NULL
            AND execution_bound_at IS NULL
        )
        OR
        (
            execution_fingerprint IS NOT NULL
            AND execution_contract_version IS NOT NULL
            AND normalization_source IS NOT NULL
            AND normalization_policy_version IS NOT NULL
            AND execution_bound_at IS NOT NULL
            AND (
                (
                    normalization_source = 'java'
                    AND skill_dictionary_version IS NOT NULL
                )
                OR
                (
                    normalization_source IN ('local','fallback_local')
                    AND skill_dictionary_version IS NULL
                )
            )
        )
        """,
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("analyze_idempotency_records") as batch_op:
            _add_execution_contract(batch_op, table_name=None)
        return
    _add_execution_contract(op, table_name="analyze_idempotency_records")


def downgrade() -> None:
    raise RuntimeError(
        "20260730_07 is forward-only; operational rollback selects local mode."
    )
