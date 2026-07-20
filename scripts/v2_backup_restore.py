#!/usr/bin/env python3
"""Version 2 PostgreSQL/private-file backup, verification, and guarded restore."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import psycopg


APPLICATION_VERSION = "2.0.1"
REQUIRED_TABLES = (
    "users", "application_records", "analysis_metrics", "evaluation_runs",
    "knowledge_documents", "resumes", "resume_versions", "file_assets",
    "agent_runs", "agent_steps", "agent_run_events", "approval_requests",
    "approval_decisions", "agent_outbox_events", "user_ai_budgets",
    "ai_usage_ledger", "worker_heartbeats", "dead_letter_records",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def database_parts(environment_name: str) -> tuple[str, dict[str, str], list[str]]:
    value = os.getenv(environment_name, "").strip()
    parsed = urlsplit(value.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("Configured database URL must be PostgreSQL.")
    database = parsed.path.lstrip("/")
    env = os.environ.copy()
    env["PGPASSWORD"] = unquote(parsed.password or "")
    args = [
        "--host", parsed.hostname,
        "--port", str(parsed.port or 5432),
        "--username", unquote(parsed.username or ""),
        "--dbname", database,
    ]
    return value.replace("postgresql+psycopg://", "postgresql://", 1), env, args


def safe_files(root: Path) -> list[Path]:
    if root.is_symlink():
        raise ValueError("File storage root cannot be a symlink.")
    root = root.resolve(strict=True)
    values: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("File storage contains a symlink.")
        if path.is_file():
            values.append(path)
    return values


def table_counts(database_url: str) -> tuple[str, dict[str, int]]:
    with psycopg.connect(database_url) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            ).fetchall()
        }
        revision = (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            if "alembic_version" in existing
            else ""
        )
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in REQUIRED_TABLES
            if table in existing
        }
    return str(revision), counts


def database_is_empty(database_url: str) -> bool:
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public')"
        ).fetchone()[0]


def create_backup(database_url_env: str, files_root: Path, knowledge: Path, destination: Path) -> Path:
    database_url, pg_env, pg_args = database_parts(database_url_env)
    if files_root.is_symlink() or knowledge.is_symlink() or destination.is_symlink():
        raise ValueError("Backup source and destination paths cannot be symlinks.")
    files_root = files_root.resolve(strict=True)
    knowledge = knowledge.resolve(strict=True)
    destination = destination.resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    minimum_free_mb = int(os.getenv("BACKUP_MINIMUM_FREE_DISK_MB", "256"))
    if minimum_free_mb < 16:
        raise ValueError("Backup minimum free disk threshold is invalid.")
    if shutil.disk_usage(destination).free < minimum_free_mb * 1024 * 1024:
        raise OSError("Backup destination does not have enough free disk space.")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    final = destination / f"v2-{timestamp}-{uuid4().hex[:8]}"
    temporary = destination / f".{final.name}.incomplete"
    temporary.mkdir(mode=0o700)
    try:
        dump = temporary / "postgres.dump"
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(dump), *pg_args],
            env=pg_env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        os.chmod(dump, 0o600)
        archive = temporary / "files.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            for path in safe_files(files_root):
                output.add(path, arcname=path.relative_to(files_root), recursive=False)
        os.chmod(archive, 0o600)
        knowledge_copy = temporary / "PROJECT_KNOWLEDGE.md"
        shutil.copyfile(knowledge, knowledge_copy)
        os.chmod(knowledge_copy, 0o600)
        revision, counts = table_counts(database_url)
        manifest = {
            "application_version": APPLICATION_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "alembic_revision": revision,
            "table_row_counts": counts,
            "files": {
                name: sha256_file(temporary / name)
                for name in ("postgres.dump", "files.tar.gz", "PROJECT_KNOWLEDGE.md")
            },
        }
        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(manifest_path, 0o600)
        os.replace(temporary, final)
        return final
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_backup(backup: Path) -> dict[str, object]:
    if backup.is_symlink():
        raise ValueError("Backup directory cannot be a symlink.")
    backup = backup.resolve(strict=True)
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    expected = {"postgres.dump", "files.tar.gz", "PROJECT_KNOWLEDGE.md"}
    if set(manifest.get("files", {})) != expected:
        raise ValueError("Backup manifest file set is invalid.")
    for name, digest in manifest["files"].items():
        if Path(name).name != name or sha256_file(backup / name) != digest:
            raise ValueError("Backup checksum verification failed.")
    with tarfile.open(backup / "files.tar.gz", "r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise ValueError("File archive contains an unsafe member.")
    return manifest


def restore_backup(database_url_env: str, backup: Path, files_root: Path, knowledge: Path, confirmation: str) -> None:
    if confirmation != "RESTORE V2 BACKUP":
        raise ValueError("Restore confirmation did not match.")
    manifest = verify_backup(backup)
    database_url, pg_env, pg_args = database_parts(database_url_env)
    if not database_is_empty(database_url):
        raise ValueError("Restore target database is not empty.")
    if files_root.is_symlink() or knowledge.is_symlink():
        raise ValueError("Restore targets cannot be symlinks.")
    files_root = files_root.resolve(strict=False)
    if files_root.exists() and any(files_root.iterdir()):
        raise ValueError("Restore file target is not empty.")
    if knowledge.exists():
        raise ValueError("Restore Project Knowledge target already exists.")
    if knowledge.parent.exists() and knowledge.parent.is_symlink():
        raise ValueError("Restore Project Knowledge parent cannot be a symlink.")
    files_root.mkdir(parents=True, exist_ok=True, mode=0o750)
    subprocess.run(
        ["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", *pg_args, str(backup / "postgres.dump")],
        env=pg_env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    with tarfile.open(backup / "files.tar.gz", "r:gz") as archive:
        archive.extractall(files_root, filter="data")
    knowledge.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    shutil.copyfile(backup / "PROJECT_KNOWLEDGE.md", knowledge)
    revision, restored_counts = table_counts(database_url)
    if revision != manifest["alembic_revision"] or restored_counts != manifest["table_row_counts"]:
        raise RuntimeError("Restored database verification failed.")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--database-url-env", default="DATABASE_URL")
    backup.add_argument("--backup-dir", type=Path, default=Path("runtime/backups"))
    backup.add_argument("--files-root", type=Path, default=Path("runtime/files"))
    backup.add_argument("--project-knowledge", type=Path, default=Path("runtime/project-knowledge/PROJECT_KNOWLEDGE.md"))
    verify = commands.add_parser("verify")
    verify.add_argument("--backup", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--database-url-env", default="DATABASE_URL")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--files-root", type=Path, default=Path("runtime/files"))
    restore.add_argument("--project-knowledge", type=Path, default=Path("runtime/project-knowledge/PROJECT_KNOWLEDGE.md"))
    restore.add_argument("--confirmation", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "backup":
            result = create_backup(args.database_url_env, args.files_root, args.project_knowledge, args.backup_dir)
            print(f"Backup created: {result}")
        elif args.command == "verify":
            verify_backup(args.backup)
            print("Backup verification passed.")
        else:
            restore_backup(args.database_url_env, args.backup, args.files_root, args.project_knowledge, args.confirmation or "")
            print("Restore completed and verified.")
    except Exception as exc:
        print(f"Operation refused safely: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
