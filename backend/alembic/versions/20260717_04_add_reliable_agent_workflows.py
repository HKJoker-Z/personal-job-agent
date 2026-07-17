"""add reliable agent workflows, approvals, budgets, and workers

Revision ID: 20260717_04
Revises: 20260713_03
Create Date: 2026-07-17 19:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_04"
down_revision: Union[str, None] = "20260713_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=True),
        sa.Column("job_revision", sa.Integer(), nullable=True),
        sa.Column("resume_version_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("package_id", sa.Uuid(), nullable=True),
        sa.Column("current_step_key", sa.String(100), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("token_limit", sa.Integer(), nullable=False),
        sa.Column("cost_limit_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("safe_error_code", sa.String(80), nullable=True),
        sa.Column("safe_error_summary", sa.String(500), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','waiting_for_approval','retry_scheduled','completed','failed','cancelled','dead_letter')",
            name=op.f("ck_agent_runs_status_valid"),
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_agent_runs_owner_user_id_users")),
        sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"], ondelete="RESTRICT", name=op.f("fk_agent_runs_resume_version_id_resume_versions")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT", name=op.f("fk_agent_runs_application_id_applications")),
        sa.ForeignKeyConstraint(["package_id"], ["application_packages.id"], ondelete="RESTRICT", name=op.f("fk_agent_runs_package_id_application_packages")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        sa.UniqueConstraint("owner_user_id", "workflow_type", "idempotency_key_hash", name="uq_agent_run_idempotency"),
    )
    _indexes("agent_runs", ("owner_user_id", "workflow_type", "status", "correlation_id", "resume_version_id", "application_id", "package_id", "retry_at"))
    op.create_index("ix_agent_runs_owner_status_created", "agent_runs", ["owner_user_id", "status", "created_at"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("step_key", sa.String(100), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("execution_token", sa.String(64), nullable=True),
        sa.Column("worker_id", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_refs", sa.JSON(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("safe_error_code", sa.String(80), nullable=True),
        sa.Column("safe_error_summary", sa.String(500), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','queued','running','waiting_for_approval','completed','skipped','failed','cancelled','retry_scheduled')",
            name=op.f("ck_agent_steps_status_valid"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE", name=op.f("fk_agent_steps_run_id_agent_runs")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_agent_steps_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_steps")),
        sa.UniqueConstraint("run_id", "step_key", name="uq_agent_step_key"),
        sa.UniqueConstraint("idempotency_key", name="uq_agent_step_idempotency"),
    )
    _indexes("agent_steps", ("run_id", "owner_user_id", "status", "execution_token", "worker_id", "lease_expires_at", "scheduled_at"))
    op.create_index("ix_agent_steps_run_order", "agent_steps", ["run_id", "step_order"])
    op.create_index("ix_agent_steps_status_scheduled", "agent_steps", ["status", "scheduled_at"])

    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("safe_payload", sa.JSON(), nullable=False),
        sa.Column("run_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE", name=op.f("fk_agent_run_events_run_id_agent_runs")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_agent_run_events_owner_user_id_users")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="SET NULL", name=op.f("fk_agent_run_events_step_id_agent_steps")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_run_events")),
    )
    _indexes("agent_run_events", ("run_id", "owner_user_id", "step_id", "event_type", "created_at"))
    op.create_index("ix_agent_events_run_id_id", "agent_run_events", ["run_id", "id"])

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("approval_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("safe_summary", sa.String(500), nullable=False),
        sa.Column("risk_level", sa.String(30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','approved','rejected','expired','cancelled')", name=op.f("ck_approval_requests_status_valid")),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE", name=op.f("fk_approval_requests_run_id_agent_runs")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="CASCADE", name=op.f("fk_approval_requests_step_id_agent_steps")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_approval_requests_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
        sa.UniqueConstraint("run_id", "step_id", "approval_type", name="uq_approval_request_step_type"),
    )
    _indexes("approval_requests", ("run_id", "step_id", "owner_user_id", "approval_type", "status", "expires_at", "created_at"))
    op.create_index("ix_approval_owner_status_created", "approval_requests", ["owner_user_id", "status", "created_at"])

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_request_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("request_revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("safe_reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('approve','reject')", name=op.f("ck_approval_decisions_decision_valid")),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"], ondelete="CASCADE", name=op.f("fk_approval_decisions_approval_request_id_approval_requests")),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE", name=op.f("fk_approval_decisions_run_id_agent_runs")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_approval_decisions_owner_user_id_users")),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_approval_decisions_decided_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_decisions")),
        sa.UniqueConstraint("approval_request_id", "idempotency_key", name="uq_approval_decision_idempotency"),
    )
    _indexes("approval_decisions", ("approval_request_id", "run_id", "owner_user_id", "decided_by_user_id"))
    op.create_index("ix_approval_decisions_request_created", "approval_decisions", ["approval_request_id", "created_at"])

    op.create_table(
        "agent_outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("deduplication_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(120), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','publishing','published','failed','dead_letter')", name=op.f("ck_agent_outbox_events_status_valid")),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE", name=op.f("fk_agent_outbox_events_run_id_agent_runs")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="CASCADE", name=op.f("fk_agent_outbox_events_step_id_agent_steps")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_outbox_events")),
        sa.UniqueConstraint("deduplication_key", name="uq_agent_outbox_deduplication"),
    )
    _indexes("agent_outbox_events", ("run_id", "step_id", "status", "available_at"))
    op.create_index("ix_agent_outbox_status_available", "agent_outbox_events", ["status", "available_at"])

    op.create_table(
        "user_ai_budgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("budget_date", sa.Date(), nullable=False),
        sa.Column("daily_token_limit", sa.Integer(), nullable=False),
        sa.Column("daily_cost_limit_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("run_token_limit", sa.Integer(), nullable=False),
        sa.Column("step_token_limit", sa.Integer(), nullable=False),
        sa.Column("concurrent_run_limit", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_user_ai_budgets_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_ai_budgets")),
        sa.UniqueConstraint("user_id", "budget_date", name="uq_user_ai_budget_date"),
    )
    _indexes("user_ai_budgets", ("user_id", "budget_date"))

    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("usage_key", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_ai_usage_ledger_owner_user_id_users")),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE", name=op.f("fk_ai_usage_ledger_run_id_agent_runs")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="CASCADE", name=op.f("fk_ai_usage_ledger_step_id_agent_steps")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_ledger")),
        sa.UniqueConstraint("usage_key", name="uq_ai_usage_ledger_key"),
    )
    _indexes("ai_usage_ledger", ("owner_user_id", "run_id", "step_id", "created_at"))
    op.create_index("ix_ai_usage_user_created", "ai_usage_ledger", ["owner_user_id", "created_at"])

    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(120), nullable=False),
        sa.Column("hostname_hash", sa.String(64), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("active_tasks", sa.Integer(), nullable=False),
        sa.Column("worker_version", sa.String(80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shutdown_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('starting','ready','busy','stopping','stopped')", name=op.f("ck_worker_heartbeats_status_valid")),
        sa.PrimaryKeyConstraint("worker_id", name=op.f("pk_worker_heartbeats")),
    )
    _indexes("worker_heartbeats", ("status", "last_heartbeat_at"))

    op.create_table(
        "dead_letter_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("outbox_event_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("safe_error_summary", sa.String(500), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("safe_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open','resolved')", name=op.f("ck_dead_letter_records_status_valid")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_dead_letter_records_owner_user_id_users")),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE", name=op.f("fk_dead_letter_records_run_id_agent_runs")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], ondelete="SET NULL", name=op.f("fk_dead_letter_records_step_id_agent_steps")),
        sa.ForeignKeyConstraint(["outbox_event_id"], ["agent_outbox_events.id"], ondelete="SET NULL", name=op.f("fk_dead_letter_records_outbox_event_id_agent_outbox_events")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dead_letter_records")),
    )
    _indexes("dead_letter_records", ("owner_user_id", "run_id", "step_id", "outbox_event_id", "status"))
    op.create_index("ix_dead_letter_owner_status_created", "dead_letter_records", ["owner_user_id", "status", "created_at"])


def downgrade() -> None:
    for table in (
        "dead_letter_records",
        "worker_heartbeats",
        "ai_usage_ledger",
        "user_ai_budgets",
        "approval_decisions",
        "approval_requests",
        "agent_run_events",
        "agent_outbox_events",
        "agent_steps",
        "agent_runs",
    ):
        op.drop_table(table)
