"""create version 2 phase 1 schema

Revision ID: 20260712_01
Revises:
Create Date: 2026-07-12 14:11:14.015096
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260712_01'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Generated from the reviewed ORM metadata, then manually checked for
    # ownership, circular Resume constraints, and PostgreSQL search behavior.
    op.create_table('auth_login_attempts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('subject_hash', sa.String(length=64), nullable=False),
    sa.Column('client_hash', sa.String(length=64), nullable=False),
    sa.Column('failed_count', sa.Integer(), nullable=False),
    sa.Column('first_failed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_failed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_login_attempts')),
    sa.UniqueConstraint('subject_hash', 'client_hash', name=op.f('uq_auth_login_attempts_subject_hash'))
    )
    with op.batch_alter_table('auth_login_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_login_attempts_client_hash'), ['client_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_auth_login_attempts_subject_hash'), ['subject_hash'], unique=False)

    op.create_table('migration_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('migration_version', sa.String(length=40), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('row_count_summary', sa.JSON(), nullable=False),
    sa.Column('verification_summary', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_migration_runs')),
    sa.UniqueConstraint('source_fingerprint', name=op.f('uq_migration_runs_source_fingerprint'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('normalized_email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=512), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('admin','user')", name=op.f('ck_users_role_valid')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_normalized_email'), ['normalized_email'], unique=True)

    op.create_table('analysis_step_metrics',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('workflow_id', sa.String(length=128), nullable=False),
    sa.Column('step_key', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('duration_us', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_analysis_step_metrics_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_step_metrics'))
    )
    with op.batch_alter_table('analysis_step_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_analysis_step_metrics_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_step_metrics_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_step_metrics_step_key'), ['step_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_step_metrics_workflow_id'), ['workflow_id'], unique=False)

    op.create_table('application_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('company_name', sa.String(length=500), nullable=False),
    sa.Column('job_title', sa.String(length=500), nullable=False),
    sa.Column('job_url', sa.Text(), nullable=True),
    sa.Column('resume_filename', sa.String(length=255), nullable=True),
    sa.Column('application_status', sa.String(length=40), nullable=False),
    sa.Column('match_score', sa.Integer(), nullable=False),
    sa.Column('match_reason', sa.Text(), nullable=False),
    sa.Column('job_summary', sa.Text(), nullable=False),
    sa.Column('matched_skills', sa.Text(), nullable=False),
    sa.Column('missing_skills', sa.Text(), nullable=False),
    sa.Column('resume_suggestions', sa.Text(), nullable=False),
    sa.Column('cover_letter', sa.Text(), nullable=False),
    sa.Column('scoring_breakdown', sa.Text(), nullable=False),
    sa.Column('ats_analysis', sa.Text(), nullable=False),
    sa.Column('upgraded_resume_bullets', sa.Text(), nullable=False),
    sa.Column('rag_mode', sa.String(length=30), nullable=False),
    sa.Column('rag_sources', sa.Text(), nullable=False),
    sa.Column('workflow_id', sa.String(length=128), nullable=True),
    sa.Column('workflow_steps', sa.Text(), nullable=False),
    sa.Column('workflow_duration_ms', sa.Float(), nullable=True),
    sa.Column('workflow_duration_us', sa.BigInteger(), nullable=True),
    sa.Column('next_action', sa.Text(), nullable=False),
    sa.Column('next_action_decision', sa.String(length=30), nullable=False),
    sa.Column('next_action_decision_notes', sa.Text(), nullable=True),
    sa.Column('next_action_decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('security_scan', sa.Text(), nullable=False),
    sa.Column('security_status', sa.String(length=40), nullable=False),
    sa.Column('security_policy_version', sa.String(length=40), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_application_records_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_application_records'))
    )
    with op.batch_alter_table('application_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_application_records_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_application_records_workflow_id'), ['workflow_id'], unique=False)

    op.create_table('audit_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('resource_type', sa.String(length=80), nullable=True),
    sa.Column('resource_id', sa.String(length=64), nullable=True),
    sa.Column('outcome', sa.String(length=30), nullable=False),
    sa.Column('safe_metadata', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audit_events_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_events_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_events_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_events_user_id'), ['user_id'], unique=False)

    op.create_table('career_profiles',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('headline', sa.String(length=240), nullable=False),
    sa.Column('professional_summary', sa.Text(), nullable=False),
    sa.Column('current_location', sa.String(length=200), nullable=False),
    sa.Column('phone', sa.String(length=80), nullable=False),
    sa.Column('public_email', sa.String(length=320), nullable=False),
    sa.Column('website', sa.String(length=500), nullable=False),
    sa.Column('linkedin_url', sa.String(length=500), nullable=False),
    sa.Column('github_url', sa.String(length=500), nullable=False),
    sa.Column('completeness_score', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_career_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_career_profiles')),
    sa.UniqueConstraint('user_id', name=op.f('uq_career_profiles_user_id'))
    )
    op.create_table('evaluation_results',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('run_id', sa.String(length=128), nullable=False),
    sa.Column('case_id', sa.String(length=128), nullable=False),
    sa.Column('case_name', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('checks_json', sa.Text(), nullable=True),
    sa.Column('failure_summary', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_evaluation_results_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_results'))
    )
    with op.batch_alter_table('evaluation_results', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evaluation_results_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evaluation_results_run_id'), ['run_id'], unique=False)

    op.create_table('evaluation_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('run_id', sa.String(length=128), nullable=False),
    sa.Column('suite_name', sa.String(length=120), nullable=False),
    sa.Column('suite_version', sa.String(length=40), nullable=False),
    sa.Column('mode', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('total_cases', sa.Integer(), nullable=False),
    sa.Column('passed_cases', sa.Integer(), nullable=False),
    sa.Column('failed_cases', sa.Integer(), nullable=False),
    sa.Column('error_cases', sa.Integer(), nullable=False),
    sa.Column('pass_rate', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_evaluation_runs_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_runs')),
    sa.UniqueConstraint('run_id', name=op.f('uq_evaluation_runs_run_id'))
    )
    with op.batch_alter_table('evaluation_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evaluation_runs_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evaluation_runs_started_at'), ['started_at'], unique=False)

    op.create_table('file_assets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=120), nullable=False),
    sa.Column('media_type', sa.String(length=160), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_file_assets_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_file_assets')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_file_assets_storage_key'))
    )
    with op.batch_alter_table('file_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_file_assets_sha256'), ['sha256'], unique=False)
        batch_op.create_index(batch_op.f('ix_file_assets_user_id'), ['user_id'], unique=False)

    op.create_table('knowledge_documents',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('source_filename', sa.String(length=500), nullable=True),
    sa.Column('content_preview', sa.Text(), nullable=True),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_knowledge_documents_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_documents'))
    )
    with op.batch_alter_table('knowledge_documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_knowledge_documents_owner_user_id'), ['owner_user_id'], unique=False)

    op.create_table('resumes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=240), nullable=False),
    sa.Column('language', sa.String(length=20), nullable=False),
    sa.Column('target_role', sa.String(length=240), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('active_version_id', sa.Uuid(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_resumes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_resumes'))
    )
    with op.batch_alter_table('resumes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_resumes_user_id'), ['user_id'], unique=False)

    op.create_table('user_sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('idle_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('absolute_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoke_reason', sa.String(length=120), nullable=True),
    sa.Column('user_agent_hash', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions'))
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('analysis_metrics',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('workflow_id', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome', sa.String(length=50), nullable=False),
    sa.Column('workflow_status', sa.String(length=50), nullable=True),
    sa.Column('workflow_duration_ms', sa.Float(), nullable=True),
    sa.Column('workflow_duration_us', sa.BigInteger(), nullable=True),
    sa.Column('llm_duration_ms', sa.Float(), nullable=True),
    sa.Column('rag_retrieval_duration_ms', sa.Float(), nullable=True),
    sa.Column('rag_mode', sa.String(length=30), nullable=True),
    sa.Column('rag_source_count', sa.Integer(), nullable=False),
    sa.Column('rag_hit', sa.Integer(), nullable=False),
    sa.Column('rag_reconciliation_count', sa.Integer(), nullable=False),
    sa.Column('security_status', sa.String(length=40), nullable=True),
    sa.Column('security_risk_level', sa.String(length=40), nullable=True),
    sa.Column('prompt_injection_detected', sa.Integer(), nullable=False),
    sa.Column('sensitive_data_detected', sa.Integer(), nullable=False),
    sa.Column('output_leakage_detected', sa.Integer(), nullable=False),
    sa.Column('pii_email_redaction_count', sa.Integer(), nullable=False),
    sa.Column('pii_phone_redaction_count', sa.Integer(), nullable=False),
    sa.Column('pii_address_redaction_count', sa.Integer(), nullable=False),
    sa.Column('security_finding_codes', sa.Text(), nullable=True),
    sa.Column('json_parse_success', sa.Integer(), nullable=True),
    sa.Column('saved_to_history', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=True),
    sa.Column('next_action', sa.String(length=80), nullable=True),
    sa.Column('error_code', sa.String(length=120), nullable=True),
    sa.Column('error_stage', sa.String(length=120), nullable=True),
    sa.Column('source_type', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['application_id'], ['application_records.id'], name=op.f('fk_analysis_metrics_application_id_application_records'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_analysis_metrics_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_metrics')),
    sa.UniqueConstraint('workflow_id', name=op.f('uq_analysis_metrics_workflow_id'))
    )
    with op.batch_alter_table('analysis_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_analysis_metrics_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_metrics_outcome'), ['outcome'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_metrics_owner_user_id'), ['owner_user_id'], unique=False)

    op.create_table('knowledge_chunks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('token_estimate', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], name=op.f('fk_knowledge_chunks_document_id_knowledge_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_chunks')),
    sa.UniqueConstraint('document_id', 'chunk_index', name=op.f('uq_knowledge_chunks_document_id'))
    )
    with op.batch_alter_table('knowledge_chunks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_knowledge_chunks_document_id'), ['document_id'], unique=False)

    op.create_table('profile_certifications',
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('issuer', sa.String(length=240), nullable=False),
    sa.Column('issue_date', sa.Date(), nullable=True),
    sa.Column('expiry_date', sa.Date(), nullable=True),
    sa.Column('credential_id', sa.String(length=200), nullable=False),
    sa.Column('credential_url', sa.String(length=500), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_certifications_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_certifications'))
    )
    with op.batch_alter_table('profile_certifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_certifications_profile_id'), ['profile_id'], unique=False)

    op.create_table('profile_educations',
    sa.Column('institution', sa.String(length=240), nullable=False),
    sa.Column('degree', sa.String(length=200), nullable=False),
    sa.Column('field_of_study', sa.String(length=200), nullable=False),
    sa.Column('location', sa.String(length=200), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('grade', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_educations_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_educations'))
    )
    with op.batch_alter_table('profile_educations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_educations_profile_id'), ['profile_id'], unique=False)

    op.create_table('profile_experiences',
    sa.Column('company', sa.String(length=240), nullable=False),
    sa.Column('role_title', sa.String(length=240), nullable=False),
    sa.Column('location', sa.String(length=200), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('is_current', sa.Boolean(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('achievements', sa.JSON(), nullable=False),
    sa.Column('skills', sa.JSON(), nullable=False),
    sa.Column('source_type', sa.String(length=30), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("verification_status IN ('draft','needs_review','confirmed')", name=op.f('ck_profile_experiences_verification_valid')),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_experiences_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_experiences'))
    )
    with op.batch_alter_table('profile_experiences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_experiences_profile_id'), ['profile_id'], unique=False)

    op.create_table('profile_languages',
    sa.Column('language', sa.String(length=120), nullable=False),
    sa.Column('proficiency', sa.String(length=80), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_languages_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_languages'))
    )
    with op.batch_alter_table('profile_languages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_languages_profile_id'), ['profile_id'], unique=False)

    op.create_table('profile_preferences',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('target_roles', sa.JSON(), nullable=False),
    sa.Column('target_locations', sa.JSON(), nullable=False),
    sa.Column('employment_types', sa.JSON(), nullable=False),
    sa.Column('work_modes', sa.JSON(), nullable=False),
    sa.Column('minimum_salary', sa.BigInteger(), nullable=True),
    sa.Column('salary_currency', sa.String(length=8), nullable=False),
    sa.Column('salary_period', sa.String(length=30), nullable=False),
    sa.Column('work_authorization', sa.String(length=240), nullable=False),
    sa.Column('sponsorship_required', sa.Boolean(), nullable=True),
    sa.Column('willing_to_relocate', sa.Boolean(), nullable=True),
    sa.Column('excluded_role_keywords', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_preferences_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_preferences')),
    sa.UniqueConstraint('profile_id', name=op.f('uq_profile_preferences_profile_id'))
    )
    op.create_table('profile_projects',
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('role', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('technologies', sa.JSON(), nullable=False),
    sa.Column('achievements', sa.JSON(), nullable=False),
    sa.Column('metrics', sa.JSON(), nullable=False),
    sa.Column('project_url', sa.String(length=500), nullable=False),
    sa.Column('repository_url', sa.String(length=500), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('source_type', sa.String(length=30), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_projects_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_projects'))
    )
    with op.batch_alter_table('profile_projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_projects_profile_id'), ['profile_id'], unique=False)

    op.create_table('profile_revisions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('change_type', sa.String(length=80), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_profile_revisions_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_revisions_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_revisions')),
    sa.UniqueConstraint('profile_id', 'revision_number', name=op.f('uq_profile_revisions_profile_id'))
    )
    with op.batch_alter_table('profile_revisions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_revisions_profile_id'), ['profile_id'], unique=False)

    op.create_table('profile_skills',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('category', sa.String(length=120), nullable=False),
    sa.Column('proficiency', sa.String(length=80), nullable=False),
    sa.Column('years_experience', sa.Float(), nullable=True),
    sa.Column('last_used_at', sa.Date(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['career_profiles.id'], name=op.f('fk_profile_skills_profile_id_career_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_skills'))
    )
    with op.batch_alter_table('profile_skills', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_skills_profile_id'), ['profile_id'], unique=False)

    op.create_table('resume_versions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('parent_version_id', sa.Uuid(), nullable=True),
    sa.Column('source_type', sa.String(length=30), nullable=False),
    sa.Column('source_file_id', sa.Uuid(), nullable=True),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.Column('content_json', sa.JSON(), nullable=False),
    sa.Column('parsed_text', sa.Text(), nullable=False),
    sa.Column('change_summary', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_resume_versions_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['parent_version_id'], ['resume_versions.id'], name=op.f('fk_resume_versions_parent_version_id_resume_versions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['resume_id'], ['resumes.id'], name=op.f('fk_resume_versions_resume_id_resumes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_file_id'], ['file_assets.id'], name=op.f('fk_resume_versions_source_file_id_file_assets'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_resume_versions')),
    sa.UniqueConstraint('resume_id', 'version_number', name=op.f('uq_resume_versions_resume_id'))
    )
    with op.batch_alter_table('resume_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_resume_versions_resume_id'), ['resume_id'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('resumes', schema=None) as batch_op:
            batch_op.create_foreign_key(
                'fk_resumes_active_version_id_resume_versions',
                'resume_versions',
                ['active_version_id'],
                ['id'],
            )
    else:
        op.create_foreign_key(
            'fk_resumes_active_version_id_resume_versions',
            'resumes',
            'resume_versions',
            ['active_version_id'],
            ['id'],
        )
    if bind.dialect.name == 'postgresql':
        op.execute(
            "CREATE INDEX ix_knowledge_chunks_fts "
            "ON knowledge_chunks USING GIN (to_tsvector('simple', content))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS ix_knowledge_chunks_fts')
        op.drop_constraint(
            'fk_resumes_active_version_id_resume_versions',
            'resumes',
            type_='foreignkey',
        )
    else:
        with op.batch_alter_table('resumes', schema=None) as batch_op:
            batch_op.drop_constraint(
                'fk_resumes_active_version_id_resume_versions', type_='foreignkey'
            )
    with op.batch_alter_table('resume_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_resume_versions_resume_id'))

    op.drop_table('resume_versions')
    with op.batch_alter_table('profile_skills', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_skills_profile_id'))

    op.drop_table('profile_skills')
    with op.batch_alter_table('profile_revisions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_revisions_profile_id'))

    op.drop_table('profile_revisions')
    with op.batch_alter_table('profile_projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_projects_profile_id'))

    op.drop_table('profile_projects')
    op.drop_table('profile_preferences')
    with op.batch_alter_table('profile_languages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_languages_profile_id'))

    op.drop_table('profile_languages')
    with op.batch_alter_table('profile_experiences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_experiences_profile_id'))

    op.drop_table('profile_experiences')
    with op.batch_alter_table('profile_educations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_educations_profile_id'))

    op.drop_table('profile_educations')
    with op.batch_alter_table('profile_certifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_certifications_profile_id'))

    op.drop_table('profile_certifications')
    with op.batch_alter_table('knowledge_chunks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_knowledge_chunks_document_id'))

    op.drop_table('knowledge_chunks')
    with op.batch_alter_table('analysis_metrics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_analysis_metrics_owner_user_id'))
        batch_op.drop_index(batch_op.f('ix_analysis_metrics_outcome'))
        batch_op.drop_index(batch_op.f('ix_analysis_metrics_created_at'))

    op.drop_table('analysis_metrics')
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_sessions_token_hash'))

    op.drop_table('user_sessions')
    with op.batch_alter_table('resumes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_resumes_user_id'))

    op.drop_table('resumes')
    with op.batch_alter_table('knowledge_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_knowledge_documents_owner_user_id'))

    op.drop_table('knowledge_documents')
    with op.batch_alter_table('file_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_file_assets_user_id'))
        batch_op.drop_index(batch_op.f('ix_file_assets_sha256'))

    op.drop_table('file_assets')
    with op.batch_alter_table('evaluation_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evaluation_runs_started_at'))
        batch_op.drop_index(batch_op.f('ix_evaluation_runs_owner_user_id'))

    op.drop_table('evaluation_runs')
    with op.batch_alter_table('evaluation_results', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evaluation_results_run_id'))
        batch_op.drop_index(batch_op.f('ix_evaluation_results_owner_user_id'))

    op.drop_table('evaluation_results')
    op.drop_table('career_profiles')
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_events_user_id'))
        batch_op.drop_index(batch_op.f('ix_audit_events_event_type'))
        batch_op.drop_index(batch_op.f('ix_audit_events_created_at'))

    op.drop_table('audit_events')
    with op.batch_alter_table('application_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_application_records_workflow_id'))
        batch_op.drop_index(batch_op.f('ix_application_records_owner_user_id'))

    op.drop_table('application_records')
    with op.batch_alter_table('analysis_step_metrics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_analysis_step_metrics_workflow_id'))
        batch_op.drop_index(batch_op.f('ix_analysis_step_metrics_step_key'))
        batch_op.drop_index(batch_op.f('ix_analysis_step_metrics_owner_user_id'))
        batch_op.drop_index(batch_op.f('ix_analysis_step_metrics_created_at'))

    op.drop_table('analysis_step_metrics')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_normalized_email'))

    op.drop_table('users')
    op.drop_table('migration_runs')
    with op.batch_alter_table('auth_login_attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_login_attempts_subject_hash'))
        batch_op.drop_index(batch_op.f('ix_auth_login_attempts_client_hash'))

    op.drop_table('auth_login_attempts')
