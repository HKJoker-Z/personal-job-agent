import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_utils import normalized_security_scan


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = (BACKEND_DIR / "data" / "app.db").resolve(strict=False)
ALLOWED_APP_ENVS = ("development", "production", "test")

ALLOWED_APPLICATION_STATUSES = ("Saved", "Applied", "Interview", "Rejected", "Offer")
ALLOWED_NEXT_ACTION_DECISIONS = ("pending", "accepted", "dismissed", "completed")
ALLOWED_KNOWLEDGE_CATEGORIES = (
    "Resume",
    "Project Experience",
    "Skill Profile",
    "Past Cover Letter",
    "Company Research",
    "Other",
)
SCORING_BREAKDOWN_KEYS = (
    "skills_match",
    "project_experience",
    "education",
    "work_experience",
    "keyword_match",
)
ATS_ANALYSIS_KEYS = (
    "important_keywords",
    "matched_keywords",
    "missing_keywords",
    "keyword_suggestions",
)
CONTENT_PREVIEW_CHARS = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_app_env() -> str:
    """Return the supported runtime environment without caching environment state."""
    app_env = os.getenv("APP_ENV", "development").strip().lower() or "development"
    if app_env not in ALLOWED_APP_ENVS:
        raise RuntimeError("APP_ENV must be development, production, or test.")
    return app_env


def get_database_path() -> Path:
    """Resolve the configured SQLite database path relative to this module when needed."""
    configured_path = os.getenv("APP_DATABASE_PATH", "").strip()
    if not configured_path:
        return DEFAULT_DATABASE_PATH
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path.resolve(strict=False)


def is_default_application_database(path: Path) -> bool:
    """Identify the real application database, including an existing symlink to it."""
    return path.expanduser().resolve(strict=False) == DEFAULT_DATABASE_PATH


def assert_safe_test_database(path: Path, app_env: str) -> None:
    """Fail closed so tests can never silently write the user's application database."""
    if app_env == "test" and is_default_application_database(path):
        raise RuntimeError(
            "APP_ENV=test requires APP_DATABASE_PATH to point to a non-default temporary SQLite database."
        )


def get_connection() -> sqlite3.Connection:
    database_path = get_database_path()
    assert_safe_test_database(database_path, get_app_env())
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def default_scoring_breakdown() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "score": 0,
            "reason": "",
            "evidence": [],
        }
        for key in SCORING_BREAKDOWN_KEYS
    }


def default_ats_analysis() -> dict[str, list[str]]:
    return {key: [] for key in ATS_ANALYSIS_KEYS}


def default_scoring_breakdown_json() -> str:
    return json.dumps(default_scoring_breakdown(), ensure_ascii=False)


def default_ats_analysis_json() -> str:
    return json.dumps(default_ats_analysis(), ensure_ascii=False)


def get_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def add_column_if_missing(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    existing_columns: set[str],
    column_name: str,
    column_definition: str,
) -> None:
    if column_name in existing_columns:
        return

    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")
    existing_columns.add(column_name)


