#!/usr/bin/env python3
"""Create consistent SQLite and Project Knowledge backups with checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


APPLICATION_VERSION = "1.9"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sqlite_backup(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        integrity = destination_connection.execute("PRAGMA quick_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise sqlite3.DatabaseError("Backup database integrity check failed.")
    finally:
        destination_connection.close()
        source_connection.close()


def create_backup(database_path: Path, project_knowledge_path: Path, backup_dir: Path) -> Path:
    database_path = database_path.expanduser().resolve(strict=True)
    project_knowledge_path = project_knowledge_path.expanduser().resolve(strict=True)
    backup_dir = backup_dir.expanduser().resolve(strict=False)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    final_dir = backup_dir / timestamp
    if final_dir.exists():
        final_dir = backup_dir / f"{timestamp}-{uuid4().hex[:8]}"
    temporary_dir = backup_dir / f".{final_dir.name}.incomplete-{uuid4().hex}"
    temporary_dir.mkdir(mode=0o700)
    try:
        database_backup = temporary_dir / "app.db"
        knowledge_backup = temporary_dir / "PROJECT_KNOWLEDGE.md"
        sqlite_backup(database_path, database_backup)
        shutil.copyfile(project_knowledge_path, knowledge_backup)
        os.chmod(database_backup, 0o600)
        os.chmod(knowledge_backup, 0o600)
        manifest = {
            "application_version": APPLICATION_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "included_files": [
                {"name": "app.db", "sha256": sha256_file(database_backup)},
                {"name": "PROJECT_KNOWLEDGE.md", "sha256": sha256_file(knowledge_backup)},
            ],
        }
        manifest_tmp = temporary_dir / ".manifest.json.tmp"
        manifest_tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(manifest_tmp, 0o600)
        os.replace(manifest_tmp, temporary_dir / "manifest.json")
        os.replace(temporary_dir, final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up runtime SQLite and Project Knowledge data.")
    parser.add_argument("--database-path", type=Path, default=PROJECT_ROOT / "runtime/data/app.db")
    parser.add_argument(
        "--project-knowledge-path",
        type=Path,
        default=PROJECT_ROOT / "runtime/project-knowledge/PROJECT_KNOWLEDGE.md",
    )
    parser.add_argument("--backup-dir", type=Path, default=PROJECT_ROOT / "runtime/backups")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = create_backup(args.database_path, args.project_knowledge_path, args.backup_dir)
    except (OSError, sqlite3.Error) as exc:
        print(f"Backup failed safely: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"Backup created: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
