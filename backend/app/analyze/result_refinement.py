"""Post-provider Analyze result validation, refinement, and output safety."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, NoReturn

from agent_workflow import AgentWorkflow, WorkflowContext
from analysis_fallback import deterministic_scoring
from analysis_contract import safe_model_metadata
from app.materials.grounding import EvidenceSource, validate_claims
from fastapi import HTTPException
from recommendation_engine import generate_next_action
from security_utils import (
    POLICY_VERSION as SECURITY_POLICY_VERSION,
    empty_security_scan,
    merge_security_scans,
    normalized_security_scan,
    scan_llm_output,
    security_status_from_scan,
)


FailureHandler = Callable[..., NoReturn]
BlockedHandler = Callable[..., NoReturn]
SkipStepsHandler = Callable[..., None]
EvidenceValidator = Callable[..., dict[str, Any]]
EvidenceReconciler = Callable[..., list[str]]
GroundingEnforcer = Callable[..., None]
MatchScoreCalculator = Callable[[dict[str, Any]], int]
NarrativeEnsurer = Callable[[dict[str, Any], str], None]
RagSourceBuilder = Callable[..., list[dict[str, Any]]]
ListNormalizer = Callable[[Any], list[str]]


def sanitize_provider_narratives(
    result: dict[str, Any],
    *,
    resume_text: str,
    job_description: str,
    retrieved_chunks: list[dict[str, Any]],
) -> int:
    """Remove unsupported narrative sentences while retaining safe peers."""
    sources = [
        EvidenceSource("resume", None, None, resume_text),
        EvidenceSource("job_description", None, None, job_description),
    ]
    sources.extend(
        EvidenceSource(
            "project_knowledge",
            str(chunk.get("chunk_id") or "") or None,
            None,
            "" if chunk.get("content") is None else str(chunk.get("content")),
        )
        for chunk in retrieved_chunks
    )

    def clean_text(value: Any) -> tuple[str, int]:
        if not isinstance(value, str) or not value.strip():
            return "", 0
        kept: list[str] = []
        removed = 0
        for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", value):
            sentence = sentence.strip()
            if not sentence:
                continue
            links = validate_claims(sentence, sources)
            if any(
                item.get("support_status") in {"unsupported", "partially_supported"}
                for item in links
            ):
                removed += 1
                continue
            kept.append(sentence)
        return " ".join(kept)[:480], removed

    def clean_list(value: Any) -> tuple[list[str], int]:
        if not isinstance(value, list):
            return [], 0
        kept: list[str] = []
        removed = 0
        for item in value:
            clean, count = clean_text(item)
            removed += count
            if clean:
                kept.append(clean)
        return list(dict.fromkeys(kept)), removed

    removed_total = 0
    summary, removed = clean_text(result.get("job_summary"))
    removed_total += removed
    if isinstance(result.get("job_summary"), str):
        result["job_summary"] = summary
    reason, removed = clean_text(result.get("match_reason"))
    removed_total += removed
    if isinstance(result.get("match_reason"), str):
        result["match_reason"] = reason
    for field_name in ("recommendations", "resume_suggestions"):
        cleaned, removed = clean_list(result.get(field_name))
        removed_total += removed
        if isinstance(result.get(field_name), list):
            result[field_name] = cleaned
    return removed_total


def sanitize_provider_result_narratives(
    result: dict[str, Any],
    analysis_status: str,
    parsed_warnings: list[str],
    *,
    resume_text: str,
    job_description: str,
    retrieved_chunks: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Apply narrative grounding after parsing without changing parse ownership."""
    removed_narratives = sanitize_provider_narratives(
        result,
        resume_text=resume_text,
        job_description=job_description,
        retrieved_chunks=retrieved_chunks,
    )
    if removed_narratives:
        parsed_warnings.append(
            "Unsupported narrative claims were removed while preserving the safe analysis."
        )
        if analysis_status == "complete":
            analysis_status = "partial"
    return analysis_status, parsed_warnings


