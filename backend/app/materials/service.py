"""Grounded Package generation, immutable editing, validation, review, and approval."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationMaterial,
    ApplicationMaterialVersion,
    ApplicationPackage,
    CareerProfile,
    Job,
    JobMatchAnalysis,
    JobMatchEvidence,
    JobRequirement,
    MaterialEvidenceLink,
    MaterialReview,
    ProfileRevision,
    Resume,
    ResumeVersion,
    utc_now,
)
from app.db.repositories.auth import AuthRepository
from app.materials.grounding import EvidenceSource, validate_claims, validation_summary
from app.materials.generator import generate_grounded_material
from app.materials.repository import MaterialRepository
from security_utils import scan_untrusted_text


class MaterialNotFound(RuntimeError):
    pass


class MaterialConflict(RuntimeError):
    pass


def _json(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _columns(value: object, excluded: set[str] | None = None) -> dict[str, object]:
    return {
        column.name: _json(getattr(value, column.name))
        for column in value.__table__.columns
        if column.name not in (excluded or set())
    }


def _flatten(value: object, *, blocked: set[str] | None = None) -> list[str]:
    values: list[str] = []
    blocked = blocked or set()
    if isinstance(value, str) and value.strip():
        values.append(value.strip())
    elif isinstance(value, (int, float, bool)):
        values.append(str(value))
    elif isinstance(value, dict):
        for key, child in value.items():
            if key not in blocked:
                values.extend(_flatten(child, blocked=blocked))
    elif isinstance(value, list):
        for child in value:
            values.extend(_flatten(child, blocked=blocked))
    return values


class MaterialService:
    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id
        self.repository = MaterialRepository(db)

    def create_package(self, application_id: UUID, values: dict[str, object]) -> dict[str, object]:
        application = self._application(application_id)
        job = self._job(application.job_id)
        resume = self._resume(UUID(str(values["source_resume_version_id"])))
        analysis = self._analysis(UUID(str(values["match_analysis_id"])))
        if analysis.job_id != job.id:
            raise MaterialConflict("Match Analysis does not belong to the Application Job.")
        if resume.status != "final":
            raise MaterialConflict("Application Packages require a finalized source Resume Version.")
        package = ApplicationPackage(
            owner_user_id=self.owner_id,
            application_id=application.id,
            job_id=job.id,
            source_profile_revision=analysis.profile_revision,
            source_job_revision=analysis.job_revision,
            source_resume_version_id=resume.id,
            source_match_analysis_id=analysis.id,
            title=str(values["title"]),
            status="draft",
        )
        self.db.add(package)
        self.db.flush()
        self._audit("application_package.created", package.id, {"application_id": str(application.id)})
        return self._package_detail(package)

    def packages(self, application_id: UUID) -> list[dict[str, object]]:
        self._application(application_id)
        return [self._package_summary(item) for item in self.repository.packages(self.owner_id, application_id)]

    def package(self, package_id: UUID) -> dict[str, object]:
        return self._package_detail(self._package(package_id))

    def update_package(self, package_id: UUID, expected_revision: int, title: str) -> dict[str, object]:
        package = self._package(package_id, for_update=True)
        self._expect(package.revision, expected_revision)
        if package.status in {"approved", "archived"}:
            raise MaterialConflict("Approved or archived Packages cannot be edited.")
        package.title = title
        package.revision += 1
        self._audit("application_package.updated", package.id, {"revision": package.revision})
        return self._package_detail(package)

    def archive_package(self, package_id: UUID, expected_revision: int) -> dict[str, object]:
        package = self._package(package_id, for_update=True)
        self._expect(package.revision, expected_revision)
        package.status = "archived"
        package.revision += 1
        self._audit("application_package.archived", package.id)
        return self._package_detail(package)

    def approve_package(self, package_id: UUID, expected_revision: int) -> dict[str, object]:
        package = self._package(package_id, for_update=True)
        self._expect(package.revision, expected_revision)
        materials = self.repository.materials(self.owner_id, package.id)
        required = {"tailored_resume", "cover_letter"}
        accepted: set[str] = set()
        for material in materials:
            if material.material_type not in required or material.status != "approved" or not material.active_version_id:
                continue
            version = self.repository.version(self.owner_id, material.active_version_id)
            if version and version.finalized_at and version.validation_status == "valid" and version.unsupported_claim_count == 0:
                accepted.add(material.material_type)
        if accepted != required:
            raise MaterialConflict("A finalized, approved, fully supported Resume and Cover Letter are required.")
        package.status = "approved"
        package.approved_at = utc_now()
        package.approved_by_user_id = self.owner_id
        package.revision += 1
        self._audit("application_package.approved", package.id, {"revision": package.revision})
        return self._package_detail(package)

    def generate_resume(self, package_id: UUID, force_new: bool = False) -> dict[str, object]:
        started = time.monotonic()
        package = self._package(package_id)
        resume = self._resume(package.source_resume_version_id)
        if resume.status != "final":
            raise MaterialConflict("Tailored Resume generation requires a finalized source Resume Version.")
        analysis = self._analysis(package.source_match_analysis_id)
        evidence = list(self.db.scalars(select(JobMatchEvidence).where(
            JobMatchEvidence.analysis_id == analysis.id,
            JobMatchEvidence.evidence_kind.in_(("matched", "partial", "hard_filter")),
            JobMatchEvidence.source_id.is_not(None),
        )))
        content = dict(resume.content_json)
        content.pop("header", None)  # Contact details are merged locally by export, never sent to a model.
        # Build the model/validation text only from Resume prose. Snapshot IDs and
        # keyword bookkeeping remain local JSON metadata and are never interpreted
        # as candidate claims.
        text_values = _flatten(content, blocked={"schema_version", "tailoring"})
        text = "\n".join(text_values)[:50_000]
        content["tailoring"] = {
            "selected_evidence_ids": [str(item.id) for item in evidence],
            "keyword_coverage": sorted({item.dimension for item in evidence if item.contribution > 0}),
            "missing_keywords": sorted({item.dimension for item in self._analysis_evidence(analysis.id) if item.evidence_kind in {"missing", "unknown"}}),
            "source_resume_version_id": str(resume.id),
        }
        content, text, model_metadata = generate_grounded_material(
            material_type="tailored_resume", seed_text=text, seed_json=content,
            evidence=[item.text for item in self._evidence_sources(package)],
        )
        material = self._material_for_generation(package, "tailored_resume", "Tailored Resume", force_new)
        version = self._create_version(
            material, "generated", content, text,
            {**model_metadata, "duration_ms": round((time.monotonic() - started) * 1000, 2), "source_resume_version_id": str(resume.id)},
        )
        return self._version_detail(version)

    def generate_cover_letter(self, package_id: UUID, force_new: bool = False) -> dict[str, object]:
        started = time.monotonic()
        package = self._package(package_id)
        job = self._job(package.job_id)
        analysis = self._analysis(package.source_match_analysis_id)
        matched = [item for item in self._analysis_evidence(analysis.id) if item.evidence_kind == "matched"][:3]
        role = job.title or "the advertised role"
        company = job.company_name or "your organization"
        strengths = ", ".join(dict.fromkeys(item.dimension.replace("_", " ") for item in matched))
        evidence_sentence = (
            f"My confirmed experience provides relevant evidence in {strengths}." if strengths
            else "I would welcome the opportunity to discuss how my confirmed experience relates to the role."
        )
        text = (
            f"Dear Hiring Team,\n\nI am applying for {role} at {company}. "
            f"{evidence_sentence}\n\nI have kept this draft limited to facts in my confirmed profile and source resume. "
            "Thank you for considering my application.\n\nSincerely"
        )
        content = {"sections": {"opening": f"Application for {role}", "body": evidence_sentence, "closing": "Thank you for considering my application."}}
        content, text, model_metadata = generate_grounded_material(
            material_type="cover_letter", seed_text=text, seed_json=content,
            evidence=[item.text for item in self._evidence_sources(package)],
        )
        material = self._material_for_generation(package, "cover_letter", "Cover Letter", force_new)
        version = self._create_version(
            material, "generated", content, text,
            {**model_metadata, "duration_ms": round((time.monotonic() - started) * 1000, 2), "selected_evidence_count": len(matched)},
        )
        return self._version_detail(version)

    def generate_answers(self, package_id: UUID, questions: list[dict[str, str]]) -> list[dict[str, object]]:
        package = self._package(package_id)
        analysis = self._analysis(package.source_match_analysis_id)
        revision = self._profile_revision(analysis)
        preferences = dict(revision.snapshot.get("preferences") or {})
        matched = [item for item in self._analysis_evidence(analysis.id) if item.evidence_kind == "matched"]
        results: list[dict[str, object]] = []
        for item in questions:
            question = item["question"]
            scan = scan_untrusted_text(question, "job_description")
            normalized = question.casefold()
            state = "draft"
            if scan.get("prompt_injection_detected"):
                answer, state = "This question requires manual review because it contains instruction-like content.", "needs_user_input"
            elif "work authorization" in normalized or "sponsor" in normalized:
                authorization = str(preferences.get("work_authorization") or "").strip()
                if authorization:
                    answer = authorization
                else:
                    answer, state = "Work authorization has not been confirmed.", "needs_user_input"
            elif "salary" in normalized or "compensation" in normalized:
                minimum = preferences.get("minimum_salary")
                currency = preferences.get("salary_currency")
                if minimum is not None and currency:
                    answer = f"My confirmed minimum compensation preference is {currency} {minimum}."
                else:
                    answer, state = "Salary expectations require user input.", "needs_user_input"
            elif matched:
                dimensions = ", ".join(dict.fromkeys(value.dimension.replace("_", " ") for value in matched[:3]))
                answer = f"My confirmed evidence most relevant to this role is in {dimensions}."
            else:
                answer, state = "There is not enough confirmed evidence to answer this question.", "needs_user_input"
            material = ApplicationMaterial(
                package_id=package.id, owner_user_id=self.owner_id, material_type="application_answer",
                title=question[:240], status="draft",
            )
            self.db.add(material)
            self.db.flush()
            content = {"key": item["key"], "question": question, "answer": answer, "answer_status": state}
            model_metadata: dict[str, object] = {
                "provider": "deterministic-test" if os.getenv("APP_ENV") == "test" else "deterministic-fallback",
                "prompt_injection_detected": bool(scan.get("prompt_injection_detected")),
            }
            if state == "draft":
                content, answer, generated_metadata = generate_grounded_material(
                    material_type="application_answer", seed_text=answer,
                    seed_json=content,
                    evidence=[value.text for value in self._evidence_sources(package)],
                )
                model_metadata.update(generated_metadata)
            version = self._create_version(
                material, "generated", content, answer, model_metadata,
            )
            if state == "needs_user_input":
                version.validation_status = "needs_user_input"
            results.append(self._version_detail(version))
        return results

    def material(self, material_id: UUID) -> dict[str, object]:
        material = self._material(material_id)
        return self._material_detail(material)

    def versions(self, material_id: UUID) -> list[dict[str, object]]:
        self._material(material_id)
        return [self._version_detail(item) for item in self.repository.versions(self.owner_id, material_id)]

    def edit(self, material_id: UUID, expected_active: UUID, content_json: dict[str, object], content_text: str, summary: str) -> dict[str, object]:
        material = self._material(material_id, for_update=True)
        if material.active_version_id != expected_active:
            raise MaterialConflict("Material was modified by another request.")
        parent = self.repository.version(self.owner_id, expected_active)
        if not parent or parent.material_id != material.id:
            raise MaterialNotFound("Material Version not found.")
        version = self._create_version(
            material, "user_edit", content_json, content_text,
            {"change_summary": summary, "parent_version_id": str(parent.id)}, parent.id,
        )
        material.status = "draft"
        return self._version_detail(version)

    def validate(self, version_id: UUID) -> dict[str, object]:
        version = self._version(version_id)
        self._validate_version(version)
        self._audit("material.validated", version.id, {
            "validation_status": version.validation_status,
            "unsupported_claim_count": version.unsupported_claim_count,
            "evidence_coverage": version.evidence_coverage,
        })
        return self._version_detail(version)

    def evidence(self, version_id: UUID) -> list[dict[str, object]]:
        self._version(version_id)
        return [_columns(item, {"material_version_id"}) for item in self.repository.evidence(self.owner_id, version_id)]

    def confirm_evidence(self, version_id: UUID, evidence_id: UUID) -> dict[str, object]:
        version = self._version(version_id)
        if version.finalized_at is not None:
            raise MaterialConflict("Finalized Material evidence cannot be changed.")
        link = self.repository.evidence_link(
            self.owner_id, version_id, evidence_id, for_update=True,
        )
        if not link:
            raise MaterialNotFound("Material Evidence Link not found.")
        if link.support_status not in {"unsupported", "partially_supported", "needs_user_input"}:
            raise MaterialConflict("Only an unresolved claim can be explicitly confirmed.")
        link.support_status = "user_confirmed"
        link.source_type = "user_confirmation"
        link.source_id = str(self.owner_id)
        link.source_revision = None
        link.evidence_summary = "Explicitly confirmed by the owning user for this Material Version only."
        links = self.repository.evidence(self.owner_id, version_id)
        status, unsupported, coverage = validation_summary([
            {"support_status": item.support_status} for item in links
        ])
        version.validation_status = status
        version.unsupported_claim_count = unsupported
        version.evidence_coverage = coverage
        self._audit("material.claim.user_confirmed", version.id, {
            "evidence_link_id": str(link.id), "validation_status": status,
            "unsupported_claim_count": unsupported,
        })
        return self._version_detail(version)

    def review(self, version_id: UUID, decision: str, notes: str) -> dict[str, object]:
        version = self._version(version_id)
        material = self._material(version.material_id, for_update=True)
        if decision == "approve":
            if version.validation_status != "valid" or version.unsupported_claim_count:
                raise MaterialConflict("Only a fully supported validated Material Version can be approved.")
            material.status = "approved"
        elif decision == "request_changes":
            material.status = "in_review"
        else:
            material.status = "draft"
        review = MaterialReview(
            material_version_id=version.id, reviewer_user_id=self.owner_id,
            decision=decision, notes=notes,
        )
        self.db.add(review)
        self.db.flush()
        self._audit("material.reviewed", version.id, {"decision": decision})
        return {"material": self._material_detail(material), "review": _columns(review, {"notes"})}

    def finalize(self, version_id: UUID) -> dict[str, object]:
        version = self._version(version_id)
        material = self._material(version.material_id, for_update=True)
        if material.active_version_id != version.id:
            raise MaterialConflict("Only the active Material Version can be finalized.")
        if version.validation_status != "valid" or version.unsupported_claim_count != 0:
            raise MaterialConflict("Validation must complete with no unsupported claims before finalization.")
        if material.status != "approved":
            raise MaterialConflict("Material review approval is required before finalization.")
        if version.finalized_at is None:
            version.finalized_at = utc_now()
            self._audit("material.finalized", version.id)
        return self._version_detail(version)

    def _create_version(
        self, material: ApplicationMaterial, source_type: str,
        content_json: dict[str, object], content_text: str,
        metadata: dict[str, object], parent_id: UUID | None = None,
    ) -> ApplicationMaterialVersion:
        version = ApplicationMaterialVersion(
            material_id=material.id, version_number=self.repository.next_version(material.id),
            parent_version_id=parent_id or material.active_version_id, source_type=source_type,
            content_json=content_json, content_text=content_text,
            model_provider=str(metadata.get("provider") or "user"),
            model_name=str(metadata.get("model")) if metadata.get("model") else None,
            prompt_version=str(metadata.get("prompt_version") or "grounded-material-v1"), generation_metadata=metadata,
            validation_status="pending", unsupported_claim_count=0, evidence_coverage=0,
            created_by_user_id=self.owner_id,
        )
        self.db.add(version)
        self.db.flush()
        material.active_version_id = version.id
        material.status = "draft"
        self._validate_version(version)
        self._audit("material.version.created", version.id, {
            "material_type": material.material_type, "version_number": version.version_number,
            "provider": version.model_provider, "prompt_version": version.prompt_version,
            "validation_status": version.validation_status,
            "unsupported_claim_count": version.unsupported_claim_count,
        })
        return version

    def _validate_version(self, version: ApplicationMaterialVersion) -> None:
        material = self._material(version.material_id)
        package = self._package(material.package_id)
        links = validate_claims(version.content_text, self._evidence_sources(package))
        self.db.execute(delete(MaterialEvidenceLink).where(MaterialEvidenceLink.material_version_id == version.id))
        for values in links:
            self.db.add(MaterialEvidenceLink(material_version_id=version.id, **values))
        status, unsupported, coverage = validation_summary(links)
        version.validation_status = status
        version.unsupported_claim_count = unsupported
        version.evidence_coverage = coverage
        self.db.flush()

    def _evidence_sources(self, package: ApplicationPackage) -> list[EvidenceSource]:
        analysis = self._analysis(package.source_match_analysis_id)
        revision = self._profile_revision(analysis)
        resume = self._resume(package.source_resume_version_id)
        job = self._job(package.job_id)
        sources = [
            EvidenceSource("resume_version", str(resume.id), resume.version_number, resume.parsed_text or "\n".join(_flatten(resume.content_json))),
            EvidenceSource("job", str(job.id), job.revision, " ".join(filter(None, (job.company_name, job.title, job.location)))),
        ]
        blocked = {"phone", "public_email", "website", "linkedin_url", "github_url"}
        for resource in ("experiences", "projects", "skills", "educations", "languages", "certifications"):
            for item in list(revision.snapshot.get(resource) or []):
                if item.get("verification_status") == "confirmed":
                    sources.append(EvidenceSource(
                        f"profile_{resource.rstrip('s')}", str(item.get("id")) if item.get("id") else None,
                        revision.revision_number, " ".join(_flatten(item, blocked=blocked)),
                    ))
        preference = revision.snapshot.get("preferences")
        if preference:
            sources.append(EvidenceSource(
                "profile_preference", str(preference.get("id")) if preference.get("id") else None,
                revision.revision_number, " ".join(_flatten(preference, blocked=blocked)),
            ))
        return sources

    def _material_for_generation(self, package: ApplicationPackage, material_type: str, title: str, force_new: bool) -> ApplicationMaterial:
        material = None if force_new else self.repository.reusable_material(self.owner_id, package.id, material_type)
        if material and material.status == "approved":
            raise MaterialConflict("Create a new Material before regenerating an approved one.")
        if material is None:
            material = ApplicationMaterial(
                package_id=package.id, owner_user_id=self.owner_id,
                material_type=material_type, title=title, status="draft",
            )
            self.db.add(material)
            self.db.flush()
        return material

    def _application(self, application_id: UUID) -> Application:
        value = self.db.scalar(select(Application).where(
            Application.id == application_id, Application.owner_user_id == self.owner_id,
            Application.archived_at.is_(None),
        ))
        if not value:
            raise MaterialNotFound("Application not found.")
        return value

    def _job(self, job_id: UUID) -> Job:
        value = self.db.scalar(select(Job).where(Job.id == job_id, Job.owner_user_id == self.owner_id))
        if not value:
            raise MaterialNotFound("Job not found.")
        return value

    def _resume(self, version_id: UUID) -> ResumeVersion:
        value = self.db.scalar(select(ResumeVersion).join(
            Resume, Resume.id == ResumeVersion.resume_id
        ).where(
            ResumeVersion.id == version_id, Resume.user_id == self.owner_id,
            Resume.archived_at.is_(None),
        ))
        if not value:
            raise MaterialNotFound("Resume Version not found.")
        return value

    def _analysis(self, analysis_id: UUID) -> JobMatchAnalysis:
        value = self.db.scalar(select(JobMatchAnalysis).where(
            JobMatchAnalysis.id == analysis_id, JobMatchAnalysis.owner_user_id == self.owner_id,
            JobMatchAnalysis.status == "completed",
        ))
        if not value:
            raise MaterialNotFound("Match Analysis not found.")
        return value

    def _analysis_evidence(self, analysis_id: UUID) -> list[JobMatchEvidence]:
        return list(self.db.scalars(select(JobMatchEvidence).join(JobMatchAnalysis).where(
            JobMatchEvidence.analysis_id == analysis_id,
            JobMatchAnalysis.owner_user_id == self.owner_id,
        )))

    def _profile_revision(self, analysis: JobMatchAnalysis) -> ProfileRevision:
        value = self.db.scalar(select(ProfileRevision).join(CareerProfile).where(
            ProfileRevision.profile_id == analysis.profile_id,
            ProfileRevision.revision_number == analysis.profile_revision,
            CareerProfile.user_id == self.owner_id,
        ))
        if not value:
            raise MaterialNotFound("Profile Revision not found.")
        return value

    def _package(self, package_id: UUID, *, for_update: bool = False) -> ApplicationPackage:
        value = self.repository.package(self.owner_id, package_id, for_update=for_update)
        if not value:
            raise MaterialNotFound("Application Package not found.")
        return value

    def _material(self, material_id: UUID, *, for_update: bool = False) -> ApplicationMaterial:
        value = self.repository.material(self.owner_id, material_id, for_update=for_update)
        if not value:
            raise MaterialNotFound("Application Material not found.")
        return value

    def _version(self, version_id: UUID) -> ApplicationMaterialVersion:
        value = self.repository.version(self.owner_id, version_id)
        if not value:
            raise MaterialNotFound("Material Version not found.")
        return value

    @staticmethod
    def _expect(current: int, expected: int) -> None:
        if current != expected:
            raise MaterialConflict("Application Package was modified by another request.")

    def _package_summary(self, package: ApplicationPackage) -> dict[str, object]:
        return _columns(package, {"owner_user_id", "approved_by_user_id"})

    def _package_detail(self, package: ApplicationPackage) -> dict[str, object]:
        return {
            **self._package_summary(package),
            "materials": [self._material_detail(item) for item in self.repository.materials(self.owner_id, package.id)],
        }

    def _material_detail(self, material: ApplicationMaterial) -> dict[str, object]:
        return {
            **_columns(material, {"owner_user_id"}),
            "active_version": self._version_detail(self.repository.version(self.owner_id, material.active_version_id))
            if material.active_version_id else None,
        }

    def _version_detail(self, version: ApplicationMaterialVersion | None) -> dict[str, object] | None:
        if version is None:
            return None
        return {
            **_columns(version),
            "evidence": [_columns(item, {"material_version_id"}) for item in self.repository.evidence(self.owner_id, version.id)],
            "reviews": [_columns(item, {"notes"}) for item in self.repository.reviews(self.owner_id, version.id)],
        }

    def _audit(self, event: str, resource_id: UUID, metadata: dict[str, object] | None = None) -> None:
        AuthRepository(self.db).audit(
            event, user_id=self.owner_id, resource_type="application_material",
            resource_id=str(resource_id), safe_metadata=metadata or {},
        )
