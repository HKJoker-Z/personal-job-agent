#!/usr/bin/env python3
"""Preview or safely migrate legacy local data into runtime directories."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from backup_runtime import create_backup, sqlite_backup


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def migrate(confirm: bool) -> int:
    source_db = PROJECT_ROOT / "backend/data/app.db"
    source_knowledge = PROJECT_ROOT / "docs/PROJECT_KNOWLEDGE.md"
    target_db = PROJECT_ROOT / "runtime/data/app.db"
    target_knowledge = PROJECT_ROOT / "runtime/project-knowledge/PROJECT_KNOWLEDGE.md"
    backup_root = PROJECT_ROOT / "runtime/backups"
    print("Migration preview:")
    print(f"  database: {'available' if source_db.is_file() else 'missing'} -> runtime/data/app.db")
    print(
        f"  project knowledge: {'available' if source_knowledge.is_file() else 'missing'} "
        "-> runtime/project-knowledge/PROJECT_KNOWLEDGE.md"
    )
    if not confirm:
        print('No files changed. Re-run with --confirmation "MIGRATE EXISTING DATA".')
        return 0
    if not source_db.is_file() or not source_knowledge.is_file():
        print("Migration source data is incomplete.", file=sys.stderr)
        return 1
    if target_db.exists() or target_knowledge.exists():
        print("Migration target already exists; refusing to overwrite it.", file=sys.stderr)
        return 1
    target_db.parent.mkdir(parents=True, exist_ok=True)
    target_knowledge.parent.mkdir(parents=True, exist_ok=True)
    create_backup(source_db, source_knowledge, backup_root)
    db_tmp = target_db.with_name(f".{target_db.name}.{uuid4().hex}.tmp")
    knowledge_tmp = target_knowledge.with_name(f".{target_knowledge.name}.{uuid4().hex}.tmp")
    try:
        sqlite_backup(source_db, db_tmp)
        shutil.copyfile(source_knowledge, knowledge_tmp)
        os.replace(db_tmp, target_db)
        os.replace(knowledge_tmp, target_knowledge)
    finally:
        for path in (db_tmp, knowledge_tmp):
            if path.exists():
                path.unlink()
    print("Migration completed; source files were preserved.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()
    return migrate(args.confirmation == "MIGRATE EXISTING DATA")


if __name__ == "__main__":
    raise SystemExit(main())