def ensure_knowledge_fts(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
            USING fts5(
                content,
                title,
                category,
                chunk_id UNINDEXED,
                document_id UNINDEXED
            )
            """
        )
    except sqlite3.OperationalError:
        return False
    return True


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS application_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                company_name TEXT NOT NULL DEFAULT 'Unknown Company',
                job_title TEXT NOT NULL DEFAULT 'Unknown Position',
                job_url TEXT,
                resume_filename TEXT,
                application_status TEXT NOT NULL DEFAULT 'Saved',
                match_score INTEGER NOT NULL DEFAULT 0,
                match_reason TEXT NOT NULL DEFAULT '',
                job_summary TEXT NOT NULL DEFAULT '',
                matched_skills TEXT NOT NULL DEFAULT '[]',
                missing_skills TEXT NOT NULL DEFAULT '[]',
                resume_suggestions TEXT NOT NULL DEFAULT '[]',
                cover_letter TEXT NOT NULL DEFAULT '',
                scoring_breakdown TEXT NOT NULL DEFAULT '{"skills_match":{"score":0,"reason":"","evidence":[]},"project_experience":{"score":0,"reason":"","evidence":[]},"education":{"score":0,"reason":"","evidence":[]},"work_experience":{"score":0,"reason":"","evidence":[]},"keyword_match":{"score":0,"reason":"","evidence":[]}}',
                ats_analysis TEXT NOT NULL DEFAULT '{"important_keywords":[],"matched_keywords":[],"missing_keywords":[],"keyword_suggestions":[]}',
                upgraded_resume_bullets TEXT NOT NULL DEFAULT '[]',
                rag_mode TEXT NOT NULL DEFAULT '',
                rag_sources TEXT NOT NULL DEFAULT '[]',
                workflow_id TEXT,
                workflow_steps TEXT NOT NULL DEFAULT '[]',
                workflow_duration_ms REAL,
                workflow_duration_us INTEGER,
                next_action TEXT NOT NULL DEFAULT '{}',
                next_action_decision TEXT NOT NULL DEFAULT 'pending',
                next_action_decision_notes TEXT,
                next_action_decided_at TEXT,
                security_scan TEXT NOT NULL DEFAULT '{}',
                security_status TEXT NOT NULL DEFAULT 'not_available',
                security_policy_version TEXT,
                notes TEXT
            )
            """
        )
        existing_columns = get_table_columns(connection, "application_records")
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="scoring_breakdown",
            column_definition=(
                "scoring_breakdown TEXT NOT NULL DEFAULT "
                f"'{default_scoring_breakdown_json()}'"
            ),
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="ats_analysis",
            column_definition=(
                "ats_analysis TEXT NOT NULL DEFAULT "
                f"'{default_ats_analysis_json()}'"
            ),
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="upgraded_resume_bullets",
            column_definition="upgraded_resume_bullets TEXT NOT NULL DEFAULT '[]'",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="rag_sources",
            column_definition="rag_sources TEXT NOT NULL DEFAULT '[]'",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="rag_mode",
            column_definition="rag_mode TEXT NOT NULL DEFAULT ''",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="workflow_id",
            column_definition="workflow_id TEXT",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="workflow_steps",
            column_definition="workflow_steps TEXT NOT NULL DEFAULT '[]'",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="workflow_duration_ms",
            column_definition="workflow_duration_ms REAL",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="workflow_duration_us",
            column_definition="workflow_duration_us INTEGER",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="next_action",
            column_definition="next_action TEXT NOT NULL DEFAULT '{}'",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="next_action_decision",
            column_definition="next_action_decision TEXT NOT NULL DEFAULT 'pending'",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="next_action_decision_notes",
            column_definition="next_action_decision_notes TEXT",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="next_action_decided_at",
            column_definition="next_action_decided_at TEXT",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="security_scan",
            column_definition="security_scan TEXT NOT NULL DEFAULT '{}'",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="security_status",
            column_definition="security_status TEXT NOT NULL DEFAULT 'not_available'",
        )
        add_column_if_missing(
            connection,
            table_name="application_records",
            existing_columns=existing_columns,
            column_name="security_policy_version",
            column_definition="security_policy_version TEXT",
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_application_records_status
            ON application_records(application_status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_application_records_company_title
            ON application_records(company_name, job_title)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                source_filename TEXT,
                content_preview TEXT,
                chunk_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_estimate INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_documents_category
            ON knowledge_documents(category)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document_id
            ON knowledge_chunks(document_id)
            """
        )
        ensure_knowledge_fts(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                outcome TEXT NOT NULL,
                workflow_status TEXT,
                workflow_duration_ms REAL,
                workflow_duration_us INTEGER,
                llm_duration_ms REAL,
                rag_retrieval_duration_ms REAL,
                rag_mode TEXT,
                rag_source_count INTEGER NOT NULL DEFAULT 0,
                rag_hit INTEGER NOT NULL DEFAULT 0,
                rag_reconciliation_count INTEGER NOT NULL DEFAULT 0,
                security_status TEXT,
                security_risk_level TEXT,
                prompt_injection_detected INTEGER NOT NULL DEFAULT 0,
                sensitive_data_detected INTEGER NOT NULL DEFAULT 0,
                output_leakage_detected INTEGER NOT NULL DEFAULT 0,
                pii_email_redaction_count INTEGER NOT NULL DEFAULT 0,
                pii_phone_redaction_count INTEGER NOT NULL DEFAULT 0,
                pii_address_redaction_count INTEGER NOT NULL DEFAULT 0,
                security_finding_codes TEXT,
                json_parse_success INTEGER,
                saved_to_history INTEGER NOT NULL DEFAULT 0,
                application_id INTEGER,
                next_action TEXT,
                error_code TEXT,
                error_stage TEXT,
                source_type TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_metrics_created_at
            ON analysis_metrics(created_at)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_metrics_outcome
            ON analysis_metrics(outcome)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_metrics_security
            ON analysis_metrics(security_status, security_risk_level)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_step_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                step_key TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms REAL,
                duration_us INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_step_metrics_workflow_step
            ON analysis_step_metrics(workflow_id, step_key)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_step_metrics_created_at
            ON analysis_step_metrics(created_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                suite_name TEXT NOT NULL,
                suite_version TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_ms REAL,
                total_cases INTEGER NOT NULL DEFAULT 0,
                passed_cases INTEGER NOT NULL DEFAULT 0,
                failed_cases INTEGER NOT NULL DEFAULT 0,
                error_cases INTEGER NOT NULL DEFAULT 0,
                pass_rate REAL NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_runs_started_at
            ON evaluation_runs(started_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                case_name TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms REAL,
                checks_json TEXT,
                failure_summary TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_results_run_id
            ON evaluation_results(run_id)
            """
        )


def serialize_list(value: Any) -> str:
    if not isinstance(value, list):
        return "[]"
    return json.dumps([str(item) for item in value if item is not None], ensure_ascii=False)


def deserialize_list(value: Any) -> list[str]:
    if not value:
        return []

    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(parsed, list):
        return []

    return [str(item) for item in parsed if item is not None]


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def serialize_json(value: Any, fallback: Any) -> str:
    if not isinstance(value, type(fallback)):
        value = fallback
    return json.dumps(value, ensure_ascii=False)


def deserialize_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback

    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback

    if not isinstance(parsed, type(fallback)):
        return fallback

    return parsed


def normalize_db_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def deserialize_scoring_breakdown(value: Any) -> dict[str, dict[str, Any]]:
    parsed = deserialize_json(value, {})
    if not isinstance(parsed, dict):
        parsed = {}

    normalized = default_scoring_breakdown()
    for key in SCORING_BREAKDOWN_KEYS:
        section = parsed.get(key)
        if not isinstance(section, dict):
            continue

        normalized[key] = {
            "score": normalize_db_score(section.get("score")),
            "reason": clean_text(section.get("reason")),
            "evidence": normalize_string_list(section.get("evidence")),
        }
    return normalized


def deserialize_ats_analysis(value: Any) -> dict[str, list[str]]:
    parsed = deserialize_json(value, {})
    if not isinstance(parsed, dict):
        parsed = {}

    normalized = default_ats_analysis()
    for key in ATS_ANALYSIS_KEYS:
        normalized[key] = normalize_string_list(parsed.get(key))
    return normalized


def deserialize_upgraded_resume_bullets(value: Any) -> list[dict[str, str]]:
    parsed = deserialize_json(value, [])
    if not isinstance(parsed, list):
        return []

    bullets: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        original = clean_text(item.get("original"))
        improved = clean_text(item.get("improved"))
        reason = clean_text(item.get("reason"))
        if not original:
            continue
        bullets.append(
            {
                "original": original,
                "improved": improved,
                "reason": reason,
            }
        )
    return bullets


def deserialize_rag_sources(value: Any) -> list[dict[str, Any]]:
    parsed = deserialize_json(value, [])
    if not isinstance(parsed, list):
        return []

    sources: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        source = {
            "chunk_id": safe_int(item.get("chunk_id")),
            "document_id": safe_int(item.get("document_id")),
            "document_title": clean_text(item.get("document_title")),
            "category": clean_text(item.get("category")),
            "chunk_index": safe_int(item.get("chunk_index")),
            "content_preview": clean_text(item.get("content_preview")),
            "relevance_reason": clean_text(item.get("relevance_reason")),
        }
        if source["document_title"] or source["document_id"] or source["chunk_id"]:
            sources.append(source)
    return sources


def deserialize_workflow_steps(value: Any) -> list[dict[str, Any]]:
    parsed = deserialize_json(value, [])
    if not isinstance(parsed, list):
        return []

    steps: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        steps.append(
            {
                "key": clean_text(item.get("key")),
                "name": clean_text(item.get("name")),
                "status": clean_text(item.get("status"), "pending"),
                "message": clean_text(item.get("message")),
                "started_at": clean_text(item.get("started_at")),
                "completed_at": clean_text(item.get("completed_at")),
                "duration_ms": safe_float(item.get("duration_ms")),
                "duration_us": safe_int(item.get("duration_us")),
            }
        )
    return steps


def default_next_action() -> dict[str, Any]:
    return {
        "action": "",
        "label": "No Recommendation",
        "priority": "low",
        "confidence": 0.0,
        "reason": "No next-action recommendation is available for this record.",
        "recommended_tasks": [],
        "evidence": [],
        "critical_missing_skills": [],
    }


def deserialize_next_action(value: Any) -> dict[str, Any]:
    parsed = deserialize_json(value, {})
    if not isinstance(parsed, dict) or not parsed:
        return default_next_action()

    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "action": clean_text(parsed.get("action")),
        "label": clean_text(parsed.get("label"), "No Recommendation"),
        "priority": clean_text(parsed.get("priority"), "low"),
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": clean_text(parsed.get("reason")),
        "recommended_tasks": normalize_string_list(parsed.get("recommended_tasks")),
        "evidence": normalize_string_list(parsed.get("evidence")),
        "critical_missing_skills": normalize_string_list(parsed.get("critical_missing_skills")),
    }


