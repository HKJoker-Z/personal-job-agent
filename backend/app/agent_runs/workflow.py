"""Idempotent execution of the asynchronous Application Package workflow."""

from __future__ import annotations

import socket
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent_runs.definitions import MODEL_STEPS, WORKFLOW_TYPE, validate_queue_payload
from app.agent_runs.service import AgentBudgetExceeded, AgentConflict, AgentRunService
from app.db.models import (
    AgentRun,
    AgentStep,
    ApplicationMaterial,
    ApplicationMaterialVersion,
    ApplicationPackage,
    JobMatchEvidence,
)
from app.db.session import session_factory
from app.materials.generator import MaterialGenerationError, MaterialGenerationTimeout
from app.materials.service import MaterialConflict, MaterialNotFound, MaterialService


class PermanentWorkflowError(RuntimeError):
    pass


class TransientWorkflowError(RuntimeError):
    pass


def execute_delivery(payload: dict[str, Any], worker_id: str) -> bool:
    """Claim, execute, and transactionally finish one safe-ID-only delivery."""
    safe = validate_queue_payload(payload)
    run_id = UUID(safe["run_id"])
    step_id = UUID(safe["step_id"])
    factory = session_factory()
    claim_db = factory()
    try:
        claim = AgentRunService(claim_db).claim_step(
            run_id, step_id, worker_id, delivery_attempt=int(safe["attempt"]),
        )
        claim_db.commit()
    except Exception:
        claim_db.rollback()
        raise
    finally:
        claim_db.close()
    if claim is None:
        return False

    db = factory()
    try:
        service = AgentRunService(db)
        run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        step = db.scalar(select(AgentStep).where(AgentStep.id == step_id).with_for_update())
        if run is None or step is None:
            raise PermanentWorkflowError("Agent Run Step is unavailable.")
        if step.step_key in MODEL_STEPS:
            projected_input_tokens = 6300
            projected_output_tokens = service.settings.model_max_output_tokens
            projected_tokens = projected_input_tokens + projected_output_tokens
            projected_cost = (
                projected_input_tokens * service.settings.model_input_cost_per_million_usd
                + projected_output_tokens * service.settings.model_output_cost_per_million_usd
            ) / 1_000_000
            service.ensure_budget(run, step, projected_tokens, projected_cost)
            if service.high_cost_approval_required(run, step, projected_cost):
                requested = service.request_high_cost_approval(
                    run.id, step.id, str(claim["execution_token"]),
                )
                db.commit()
                return requested
        output, usage = _execute_step(db, run, step)
        completed = service.complete_step(run.id, step.id, str(claim["execution_token"]), output, usage)
        db.commit()
        return completed
    except Exception as exc:
        db.rollback()
        failure_db = factory()
        try:
            code, summary, retriable = classify_error(exc)
            AgentRunService(failure_db).fail_step(
                run_id, step_id, str(claim["execution_token"]), code, summary, retriable,
                _failure_usage(exc),
            )
            failure_db.commit()
        except Exception:
            failure_db.rollback()
            raise
        finally:
            failure_db.close()
        return False
    finally:
        db.close()


