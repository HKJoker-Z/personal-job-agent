"""Security and Project Knowledge preparation for the Analyze workflow."""

from __future__ import annotations

import logging
from typing import Any, Callable, NoReturn

from agent_workflow import AgentWorkflow, WorkflowContext
from fastapi import HTTPException
from safe_prompt import build_safe_analysis_prompt
from security_utils import (
    merge_security_scans,
    prepare_resume_for_llm,
    scan_and_sanitize_untrusted_text,
    scan_project_chunks,
)


logger = logging.getLogger("personal-job-agent")
FailureHandler = Callable[..., NoReturn]
BlockedHandler = Callable[..., NoReturn]
SkipStepsHandler = Callable[..., None]
RetrievalQueryBuilder = Callable[[str, str], str]
ProjectKnowledgeRetriever = Callable[
    [str, int], tuple[list[dict[str, Any]], str]
]
RagSourceBuilder = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
SafePromptBuilder = Callable[..., str]
ResumePreparer = Callable[[str], tuple[str, dict[str, Any]]]
UntrustedTextScanner = Callable[[str, str], tuple[str, dict[str, Any]]]
ProjectChunkScanner = Callable[
    [list[dict[str, Any]]],
    tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]],
]


def scan_untrusted_input(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    failure_handler: FailureHandler,
    blocked_handler: BlockedHandler,
    skip_steps_after: SkipStepsHandler,
    resume_preparer: ResumePreparer = prepare_resume_for_llm,
    untrusted_text_scanner: UntrustedTextScanner = scan_and_sanitize_untrusted_text,
) -> None:
    workflow.start_step("scan_untrusted_input", "Scan Untrusted Input")
    try:
        sanitized_resume_text, resume_scan = resume_preparer(context.resume_text)
        sanitized_job_text, job_scan = untrusted_text_scanner(
            context.job_text,
            "job_description",
        )
        context.sanitized_resume_text = sanitized_resume_text
        context.sanitized_job_text = sanitized_job_text
        context.security_scan = merge_security_scans(resume_scan, job_scan)
        if context.security_scan.get("blocked"):
            workflow.fail_step(
                "scan_untrusted_input",
                "Sensitive credential-like content was detected before LLM invocation.",
            )
            skip_steps_after(
                workflow,
                after_key="scan_untrusted_input",
                message="Skipped because security scanning blocked the request.",
            )
            blocked_handler(workflow, context)
        if context.security_scan.get("prompt_injection_detected"):
            workflow.add_warning()
        workflow.complete_step(
            "scan_untrusted_input",
            "Untrusted resume and job description were scanned and prepared for analysis.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="scan_untrusted_input",
            message="Security scanning failed.",
            error_code="UNTRUSTED_INPUT_SCAN_FAILED",
            exc=exc,
        )


def prepare_project_evidence(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    failure_handler: FailureHandler,
    blocked_handler: BlockedHandler,
    skip_steps_after: SkipStepsHandler,
    retrieval_query_builder: RetrievalQueryBuilder,
    project_knowledge_retriever: ProjectKnowledgeRetriever,
    rag_source_builder: RagSourceBuilder,
    project_chunk_scanner: ProjectChunkScanner = scan_project_chunks,
    safe_prompt_builder: SafePromptBuilder = build_safe_analysis_prompt,
) -> None:
    logger.info(
        "Analyze RAG settings rag_mode=%s use_knowledge_base=%s rag_top_k=%s",
        context.rag_mode,
        context.rag_mode == "project",
        context.rag_top_k,
    )
    if context.rag_mode == "off":
        workflow.skip_step(
            "retrieve_project_evidence",
            "Retrieve Project Knowledge",
            "Project Knowledge RAG is off for this analysis.",
        )
    else:
        _retrieve_project_evidence(
            workflow=workflow,
            context=context,
            failure_handler=failure_handler,
            retrieval_query_builder=retrieval_query_builder,
            project_knowledge_retriever=project_knowledge_retriever,
            rag_source_builder=rag_source_builder,
        )

    if context.rag_mode == "off":
        workflow.skip_step(
            "scan_project_evidence",
            "Scan Project Evidence",
            "Project Knowledge RAG is off for this analysis.",
        )
    else:
        _scan_project_evidence(
            workflow=workflow,
            context=context,
            failure_handler=failure_handler,
            blocked_handler=blocked_handler,
            skip_steps_after=skip_steps_after,
            project_chunk_scanner=project_chunk_scanner,
            rag_source_builder=rag_source_builder,
        )

    _build_safe_prompt(
        workflow=workflow,
        context=context,
        failure_handler=failure_handler,
        safe_prompt_builder=safe_prompt_builder,
    )