def refine_analyze_result(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    result: dict[str, Any],
    analysis_status: str,
    analysis_warnings: list[str],
    failure_handler: FailureHandler,
    blocked_handler: BlockedHandler,
    skip_steps_after: SkipStepsHandler,
    evidence_validator: EvidenceValidator,
    evidence_reconciler: EvidenceReconciler,
    grounding_enforcer: GroundingEnforcer,
    match_score_calculator: MatchScoreCalculator,
    narrative_ensurer: NarrativeEnsurer,
    rag_source_builder: RagSourceBuilder,
    list_normalizer: ListNormalizer,
) -> str:
    """Run the post-provider refinement steps in their existing order."""
    analysis_status = _validate_evidence_references(
        workflow=workflow,
        context=context,
        result=result,
        analysis_status=analysis_status,
        analysis_warnings=analysis_warnings,
        failure_handler=failure_handler,
        evidence_validator=evidence_validator,
    )
    analysis_status = _reconcile_evidence(
        workflow=workflow,
        context=context,
        result=result,
        analysis_status=analysis_status,
        analysis_warnings=analysis_warnings,
        failure_handler=failure_handler,
        evidence_reconciler=evidence_reconciler,
        grounding_enforcer=grounding_enforcer,
        match_score_calculator=match_score_calculator,
        narrative_ensurer=narrative_ensurer,
        rag_source_builder=rag_source_builder,
        list_normalizer=list_normalizer,
    )
    _recommend_next_action(
        workflow=workflow,
        context=context,
        result=result,
        failure_handler=failure_handler,
    )
    _prepare_security_fields(context, result)
    _scan_final_output(
        workflow=workflow,
        context=context,
        result=result,
        failure_handler=failure_handler,
        blocked_handler=blocked_handler,
        skip_steps_after=skip_steps_after,
    )
    return analysis_status


def _validate_evidence_references(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    result: dict[str, Any],
    analysis_status: str,
    analysis_warnings: list[str],
    failure_handler: FailureHandler,
    evidence_validator: EvidenceValidator,
) -> str:
    workflow.start_step("validate_evidence_references", "Validate Evidence References")
    try:
        evidence_validation = evidence_validator(
            result,
            resume_text=context.sanitized_resume_text,
            retrieved_chunks=context.retrieved_chunks,
        )
        if evidence_validation["rejected_reference_count"]:
            workflow.add_warning()
            analysis_warnings.append(
                "Unknown or unsupported evidence references were ignored without blocking the analysis."
            )
            if analysis_status == "complete":
                analysis_status = "partial"
        workflow.complete_step(
            "validate_evidence_references",
            (
                "Validated model evidence IDs against the current request; rejected "
                f"{evidence_validation['rejected_reference_count']} reference(s)."
            ),
        )
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="validate_evidence_references",
            message="Evidence reference validation failed safely.",
            error_code="EVIDENCE_REFERENCE_VALIDATION_FAILED",
            exc=exc,
        )
    return analysis_status


