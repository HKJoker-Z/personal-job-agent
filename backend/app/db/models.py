"""Version 2 ORM model set, including faithful models of Version 1.9 tables."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect as sa_inspect,
    literal_column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','user')", name="role_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(120))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    user: Mapped[User] = relationship()


class AuthLoginAttempt(Base):
    __tablename__ = "auth_login_attempts"
    __table_args__ = (UniqueConstraint("subject_hash", "client_hash"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    client_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(30), default="success", nullable=False)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class CareerProfile(TimestampMixin, Base):
    __tablename__ = "career_profiles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    headline: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    professional_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    current_location: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    public_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    linkedin_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    github_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    completeness_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ProfileOwnedMixin(TimestampMixin):
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("career_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    verification_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ProfileExperience(ProfileOwnedMixin, Base):
    __tablename__ = "profile_experiences"
    __table_args__ = (
        CheckConstraint("verification_status IN ('draft','needs_review','confirmed')", name="verification_valid"),
    )

    company: Mapped[str] = mapped_column(String(240), nullable=False)
    role_title: Mapped[str] = mapped_column(String(240), nullable=False)
    location: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    achievements: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    skills: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)


class ProfileEducation(ProfileOwnedMixin, Base):
    __tablename__ = "profile_educations"

    institution: Mapped[str] = mapped_column(String(240), nullable=False)
    degree: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    field_of_study: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    location: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    grade: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class ProfileProject(ProfileOwnedMixin, Base):
    __tablename__ = "profile_projects"

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    role: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    technologies: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    achievements: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    metrics: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    project_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    repository_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)


class ProfileSkill(ProfileOwnedMixin, Base):
    __tablename__ = "profile_skills"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    proficiency: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    years_experience: Mapped[float | None] = mapped_column(Float)
    last_used_at: Mapped[date | None] = mapped_column(Date)


class ProfileLanguage(ProfileOwnedMixin, Base):
    __tablename__ = "profile_languages"

    language: Mapped[str] = mapped_column(String(120), nullable=False)
    proficiency: Mapped[str] = mapped_column(String(80), nullable=False)


class ProfileCertification(ProfileOwnedMixin, Base):
    __tablename__ = "profile_certifications"

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    issuer: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    credential_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    credential_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class ProfilePreference(TimestampMixin, Base):
    __tablename__ = "profile_preferences"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("career_profiles.id", ondelete="CASCADE"), unique=True)
    target_roles: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    target_locations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    employment_types: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    work_modes: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    minimum_salary: Mapped[int | None] = mapped_column(BigInteger)
    salary_currency: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    salary_period: Mapped[str] = mapped_column(String(30), default="annual", nullable=False)
    work_authorization: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    sponsorship_required: Mapped[bool | None] = mapped_column(Boolean)
    willing_to_relocate: Mapped[bool | None] = mapped_column(Boolean)
    excluded_role_keywords: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class ProfileRevision(Base):
    __tablename__ = "profile_revisions"
    __table_args__ = (UniqueConstraint("profile_id", "revision_number"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("career_profiles.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class FileAsset(Base):
    __tablename__ = "file_assets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    target_role: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    active_version_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("resume_versions.id", use_alter=True, name="fk_resumes_active_version_id_resume_versions"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "version_number"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    resume_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("resume_versions.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
    source_file_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("file_assets.id", ondelete="RESTRICT"))
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    parsed_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    change_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("salary_min IS NULL OR salary_min >= 0", name="salary_min_nonnegative"),
        CheckConstraint("salary_max IS NULL OR salary_max >= 0", name="salary_max_nonnegative"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min",
            name="salary_range_valid",
        ),
        CheckConstraint("length(description) <= 200000", name="description_length_valid"),
        CheckConstraint(
            "status IN ('new','reviewed','shortlisted','ignored','closed','archived')",
            name="status_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_name: Mapped[str | None] = mapped_column(String(300))
    normalized_company_name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    normalized_title: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    location: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    normalized_location: Mapped[str] = mapped_column(String(300), index=True, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    description_text_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    external_reference: Mapped[str | None] = mapped_column(String(500))
    employment_type: Mapped[str | None] = mapped_column(String(80))
    work_mode: Mapped[str | None] = mapped_column(String(80))
    seniority: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(200))
    salary_min: Mapped[int | None] = mapped_column(BigInteger)
    salary_max: Mapped[int | None] = mapped_column(BigInteger)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(30))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


JOB_ACTIVE_DEDUP_UNIQUE = Index(
    "uq_jobs_owner_deduplication_key_active",
    Job.__table__.c.owner_user_id,
    Job.__table__.c.deduplication_key,
    unique=True,
    postgresql_where=Job.__table__.c.archived_at.is_(None),
    sqlite_where=Job.__table__.c.archived_at.is_(None),
)
Job.__table__.append_constraint(JOB_ACTIVE_DEDUP_UNIQUE)


class JobSource(Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        CheckConstraint("source_type IN ('manual','url','pdf','docx','csv','migrated')", name="source_type_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    original_url: Mapped[str | None] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    external_id: Mapped[str | None] = mapped_column(String(500))
    file_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("file_assets.id", ondelete="RESTRICT"), index=True
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status_summary: Mapped[str | None] = mapped_column(String(80))
    media_type: Mapped[str | None] = mapped_column(String(160))
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class JobRequirement(TimestampMixin, Base):
    __tablename__ = "job_requirements"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_valid"),
        CheckConstraint("evidence_start IS NULL OR evidence_start >= 0", name="evidence_start_valid"),
        CheckConstraint(
            "evidence_end IS NULL OR evidence_start IS NULL OR evidence_end >= evidence_start",
            name="evidence_end_valid",
        ),
        CheckConstraint("category IN ('skill','education','experience','language','certification','location','work_authorization','responsibility','benefit','other')", name="category_valid"),
        CheckConstraint("requirement_type IN ('required','preferred','informational','hard_filter')", name="requirement_type_valid"),
        CheckConstraint("extraction_source IN ('deterministic','llm','user')", name="extraction_source_valid"),
        CheckConstraint("verification_status IN ('needs_review','confirmed','rejected')", name="verification_status_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    requirement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    minimum_years: Mapped[float | None] = mapped_column(Float)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_start: Mapped[int | None] = mapped_column(Integer)
    evidence_end: Mapped[int | None] = mapped_column(Integer)
    extraction_source: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), default="needs_review", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class JobDuplicateCandidate(Base):
    __tablename__ = "job_duplicate_candidates"
    __table_args__ = (
        CheckConstraint("job_id <> candidate_job_id", name="jobs_different"),
        CheckConstraint("similarity_score >= 0 AND similarity_score <= 1", name="similarity_valid"),
        CheckConstraint("match_type IN ('exact','near')", name="match_type_valid"),
        CheckConstraint("status IN ('pending','confirmed_duplicate','not_duplicate','dismissed')", name="status_valid"),
        UniqueConstraint("owner_user_id", "job_id", "candidate_job_id", name="uq_job_duplicate_pair"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    match_type: Mapped[str] = mapped_column(String(30), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint("current_stage IN ('saved','shortlisted','preparing','ready_to_apply','applied','assessment','interview','final_interview','offer','accepted','rejected','withdrawn','closed')", name="stage_valid"),
        CheckConstraint("priority IN ('low','normal','high','urgent')", name="priority_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    current_stage: Mapped[str] = mapped_column(String(40), default="saved", index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True, nullable=False)
    resume_version_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("resume_versions.id", ondelete="RESTRICT"), index=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expected_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


APPLICATION_ACTIVE_UNIQUE = Index(
    "uq_applications_owner_job_active",
    Application.__table__.c.owner_user_id,
    Application.__table__.c.job_id,
    unique=True,
    postgresql_where=Application.__table__.c.archived_at.is_(None),
    sqlite_where=Application.__table__.c.archived_at.is_(None),
)
Application.__table__.append_constraint(APPLICATION_ACTIVE_UNIQUE)


class ApplicationStageHistory(Base):
    __tablename__ = "application_stage_history"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    to_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    changed_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    revision_before: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_after: Mapped[int] = mapped_column(Integer, nullable=False)


class ApplicationNote(TimestampMixin, Base):
    __tablename__ = "application_notes"
    __table_args__ = (
        CheckConstraint("note_type IN ('general','recruiter','interview','follow_up','outcome','private')", name="note_type_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(30), default="general", index=True, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ApplicationTask(TimestampMixin, Base):
    __tablename__ = "application_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('pending','in_progress','completed','cancelled')", name="status_valid"),
        CheckConstraint("priority IN ('low','normal','high','urgent')", name="priority_valid"),
        CheckConstraint("task_type IN ('review_job','tailor_resume','prepare_application','submit_application','follow_up','assessment','interview_preparation','interview','document_request','other')", name="task_type_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    application_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    job_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class JobImportRun(Base):
    __tablename__ = "job_import_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    import_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    safe_error_summary: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobMergeHistory(Base):
    __tablename__ = "job_merge_history"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    source_job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    field_selection: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    merged_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MigrationRun(Base):
    __tablename__ = "migration_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    migration_version: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    row_count_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    verification_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ApplicationRecord(Base):
    __tablename__ = "application_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    company_name: Mapped[str] = mapped_column(String(500), default="Unknown Company", nullable=False)
    job_title: Mapped[str] = mapped_column(String(500), default="Unknown Position", nullable=False)
    job_url: Mapped[str | None] = mapped_column(Text)
    resume_filename: Mapped[str | None] = mapped_column(String(255))
    application_status: Mapped[str] = mapped_column(String(40), default="Saved", nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    match_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    job_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    matched_skills: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    missing_skills: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    resume_suggestions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    cover_letter: Mapped[str] = mapped_column(Text, default="", nullable=False)
    scoring_breakdown: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    ats_analysis: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    upgraded_resume_bullets: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    rag_mode: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    rag_sources: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(128), index=True)
    workflow_steps: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    workflow_duration_ms: Mapped[float | None] = mapped_column(Float)
    workflow_duration_us: Mapped[int | None] = mapped_column(BigInteger)
    next_action: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    next_action_decision: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    next_action_decision_notes: Mapped[str | None] = mapped_column(Text)
    next_action_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    security_scan: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    security_status: Mapped[str] = mapped_column(String(40), default="not_available", nullable=False)
    security_policy_version: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(500))
    content_preview: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalysisMetric(Base):
    __tablename__ = "analysis_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(50), index=True)
    workflow_status: Mapped[str | None] = mapped_column(String(50))
    workflow_duration_ms: Mapped[float | None] = mapped_column(Float)
    workflow_duration_us: Mapped[int | None] = mapped_column(BigInteger)
    llm_duration_ms: Mapped[float | None] = mapped_column(Float)
    rag_retrieval_duration_ms: Mapped[float | None] = mapped_column(Float)
    rag_mode: Mapped[str | None] = mapped_column(String(30))
    rag_source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rag_hit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rag_reconciliation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    security_status: Mapped[str | None] = mapped_column(String(40))
    security_risk_level: Mapped[str | None] = mapped_column(String(40))
    prompt_injection_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sensitive_data_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_leakage_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pii_email_redaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pii_phone_redaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pii_address_redaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    security_finding_codes: Mapped[str | None] = mapped_column(Text)
    json_parse_success: Mapped[int | None] = mapped_column(Integer)
    saved_to_history: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    application_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("application_records.id", ondelete="SET NULL"))
    next_action: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_stage: Mapped[str | None] = mapped_column(String(120))
    source_type: Mapped[str | None] = mapped_column(String(40))


class AnalysisStepMetric(Base):
    __tablename__ = "analysis_step_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(String(128), index=True)
    step_key: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    duration_us: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True)
    suite_name: Mapped[str] = mapped_column(String(120))
    suite_version: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    error_cases: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    case_id: Mapped[str] = mapped_column(String(128))
    case_name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    checks_json: Mapped[str | None] = mapped_column(Text)
    failure_summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@event.listens_for(ResumeVersion, "before_update")
def prevent_resume_version_content_update(_mapper: object, _connection: object, target: ResumeVersion) -> None:
    state = sa_inspect(target)
    immutable_fields = (
        "resume_id",
        "version_number",
        "parent_version_id",
        "content_json",
        "parsed_text",
        "schema_version",
        "source_file_id",
        "source_type",
        "change_summary",
        "created_by",
        "created_at",
    )
    if any(state.attrs[field].history.has_changes() for field in immutable_fields):
        raise ValueError("Resume Version content is immutable; create a new Version instead.")


@event.listens_for(ApplicationStageHistory, "before_update")
@event.listens_for(ApplicationStageHistory, "before_delete")
def prevent_stage_history_mutation(_mapper: object, _connection: object, _target: ApplicationStageHistory) -> None:
    raise ValueError("Application Stage History is append-only.")


KNOWLEDGE_FTS_INDEX = Index(
    "ix_knowledge_chunks_fts",
    func.to_tsvector(literal_column("'simple'"), KnowledgeChunk.__table__.c.content),
    postgresql_using="gin",
)
KnowledgeChunk.__table__.append_constraint(KNOWLEDGE_FTS_INDEX)
KNOWLEDGE_FTS_INDEX.ddl_if(dialect="postgresql")
