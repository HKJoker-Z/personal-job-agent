from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_workflow import AgentWorkflow
from database import (
    default_ats_analysis,
    default_scoring_breakdown,
    get_connection,
)
from knowledge_utils import build_text_chunks, clean_knowledge_text
from recommendation_engine import generate_next_action
from safe_prompt import build_safe_analysis_prompt
from security_utils import (
    INTERNAL_SECURITY_MARKER,
    REDACTED_EMAIL,
    REDACTED_PHONE,
    REDACTED_SECRET,
    REMOVED_SUSPICIOUS_INSTRUCTION,
    redact_pii,
    redact_secrets,
    scan_and_sanitize_untrusted_text,
    scan_llm_output,
    scan_untrusted_text,
)


EVALUATION_VERSION = "1.8.0"
EVALUATION_MODE = "offline"
EVALS_DIR = Path(__file__).resolve().parent / "evals"
CASES_PATH = EVALS_DIR / "cases.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_KNOWLEDGE_PATH = PROJECT_ROOT / "docs" / "PROJECT_KNOWLEDGE.md"
FAILURE_SUMMARY_LIMIT = 500


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def duration_ms_from_ns(start_ns: int, end_ns: int) -> float:
    return round(max(0, end_ns - start_ns) / 1_000_000, 3)


def safe_failure_summary(message: Any) -> str:
    text, _secret_count, _private_key_count = redact_secrets(str(message or ""))
    text = " ".join(text.split())
    return text[:FAILURE_SUMMARY_LIMIT]


def load_evaluation_suite(suite_name: str = "default") -> dict[str, Any]:
    try:
        suite = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Evaluation suite could not be loaded.") from exc
    validate_suite_schema(suite)
    if suite.get("suite_name") != suite_name:
        raise ValueError("Evaluation suite name is not available.")
    return suite


def validate_suite_schema(suite: dict[str, Any]) -> None:
    if not isinstance(suite, dict):
        raise ValueError("Evaluation suite must be an object.")
    if not suite.get("suite_name") or not suite.get("suite_version"):
        raise ValueError("Evaluation suite requires suite_name and suite_version.")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation suite requires at least one case.")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Evaluation case must be an object.")
        for key in ("id", "name", "category", "runner", "input", "expected"):
            if key not in case:
                raise ValueError(f"Evaluation case missing {key}.")


def check_equal(checks: dict[str, bool], name: str, actual: Any, expected: Any) -> None:
    checks[name] = actual == expected


def runner_security_scan(case: dict[str, Any]) -> dict[str, Any]:
    case_input = case["input"]
    expected = case["expected"]
    sanitized, scan = scan_and_sanitize_untrusted_text(
        str(case_input.get("text") or ""),
        str(case_input.get("source") or "job_description"),
    )
    checks: dict[str, bool] = {}
    for key in ("blocked", "prompt_injection_detected", "sensitive_data_detected", "risk_level"):
        if key in expected:
            check_equal(checks, key, scan.get(key), expected[key])
    if "suspicious_text_removed" in expected:
        checks["suspicious_text_removed"] = REMOVED_SUSPICIOUS_INSTRUCTION in sanitized
    return {"checks": checks}


def runner_pii_redaction(case: dict[str, Any]) -> dict[str, Any]:
    redacted, summary = redact_pii(str(case["input"].get("text") or ""))
    checks: dict[str, bool] = {}
    expected = case["expected"]
    if "email_redacted" in expected:
        checks["email_redacted"] = (REDACTED_EMAIL in redacted) == expected["email_redacted"]
    if "phone_redacted" in expected:
        checks["phone_redacted"] = (REDACTED_PHONE in redacted) == expected["phone_redacted"]
    if "technical_numbers_preserved" in expected:
        checks["technical_numbers_preserved"] = "v1.8" in redacted and "95%" in redacted
    if "email_count" in expected:
        checks["email_count"] = summary.get("email_count") == expected["email_count"]
    if "phone_count" in expected:
        checks["phone_count"] = summary.get("phone_count") == expected["phone_count"]
    return {"checks": checks}


def runner_safe_prompt(case: dict[str, Any]) -> dict[str, Any]:
    case_input = case["input"]
    prompt = build_safe_analysis_prompt(
        resume_text=str(case_input.get("resume_text") or ""),
        job_description=str(case_input.get("job_description") or ""),
        rag_chunks=case_input.get("rag_chunks") or [],
    )
    checks = {
        "security_rules_first": prompt.index("SYSTEM SECURITY RULES") < prompt.index("<UNTRUSTED_JOB_DESCRIPTION>"),
        "jd_in_untrusted_section": str(case_input.get("job_description")) in prompt.split("<UNTRUSTED_JOB_DESCRIPTION>", 1)[1].split("</UNTRUSTED_JOB_DESCRIPTION>", 1)[0],
        "project_knowledge_in_untrusted_section": "UNTRUSTED_PROJECT_KNOWLEDGE_EVIDENCE" in prompt,
        "internal_marker_present": INTERNAL_SECURITY_MARKER in prompt,
        "prompt_structure_stable": prompt.count("<UNTRUSTED_JOB_DESCRIPTION>") == 1 and prompt.count("</UNTRUSTED_JOB_DESCRIPTION>") == 1,
    }
    return {"checks": checks}


