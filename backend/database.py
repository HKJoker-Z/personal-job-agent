import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"

ALLOWED_APPLICATION_STATUSES = ("Saved", "Applied", "Interview", "Rejected", "Offer")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


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
                notes TEXT
            )
            """
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


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text or fallback


def row_to_list_item(row: sqlite3.Row) -> dict[str, Any]:
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
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                match_score
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


def delete_application_record(application_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM application_records WHERE id = ?",
            (application_id,),
        )
        return cursor.rowcount > 0
