import unittest

from agent_workflow import AgentWorkflow, WorkflowContext
from fastapi import HTTPException

from app.analyze.result_refinement import refine_analyze_result
from legacy_application import (
    build_default_rag_sources,
    calculate_weighted_match_score,
    enforce_analysis_grounding,
    ensure_deterministic_narratives,
    normalize_list,
    reconcile_result_with_rag_evidence,
    validate_model_evidence_references,
)


def breakdown(evidence=None):
    evidence = list(evidence or [])
    return {
        key: {"score": 70, "reason": "Synthetic supported dimension.", "evidence": evidence}
        for key in (
            "skills_match",
            "project_experience",
            "education",
            "work_experience",
            "keyword_match",
        )
    }


def refinement_result(*, evidence_ids=None, unsupported_candidates=None):
    return {
        "matched_skills": ["Python"],
        "missing_skills": ["Kubernetes"],
        "unknown_skills": [],
        "job_summary": "Synthetic backend role.",
        "match_reason": "Python is supported.",
        "recommendations": ["Keep verified evidence prominent."],
        "resume_suggestions": ["Keep verified evidence prominent."],
        "cover_letter": "",
        "upgraded_resume_bullets": [],
        "ats_analysis": {
            "important_keywords": ["Python", "Kubernetes"],
            "matched_keywords": ["Python"],
            "missing_keywords": ["Kubernetes"],
            "keyword_suggestions": [],
        },
        "scoring_breakdown": breakdown(["resume"]),
        "_model_evidence_references": [
            {"skill": "Python", "evidence_ids": list(evidence_ids or ["resume"])}
        ],
        "_unsupported_claim_candidates": list(unsupported_candidates or []),
    }