def _reconcile_evidence(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    result: dict[str, Any],
    analysis_status: str,
    analysis_warnings: list[str],
    failure_handler: FailureHandler,
    evidence_reconciler: EvidenceReconciler,
    grounding_enforcer: GroundingEnforcer,
    match_score_calculator: MatchScoreCalculator,
    narrative_ensurer: NarrativeEnsurer,
    rag_source_builder: RagSourceBuilder,
    list_normalizer: ListNormalizer,
) -> str:
    workflow.start_step("reconcile_evidence", "Reconcile Evidence")
    try:
        corrected_terms = evidence_reconciler(result, context.retrieved_chunks)
        context.rag_reconciliation_count = len(corrected_terms)
        result["rag_mode"] = context.rag_mode
        result["used_knowledge_base"] = bool(
            context.rag_mode == "project" and context.retrieved_chunks
        )
        result["retrieval_count"] = len(context.retrieved_chunks)
        grounding_enforcer(
            result,
            context.sanitized_resume_text,
            context.retrieved_chunks,
        )
        result["scoring_breakdown"] = deterministic_scoring(
            result,
            context.sanitized_resume_text,
            context.sanitized_job_text,
            context.retrieved_chunks,
        )
        result["match_score"] = match_score_calculator(result["scoring_breakdown"])
        narrative_ensurer(result, context.sanitized_job_text)
        result["rag_sources"] = rag_source_builder(
            context.retrieved_chunks,
            result.get("matched_skills") or [],
        )
        if not result["used_knowledge_base"]:
            result["rag_sources"] = []
        if (result.get("claim_validation") or {}).get("unsupported_claim_count"):
            workflow.add_warning()
            analysis_warnings.append(
                "Unsupported candidate claims were removed without blocking the reliable result."
            )
            if analysis_status == "complete":
                analysis_status = "partial"
        result["analysis_status"] = analysis_status
        context.model_metadata = safe_model_metadata({
            **context.model_metadata,
            "result_state": analysis_status,
        })
        result["analysis_warnings"] = list(dict.fromkeys(analysis_warnings))
        result["recommendations"] = list_normalizer(
            result.get("recommendations") or result.get("resume_suggestions")
        )
        result["resume_suggestions"] = list(result["recommendations"])
        result.setdefault("unknown_skills", [])
        result.setdefault("cover_letter", "")
        result.setdefault("upgraded_resume_bullets", [])
        result.setdefault("ats_analysis", {})
        result.setdefault("evidence_mapping", [])
        workflow.complete_step(
            "reconcile_evidence",
            (
                f"Reconciled Project Knowledge evidence; corrected {len(corrected_terms)} "
                "RAG-supported term(s)."
            ),
        )
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="reconcile_evidence",
            message="Evidence reconciliation failed.",
            error_code="EVIDENCE_RECONCILIATION_FAILED",
            exc=exc,
        )
    return analysis_status


def _recommend_next_action(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    result: dict[str, Any],
    failure_handler: FailureHandler,
) -> None:
    workflow.start_step("recommend_next_action", "Recommend Next Action")
    try:
        context.next_action = generate_next_action(result)
        result["next_action"] = context.next_action
        result["next_action_decision"] = "pending"
        workflow.complete_step(
            "recommend_next_action",
            f"Recommended next action: {context.next_action.get('label', 'No Recommendation')}.",
        )
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="recommend_next_action",
            message="Next-action recommendation failed.",
            error_code="NEXT_ACTION_RECOMMENDATION_FAILED",
            exc=exc,
        )


def _prepare_security_fields(
    context: WorkflowContext,
    result: dict[str, Any],
) -> None:
    context.security_scan = normalized_security_scan(
        context.security_scan or empty_security_scan()
    )
    context.security_status = security_status_from_scan(context.security_scan)
    result["security_scan"] = context.security_scan
    result["security_status"] = context.security_status
    result["security_policy_version"] = SECURITY_POLICY_VERSION


def _scan_final_output(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    result: dict[str, Any],
    failure_handler: FailureHandler,
    blocked_handler: BlockedHandler,
    skip_steps_after: SkipStepsHandler,
) -> None:
    workflow.start_step("final_output_scan", "Final Output Security Scan")
    try:
        serialized_result = json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        _sanitized_final, final_scan, final_marker = scan_llm_output(serialized_result)
        context.security_scan = merge_security_scans(context.security_scan, final_scan)
        if final_marker or final_scan.get("sensitive_data_detected") or final_scan.get("blocked"):
            workflow.fail_step(
                "final_output_scan",
                "Final serialized analysis failed the blocking security boundary.",
            )
            skip_steps_after(
                workflow,
                after_key="final_output_scan",
                message="Skipped because final output security scanning blocked the response.",
            )
            blocked_handler(
                workflow,
                context,
                status_code=502,
                message="The analysis result failed final security validation. Please try again.",
                error_code="OUTPUT_SECURITY_BLOCKED",
                error_stage="final_output_scan",
            )
        context.security_scan = normalized_security_scan(context.security_scan)
        context.security_status = security_status_from_scan(context.security_scan)
        result["security_scan"] = context.security_scan
        result["security_status"] = context.security_status
        workflow.complete_step(
            "final_output_scan",
            "Final serialized analysis passed output security scanning.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="final_output_scan",
            message="Final output security scanning failed.",
            error_code="FINAL_OUTPUT_SCAN_FAILED",
            exc=exc,
        )