def deserialize_security_scan(value: Any) -> dict[str, Any]:
    parsed = deserialize_json(value, {})
    if not parsed:
        return {}
    return normalized_security_scan(parsed)


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text or fallback


def safe_int(value: Any, fallback: Any = 0) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def safe_float(value: Any, fallback: Any = 0.0) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def row_to_list_item(row: sqlite3.Row) -> dict[str, Any]:
    next_action = deserialize_next_action(row["next_action"])
    security_scan = deserialize_security_scan(row["security_scan"])
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "company_name": row["company_name"] or "Unknown Company",
        "job_title": row["job_title"] or "Unknown Position",
        "job_url": row["job_url"],
        "resume_filename": row["resume_filename"],
        "application_status": row["application_status"] or "Saved",
        "match_score": row["match_score"],
        "rag_mode": clean_text(row["rag_mode"]),
        "next_action_label": next_action.get("label") or "No Recommendation",
        "next_action_decision": clean_text(row["next_action_decision"], "pending"),
        "security_status": clean_text(row["security_status"], "not_available"),
        "security_risk_level": clean_text(security_scan.get("risk_level"), "not_available"),
    }


def row_to_detail(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "company_name": row["company_name"] or "Unknown Company",
        "job_title": row["job_title"] or "Unknown Position",
        "job_url": row["job_url"],
        "resume_filename": row["resume_filename"],
        "application_status": row["application_status"] or "Saved",
        "match_score": row["match_score"],
        "match_reason": row["match_reason"] or "",
        "job_summary": row["job_summary"] or "",
        "matched_skills": deserialize_list(row["matched_skills"]),
        "missing_skills": deserialize_list(row["missing_skills"]),
        "resume_suggestions": deserialize_list(row["resume_suggestions"]),
        "cover_letter": row["cover_letter"] or "",
        "scoring_breakdown": deserialize_scoring_breakdown(row["scoring_breakdown"]),
        "ats_analysis": deserialize_ats_analysis(row["ats_analysis"]),
        "upgraded_resume_bullets": deserialize_upgraded_resume_bullets(
            row["upgraded_resume_bullets"]
        ),
        "rag_mode": clean_text(row["rag_mode"]),
        "rag_sources": deserialize_rag_sources(row["rag_sources"]),
        "workflow_id": clean_text(row["workflow_id"]),
        "workflow_steps": deserialize_workflow_steps(row["workflow_steps"]),
        "workflow_duration_ms": safe_float(row["workflow_duration_ms"], None),
        "workflow_duration_us": safe_int(row["workflow_duration_us"], None),
        "next_action": deserialize_next_action(row["next_action"]),
        "next_action_decision": clean_text(row["next_action_decision"], "pending"),
        "next_action_decision_notes": row["next_action_decision_notes"],
        "next_action_decided_at": row["next_action_decided_at"],
        "security_scan": deserialize_security_scan(row["security_scan"]),
        "security_status": clean_text(row["security_status"], "not_available"),
        "security_policy_version": clean_text(row["security_policy_version"]) or None,
        "notes": row["notes"],
    }


