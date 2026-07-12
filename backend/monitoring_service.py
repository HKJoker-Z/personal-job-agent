from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from database import get_connection
from security_utils import normalized_security_scan


MONITORING_VERSION = "1.9"
OUTCOMES = ("completed", "completed_with_warnings", "failed", "blocked")
RECOMMENDATION_ACTIONS = (
    "apply_now",
    "improve_resume_first",
    "upskill_first",
    "save_for_later",
    "skip",
)
DECISIONS = ("pending", "accepted", "dismissed", "completed")

logger = logging.getLogger("personal-job-agent.monitoring")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def safe_float(value: Any, fallback: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def clamp_days(days: Any) -> int:
    return max(1, min(365, safe_int(days, 30)))


def clamp_limit(limit: Any) -> int:
    return max(1, min(100, safe_int(limit, 50)))


def period_bounds(days: Any) -> tuple[str, str, int]:
    safe_days = clamp_days(days)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=safe_days)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), safe_days


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def nearest_rank_percentile(values: list[float], percentile: int) -> float:
    clean_values = sorted(float(value) for value in values if value is not None)
    if not clean_values:
        return 0.0
    rank = max(1, math.ceil((percentile / 100) * len(clean_values)))
    return round(clean_values[rank - 1], 3)


def safe_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item or "").strip()]


def safe_json_dumps(value: Any) -> str:
    if not isinstance(value, (list, dict)):
        value = []
    return json.dumps(value, ensure_ascii=False)


def step_duration(steps: list[dict[str, Any]], step_key: str) -> float | None:
    for step in steps:
        if step.get("key") == step_key:
            return safe_float(step.get("duration_ms"), None)
    return None


def extract_finding_codes(security_scan: dict[str, Any]) -> list[str]:
    findings = security_scan.get("findings")
    if not isinstance(findings, list):
        return []
    codes: list[str] = []
    seen: set[str] = set()
    for item in findings:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code[:120])
    return codes