def _retrieve_project_evidence(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    failure_handler: FailureHandler,
    retrieval_query_builder: RetrievalQueryBuilder,
    project_knowledge_retriever: ProjectKnowledgeRetriever,
    rag_source_builder: RagSourceBuilder,
) -> None:
    workflow.start_step("retrieve_project_evidence", "Retrieve Project Knowledge")
    try:
        retrieval_query = retrieval_query_builder(
            context.sanitized_job_text,
            context.sanitized_resume_text,
        )
        rag_chunks, retrieval_method = project_knowledge_retriever(
            retrieval_query,
            context.rag_top_k,
        )
        context.retrieved_chunks = rag_chunks
        context.rag_sources = rag_source_builder(rag_chunks)
        if not rag_chunks:
            workflow.add_warning()
        workflow.complete_step(
            "retrieve_project_evidence",
            (
                f"Retrieved {len(rag_chunks)} Project Knowledge source(s) "
                f"using {retrieval_method}."
            ),
        )
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="retrieve_project_evidence",
            message="Project Knowledge retrieval failed.",
            error_code="PROJECT_KNOWLEDGE_RETRIEVAL_FAILED",
            exc=exc,
        )
    logger.info(
        "Project Knowledge retrieval completed result_count=%s retrieval_method=%s chunk_ids=%s titles=%s",
        len(context.retrieved_chunks),
        retrieval_method if context.retrieved_chunks else "none",
        [chunk.get("chunk_id") for chunk in context.retrieved_chunks],
        [chunk.get("document_title") for chunk in context.retrieved_chunks],
    )


def _scan_project_evidence(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    failure_handler: FailureHandler,
    blocked_handler: BlockedHandler,
    skip_steps_after: SkipStepsHandler,
    project_chunk_scanner: ProjectChunkScanner,
    rag_source_builder: RagSourceBuilder,
) -> None:
    workflow.start_step("scan_project_evidence", "Scan Project Evidence")
    try:
        sanitized_chunks, project_scan, filtered_sources = project_chunk_scanner(
            context.retrieved_chunks
        )
        context.retrieved_chunks = sanitized_chunks
        context.security_filtered_rag_sources = filtered_sources
        context.rag_sources = rag_source_builder(sanitized_chunks)
        if filtered_sources:
            context.rag_sources.extend(filtered_sources)
        context.security_scan = merge_security_scans(context.security_scan, project_scan)
        if project_scan.get("prompt_injection_detected"):
            workflow.add_warning()
        if context.security_scan.get("blocked"):
            workflow.fail_step(
                "scan_project_evidence",
                "Sensitive credential-like content was detected in Project Knowledge evidence.",
            )
            skip_steps_after(
                workflow,
                after_key="scan_project_evidence",
                message="Skipped because security scanning blocked the request.",
            )
            blocked_handler(
                workflow,
                context,
                error_code="INPUT_SECURITY_BLOCKED",
                error_stage="scan_project_evidence",
            )
        workflow.complete_step(
            "scan_project_evidence",
            (
                f"Scanned {len(context.retrieved_chunks)} Project Knowledge source(s); "
                f"filtered {len(filtered_sources)} source(s)."
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="scan_project_evidence",
            message="Project evidence security scan failed.",
            error_code="PROJECT_EVIDENCE_SCAN_FAILED",
            exc=exc,
        )


def _build_safe_prompt(
    *,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    failure_handler: FailureHandler,
    safe_prompt_builder: SafePromptBuilder,
) -> None:
    workflow.start_step("build_safe_prompt", "Build Safe Prompt")
    try:
        context.safe_prompt = safe_prompt_builder(
            resume_text=context.sanitized_resume_text,
            job_description=context.sanitized_job_text,
            rag_chunks=context.retrieved_chunks,
        )
        workflow.complete_step(
            "build_safe_prompt",
            "Safe prompt built with isolated untrusted data sections.",
        )
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="build_safe_prompt",
            message="Safe prompt construction failed.",
            error_code="SAFE_PROMPT_BUILD_FAILED",
            exc=exc,
        )