def _execute_step(db: Session, run: AgentRun, step: AgentStep) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if run.package_id is None:
        raise PermanentWorkflowError("Application Package reference is missing.")
    package = db.scalar(select(ApplicationPackage).where(
        ApplicationPackage.id == run.package_id,
        ApplicationPackage.owner_user_id == run.owner_user_id,
    ))
    if package is None:
        raise PermanentWorkflowError("Application Package is unavailable.")
    materials = MaterialService(db, run.owner_user_id)
    key = step.step_key
    if key == "validate_request":
        if package.status == "archived":
            raise PermanentWorkflowError("Archived Application Packages cannot be generated.")
        return {"package_id": package.id, "application_id": package.application_id}, None
    if key == "snapshot_profile":
        return {"profile_revision": package.source_profile_revision}, None
    if key == "snapshot_job":
        return {"job_id": package.job_id, "job_revision": package.source_job_revision}, None
    if key == "load_resume":
        return {"resume_version_id": package.source_resume_version_id}, None
    if key == "run_or_reuse_match":
        return {"match_analysis_id": package.source_match_analysis_id, "reused": True}, None
    if key == "select_grounded_evidence":
        count = db.scalar(select(func.count()).select_from(JobMatchEvidence).where(
            JobMatchEvidence.analysis_id == package.source_match_analysis_id,
            JobMatchEvidence.verification_status == "confirmed",
        )) or 0
        return {"match_analysis_id": package.source_match_analysis_id, "evidence_count": count}, None
    if key == "generate_tailored_resume":
        version = materials.generate_resume(package.id, force_new=False)
        return _version_refs(version), _usage(version)
    if key == "validate_tailored_resume":
        version = _active_version(db, package.id, run.owner_user_id, "tailored_resume")
        validated = materials.validate(version.id)
        if validated["validation_status"] != "valid" or validated["unsupported_claim_count"]:
            raise PermanentWorkflowError("Tailored Resume contains unsupported or unvalidated claims.")
        return _version_refs(validated), None
    if key == "request_resume_approval":
        version = _active_version(db, package.id, run.owner_user_id, "tailored_resume")
        return {"material_id": version.material_id, "material_version_id": version.id}, None
    if key == "generate_cover_letter":
        version = materials.generate_cover_letter(package.id, force_new=False)
        return _version_refs(version), _usage(version)
    if key == "validate_cover_letter":
        version = _active_version(db, package.id, run.owner_user_id, "cover_letter")
        validated = materials.validate(version.id)
        if validated["validation_status"] != "valid" or validated["unsupported_claim_count"]:
            raise PermanentWorkflowError("Cover Letter contains unsupported or unvalidated claims.")
        return _version_refs(validated), None
    if key == "request_cover_letter_approval":
        version = _active_version(db, package.id, run.owner_user_id, "cover_letter")
        return {"material_id": version.material_id, "material_version_id": version.id}, None
    if key == "generate_application_answers":
        existing = db.scalars(select(ApplicationMaterialVersion).join(
            ApplicationMaterial,
            ApplicationMaterialVersion.material_id == ApplicationMaterial.id,
        ).where(
            ApplicationMaterial.package_id == package.id,
            ApplicationMaterial.owner_user_id == run.owner_user_id,
            ApplicationMaterial.material_type == "application_answer",
        ).order_by(ApplicationMaterialVersion.created_at)).all()
        if existing:
            return {"material_version_ids": [item.id for item in existing], "reused": True}, None
        generated = materials.generate_answers(package.id, [{
            "key": "workflow-role-interest",
            "question": "Why are you interested in this role?",
        }])
        return {"material_version_ids": [item["id"] for item in generated]}, _usage(generated[0]) if generated else None
    if key == "validate_application_answers":
        versions = db.scalars(select(ApplicationMaterialVersion).join(
            ApplicationMaterial,
            ApplicationMaterialVersion.material_id == ApplicationMaterial.id,
        ).where(
            ApplicationMaterial.package_id == package.id,
            ApplicationMaterial.owner_user_id == run.owner_user_id,
            ApplicationMaterial.material_type == "application_answer",
        )).all()
        validated_ids: list[UUID] = []
        for version in versions:
            value = materials.validate(version.id)
            if value["validation_status"] == "invalid" or value["unsupported_claim_count"]:
                raise PermanentWorkflowError("An Application Answer contains unsupported claims.")
            validated_ids.append(version.id)
        return {"material_version_ids": validated_ids}, None
    if key == "build_package_summary":
        return {"package_id": package.id}, None
    if key == "request_package_approval":
        return {"package_id": package.id}, None
    if key == "finalize_run":
        if package.status != "approved":
            raise PermanentWorkflowError("Application Package approval is required before completion.")
        return {"package_id": package.id}, None
    if key.startswith("wait_"):
        raise AgentConflict("Approval wait steps are resumed only by an approval decision.")
    raise PermanentWorkflowError("Unknown workflow step.")


def _active_version(
    db: Session, package_id: UUID, owner_id: UUID, material_type: str,
) -> ApplicationMaterialVersion:
    material = db.scalar(select(ApplicationMaterial).where(
        ApplicationMaterial.package_id == package_id,
        ApplicationMaterial.owner_user_id == owner_id,
        ApplicationMaterial.material_type == material_type,
    ).order_by(ApplicationMaterial.created_at.desc()))
    if material is None or material.active_version_id is None:
        raise PermanentWorkflowError("Generated Application Material is unavailable.")
    version = db.get(ApplicationMaterialVersion, material.active_version_id)
    if version is None:
        raise PermanentWorkflowError("Generated Application Material Version is unavailable.")
    return version


def _version_refs(version: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_id": version["material_id"],
        "material_version_id": version["id"],
    }


def _usage(version: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(version.get("generation_metadata") or {})
    tokens = dict(metadata.get("token_metadata") or {})
    return {
        "provider": metadata.get("provider") or version.get("model_provider") or "unknown",
        "model": metadata.get("model") or version.get("model_name") or "unknown",
        "input_tokens": int(tokens.get("input_tokens") or 0),
        "output_tokens": int(tokens.get("output_tokens") or 0),
        "total_tokens": int(tokens.get("total_tokens") or 0),
        "estimated_cost_usd": Decimal(str(tokens.get("estimated_cost_usd") or 0)),
    }


def classify_error(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, (MaterialGenerationTimeout, TimeoutError, ConnectionError, socket.timeout)):
        return "provider_temporary_failure", "The model provider was temporarily unavailable.", True
    if isinstance(exc, AgentBudgetExceeded):
        return "budget_exceeded", str(exc), False
    if isinstance(exc, (PermanentWorkflowError, MaterialConflict, MaterialNotFound, AgentConflict)):
        return "workflow_validation_failed", str(exc), False
    if isinstance(exc, MaterialGenerationError):
        return "generation_policy_failed", "Generation failed validation or provider policy checks.", False
    return "workflow_internal_error", "The workflow step failed safely.", False


def _failure_usage(exc: Exception) -> dict[str, Any] | None:
    value = getattr(exc, "usage", None)
    if not isinstance(value, dict):
        return None
    return {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "input_tokens": int(value.get("input_tokens") or 0),
        "output_tokens": int(value.get("output_tokens") or 0),
        "total_tokens": int(value.get("total_tokens") or 0),
        "estimated_cost_usd": Decimal(str(value.get("estimated_cost_usd") or 0)),
    }
