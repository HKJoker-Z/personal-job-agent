"""add Version 2.0.2 job library and application pipeline

Revision ID: 20260713_02
Revises: 20260712_01
Create Date: 2026-07-13 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260713_02"
down_revision: Union[str, None] = "20260712_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(300), nullable=True),
        sa.Column("normalized_company_name", sa.String(300), nullable=False),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("normalized_title", sa.String(300), nullable=False),
        sa.Column("location", sa.String(300), nullable=False),
        sa.Column("normalized_location", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_text_hash", sa.String(64), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("external_reference", sa.String(500), nullable=True),
        sa.Column("employment_type", sa.String(80), nullable=True),
        sa.Column("work_mode", sa.String(80), nullable=True),
        sa.Column("seniority", sa.String(120), nullable=True),
        sa.Column("department", sa.String(200), nullable=True),
        sa.Column("salary_min", sa.BigInteger(), nullable=True),
        sa.Column("salary_max", sa.BigInteger(), nullable=True),
        sa.Column("salary_currency", sa.String(8), nullable=True),
        sa.Column("salary_period", sa.String(30), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("deduplication_key", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("salary_min IS NULL OR salary_min >= 0", name=op.f("ck_jobs_salary_min_nonnegative")),
        sa.CheckConstraint("salary_max IS NULL OR salary_max >= 0", name=op.f("ck_jobs_salary_max_nonnegative")),
        sa.CheckConstraint("salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min", name=op.f("ck_jobs_salary_range_valid")),
        sa.CheckConstraint("length(description) <= 200000", name=op.f("ck_jobs_description_length_valid")),
        sa.CheckConstraint("status IN ('new','reviewed','shortlisted','ignored','closed','archived')", name=op.f("ck_jobs_status_valid")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_jobs_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    for name, columns in (
        ("ix_jobs_owner_user_id", ["owner_user_id"]),
        ("ix_jobs_normalized_company_name", ["normalized_company_name"]),
        ("ix_jobs_normalized_title", ["normalized_title"]),
        ("ix_jobs_normalized_location", ["normalized_location"]),
        ("ix_jobs_description_text_hash", ["description_text_hash"]),
        ("ix_jobs_application_deadline", ["application_deadline"]),
        ("ix_jobs_source_type", ["source_type"]),
        ("ix_jobs_status", ["status"]),
        ("ix_jobs_archived_at", ["archived_at"]),
    ):
        op.create_index(name, "jobs", columns)
    op.create_index(
        "uq_jobs_owner_deduplication_key_active", "jobs", ["owner_user_id", "deduplication_key"],
        unique=True, postgresql_where=sa.text("archived_at IS NULL"), sqlite_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "job_import_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("import_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("safe_error_summary", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_job_import_runs_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_import_runs")),
    )
    for column in ("owner_user_id", "import_type", "status", "started_at"):
        op.create_index(f"ix_job_import_runs_{column}", "job_import_runs", [column])

    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("current_stage", sa.String(40), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(40), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_stage IN ('saved','shortlisted','preparing','ready_to_apply','applied','assessment','interview','final_interview','offer','accepted','rejected','withdrawn','closed')", name=op.f("ck_applications_stage_valid")),
        sa.CheckConstraint("priority IN ('low','normal','high','urgent')", name=op.f("ck_applications_priority_valid")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_applications_owner_user_id_users")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT", name=op.f("fk_applications_job_id_jobs")),
        sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"], ondelete="RESTRICT", name=op.f("fk_applications_resume_version_id_resume_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
    )
    for column in ("owner_user_id", "job_id", "current_stage", "priority", "resume_version_id", "next_action_at", "archived_at"):
        op.create_index(f"ix_applications_{column}", "applications", [column])
    op.create_index(
        "uq_applications_owner_job_active", "applications", ["owner_user_id", "job_id"],
        unique=True, postgresql_where=sa.text("archived_at IS NULL"), sqlite_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "job_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("original_url", sa.String(2048), nullable=True),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("external_id", sa.String(500), nullable=True),
        sa.Column("file_asset_id", sa.Uuid(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("http_status_summary", sa.String(80), nullable=True),
        sa.Column("media_type", sa.String(160), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_type IN ('manual','url','pdf','docx','csv','migrated')", name=op.f("ck_job_sources_source_type_valid")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE", name=op.f("fk_job_sources_job_id_jobs")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_job_sources_owner_user_id_users")),
        sa.ForeignKeyConstraint(["file_asset_id"], ["file_assets.id"], ondelete="RESTRICT", name=op.f("fk_job_sources_file_asset_id_file_assets")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_sources")),
    )
    for column in ("job_id", "owner_user_id", "source_type", "file_asset_id", "content_sha256"):
        op.create_index(f"ix_job_sources_{column}", "job_sources", [column])

    op.create_table(
        "job_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("requirement_type", sa.String(30), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("minimum_years", sa.Float(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("evidence_start", sa.Integer(), nullable=True),
        sa.Column("evidence_end", sa.Integer(), nullable=True),
        sa.Column("extraction_source", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name=op.f("ck_job_requirements_confidence_valid")),
        sa.CheckConstraint("evidence_start IS NULL OR evidence_start >= 0", name=op.f("ck_job_requirements_evidence_start_valid")),
        sa.CheckConstraint("evidence_end IS NULL OR evidence_start IS NULL OR evidence_end >= evidence_start", name=op.f("ck_job_requirements_evidence_end_valid")),
        sa.CheckConstraint("category IN ('skill','education','experience','language','certification','location','work_authorization','responsibility','benefit','other')", name=op.f("ck_job_requirements_category_valid")),
        sa.CheckConstraint("requirement_type IN ('required','preferred','informational','hard_filter')", name=op.f("ck_job_requirements_requirement_type_valid")),
        sa.CheckConstraint("extraction_source IN ('deterministic','llm','user')", name=op.f("ck_job_requirements_extraction_source_valid")),
        sa.CheckConstraint("verification_status IN ('needs_review','confirmed','rejected')", name=op.f("ck_job_requirements_verification_status_valid")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE", name=op.f("fk_job_requirements_job_id_jobs")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_job_requirements_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_requirements")),
    )
    for column in ("job_id", "owner_user_id", "category", "normalized_name", "verification_status"):
        op.create_index(f"ix_job_requirements_{column}", "job_requirements", [column])

    op.create_table(
        "job_duplicate_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_job_id", sa.Uuid(), nullable=False),
        sa.Column("match_type", sa.String(30), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("job_id <> candidate_job_id", name=op.f("ck_job_duplicate_candidates_jobs_different")),
        sa.CheckConstraint("similarity_score >= 0 AND similarity_score <= 1", name=op.f("ck_job_duplicate_candidates_similarity_valid")),
        sa.CheckConstraint("match_type IN ('exact','near')", name=op.f("ck_job_duplicate_candidates_match_type_valid")),
        sa.CheckConstraint("status IN ('pending','confirmed_duplicate','not_duplicate','dismissed')", name=op.f("ck_job_duplicate_candidates_status_valid")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_job_duplicate_candidates_owner_user_id_users")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE", name=op.f("fk_job_duplicate_candidates_job_id_jobs")),
        sa.ForeignKeyConstraint(["candidate_job_id"], ["jobs.id"], ondelete="CASCADE", name=op.f("fk_job_duplicate_candidates_candidate_job_id_jobs")),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_job_duplicate_candidates_resolved_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_duplicate_candidates")),
        sa.UniqueConstraint("owner_user_id", "job_id", "candidate_job_id", name="uq_job_duplicate_pair"),
    )
    for column in ("owner_user_id", "job_id", "candidate_job_id", "status"):
        op.create_index(f"ix_job_duplicate_candidates_{column}", "job_duplicate_candidates", [column])

    op.create_table(
        "application_stage_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("from_stage", sa.String(40), nullable=False),
        sa.Column("to_stage", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision_before", sa.Integer(), nullable=False),
        sa.Column("revision_after", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT", name=op.f("fk_application_stage_history_application_id_applications")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_application_stage_history_owner_user_id_users")),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_application_stage_history_changed_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_stage_history")),
    )
    for column in ("application_id", "owner_user_id", "changed_at"):
        op.create_index(f"ix_application_stage_history_{column}", "application_stage_history", [column])

    op.create_table(
        "application_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note_type", sa.String(30), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("note_type IN ('general','recruiter','interview','follow_up','outcome','private')", name=op.f("ck_application_notes_note_type_valid")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT", name=op.f("fk_application_notes_application_id_applications")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_application_notes_owner_user_id_users")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_application_notes_created_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_notes")),
    )
    for column in ("application_id", "owner_user_id", "note_type", "deleted_at"):
        op.create_index(f"ix_application_notes_{column}", "application_notes", [column])

    op.create_table(
        "application_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','in_progress','completed','cancelled')", name=op.f("ck_application_tasks_status_valid")),
        sa.CheckConstraint("priority IN ('low','normal','high','urgent')", name=op.f("ck_application_tasks_priority_valid")),
        sa.CheckConstraint("task_type IN ('review_job','tailor_resume','prepare_application','submit_application','follow_up','assessment','interview_preparation','interview','document_request','other')", name=op.f("ck_application_tasks_task_type_valid")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_application_tasks_owner_user_id_users")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT", name=op.f("fk_application_tasks_application_id_applications")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT", name=op.f("fk_application_tasks_job_id_jobs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_tasks")),
    )
    for column in ("owner_user_id", "application_id", "job_id", "task_type", "status", "priority", "due_at", "archived_at"):
        op.create_index(f"ix_application_tasks_{column}", "application_tasks", [column])

    op.create_table(
        "job_merge_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_job_id", sa.Uuid(), nullable=False),
        sa.Column("source_job_id", sa.Uuid(), nullable=False),
        sa.Column("field_selection", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("merged_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_job_merge_history_owner_user_id_users")),
        sa.ForeignKeyConstraint(["target_job_id"], ["jobs.id"], ondelete="RESTRICT", name=op.f("fk_job_merge_history_target_job_id_jobs")),
        sa.ForeignKeyConstraint(["source_job_id"], ["jobs.id"], ondelete="RESTRICT", name=op.f("fk_job_merge_history_source_job_id_jobs")),
        sa.ForeignKeyConstraint(["merged_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_job_merge_history_merged_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_merge_history")),
    )
    for column in ("owner_user_id", "target_job_id", "source_job_id"):
        op.create_index(f"ix_job_merge_history_{column}", "job_merge_history", [column])


def downgrade() -> None:
    for table in (
        "job_merge_history", "application_tasks", "application_notes", "application_stage_history",
        "job_duplicate_candidates", "job_requirements", "job_sources", "applications",
        "job_import_runs", "jobs",
    ):
        op.drop_table(table)
