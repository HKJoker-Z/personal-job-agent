"""add Version 2.0.3 matching ranking and application materials

Revision ID: 20260713_03
Revises: 20260713_02
Create Date: 2026-07-13 17:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260713_03"
down_revision: Union[str, None] = "20260713_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "job_match_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=True),
        sa.Column("job_revision", sa.Integer(), nullable=False),
        sa.Column("scoring_version", sa.String(40), nullable=False),
        sa.Column("synonym_map_version", sa.String(40), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("weight_config", sa.JSON(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("hard_filter_status", sa.String(20), nullable=False),
        sa.Column("recommendation", sa.String(40), nullable=False),
        sa.Column("preparation_effort", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("overall_score >= 0 AND overall_score <= 100", name=op.f("ck_job_match_analyses_overall_score_valid")),
        sa.CheckConstraint("hard_filter_status IN ('passed','warning','failed','unknown')", name=op.f("ck_job_match_analyses_hard_filter_status_valid")),
        sa.CheckConstraint("recommendation IN ('high_priority','worth_applying','apply_with_preparation','low_priority','not_recommended')", name=op.f("ck_job_match_analyses_recommendation_valid")),
        sa.CheckConstraint("status IN ('draft','completed','failed','superseded')", name=op.f("ck_job_match_analyses_status_valid")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_job_match_analyses_owner_user_id_users")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT", name=op.f("fk_job_match_analyses_job_id_jobs")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL", name=op.f("fk_job_match_analyses_application_id_applications")),
        sa.ForeignKeyConstraint(["profile_id"], ["career_profiles.id"], ondelete="RESTRICT", name=op.f("fk_job_match_analyses_profile_id_career_profiles")),
        sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"], ondelete="RESTRICT", name=op.f("fk_job_match_analyses_resume_version_id_resume_versions")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_job_match_analyses_created_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_match_analyses")),
    )
    _indexes("job_match_analyses", ("owner_user_id", "job_id", "application_id", "profile_id", "resume_version_id", "hard_filter_status", "recommendation", "status", "created_at"))
    op.create_index("ix_job_match_owner_job_created", "job_match_analyses", ["owner_user_id", "job_id", "created_at"])
    op.create_index("ix_job_match_owner_fingerprint", "job_match_analyses", ["owner_user_id", "input_fingerprint"])

    op.create_table(
        "job_match_dimensions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("weighted_score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("explanation", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("raw_score >= 0 AND raw_score <= 1", name=op.f("ck_job_match_dimensions_raw_score_valid")),
        sa.CheckConstraint("weighted_score >= 0", name=op.f("ck_job_match_dimensions_weighted_score_valid")),
        sa.CheckConstraint("max_score >= 0", name=op.f("ck_job_match_dimensions_max_score_valid")),
        sa.CheckConstraint("status IN ('matched','partial','missing','unknown','not_applicable')", name=op.f("ck_job_match_dimensions_status_valid")),
        sa.ForeignKeyConstraint(["analysis_id"], ["job_match_analyses.id"], ondelete="CASCADE", name=op.f("fk_job_match_dimensions_analysis_id_job_match_analyses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_match_dimensions")),
        sa.UniqueConstraint("analysis_id", "dimension", name="uq_job_match_dimension"),
    )
    _indexes("job_match_dimensions", ("analysis_id",))

    op.create_table(
        "job_match_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("evidence_kind", sa.String(30), nullable=False),
        sa.Column("evidence_summary", sa.String(1000), nullable=False),
        sa.Column("contribution", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("contribution >= 0 AND contribution <= 1", name=op.f("ck_job_match_evidence_contribution_valid")),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name=op.f("ck_job_match_evidence_confidence_valid")),
        sa.CheckConstraint("evidence_kind IN ('matched','partial','missing','unknown','hard_filter','contradictory')", name=op.f("ck_job_match_evidence_evidence_kind_valid")),
        sa.CheckConstraint("verification_status IN ('confirmed','needs_review','rejected','not_applicable')", name=op.f("ck_job_match_evidence_verification_status_valid")),
        sa.ForeignKeyConstraint(["analysis_id"], ["job_match_analyses.id"], ondelete="CASCADE", name=op.f("fk_job_match_evidence_analysis_id_job_match_analyses")),
        sa.ForeignKeyConstraint(["requirement_id"], ["job_requirements.id"], ondelete="SET NULL", name=op.f("fk_job_match_evidence_requirement_id_job_requirements")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_match_evidence")),
    )
    _indexes("job_match_evidence", ("analysis_id", "requirement_id"))
    op.create_index("ix_job_match_evidence_analysis_dimension", "job_match_evidence", ["analysis_id", "dimension"])

    op.create_table(
        "job_rank_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("scoring_version", sa.String(40), nullable=False),
        sa.Column("filter_config", sa.JSON(), nullable=False),
        sa.Column("weight_config", sa.JSON(), nullable=False),
        sa.Column("job_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_job_rank_runs_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_rank_runs")),
    )
    _indexes("job_rank_runs", ("owner_user_id", "created_at"))

    op.create_table(
        "job_rank_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rank_run_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("rank_score", sa.Float(), nullable=False),
        sa.Column("deadline_factor", sa.Float(), nullable=False),
        sa.Column("user_priority_factor", sa.Float(), nullable=False),
        sa.Column("preparation_effort_factor", sa.Float(), nullable=False),
        sa.Column("reason_summary", sa.JSON(), nullable=False),
        sa.CheckConstraint("rank_position > 0", name=op.f("ck_job_rank_items_rank_position_positive")),
        sa.CheckConstraint("rank_score >= 0 AND rank_score <= 100", name=op.f("ck_job_rank_items_rank_score_valid")),
        sa.ForeignKeyConstraint(["rank_run_id"], ["job_rank_runs.id"], ondelete="CASCADE", name=op.f("fk_job_rank_items_rank_run_id_job_rank_runs")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT", name=op.f("fk_job_rank_items_job_id_jobs")),
        sa.ForeignKeyConstraint(["analysis_id"], ["job_match_analyses.id"], ondelete="RESTRICT", name=op.f("fk_job_rank_items_analysis_id_job_match_analyses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_rank_items")),
        sa.UniqueConstraint("rank_run_id", "job_id", name="uq_job_rank_run_job"),
        sa.UniqueConstraint("rank_run_id", "rank_position", name="uq_job_rank_position"),
    )
    _indexes("job_rank_items", ("rank_run_id", "job_id", "analysis_id"))

    op.create_table(
        "application_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_profile_revision", sa.Integer(), nullable=False),
        sa.Column("source_job_revision", sa.Integer(), nullable=False),
        sa.Column("source_resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_match_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("status IN ('draft','in_review','approved','archived')", name=op.f("ck_application_packages_status_valid")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_application_packages_owner_user_id_users")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT", name=op.f("fk_application_packages_application_id_applications")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT", name=op.f("fk_application_packages_job_id_jobs")),
        sa.ForeignKeyConstraint(["source_resume_version_id"], ["resume_versions.id"], ondelete="RESTRICT", name=op.f("fk_application_packages_source_resume_version_id_resume_versions")),
        sa.ForeignKeyConstraint(["source_match_analysis_id"], ["job_match_analyses.id"], ondelete="RESTRICT", name=op.f("fk_application_packages_source_match_analysis_id_job_match_analyses")),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_application_packages_approved_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_packages")),
    )
    _indexes("application_packages", ("owner_user_id", "application_id", "job_id", "source_resume_version_id", "source_match_analysis_id", "status"))
    op.create_index("ix_application_package_owner_application", "application_packages", ["owner_user_id", "application_id"])
    op.create_index(
        "uq_application_packages_approved", "application_packages", ["application_id"], unique=True,
        postgresql_where=sa.text("status = 'approved'"), sqlite_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "application_materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("material_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("material_type IN ('tailored_resume','cover_letter','application_answer','recruiter_message','follow_up_message')", name=op.f("ck_application_materials_material_type_valid")),
        sa.CheckConstraint("status IN ('draft','in_review','approved','archived')", name=op.f("ck_application_materials_status_valid")),
        sa.ForeignKeyConstraint(["package_id"], ["application_packages.id"], ondelete="CASCADE", name=op.f("fk_application_materials_package_id_application_packages")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_application_materials_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_materials")),
    )
    _indexes("application_materials", ("package_id", "owner_user_id", "status"))
    op.create_index("ix_application_material_package_type", "application_materials", ["package_id", "material_type"])

    op.create_table(
        "application_material_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.String(80), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("generation_metadata", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(30), nullable=False),
        sa.Column("unsupported_claim_count", sa.Integer(), nullable=False),
        sa.Column("evidence_coverage", sa.Float(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("validation_status IN ('pending','valid','invalid','needs_user_input')", name=op.f("ck_application_material_versions_validation_status_valid")),
        sa.CheckConstraint("unsupported_claim_count >= 0", name=op.f("ck_application_material_versions_unsupported_claim_count_valid")),
        sa.CheckConstraint("evidence_coverage >= 0 AND evidence_coverage <= 100", name=op.f("ck_application_material_versions_evidence_coverage_valid")),
        sa.ForeignKeyConstraint(["material_id"], ["application_materials.id"], ondelete="CASCADE", name=op.f("fk_application_material_versions_material_id_application_materials")),
        sa.ForeignKeyConstraint(["parent_version_id"], ["application_material_versions.id"], ondelete="SET NULL", name=op.f("fk_application_material_versions_parent_version_id_application_material_versions")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_application_material_versions_created_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_material_versions")),
        sa.UniqueConstraint("material_id", "version_number", name="uq_application_material_version"),
    )
    _indexes("application_material_versions", ("material_id", "validation_status", "created_at"))

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("application_materials") as batch_op:
            batch_op.create_foreign_key(
                "fk_application_materials_active_version_id_versions",
                "application_material_versions", ["active_version_id"], ["id"],
            )
    else:
        op.create_foreign_key(
            "fk_application_materials_active_version_id_versions",
            "application_materials", "application_material_versions", ["active_version_id"], ["id"],
        )

    op.create_table(
        "material_evidence_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_version_id", sa.Uuid(), nullable=False),
        sa.Column("claim_key", sa.String(120), nullable=False),
        sa.Column("claim_text_hash", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("evidence_summary", sa.String(1000), nullable=False),
        sa.Column("support_status", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("support_status IN ('supported','partially_supported','unsupported','user_confirmed','not_applicable','needs_user_input')", name=op.f("ck_material_evidence_links_support_status_valid")),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name=op.f("ck_material_evidence_links_confidence_valid")),
        sa.ForeignKeyConstraint(["material_version_id"], ["application_material_versions.id"], ondelete="CASCADE", name=op.f("fk_material_evidence_links_material_version_id_application_material_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_evidence_links")),
    )
    _indexes("material_evidence_links", ("material_version_id", "support_status"))
    op.create_index("ix_material_evidence_version_claim", "material_evidence_links", ["material_version_id", "claim_key"])

    op.create_table(
        "material_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_version_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('request_changes','approve','reject')", name=op.f("ck_material_reviews_decision_valid")),
        sa.ForeignKeyConstraint(["material_version_id"], ["application_material_versions.id"], ondelete="CASCADE", name=op.f("fk_material_reviews_material_version_id_application_material_versions")),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_material_reviews_reviewer_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_reviews")),
    )
    _indexes("material_reviews", ("material_version_id", "reviewer_user_id", "created_at"))


def downgrade() -> None:
    op.drop_table("material_reviews")
    op.drop_table("material_evidence_links")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("application_materials") as batch_op:
            batch_op.drop_constraint("fk_application_materials_active_version_id_versions", type_="foreignkey")
    else:
        op.drop_constraint(
            "fk_application_materials_active_version_id_versions", "application_materials", type_="foreignkey"
        )
    op.drop_table("application_material_versions")
    op.drop_table("application_materials")
    op.drop_table("application_packages")
    op.drop_table("job_rank_items")
    op.drop_table("job_rank_runs")
    op.drop_table("job_match_evidence")
    op.drop_table("job_match_dimensions")
    op.drop_table("job_match_analyses")