class AnalyzeResultRefinementTest(unittest.TestCase):
    def context(self, *, rag_mode="off", chunks=None):
        return WorkflowContext(
            workflow_id="phase-3c-synthetic-workflow",
            sanitized_resume_text="Synthetic Python engineer.",
            sanitized_job_text="Synthetic backend role requiring Python.",
            rag_mode=rag_mode,
            retrieved_chunks=list(chunks or []),
            security_scan={
                "findings": [],
                "sensitive_data_detected": False,
                "prompt_injection_detected": False,
                "blocked": False,
            },
        )

    @staticmethod
    def failure_handler(*_args, **kwargs):
        raise AssertionError(kwargs.get("message", "refinement failure"))

    @staticmethod
    def blocked_handler(*_args, **kwargs):
        raise HTTPException(
            status_code=kwargs.get("status_code", 502),
            detail={"error_code": kwargs.get("error_code", "OUTPUT_SECURITY_BLOCKED")},
        )

    def refine(self, result, *, context=None, status="complete", warnings=None):
        context = context or self.context()
        workflow = AgentWorkflow(workflow_id=context.workflow_id)
        final_status = refine_analyze_result(
            workflow=workflow,
            context=context,
            result=result,
            analysis_status=status,
            analysis_warnings=list(warnings or []),
            failure_handler=self.failure_handler,
            blocked_handler=self.blocked_handler,
            skip_steps_after=lambda workflow, **kwargs: None,
            evidence_validator=validate_model_evidence_references,
            evidence_reconciler=reconcile_result_with_rag_evidence,
            grounding_enforcer=enforce_analysis_grounding,
            match_score_calculator=calculate_weighted_match_score,
            narrative_ensurer=ensure_deterministic_narratives,
            rag_source_builder=build_default_rag_sources,
            list_normalizer=normalize_list,
        )
        return final_status, context, workflow

    def test_valid_reference_and_final_scan_preserve_complete_result(self):
        result = refinement_result()
        status, context, workflow = self.refine(result)

        self.assertEqual(status, "complete")
        self.assertEqual(result["analysis_status"], "complete")
        self.assertEqual(result["evidence_reference_validation"]["status"], "passed")
        self.assertEqual(result["next_action_decision"], "pending")
        self.assertEqual(context.security_status, "passed")
        self.assertEqual(
            [step.key for step in workflow.steps],
            [
                "validate_evidence_references",
                "reconcile_evidence",
                "recommend_next_action",
                "final_output_scan",
            ],
        )
        self.assertTrue(result["next_action"])

    def test_unknown_and_rejected_references_make_complete_partial(self):
        result = refinement_result(evidence_ids=["pk:999", "not-allowed"])
        status, _context, workflow = self.refine(result)

        self.assertEqual(status, "partial")
        self.assertEqual(result["analysis_status"], "partial")
        validation = result["evidence_reference_validation"]
        self.assertEqual(validation["status"], "completed_with_rejections")
        self.assertEqual(validation["rejected_reference_count"], 2)
        self.assertIn("Unknown or unsupported evidence references", result["analysis_warnings"][0])
        self.assertTrue(workflow.has_warnings)

    def test_rag_reconciliation_and_grounding_update_public_evidence(self):
        chunks = [{
            "chunk_id": 17,
            "score": 0.9,
            "content": "# Backend evidence\nKubernetes is used by the synthetic platform.",
        }]
        result = refinement_result(evidence_ids=["resume"])
        status, context, _workflow = self.refine(
            result,
            context=self.context(rag_mode="project", chunks=chunks),
        )

        self.assertEqual(status, "complete")
        self.assertEqual(context.rag_reconciliation_count, 1)
        self.assertEqual(result["retrieval_count"], 1)
        self.assertTrue(result["used_knowledge_base"])
        self.assertEqual(result["rag_sources"][0]["chunk_id"], 17)
        self.assertIn("Kubernetes", result["matched_skills"])

    def test_unsupported_claim_changes_complete_to_partial_and_is_removed(self):
        result = refinement_result(
            unsupported_candidates=["Generated $10M revenue."]
        )
        result["cover_letter"] = "I led 50 people."
        status, _context, _workflow = self.refine(result)

        self.assertEqual(status, "partial")
        self.assertEqual(result["claim_validation"]["status"], "invalid")
        self.assertEqual(result["claim_validation"]["unsupported_claim_count"], 1)
        self.assertEqual(result["cover_letter"], "")
        self.assertIn("Unsupported candidate claims", " ".join(result["analysis_warnings"]))

    def test_fallback_status_survives_result_refinement(self):
        result = refinement_result()
        status, _context, _workflow = self.refine(result, status="fallback")
        self.assertEqual(status, "fallback")
        self.assertEqual(result["analysis_status"], "fallback")

    def test_final_output_security_block_preserves_safe_error_boundary(self):
        result = refinement_result()
        result["job_summary"] = "postgres://synthetic:synthetic-secret@localhost/test"
        context = self.context()
        workflow = AgentWorkflow(workflow_id=context.workflow_id)

        with self.assertRaises(HTTPException) as raised:
            refine_analyze_result(
                workflow=workflow,
                context=context,
                result=result,
                analysis_status="complete",
                analysis_warnings=[],
                failure_handler=self.failure_handler,
                blocked_handler=self.blocked_handler,
                skip_steps_after=lambda workflow, **kwargs: None,
                evidence_validator=validate_model_evidence_references,
                evidence_reconciler=reconcile_result_with_rag_evidence,
                grounding_enforcer=enforce_analysis_grounding,
                match_score_calculator=calculate_weighted_match_score,
                narrative_ensurer=ensure_deterministic_narratives,
                rag_source_builder=build_default_rag_sources,
                list_normalizer=normalize_list,
            )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail["error_code"], "OUTPUT_SECURITY_BLOCKED")
        self.assertEqual(workflow.steps[-1].key, "final_output_scan")
        self.assertEqual(workflow.steps[-1].status, "failed")


if __name__ == "__main__":
    unittest.main()
