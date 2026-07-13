"""Safe, scoped lifecycle operations for local monitoring and evaluation metadata."""

from __future__ import annotations

import hmac
import os
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import psycopg

from database import get_connection
from config import load_config


MONITORING_OUTCOMES = ("completed", "completed_with_warnings", "failed", "blocked")
SECURITY_STATUSES = ("passed", "passed_with_warnings", "blocked", "not_available")
RISK_LEVELS = ("low", "medium", "high", "critical")
EVALUATION_STATUSES = ("running", "completed", "completed_with_failures", "failed")
MODES = ("all", "filtered")
MAX_DATE_RANGE_DAYS = 3650
WORKFLOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class DataManagementError(ValueError):
    def __init__(self, status_code: int, error_code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


def _invalid_request(message: str) -> DataManagementError:
    return DataManagementError(400, "INVALID_DATA_MANAGEMENT_REQUEST", message)


def _as_string_list(value: Any, field_name: str, allowed: tuple[str, ...]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _invalid_request(f"{field_name} must be a list of supported values.")
    if any(item not in allowed for item in value):
        raise _invalid_request(f"{field_name} contains an unsupported value.")
    return list(dict.fromkeys(value))


def _parse_date(value: Any, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _invalid_request(f"{field_name} must use YYYY-MM-DD.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise _invalid_request(f"{field_name} must use YYYY-MM-DD.") from exc
    if value != parsed.isoformat():
        raise _invalid_request(f"{field_name} must use YYYY-MM-DD.")
    return parsed


def _utc_timestamp(value: date) -> str:
    return datetime.combine(value, time.min, tzinfo=timezone.utc).isoformat(timespec="seconds")


def _validate_mode_and_dates(payload: dict[str, Any]) -> tuple[str, date | None, date | None]:
    mode = payload.get("mode")
    if mode not in MODES:
        raise _invalid_request("mode must be all or filtered.")
    date_from = _parse_date(payload.get("date_from"), "date_from")
    date_to = _parse_date(payload.get("date_to"), "date_to")
    if date_from and date_to:
        if date_from > date_to:
            raise _invalid_request("date_from cannot be later than date_to.")
        if (date_to - date_from).days > MAX_DATE_RANGE_DAYS:
            raise _invalid_request("The date range cannot exceed 3650 days.")
    return mode, date_from, date_to


def _in_clause(column: str, values: list[str], clauses: list[str], params: list[Any]) -> None:
    if not values:
        return
    placeholders = ", ".join("?" for _ in values)
    clauses.append(f"{column} IN ({placeholders})")
    params.extend(values)


def monitoring_filter(payload: dict[str, Any]) -> tuple[str, str, list[Any]]:
    """Validate a monitoring cleanup request and produce fixed-column SQL filters."""
    mode, date_from, date_to = _validate_mode_and_dates(payload)
    outcomes = _as_string_list(payload.get("outcomes", []), "outcomes", MONITORING_OUTCOMES)
    security_statuses = _as_string_list(
        payload.get("security_statuses", []), "security_statuses", SECURITY_STATUSES
    )
    risk_levels = _as_string_list(payload.get("risk_levels", []), "risk_levels", RISK_LEVELS)
    has_filter = bool(date_from or date_to or outcomes or security_statuses or risk_levels)
    if mode == "all" and has_filter:
        raise _invalid_request("all mode cannot include filters.")
    if mode == "filtered" and not has_filter:
        raise _invalid_request("filtered mode requires at least one filter.")

    clauses: list[str] = []
    params: list[Any] = []
    if date_from:
        clauses.append("created_at >= ?")
        params.append(_utc_timestamp(date_from))
    if date_to:
        clauses.append("created_at < ?")
        params.append(_utc_timestamp(date_to + timedelta(days=1)))
    _in_clause("outcome", outcomes, clauses, params)
    _in_clause("security_status", security_statuses, clauses, params)
    _in_clause("security_risk_level", risk_levels, clauses, params)
    return mode, " AND ".join(clauses) if clauses else "1 = 1", params


def evaluation_filter(payload: dict[str, Any]) -> tuple[str, str, list[Any]]:
    """Validate evaluation cleanup inputs and produce fixed-column SQL filters."""
    mode, date_from, date_to = _validate_mode_and_dates(payload)
    statuses = _as_string_list(payload.get("statuses", []), "statuses", EVALUATION_STATUSES)
    has_filter = bool(date_from or date_to or statuses)
    if mode == "all" and has_filter:
        raise _invalid_request("all mode cannot include filters.")
    if mode == "filtered" and not has_filter:
        raise _invalid_request("filtered mode requires at least one filter.")

    clauses: list[str] = []
    params: list[Any] = []
    if date_from:
        clauses.append("started_at >= ?")
        params.append(_utc_timestamp(date_from))
    if date_to:
        clauses.append("started_at < ?")
        params.append(_utc_timestamp(date_to + timedelta(days=1)))
    _in_clause("status", statuses, clauses, params)
    return mode, " AND ".join(clauses) if clauses else "1 = 1", params


def _count(connection: sqlite3.Connection, sql: str, params: list[Any]) -> int:
    row = connection.execute(sql, params).fetchone()
    return int(row["total"] if row else 0)


def preview_monitoring_deletion(payload: dict[str, Any]) -> dict[str, Any]:
    mode, where_sql, params = monitoring_filter(payload)
    with get_connection() as connection:
        analyses = _count(
            connection,
            f"SELECT COUNT(*) AS total FROM analysis_metrics WHERE {where_sql}",
            params,
        )
        steps = _count(
            connection,
            f"""
            SELECT COUNT(*) AS total FROM analysis_step_metrics
            WHERE workflow_id IN (
                SELECT workflow_id FROM analysis_metrics WHERE {where_sql}
            )
            """,
            params,
        )
    return {
        "mode": mode,
        "analysis_metrics_count": analyses,
        "analysis_step_metrics_count": steps,
        "affected_workflow_count": analyses,
        "application_records_count": 0,
        "project_knowledge_records_count": 0,
        "will_delete_application_history": False,
        "will_delete_project_knowledge": False,
    }


def _require_confirmation(payload: dict[str, Any], expected: str) -> None:
    if payload.get("confirmation") != expected:
        raise DataManagementError(400, "CONFIRMATION_MISMATCH", "The deletion confirmation did not match.")


def delete_monitoring_data(payload: dict[str, Any]) -> dict[str, Any]:
    mode, where_sql, params = monitoring_filter(payload)
    expected_confirmation = (
        "DELETE ALL MONITORING DATA" if mode == "all" else "DELETE FILTERED MONITORING DATA"
    )
    _require_confirmation(payload, expected_confirmation)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        analyses = _count(
            connection,
            f"SELECT COUNT(*) AS total FROM analysis_metrics WHERE {where_sql}",
            params,
        )
        steps = _count(
            connection,
            f"""
            SELECT COUNT(*) AS total FROM analysis_step_metrics
            WHERE workflow_id IN (
                SELECT workflow_id FROM analysis_metrics WHERE {where_sql}
            )
            """,
            params,
        )
        connection.execute(
            f"""
            DELETE FROM analysis_step_metrics
            WHERE workflow_id IN (
                SELECT workflow_id FROM analysis_metrics WHERE {where_sql}
            )
            """,
            params,
        )
        connection.execute(f"DELETE FROM analysis_metrics WHERE {where_sql}", params)
        connection.commit()
    except (sqlite3.Error, psycopg.Error) as exc:
        if connection.in_transaction:
            connection.rollback()
        raise DataManagementError(
            500, "DATA_MANAGEMENT_OPERATION_FAILED", "Monitoring deletion could not be completed."
        ) from exc
    finally:
        connection.close()
    return {
        "deleted": True,
        "mode": mode,
        "analysis_metrics_deleted": analyses,
        "analysis_step_metrics_deleted": steps,
        "affected_workflows": analyses,
        "application_history_preserved": True,
        "project_knowledge_preserved": True,
        "evaluation_history_preserved": True,
    }


def delete_trace(workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(workflow_id, str) or not WORKFLOW_ID_PATTERN.fullmatch(workflow_id):
        raise _invalid_request("workflow_id has an unsupported format.")
    _require_confirmation(payload, "DELETE TRACE")
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        metric_count = _count(
            connection,
            "SELECT COUNT(*) AS total FROM analysis_metrics WHERE workflow_id = ?",
            [workflow_id],
        )
        if not metric_count:
            connection.rollback()
            raise DataManagementError(404, "TRACE_NOT_FOUND", "Workflow trace was not found.")
        step_count = _count(
            connection,
            "SELECT COUNT(*) AS total FROM analysis_step_metrics WHERE workflow_id = ?",
            [workflow_id],
        )
        connection.execute("DELETE FROM analysis_step_metrics WHERE workflow_id = ?", (workflow_id,))
        connection.execute("DELETE FROM analysis_metrics WHERE workflow_id = ?", (workflow_id,))
        connection.commit()
    except DataManagementError:
        raise
    except (sqlite3.Error, psycopg.Error) as exc:
        if connection.in_transaction:
            connection.rollback()
        raise DataManagementError(
            500, "DATA_MANAGEMENT_OPERATION_FAILED", "Trace deletion could not be completed."
        ) from exc
    finally:
        connection.close()
    return {
        "deleted": True,
        "workflow_id": workflow_id,
        "analysis_metrics_deleted": metric_count,
        "analysis_step_metrics_deleted": step_count,
        "application_history_preserved": True,
    }


def preview_evaluation_deletion(payload: dict[str, Any]) -> dict[str, Any]:
    _mode, where_sql, params = evaluation_filter(payload)
    with get_connection() as connection:
        runs = _count(
            connection,
            f"SELECT COUNT(*) AS total FROM evaluation_runs WHERE {where_sql}",
            params,
        )
        results = _count(
            connection,
            f"""
            SELECT COUNT(*) AS total FROM evaluation_results
            WHERE run_id IN (SELECT run_id FROM evaluation_runs WHERE {where_sql})
            """,
            params,
        )
    return {
        "evaluation_runs_count": runs,
        "evaluation_results_count": results,
        "evaluation_case_file_preserved": True,
        "will_delete_cases_json": False,
    }


def delete_evaluation_data(payload: dict[str, Any]) -> dict[str, Any]:
    mode, where_sql, params = evaluation_filter(payload)
    expected_confirmation = (
        "DELETE EVALUATION HISTORY" if mode == "all" else "DELETE FILTERED EVALUATION HISTORY"
    )
    _require_confirmation(payload, expected_confirmation)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        runs = _count(
            connection,
            f"SELECT COUNT(*) AS total FROM evaluation_runs WHERE {where_sql}",
            params,
        )
        results = _count(
            connection,
            f"""
            SELECT COUNT(*) AS total FROM evaluation_results
            WHERE run_id IN (SELECT run_id FROM evaluation_runs WHERE {where_sql})
            """,
            params,
        )
        connection.execute(
            f"""
            DELETE FROM evaluation_results
            WHERE run_id IN (SELECT run_id FROM evaluation_runs WHERE {where_sql})
            """,
            params,
        )
        connection.execute(f"DELETE FROM evaluation_runs WHERE {where_sql}", params)
        connection.commit()
    except (sqlite3.Error, psycopg.Error) as exc:
        if connection.in_transaction:
            connection.rollback()
        raise DataManagementError(
            500, "DATA_MANAGEMENT_OPERATION_FAILED", "Evaluation deletion could not be completed."
        ) from exc
    finally:
        connection.close()
    return {
        "deleted": True,
        "evaluation_runs_deleted": runs,
        "evaluation_results_deleted": results,
        "evaluation_cases_preserved": True,
        "monitoring_data_preserved": True,
    }


def remote_admin_allowed() -> bool:
    return load_config(validate_production=False).monitoring_allow_remote_admin


def is_loopback_request(client_host: str | None) -> bool:
    return client_host in {"127.0.0.1", "::1"}


def authorize_destructive_request(admin_token: str | None, client_host: str | None) -> None:
    configured_token = os.getenv("MONITORING_ADMIN_TOKEN", "")
    if not configured_token:
        raise DataManagementError(
            503,
            "DATA_MANAGEMENT_DISABLED",
            "Data management is disabled until an administrator token is configured.",
        )
    if not remote_admin_allowed() and not is_loopback_request(client_host):
        raise DataManagementError(
            403,
            "REMOTE_ADMIN_DISABLED",
            "Remote destructive operations are disabled.",
        )
    if not admin_token or not hmac.compare_digest(admin_token, configured_token):
        raise DataManagementError(403, "INVALID_ADMIN_TOKEN", "The administrator token is invalid.")


def data_management_status(client_host: str | None) -> dict[str, Any]:
    configured_token = os.getenv("MONITORING_ADMIN_TOKEN", "")
    return {
        "version": "1.9",
        "data_management_enabled": bool(configured_token),
        "admin_token_configured": bool(configured_token),
        "remote_admin_allowed": remote_admin_allowed(),
        "request_is_local": is_loopback_request(client_host),
        "monitoring_cleanup_supported": True,
        "evaluation_cleanup_supported": True,
        "trace_deletion_supported": True,
        "test_database_isolation": True,
        "limitations": [
            "Application history is not deleted by monitoring cleanup.",
            "Project Knowledge data is not deleted by monitoring cleanup.",
            "Remote destructive actions are disabled by default.",
        ],
    }