def insert_application_record(
    analysis_result: dict[str, Any],
    *,
    job_url: str | None,
    resume_filename: str | None,
) -> int:
    now = utc_now()
    company_name = clean_text(analysis_result.get("company_name"), "Unknown Company")
    job_title = clean_text(analysis_result.get("job_title"), "Unknown Position")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO application_records (
                created_at,
                updated_at,
                company_name,
                job_title,
                job_url,
                resume_filename,
                application_status,
                match_score,
                match_reason,
                job_summary,
                matched_skills,
                missing_skills,
                resume_suggestions,
                cover_letter,
                scoring_breakdown,
                ats_analysis,
                upgraded_resume_bullets,
                rag_mode,
                rag_sources,
                workflow_id,
                workflow_steps,
                workflow_duration_ms,
                workflow_duration_us,
                next_action,
                next_action_decision,
                next_action_decision_notes,
                next_action_decided_at,
                security_scan,
                security_status,
                security_policy_version,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                company_name,
                job_title,
                job_url or None,
                resume_filename or None,
                "Saved",
                int(analysis_result.get("match_score", 0)),
                clean_text(analysis_result.get("match_reason")),
                clean_text(analysis_result.get("job_summary")),
                serialize_list(analysis_result.get("matched_skills")),
                serialize_list(analysis_result.get("missing_skills")),
                serialize_list(analysis_result.get("resume_suggestions")),
                clean_text(analysis_result.get("cover_letter")),
                serialize_json(
                    analysis_result.get("scoring_breakdown"),
                    default_scoring_breakdown(),
                ),
                serialize_json(analysis_result.get("ats_analysis"), default_ats_analysis()),
                serialize_json(analysis_result.get("upgraded_resume_bullets"), []),
                clean_text(analysis_result.get("rag_mode")),
                serialize_json(analysis_result.get("rag_sources"), []),
                clean_text(analysis_result.get("workflow_id")) or None,
                serialize_json(analysis_result.get("workflow_steps"), []),
                safe_float(analysis_result.get("workflow_duration_ms"), None),
                safe_int(analysis_result.get("workflow_duration_us"), None),
                serialize_json(analysis_result.get("next_action"), {}),
                clean_text(analysis_result.get("next_action_decision"), "pending"),
                clean_text(analysis_result.get("next_action_decision_notes")) or None,
                clean_text(analysis_result.get("next_action_decided_at")) or None,
                serialize_json(analysis_result.get("security_scan"), {}),
                clean_text(analysis_result.get("security_status"), "not_available"),
                clean_text(analysis_result.get("security_policy_version")) or None,
                None,
            ),
        )
        return int(cursor.lastrowid)


