#!/usr/bin/env python3
"""Verify and atomically restore one explicitly selected runtime backup."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from backup_runtime import create_backup, sha256_file


REQUIRED_TABLES = {
    "application_records",
    "knowledge_documents",
    "knowledge_chunks",
    "analysis_metrics",
    "evaluation_runs",
}
EXPECTED_FILES = {"app.db", "PROJECT_KNOWLEDGE.md"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _safe_backup_file(backup_dir: Path, name: str) -> Path:
    if name not in EXPECTED_FILES or Path(name).is_absolute() or Path(name).name != name:
        raise ValueError("Backup manifest contains an unsafe file name.")
    path = (backup_dir / name).resolve(strict=True)
    if path.parent != backup_dir.resolve(strict=True):
        raise ValueError("Backup manifest path escapes the selected backup directory.")
    return path


def verify_backup(backup_dir: Path) -> dict[str, Path]:
    backup_dir = backup_dir.expanduser().resolve(strict=True)
    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("included_files")
    if not isinstance(entries, list):
        raise ValueError("Backup manifest is invalid.")
    verified: dict[str, Path] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Backup manifest is invalid.")
        name = entry.get("name")
        expected_checksum = entry.get("sha256")
        path = _safe_backup_file(backup_dir, str(name or ""))
        if not isinstance(expected_checksum, str) or sha256_file(path) != expected_checksum:
            raise ValueError("Backup checksum verification failed.")
        verified[str(name)] = path
    if set(verified) != EXPECTED_FILES:
        raise ValueError("Backup does not contain the required files.")
    connection = sqlite3.connect(f"file:{verified['app.db']}?mode=ro", uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if not REQUIRED_TABLES.issubset(tables):
            raise ValueError("Backup database schema is incomplete.")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Backup database integrity check failed.")
    finally:
        connection.close()
    return verified


def restore_backup(
    backup_dir: Path,
    database_path: Path,
    project_knowledge_path: Path,
    pre_restore_backup_dir: Path,
) -> Path | None:
    verified = verify_backup(backup_dir)
    database_path = database_path.expanduser().resolve(strict=False)
    project_knowledge_path = project_knowledge_path.expanduser().resolve(strict=False)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    project_knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    pre_restore = None
    if database_path.is_file() and project_knowledge_path.is_file():
        pre_restore = create_backup(database_path, project_knowledge_path, pre_restore_backup_dir)
    suffix = uuid4().hex
    db_tmp = database_path.with_name(f".{database_path.name}.restore-{suffix}.tmp")
    knowledge_tmp = project_knowledge_path.with_name(
        f".{project_knowledge_path.name}.restore-{suffix}.tmp"
    )
    db_rollback = database_path.with_name(f".{database_path.name}.rollback-{suffix}.tmp")
    knowledge_rollback = project_knowledge_path.with_name(
        f".{project_knowledge_path.name}.rollback-{suffix}.tmp"
    )
    database_existed = database_path.is_file()
    knowledge_existed = project_knowledge_path.is_file()
    try:
        shutil.copyfile(verified["app.db"], db_tmp)
        shutil.copyfile(verified["PROJECT_KNOWLEDGE.md"], knowledge_tmp)
        if database_existed:
            shutil.copyfile(database_path, db_rollback)
        if knowledge_existed:
            shutil.copyfile(project_knowledge_path, knowledge_rollback)
        os.chmod(db_tmp, 0o600)
        os.chmod(knowledge_tmp, 0o600)
        os.replace(db_tmp, database_path)
        os.replace(knowledge_tmp, project_knowledge_path)
    except Exception:
        if db_rollback.exists():
            os.replace(db_rollback, database_path)
        elif not database_existed and database_path.exists():
            database_path.unlink()
        if knowledge_rollback.exists():
            os.replace(knowledge_rollback, project_knowledge_path)
        elif not knowledge_existed and project_knowledge_path.exists():
            project_knowledge_path.unlink()
        raise
    finally:
        for path in (db_tmp, knowledge_tmp, db_rollback, knowledge_rollback):
            if path.exists():
                path.unlink()
    return pre_restore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore one verified runtime backup.")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--database-path", type=Path, default=PROJECT_ROOT / "runtime/data/app.db")
    parser.add_argument(
        "--project-knowledge-path",
        type=Path,
        default=PROJECT_ROOT / "runtime/project-knowledge/PROJECT_KNOWLEDGE.md",
    )
    parser.add_argument("--backup-dir", type=Path, default=PROJECT_ROOT / "runtime/backups")
    parser.add_argument("--confirmation", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.confirmation != "RESTORE BACKUP":
        print("Restore confirmation did not match.", file=sys.stderr)
        return 2
    try:
        pre_restore = restore_backup(
            args.backup,
            args.database_path,
            args.project_knowledge_path,
            args.backup_dir,
        )
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as exc:
        print(f"Restore refused safely: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("Restore completed. Restart the backend and verify /api/ready.")
    if pre_restore:
        print(f"Pre-restore backup: {pre_restore}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
