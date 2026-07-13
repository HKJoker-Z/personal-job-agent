"""Manual, URL, private file, and bounded CSV Job imports."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import V2Settings
from app.db.models import FileAsset, JobImportRun, utc_now
from app.db.repositories.auth import AuthRepository
from app.jobs.acquisition import SafeJobUrlFetcher
from app.jobs.normalization import canonicalize_url
from app.jobs.service import JobService, serialize_model
from app.resumes.service import extract_resume_text_safely
from app.storage.local import LocalStorageProvider
from app.storage.validation import validate_resume_upload


MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 500
MAX_CSV_CELL = 200_000
CSV_COLUMNS = (
    "company", "title", "location", "description", "url", "employment_type", "work_mode",
    "salary_min", "salary_max", "salary_currency", "application_deadline",
)


class JobImportService:
    def __init__(self, db: Session, owner_id: UUID, settings: V2Settings):
        self.db = db
        self.owner_id = owner_id
        self.settings = settings
        self.jobs = JobService(db, owner_id)
        self.storage = LocalStorageProvider(settings.file_storage_root)

    def manual(self, values: dict[str, object]) -> dict[str, object]:
        url = values.pop("url", None)
        if url:
            values["canonical_url"] = canonicalize_url(str(url))
        values["source_type"] = "manual"
        result = self.jobs.create(values, {
            "source_type": "manual", "original_url": canonicalize_url(str(url)) if url else None,
            "canonical_url": values.get("canonical_url"), "source_metadata": {},
        })
        self._run("manual", 1, result)
        return result

    def url(self, url: str, fetcher: SafeJobUrlFetcher | None = None) -> dict[str, object]:
        page = (fetcher or SafeJobUrlFetcher()).fetch(url)
        values: dict[str, object] = {
            "company_name": page.company or None,
            "title": page.title or None,
            "location": page.location,
            "description": page.description,
            "canonical_url": page.canonical_url,
            "published_at": self._date(page.published_at),
            "application_deadline": self._date(page.deadline),
            "source_type": "url",
        }
        result = self.jobs.create(values, {
            "source_type": "url", "original_url": page.original_url,
            "canonical_url": page.canonical_url, "fetched_at": utc_now(),
            "http_status_summary": page.http_status_summary, "media_type": page.media_type,
            "content_sha256": hashlib.sha256(page.description.encode("utf-8")).hexdigest(),
            "source_metadata": {"redirected": page.original_url != page.canonical_url},
        })
        self._run("url", 1, result)
        return result

    def file(self, filename: str, media_type: str, data: bytes) -> dict[str, object]:
        display, extension, digest = validate_resume_upload(
            filename, media_type, data, self.settings.max_stored_file_size_bytes
        )
        text = extract_resume_text_safely(data, media_type)
        storage_key: str | None = None
        try:
            storage_key, stored_digest = self.storage.write(extension, data, namespace="jobs")
            asset = FileAsset(
                user_id=self.owner_id, kind="job_source", original_filename=display,
                storage_key=storage_key, media_type=media_type, size_bytes=len(data), sha256=stored_digest,
            )
            self.db.add(asset)
            self.db.flush()
            source_type = extension.removeprefix(".")
            result = self.jobs.create(
                {"company_name": None, "title": None, "location": "", "description": text, "source_type": source_type},
                {
                    "source_type": source_type, "file_asset_id": asset.id, "media_type": media_type,
                    "content_sha256": digest, "source_metadata": {"filename": display},
                },
            )
            self._run(source_type, 1, result)
            return {**result, "file": serialize_model(asset, exclude={"user_id", "storage_key"})}
        except Exception:
            if storage_key:
                self.storage.remove(storage_key)
            raise

    def csv(self, data: bytes, validate_only: bool) -> dict[str, object]:
        if not data or len(data) > MAX_CSV_BYTES:
            raise ValueError("CSV is empty or exceeds the configured size limit.")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must be UTF-8 encoded.") from exc
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise ValueError("CSV header does not match the Version 2.0.2 template.")
        rows = list(reader)
        if not rows or len(rows) > MAX_CSV_ROWS:
            raise ValueError("CSV row count is outside the allowed range.")
        run = JobImportRun(owner_user_id=self.owner_id, import_type="csv_validate" if validate_only else "csv", status="running", source_count=len(rows))
        self.db.add(run)
        self.db.flush()
        results: list[dict[str, object]] = []
        for number, row in enumerate(rows, start=2):
            try:
                values = self._csv_row(row)
                if validate_only:
                    # Validation must not insert Jobs or echo descriptions.
                    self.jobs._normalized(values)
                    outcome = {"row": number, "status": "valid"}
                else:
                    with self.db.begin_nested():
                        created = self.jobs.create(values, {
                            "source_type": "csv", "original_url": canonicalize_url(row.get("url")) if row.get("url") else None,
                            "canonical_url": values.get("canonical_url"), "source_metadata": {"row": number},
                        })
                    outcome = {"row": number, "status": created["result"], "job_id": created["job"]["id"]}
                    if created["result"] == "created" or created["result"] == "duplicate_candidate":
                        run.created_count += 1
                    else:
                        run.duplicate_count += 1
                results.append(outcome)
            except Exception as exc:
                run.failed_count += 1
                results.append({"row": number, "status": "error", "error": self._safe_row_error(exc)})
        run.status = "validated" if validate_only and not run.failed_count else "completed_with_errors" if run.failed_count else "completed"
        run.completed_at = utc_now()
        run.safe_error_summary = f"{run.failed_count} row(s) failed validation." if run.failed_count else None
        AuthRepository(self.db).audit(
            "job.csv.validated" if validate_only else "job.csv.imported",
            user_id=self.owner_id, resource_type="job_import_run", resource_id=str(run.id),
            safe_metadata={"source_count": len(rows), "created_count": run.created_count, "duplicate_count": run.duplicate_count, "failed_count": run.failed_count},
        )
        return {"run": serialize_model(run, exclude={"owner_user_id", "safe_error_summary"}), "validate_only": validate_only, "rows": results}

    @staticmethod
    def template() -> str:
        return ",".join(CSV_COLUMNS) + "\n"

    def _csv_row(self, row: dict[str, str]) -> dict[str, object]:
        for key, value in row.items():
            if value is None or len(value) > MAX_CSV_CELL:
                raise ValueError("A CSV cell exceeds the allowed length.")
            if value.lstrip().startswith(("=", "+", "-", "@")):
                raise ValueError("CSV formula-like cells are not accepted.")
        if not row["company"].strip() or not row["title"].strip() or not row["description"].strip():
            raise ValueError("Company, title, and description are required.")
        def integer(name: str) -> int | None:
            return int(row[name]) if row[name].strip() else None
        return {
            "company_name": row["company"], "title": row["title"], "location": row["location"],
            "description": row["description"], "canonical_url": canonicalize_url(row["url"]) if row["url"] else None,
            "employment_type": row["employment_type"] or None, "work_mode": row["work_mode"] or None,
            "salary_min": integer("salary_min"), "salary_max": integer("salary_max"),
            "salary_currency": row["salary_currency"] or None,
            "application_deadline": self._date(row["application_deadline"]), "source_type": "csv",
        }

    def _run(self, import_type: str, source_count: int, result: dict[str, object]) -> None:
        status = str(result["result"])
        run = JobImportRun(
            owner_user_id=self.owner_id, import_type=import_type, status="completed", source_count=source_count,
            created_count=1 if status in {"created", "duplicate_candidate"} else 0,
            duplicate_count=1 if status == "existing" else 0, failed_count=0,
            completed_at=utc_now(),
        )
        self.db.add(run)

    @staticmethod
    def _date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            return parsed
        except ValueError:
            return None

    @staticmethod
    def _safe_row_error(exc: Exception) -> str:
        if isinstance(exc, ValueError):
            message = str(exc)
            if len(message) <= 160 and not any(item in message.casefold() for item in ("description", "content", "url ")):
                return message
        return "Row validation failed."