def list_application_records(
    *,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    where_clauses: list[str] = []
    params: list[Any] = []

    if status:
        where_clauses.append("application_status = ?")
        params.append(status)

    if search:
        where_clauses.append("(company_name LIKE ? OR job_title LIKE ?)")
        like_pattern = f"%{search}%"
        params.extend([like_pattern, like_pattern])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with get_connection() as connection:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS total FROM application_records {where_sql}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT
                id,
                created_at,
                updated_at,
                company_name,
                job_title,
                job_url,
                resume_filename,
                application_status,
                match_score,
                rag_mode,
                next_action,
                next_action_decision,
                security_scan,
                security_status
            FROM application_records
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    total = int(total_row["total"]) if total_row else 0
    return [row_to_list_item(row) for row in rows], total


def get_application_record(application_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM application_records WHERE id = ?",
            (application_id,),
        ).fetchone()

    return row_to_detail(row) if row else None


def update_application_record(
    application_id: int,
    *,
    application_status: str,
    notes: str | None,
    update_notes: bool,
) -> dict[str, Any] | None:
    now = utc_now()

    if update_notes:
        sql = """
            UPDATE application_records
            SET application_status = ?, notes = ?, updated_at = ?
            WHERE id = ?
        """
        params: tuple[Any, ...] = (application_status, notes, now, application_id)
    else:
        sql = """
            UPDATE application_records
            SET application_status = ?, updated_at = ?
            WHERE id = ?
        """
        params = (application_status, now, application_id)

    with get_connection() as connection:
        cursor = connection.execute(sql, params)
        if cursor.rowcount == 0:
            return None

    return get_application_record(application_id)


def update_application_workflow_steps(
    application_id: int,
    *,
    workflow_steps: list[dict[str, Any]],
    workflow_duration_ms: float | None = None,
    workflow_duration_us: int | None = None,
) -> dict[str, Any] | None:
    now = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE application_records
            SET workflow_steps = ?,
                workflow_duration_ms = ?,
                workflow_duration_us = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                serialize_json(workflow_steps, []),
                workflow_duration_ms,
                workflow_duration_us,
                now,
                application_id,
            ),
        )
        if cursor.rowcount == 0:
            return None

    return get_application_record(application_id)