def has_output_leakage(security_scan: dict[str, Any]) -> bool:
    for item in security_scan.get("findings", []) if isinstance(security_scan.get("findings"), list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("category") == "output_leakage" or str(item.get("code", "")).startswith("llm_output"):
            return True
    return False


def build_analysis_metric(
    *,
    workflow_id: str,
    workflow_status: str | None,
    workflow_duration_ms: float | None,
    workflow_duration_us: int | None,
    workflow_steps: list[dict[str, Any]],
    outcome: str,
    rag_mode: str | None = None,
    rag_source_count: int = 0,
    rag_reconciliation_count: int = 0,
    security_scan: dict[str, Any] | None = None,
    security_status: str | None = None,
    json_parse_success: bool | None = None,
    saved_to_history: bool = False,
    application_id: int | None = None,
    next_action: str | None = None,
    error_code: str | None = None,
    error_stage: str | None = None,
    source_type: str | None = None,
    created_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    scan = normalized_security_scan(security_scan or {})
    summary = scan.get("redaction_summary") if isinstance(scan.get("redaction_summary"), dict) else {}
    safe_outcome = outcome if outcome in OUTCOMES else "failed"
    safe_source_count = max(0, int(rag_source_count or 0))
    llm_duration_ms = step_duration(workflow_steps, "run_llm_analysis")
    rag_retrieval_duration_ms = step_duration(workflow_steps, "retrieve_project_evidence")
    return {
        "workflow_id": workflow_id,
        "created_at": created_at or utc_now(),
        "completed_at": completed_at,
        "outcome": safe_outcome,
        "workflow_status": workflow_status,
        "workflow_duration_ms": workflow_duration_ms,
        "workflow_duration_us": workflow_duration_us,
        "llm_duration_ms": llm_duration_ms,
        "rag_retrieval_duration_ms": rag_retrieval_duration_ms,
        "rag_mode": rag_mode,
        "rag_source_count": safe_source_count,
        "rag_hit": bool_int(safe_source_count > 0),
        "rag_reconciliation_count": max(0, int(rag_reconciliation_count or 0)),
        "security_status": security_status,
        "security_risk_level": scan.get("risk_level") or "low",
        "prompt_injection_detected": bool_int(scan.get("prompt_injection_detected")),
        "sensitive_data_detected": bool_int(scan.get("sensitive_data_detected")),
        "output_leakage_detected": bool_int(has_output_leakage(scan)),
        "pii_email_redaction_count": safe_int(summary.get("email_count")),
        "pii_phone_redaction_count": safe_int(summary.get("phone_count")),
        "pii_address_redaction_count": safe_int(summary.get("address_count")),
        "security_finding_codes": extract_finding_codes(scan),
        "json_parse_success": None if json_parse_success is None else bool_int(json_parse_success),
        "saved_to_history": bool_int(saved_to_history),
        "application_id": application_id,
        "next_action": next_action,
        "error_code": error_code,
        "error_stage": error_stage,
        "source_type": source_type,
    }


def record_analysis_metric(metric: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO analysis_metrics (
                workflow_id, created_at, completed_at, outcome, workflow_status,
                workflow_duration_ms, workflow_duration_us, llm_duration_ms,
                rag_retrieval_duration_ms, rag_mode, rag_source_count, rag_hit,
                rag_reconciliation_count, security_status, security_risk_level,
                prompt_injection_detected, sensitive_data_detected,
                output_leakage_detected, pii_email_redaction_count,
                pii_phone_redaction_count, pii_address_redaction_count,
                security_finding_codes, json_parse_success, saved_to_history,
                application_id, next_action, error_code, error_stage, source_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                completed_at = excluded.completed_at,
                outcome = excluded.outcome,
                workflow_status = excluded.workflow_status,
                workflow_duration_ms = excluded.workflow_duration_ms,
                workflow_duration_us = excluded.workflow_duration_us,
                llm_duration_ms = excluded.llm_duration_ms,
                rag_retrieval_duration_ms = excluded.rag_retrieval_duration_ms,
                rag_mode = excluded.rag_mode,
                rag_source_count = excluded.rag_source_count,
                rag_hit = excluded.rag_hit,
                rag_reconciliation_count = excluded.rag_reconciliation_count,
                security_status = excluded.security_status,
                security_risk_level = excluded.security_risk_level,
                prompt_injection_detected = excluded.prompt_injection_detected,
                sensitive_data_detected = excluded.sensitive_data_detected,
                output_leakage_detected = excluded.output_leakage_detected,
                pii_email_redaction_count = excluded.pii_email_redaction_count,
                pii_phone_redaction_count = excluded.pii_phone_redaction_count,
                pii_address_redaction_count = excluded.pii_address_redaction_count,
                security_finding_codes = excluded.security_finding_codes,
                json_parse_success = excluded.json_parse_success,
                saved_to_history = excluded.saved_to_history,
                application_id = excluded.application_id,
                next_action = excluded.next_action,
                error_code = excluded.error_code,
                error_stage = excluded.error_stage,
                source_type = excluded.source_type
            """,
            (
                metric["workflow_id"],
                metric["created_at"],
                metric.get("completed_at"),
                metric["outcome"],
                metric.get("workflow_status"),
                metric.get("workflow_duration_ms"),
                metric.get("workflow_duration_us"),
                metric.get("llm_duration_ms"),
                metric.get("rag_retrieval_duration_ms"),
                metric.get("rag_mode"),
                metric.get("rag_source_count", 0),
                metric.get("rag_hit", 0),
                metric.get("rag_reconciliation_count", 0),
                metric.get("security_status"),
                metric.get("security_risk_level"),
                metric.get("prompt_injection_detected", 0),
                metric.get("sensitive_data_detected", 0),
                metric.get("output_leakage_detected", 0),
                metric.get("pii_email_redaction_count", 0),
                metric.get("pii_phone_redaction_count", 0),
                metric.get("pii_address_redaction_count", 0),
                safe_json_dumps(metric.get("security_finding_codes") or []),
                metric.get("json_parse_success"),
                metric.get("saved_to_history", 0),
                metric.get("application_id"),
                metric.get("next_action"),
                metric.get("error_code"),
                metric.get("error_stage"),
                metric.get("source_type"),
            ),
        )


def record_step_metrics(workflow_id: str, steps: list[dict[str, Any]], created_at: str | None = None) -> None:
    created = created_at or utc_now()
    with get_connection() as connection:
        connection.execute("DELETE FROM analysis_step_metrics WHERE workflow_id = ?", (workflow_id,))
        for step in steps:
            if not isinstance(step, dict):
                continue
            connection.execute(
                """
                INSERT INTO analysis_step_metrics (
                    workflow_id, step_key, status, duration_ms, duration_us, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    str(step.get("key") or "")[:120],
                    str(step.get("status") or "pending")[:40],
                    safe_float(step.get("duration_ms"), None),
                    safe_int(step.get("duration_us"), None),
                    created,
                ),
            )


def persist_analysis_metrics(metric: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    record_analysis_metric(metric)
    record_step_metrics(metric["workflow_id"], steps, metric.get("created_at"))


def persist_analysis_metrics_best_effort(metric: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    try:
        persist_analysis_metrics(metric, steps)
    except Exception as exc:
        logger.warning("Monitoring metrics persistence failed error_type=%s", type(exc).__name__)


def rows_for_period(days: Any) -> tuple[list[sqlite3.Row], str, str, int]:
    start, end, safe_days = period_bounds(days)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM analysis_metrics
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at DESC
            """,
            (start, end),
        ).fetchall()
    return rows, start, end, safe_days


def get_overview(days: Any = 30) -> dict[str, Any]:
    rows, start, end, safe_days = rows_for_period(days)
    total = len(rows)
    completed = sum(1 for row in rows if row["outcome"] == "completed")
    warnings = sum(1 for row in rows if row["outcome"] == "completed_with_warnings")
    failed = sum(1 for row in rows if row["outcome"] == "failed")
    blocked = sum(1 for row in rows if row["outcome"] == "blocked")
    workflow_durations = [float(row["workflow_duration_ms"]) for row in rows if row["workflow_duration_ms"] is not None]
    llm_durations = [float(row["llm_duration_ms"]) for row in rows if row["llm_duration_ms"] is not None]
    rag_enabled = [row for row in rows if row["rag_mode"] == "project"]
    rag_hits = sum(1 for row in rag_enabled if int(row["rag_hit"] or 0) == 1)
    json_failures = sum(1 for row in rows if row["json_parse_success"] == 0)
    return {
        "period_days": safe_days,
        "period_start": start,
        "period_end": end,
        "total_analyses": total,
        "completed": completed,
        "completed_with_warnings": warnings,
        "failed": failed,
        "blocked": blocked,
        "completion_rate": safe_rate(completed + warnings, total),
        "clean_success_rate": safe_rate(completed, total),
        "average_workflow_duration_ms": average(workflow_durations),
        "average_llm_duration_ms": average(llm_durations),
        "rag_hit_rate": safe_rate(rag_hits, len(rag_enabled)),
        "security_warning_rate": safe_rate(warnings, total),
        "json_parse_failure_count": json_failures,
    }


def get_workflow_step_performance(days: Any = 30) -> dict[str, Any]:
    start, end, safe_days = period_bounds(days)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM analysis_step_metrics
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY step_key, created_at
            """,
            (start, end),
        ).fetchall()
    by_step: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_step.setdefault(row["step_key"], []).append(row)
    items: list[dict[str, Any]] = []
    for step_key, step_rows in sorted(by_step.items()):
        latency_rows = [
            row for row in step_rows
            if row["duration_ms"] is not None and row["status"] != "skipped"
        ]
        latencies = [float(row["duration_ms"]) for row in latency_rows]
        items.append(
            {
                "step_key": step_key,
                "total_count": len(step_rows),
                "completed_count": sum(1 for row in step_rows if row["status"] == "completed"),
                "failed_count": sum(1 for row in step_rows if row["status"] == "failed"),
                "skipped_count": sum(1 for row in step_rows if row["status"] == "skipped"),
                "average_ms": average(latencies),
                "minimum_ms": round(min(latencies), 3) if latencies else 0.0,
                "maximum_ms": round(max(latencies), 3) if latencies else 0.0,
                "p50_ms": nearest_rank_percentile(latencies, 50),
                "p95_ms": nearest_rank_percentile(latencies, 95),
            }
        )
    return {"period_days": safe_days, "period_start": start, "period_end": end, "items": items}


def get_rag_metrics(days: Any = 30) -> dict[str, Any]:
    rows, start, end, safe_days = rows_for_period(days)
    rag_enabled = [row for row in rows if row["rag_mode"] == "project"]
    hit_runs = [row for row in rag_enabled if int(row["rag_hit"] or 0) == 1]
    source_counts = [int(row["rag_source_count"] or 0) for row in rag_enabled]
    retrieval_durations = [
        float(row["rag_retrieval_duration_ms"])
        for row in rows
        if row["rag_retrieval_duration_ms"] is not None
    ]
    reconciliation_rows = [row for row in rows if int(row["rag_reconciliation_count"] or 0) > 0]
    return {
        "period_days": safe_days,
        "period_start": start,
        "period_end": end,
        "rag_enabled_runs": len(rag_enabled),
        "rag_hit_runs": len(hit_runs),
        "rag_no_hit_runs": max(0, len(rag_enabled) - len(hit_runs)),
        "rag_hit_rate": safe_rate(len(hit_runs), len(rag_enabled)),
        "average_source_count": average([float(value) for value in source_counts]),
        "average_retrieval_duration_ms": average(retrieval_durations),
        "reconciliation_runs": len(reconciliation_rows),
        "reconciliation_total": sum(int(row["rag_reconciliation_count"] or 0) for row in rows),
    }


def get_security_metrics(days: Any = 30) -> dict[str, Any]:
    rows, start, end, safe_days = rows_for_period(days)
    finding_distribution: dict[str, int] = {}
    for row in rows:
        for code in safe_json_list(row["security_finding_codes"]):
            finding_distribution[code] = finding_distribution.get(code, 0) + 1
    return {
        "period_days": safe_days,
        "period_start": start,
        "period_end": end,
        "passed": sum(1 for row in rows if row["security_status"] == "passed"),
        "passed_with_warnings": sum(1 for row in rows if row["security_status"] == "passed_with_warnings"),
        "blocked": sum(1 for row in rows if row["security_status"] == "blocked"),
        "prompt_injection_detection_count": sum(int(row["prompt_injection_detected"] or 0) for row in rows),
        "sensitive_data_detection_count": sum(int(row["sensitive_data_detected"] or 0) for row in rows),
        "output_leakage_detection_count": sum(int(row["output_leakage_detected"] or 0) for row in rows),
        "total_email_redactions": sum(int(row["pii_email_redaction_count"] or 0) for row in rows),
        "total_phone_redactions": sum(int(row["pii_phone_redaction_count"] or 0) for row in rows),
        "total_address_redactions": sum(int(row["pii_address_redaction_count"] or 0) for row in rows),
        "finding_codes": dict(sorted(finding_distribution.items())),
    }


def get_recommendation_metrics(days: Any = 30) -> dict[str, Any]:
    rows, start, end, safe_days = rows_for_period(days)
    action_distribution = {action: 0 for action in RECOMMENDATION_ACTIONS}
    for row in rows:
        action = row["next_action"]
        if action in action_distribution:
            action_distribution[action] += 1
    with get_connection() as connection:
        decision_rows = connection.execute(
            """
            SELECT next_action_decision FROM application_records
            WHERE created_at >= ? AND created_at <= ?
            """,
            (start, end),
        ).fetchall()
    decision_distribution = {decision: 0 for decision in DECISIONS}
    for row in decision_rows:
        decision = row["next_action_decision"] or "pending"
        if decision in decision_distribution:
            decision_distribution[decision] += 1
    decision_total = sum(decision_distribution.values())
    accepted_or_completed = decision_distribution["accepted"] + decision_distribution["completed"]
    return {
        "period_days": safe_days,
        "period_start": start,
        "period_end": end,
        "action_distribution": action_distribution,
        "decision_distribution": decision_distribution,
        "recommendation_acceptance_rate": safe_rate(accepted_or_completed, decision_total),
    }


def list_traces(
    *,
    days: Any = 30,
    limit: Any = 50,
    offset: Any = 0,
    outcome: str | None = None,
    security_status: str | None = None,
    risk_level: str | None = None,
) -> dict[str, Any]:
    start, end, safe_days = period_bounds(days)
    safe_limit = clamp_limit(limit)
    safe_offset = max(0, safe_int(offset, 0))
    where = ["created_at >= ?", "created_at <= ?"]
    params: list[Any] = [start, end]
    if outcome:
        where.append("outcome = ?")
        params.append(outcome)
    if security_status:
        where.append("security_status = ?")
        params.append(security_status)
    if risk_level:
        where.append("security_risk_level = ?")
        params.append(risk_level)
    where_sql = " AND ".join(where)
    with get_connection() as connection:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS total FROM analysis_metrics WHERE {where_sql}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT workflow_id, created_at, outcome, workflow_status, workflow_duration_ms,
                   llm_duration_ms, rag_mode, rag_source_count, security_status,
                   security_risk_level, next_action, error_code, error_stage, application_id
            FROM analysis_metrics
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        ).fetchall()
    return {
        "period_days": safe_days,
        "period_start": start,
        "period_end": end,
        "total": int(total_row["total"] if total_row else 0),
        "limit": safe_limit,
        "offset": safe_offset,
        "items": [dict(row) for row in rows],
    }


def get_trace_detail(workflow_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM analysis_metrics WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if row is None:
            return None
        step_rows = connection.execute(
            """
            SELECT step_key, status, duration_ms, duration_us
            FROM analysis_step_metrics
            WHERE workflow_id = ?
            ORDER BY id ASC
            """,
            (workflow_id,),
        ).fetchall()
    return {
        "workflow_id": row["workflow_id"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "outcome": row["outcome"],
        "workflow_status": row["workflow_status"],
        "workflow_duration_ms": row["workflow_duration_ms"],
        "llm_duration_ms": row["llm_duration_ms"],
        "steps": [dict(step) for step in step_rows],
        "rag": {
            "mode": row["rag_mode"],
            "source_count": int(row["rag_source_count"] or 0),
            "hit": bool(row["rag_hit"]),
            "reconciliation_count": int(row["rag_reconciliation_count"] or 0),
        },
        "security": {
            "status": row["security_status"],
            "risk_level": row["security_risk_level"],
            "prompt_injection_detected": bool(row["prompt_injection_detected"]),
            "sensitive_data_detected": bool(row["sensitive_data_detected"]),
            "output_leakage_detected": bool(row["output_leakage_detected"]),
            "finding_codes": safe_json_list(row["security_finding_codes"]),
        },
        "json_parse_success": None if row["json_parse_success"] is None else bool(row["json_parse_success"]),
        "saved_to_history": bool(row["saved_to_history"]),
        "application_id": row["application_id"],
        "next_action": row["next_action"],
        "error_code": row["error_code"],
        "error_stage": row["error_stage"],
    }


def monitoring_status() -> dict[str, Any]:
    return {
        "enabled": True,
        "storage": "sqlite",
        "version": MONITORING_VERSION,
        "privacy_mode": "metadata_only",
        "limitations": [
            "Monitoring is local and process-level.",
            "This version does not provide distributed tracing.",
            "Raw resumes, job descriptions, prompts, and model responses are not stored.",
        ],
    }