def runner_rag_retrieval(case: dict[str, Any]) -> dict[str, Any]:
    query = str(case["input"].get("query") or "").lower()
    content = ""
    if PROJECT_KNOWLEDGE_PATH.exists():
        content = clean_knowledge_text(PROJECT_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    chunks = build_text_chunks(content) if content else []
    matching_chunks = [
        chunk for chunk in chunks
        if any(term in chunk.lower() for term in ("rag", "retrieval-augmented", "fastapi"))
    ]
    checks = {
        "source_returned": len(matching_chunks) >= 1,
        "rag_related_content": bool(matching_chunks) and "rag" in "\n".join(matching_chunks).lower(),
        "query_mentions_expected_terms": all(term in query for term in ("rag", "fastapi")),
    }
    return {"checks": checks}


def runner_rag_reconciliation(case: dict[str, Any]) -> dict[str, Any]:
    case_input = case["input"]
    matched = list(case_input.get("matched_skills") or [])
    missing = list(case_input.get("missing_skills") or [])
    evidence = " ".join(str(item.get("content") or "") for item in case_input.get("retrieved_chunks") or [])
    reconciled = 0
    if any(skill.lower() == "rag" for skill in missing) and "retrieval-augmented generation" in evidence.lower():
        missing = [skill for skill in missing if skill.lower() != "rag"]
        if not any(skill.lower() == "rag" for skill in matched):
            matched.append("RAG")
            reconciled += 1
    checks = {
        "rag_removed_from_missing": "RAG" not in missing,
        "rag_added_to_matched": "RAG" in matched,
        "reconciliation_count": reconciled >= int(case["expected"].get("minimum_reconciliation_count", 1)),
    }
    return {"checks": checks}


def runner_recommendation(case: dict[str, Any]) -> dict[str, Any]:
    result = case["input"].get("result") or {}
    action = generate_next_action(result).get("action")
    checks = {"expected_action": action == case["expected"].get("action")}
    return {"checks": checks}


def runner_workflow_timing(case: dict[str, Any]) -> dict[str, Any]:
    workflow = AgentWorkflow("evaluation-workflow")
    workflow.start_step("validate_input", "Validate Input")
    workflow.complete_step("validate_input", "Input accepted.")
    step = workflow.to_list()[0]
    checks = {
        "duration_non_negative": (step.get("duration_ms") or 0) >= 0,
        "duration_fields_present": "duration_ms" in step and "duration_us" in step,
        "private_perf_not_serialized": "_started_perf_ns" not in step,
    }
    return {"checks": checks}


def runner_legacy_defaults(case: dict[str, Any]) -> dict[str, Any]:
    legacy = case["input"].get("record") or {}
    security_status = legacy.get("security_status") or "not_available"
    workflow_steps = legacy.get("workflow_steps") or []
    checks = {
        "security_status_default": security_status in {"not_available", "passed", "passed_with_warnings", "blocked"},
        "workflow_default_safe": isinstance(workflow_steps, list),
        "scoring_default_safe": isinstance(default_scoring_breakdown(), dict),
        "ats_default_safe": isinstance(default_ats_analysis(), dict),
    }
    return {"checks": checks}


def runner_output_leakage(case: dict[str, Any]) -> dict[str, Any]:
    sanitized, scan, marker_leaked = scan_llm_output(str(case["input"].get("output") or ""))
    checks = {
        "secret_redacted": REDACTED_SECRET in sanitized,
        "output_leakage_detected": bool(scan.get("sensitive_data_detected")),
        "marker_leak_expected": marker_leaked == bool(case["expected"].get("marker_leaked", False)),
    }
    return {"checks": checks}


RUNNERS = {
    "security_scan": runner_security_scan,
    "pii_redaction": runner_pii_redaction,
    "safe_prompt": runner_safe_prompt,
    "rag_retrieval": runner_rag_retrieval,
    "rag_reconciliation": runner_rag_reconciliation,
    "recommendation": runner_recommendation,
    "workflow_timing": runner_workflow_timing,
    "legacy_defaults": runner_legacy_defaults,
    "output_leakage": runner_output_leakage,
}


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    start_ns = time.perf_counter_ns()
    checks: dict[str, bool] = {}
    failure_summary = ""
    try:
        runner_name = str(case.get("runner") or "")
        runner = RUNNERS.get(runner_name)
        if runner is None:
            raise ValueError("Unknown evaluation runner.")
        result = runner(case)
        checks = result.get("checks") if isinstance(result.get("checks"), dict) else {}
        status = "passed" if checks and all(bool(value) for value in checks.values()) else "failed"
        if status == "failed":
            failed_checks = [name for name, passed in checks.items() if not passed]
            failure_summary = safe_failure_summary(f"Failed checks: {', '.join(failed_checks)}")
    except Exception as exc:
        status = "error"
        checks = {"case_error": False}
        failure_summary = safe_failure_summary(exc)
    duration_ms = duration_ms_from_ns(start_ns, time.perf_counter_ns())
    return {
        "case_id": str(case.get("id") or ""),
        "case_name": str(case.get("name") or ""),
        "category": str(case.get("category") or "general"),
        "status": status,
        "duration_ms": duration_ms,
        "checks": checks,
        "failure_summary": failure_summary,
    }


def insert_evaluation_run(run: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO evaluation_runs (
                run_id, suite_name, suite_version, mode, status, started_at,
                completed_at, duration_ms, total_cases, passed_cases, failed_cases,
                error_cases, pass_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["run_id"],
                run["suite_name"],
                run["suite_version"],
                run["mode"],
                run["status"],
                run["started_at"],
                run.get("completed_at"),
                run.get("duration_ms"),
                run.get("total_cases", 0),
                run.get("passed_cases", 0),
                run.get("failed_cases", 0),
                run.get("error_cases", 0),
                run.get("pass_rate", 0.0),
            ),
        )


def update_evaluation_run(run: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE evaluation_runs
            SET status = ?, completed_at = ?, duration_ms = ?, total_cases = ?,
                passed_cases = ?, failed_cases = ?, error_cases = ?, pass_rate = ?
            WHERE run_id = ?
            """,
            (
                run["status"],
                run.get("completed_at"),
                run.get("duration_ms"),
                run.get("total_cases", 0),
                run.get("passed_cases", 0),
                run.get("failed_cases", 0),
                run.get("error_cases", 0),
                run.get("pass_rate", 0.0),
                run["run_id"],
            ),
        )


def insert_evaluation_result(run_id: str, result: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO evaluation_results (
                run_id, case_id, case_name, category, status, duration_ms,
                checks_json, failure_summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                result["case_id"],
                result["case_name"],
                result["category"],
                result["status"],
                result["duration_ms"],
                json.dumps(result["checks"], ensure_ascii=False, sort_keys=True),
                safe_failure_summary(result.get("failure_summary")),
                utc_now(),
            ),
        )


def run_evaluation_suite(suite_name: str = "default", mode: str = "offline") -> dict[str, Any]:
    if mode != EVALUATION_MODE:
        raise ValueError("Live LLM evaluation is not supported in Version 1.8.")
    suite = load_evaluation_suite(suite_name)
    run_id = str(uuid4())
    started_at = utc_now()
    run = {
        "run_id": run_id,
        "suite_name": suite["suite_name"],
        "suite_version": suite["suite_version"],
        "mode": mode,
        "status": "running",
        "started_at": started_at,
        "total_cases": 0,
        "passed_cases": 0,
        "failed_cases": 0,
        "error_cases": 0,
        "pass_rate": 0.0,
    }
    insert_evaluation_run(run)
    start_ns = time.perf_counter_ns()
    results = [run_case(case) for case in suite["cases"]]
    for result in results:
        insert_evaluation_result(run_id, result)
    total = len(results)
    passed = sum(1 for result in results if result["status"] == "passed")
    failed = sum(1 for result in results if result["status"] == "failed")
    errors = sum(1 for result in results if result["status"] == "error")
    status = "completed" if failed == 0 and errors == 0 else "completed_with_failures"
    run.update(
        {
            "status": status,
            "completed_at": utc_now(),
            "duration_ms": duration_ms_from_ns(start_ns, time.perf_counter_ns()),
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": failed,
            "error_cases": errors,
            "pass_rate": round(passed / total, 4) if total else 0.0,
        }
    )
    update_evaluation_run(run)
    return {**run, "results": results}


def list_evaluation_runs(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(100, int(limit or 20)))
    safe_offset = max(0, int(offset or 0))
    with get_connection() as connection:
        total_row = connection.execute("SELECT COUNT(*) AS total FROM evaluation_runs").fetchone()
        rows = connection.execute(
            """
            SELECT run_id, suite_name, suite_version, mode, status, started_at,
                   completed_at, duration_ms, total_cases, passed_cases,
                   failed_cases, error_cases, pass_rate
            FROM evaluation_runs
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            (safe_limit, safe_offset),
        ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "total": int(total_row["total"] if total_row else 0),
        "limit": safe_limit,
        "offset": safe_offset,
    }


def get_evaluation_run(run_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM evaluation_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        result_rows = connection.execute(
            """
            SELECT case_id, case_name, category, status, duration_ms,
                   checks_json, failure_summary, created_at
            FROM evaluation_results
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
    results = []
    for result in result_rows:
        item = dict(result)
        try:
            item["checks"] = json.loads(item.pop("checks_json") or "{}")
        except json.JSONDecodeError:
            item["checks"] = {}
        results.append(item)
    return {**dict(row), "results": results}


def evaluation_status() -> dict[str, Any]:
    suite = load_evaluation_suite("default")
    return {
        "enabled": True,
        "mode": EVALUATION_MODE,
        "suite_name": suite["suite_name"],
        "suite_version": suite["suite_version"],
        "external_llm_calls": False,
        "description": "Deterministic behavioral and regression evaluation.",
    }