def update_next_action_decision(
    application_id: int,
    *,
    decision: str,
    notes: str | None,
) -> dict[str, Any] | None:
    now = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE application_records
            SET next_action_decision = ?,
                next_action_decision_notes = ?,
                next_action_decided_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (decision, notes, now, now, application_id),
        )
        if cursor.rowcount == 0:
            return None

    return get_application_record(application_id)


def delete_application_record(application_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM application_records WHERE id = ?",
            (application_id,),
        )
        return cursor.rowcount > 0


def row_to_knowledge_list_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "title": row["title"],
        "category": row["category"],
        "source_filename": row["source_filename"],
        "content_preview": row["content_preview"] or "",
        "chunk_count": safe_int(row["chunk_count"]),
    }


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def insert_fts_row(
    connection: sqlite3.Connection,
    *,
    chunk_id: int,
    document_id: int,
    title: str,
    category: str,
    content: str,
) -> None:
    try:
        connection.execute(
            """
            INSERT INTO knowledge_chunks_fts (
                content,
                title,
                category,
                chunk_id,
                document_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (content, title, category, str(chunk_id), str(document_id)),
        )
    except sqlite3.OperationalError:
        return


def create_knowledge_document(
    *,
    title: str,
    category: str,
    source_filename: str | None,
    content: str,
    chunks: list[str],
) -> dict[str, Any]:
    now = utc_now()
    preview = content[:CONTENT_PREVIEW_CHARS]

    with get_connection() as connection:
        fts_available = ensure_knowledge_fts(connection)
        cursor = connection.execute(
            """
            INSERT INTO knowledge_documents (
                created_at,
                updated_at,
                title,
                category,
                source_filename,
                content_preview,
                chunk_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now, now, title, category, source_filename or None, preview, len(chunks)),
        )
        document_id = int(cursor.lastrowid)

        for chunk_index, chunk in enumerate(chunks):
            chunk_cursor = connection.execute(
                """
                INSERT INTO knowledge_chunks (
                    document_id,
                    chunk_index,
                    content,
                    token_estimate,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (document_id, chunk_index, chunk, estimate_tokens(chunk), now),
            )
            if fts_available:
                insert_fts_row(
                    connection,
                    chunk_id=int(chunk_cursor.lastrowid),
                    document_id=document_id,
                    title=title,
                    category=category,
                    content=chunk,
                )

    return {
        "id": document_id,
        "title": title,
        "category": category,
        "chunk_count": len(chunks),
    }


def list_knowledge_documents(
    *,
    category: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    where_clauses: list[str] = []
    params: list[Any] = []

    if category:
        where_clauses.append("category = ?")
        params.append(category)

    if search:
        where_clauses.append(
            "(title LIKE ? OR source_filename LIKE ? OR content_preview LIKE ?)"
        )
        like_pattern = f"%{search}%"
        params.extend([like_pattern, like_pattern, like_pattern])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with get_connection() as connection:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS total FROM knowledge_documents {where_sql}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT
                id,
                created_at,
                updated_at,
                title,
                category,
                source_filename,
                content_preview,
                chunk_count
            FROM knowledge_documents
            {where_sql}
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    total = int(total_row["total"]) if total_row else 0
    return [row_to_knowledge_list_item(row) for row in rows], total


def get_knowledge_document(document_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        document = connection.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document is None:
            return None

        chunk_rows = connection.execute(
            """
            SELECT id, chunk_index, content
            FROM knowledge_chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC
            """,
            (document_id,),
        ).fetchall()

    detail = row_to_knowledge_list_item(document)
    detail["chunks"] = [
        {
            "id": row["id"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
        }
        for row in chunk_rows
    ]
    return detail


def delete_knowledge_document(document_id: int) -> bool:
    with get_connection() as connection:
        try:
            connection.execute(
                "DELETE FROM knowledge_chunks_fts WHERE document_id = ?",
                (str(document_id),),
            )
        except sqlite3.OperationalError:
            pass

        connection.execute(
            "DELETE FROM knowledge_chunks WHERE document_id = ?",
            (document_id,),
        )
        cursor = connection.execute(
            "DELETE FROM knowledge_documents WHERE id = ?",
            (document_id,),
        )
        return cursor.rowcount > 0


def find_project_knowledge_document(
    *,
    title: str,
    source_filename: str,
) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                created_at,
                updated_at,
                title,
                category,
                source_filename,
                content_preview,
                chunk_count
            FROM knowledge_documents
            WHERE source_filename = ? OR title = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (source_filename, title),
        ).fetchone()

    return row_to_knowledge_list_item(row) if row else None


def rebuild_project_knowledge_document(
    *,
    title: str,
    category: str,
    source_filename: str,
    content: str,
    chunks: list[str],
) -> dict[str, Any]:
    now = utc_now()
    preview = content[:CONTENT_PREVIEW_CHARS]

    with get_connection() as connection:
        fts_available = ensure_knowledge_fts(connection)
        existing_rows = connection.execute(
            """
            SELECT id
            FROM knowledge_documents
            WHERE source_filename = ? OR title = ?
            ORDER BY id ASC
            """,
            (source_filename, title),
        ).fetchall()
        existing_ids = [int(row["id"]) for row in existing_rows]

        if existing_ids:
            document_id = existing_ids[0]
            ids_to_clear = existing_ids
            placeholders = ",".join("?" for _id in ids_to_clear)

            try:
                connection.execute(
                    f"DELETE FROM knowledge_chunks_fts WHERE document_id IN ({placeholders})",
                    [str(document_id) for document_id in ids_to_clear],
                )
            except sqlite3.OperationalError:
                pass

            connection.execute(
                f"DELETE FROM knowledge_chunks WHERE document_id IN ({placeholders})",
                ids_to_clear,
            )

            duplicate_ids = existing_ids[1:]
            if duplicate_ids:
                duplicate_placeholders = ",".join("?" for _id in duplicate_ids)
                connection.execute(
                    f"DELETE FROM knowledge_documents WHERE id IN ({duplicate_placeholders})",
                    duplicate_ids,
                )

            connection.execute(
                """
                UPDATE knowledge_documents
                SET updated_at = ?,
                    title = ?,
                    category = ?,
                    source_filename = ?,
                    content_preview = ?,
                    chunk_count = ?
                WHERE id = ?
                """,
                (now, title, category, source_filename, preview, len(chunks), document_id),
            )
        else:
            cursor = connection.execute(
                """
                INSERT INTO knowledge_documents (
                    created_at,
                    updated_at,
                    title,
                    category,
                    source_filename,
                    content_preview,
                    chunk_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now, now, title, category, source_filename, preview, len(chunks)),
            )
            document_id = int(cursor.lastrowid)

        for chunk_index, chunk in enumerate(chunks):
            chunk_cursor = connection.execute(
                """
                INSERT INTO knowledge_chunks (
                    document_id,
                    chunk_index,
                    content,
                    token_estimate,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (document_id, chunk_index, chunk, estimate_tokens(chunk), now),
            )
            if fts_available:
                insert_fts_row(
                    connection,
                    chunk_id=int(chunk_cursor.lastrowid),
                    document_id=document_id,
                    title=title,
                    category=category,
                    content=chunk,
                )

    return {
        "id": document_id,
        "title": title,
        "category": category,
        "source_filename": source_filename,
        "chunk_count": len(chunks),
        "updated_at": now,
    }


def tokenize_search_query(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#.\-]*|[\u4e00-\u9fff]+", query.lower())
    return [token for token in tokens if len(token) > 1]


def build_fts_query(query: str) -> str:
    tokens = tokenize_search_query(query)
    if not tokens:
        return ""
    quoted_tokens = []
    for token in tokens[:12]:
        escaped_token = token.replace('"', '""')
        quoted_tokens.append(f'"{escaped_token}"')
    return " OR ".join(quoted_tokens)


def fts_search_knowledge_chunks(
    query: str,
    top_k: int,
    *,
    document_id: int | None = None,
) -> list[dict[str, Any]]:
    fts_query = build_fts_query(query)
    if not fts_query:
        return []

    with get_connection() as connection:
        if not ensure_knowledge_fts(connection):
            return []

        try:
            document_filter = ""
            params: list[Any] = [fts_query]
            if document_id is not None:
                document_filter = "AND knowledge_chunks_fts.document_id = ?"
                params.append(str(document_id))
            params.append(top_k)

            rows = connection.execute(
                f"""
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    d.title AS document_title,
                    d.category,
                    c.chunk_index,
                    c.content,
                    bm25(knowledge_chunks_fts) AS rank
                FROM knowledge_chunks_fts
                JOIN knowledge_chunks c
                    ON c.id = CAST(knowledge_chunks_fts.chunk_id AS INTEGER)
                JOIN knowledge_documents d
                    ON d.id = c.document_id
                WHERE knowledge_chunks_fts MATCH ?
                {document_filter}
                ORDER BY rank ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    items: list[dict[str, Any]] = []
    for row in rows:
        rank = abs(float(row["rank"] or 0))
        score = 1.0 / (1.0 + rank)
        items.append(
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "document_title": row["document_title"],
                "category": row["category"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "score": round(score, 4),
            }
        )
    return items


def fallback_search_knowledge_chunks(
    query: str,
    top_k: int,
    *,
    document_id: int | None = None,
) -> list[dict[str, Any]]:
    tokens = tokenize_search_query(query)
    if not tokens:
        return []

    with get_connection() as connection:
        document_filter = ""
        params: list[Any] = []
        if document_id is not None:
            document_filter = "WHERE c.document_id = ?"
            params.append(document_id)

        rows = connection.execute(
            f"""
            SELECT
                c.id AS chunk_id,
                c.document_id,
                d.title AS document_title,
                d.category,
                c.chunk_index,
                c.content
            FROM knowledge_chunks c
            JOIN knowledge_documents d
                ON d.id = c.document_id
            {document_filter}
            """,
            params,
        ).fetchall()

    scored_items: list[dict[str, Any]] = []
    unique_tokens = list(dict.fromkeys(tokens[:20]))
    for row in rows:
        content = str(row["content"] or "")
        title = str(row["document_title"] or "")
        category = str(row["category"] or "")
        searchable_content = content.lower()
        searchable_title = title.lower()
        searchable_category = category.lower()

        score = 0.0
        for token in unique_tokens:
            if token in searchable_content:
                score += min(searchable_content.count(token), 3)
            if token in searchable_title:
                score += 2.5
            if token in searchable_category:
                score += 1.5

        if score <= 0:
            continue

        normalized_score = score / (len(unique_tokens) * 3.5)
        scored_items.append(
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "document_title": title,
                "category": category,
                "chunk_index": row["chunk_index"],
                "content": content,
                "score": round(min(normalized_score, 1.0), 4),
            }
        )

    scored_items.sort(key=lambda item: item["score"], reverse=True)
    return scored_items[:top_k]


def search_knowledge_chunks(
    query: str,
    top_k: int,
    *,
    document_id: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    fts_items = fts_search_knowledge_chunks(query, top_k, document_id=document_id)
    if fts_items:
        return fts_items, "fts5"
    return fallback_search_knowledge_chunks(query, top_k, document_id=document_id), "fallback"
