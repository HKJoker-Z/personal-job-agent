"""Security-sensitive administrative CLI. Passwords are never command arguments."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.core.security import hash_password, normalize_email
from app.db.models import utc_now
from app.db.repositories.auth import AuthRepository
from app.db.session import session_factory
from app.migration.postgres_writer import PostgreSQLV1Writer
from app.migration.sqlite_reader import SQLiteV1Reader


def _password(prompt: str) -> str:
    settings = load_v2_settings()
    test_value = os.getenv("PJA_TEST_ADMIN_PASSWORD") if settings.app_env == "test" else None
    if test_value:
        return test_value
    first = getpass.getpass(prompt)
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("Passwords did not match.")
    return first


def create_admin(args: argparse.Namespace) -> None:
    db = session_factory()()
    try:
        user = AuthService(db, load_v2_settings()).create_user(
            args.email,
            _password("New admin password: "),
            args.display_name,
            "admin",
        )
        db.commit()
        print(f"Administrator created: {user.id}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def change_password(args: argparse.Namespace) -> None:
    db = session_factory()()
    try:
        repository = AuthRepository(db)
        user = repository.user_by_email(normalize_email(args.email))
        if user is None:
            raise ValueError("User not found.")
        user.password_hash = hash_password(_password("New password: "))
        user.password_changed_at = utc_now()
        user.version += 1
        repository.revoke_user_sessions(user.id, utc_now(), "admin_password_change")
        repository.audit("auth.password_changed_by_cli", user_id=user.id)
        db.commit()
        print("Password changed and Sessions revoked.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def deactivate(args: argparse.Namespace) -> None:
    db = session_factory()()
    try:
        repository = AuthRepository(db)
        user = repository.user_by_email(normalize_email(args.email))
        if user is None:
            raise ValueError("User not found.")
        user.is_active = False
        repository.revoke_user_sessions(user.id, utc_now(), "user_deactivated")
        repository.audit("auth.user_deactivated", user_id=user.id)
        db.commit()
        print("User deactivated and Sessions revoked.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def revoke_all(args: argparse.Namespace) -> None:
    db = session_factory()()
    try:
        repository = AuthRepository(db)
        user = repository.user_by_email(normalize_email(args.email))
        if user is None:
            raise ValueError("User not found.")
        count = repository.revoke_user_sessions(user.id, utc_now(), "cli_revoke_all")
        repository.audit("auth.sessions_revoked_by_cli", user_id=user.id, safe_metadata={"count": count})
        db.commit()
        print(f"Sessions revoked: {count}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _write_report(path: Path, report: dict[str, object]) -> None:
    destination = path.expanduser().resolve(strict=False)
    if destination.exists() and destination.is_symlink():
        raise ValueError("Migration report path cannot be a symlink.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def migrate_v1(args: argparse.Namespace) -> None:
    reader = SQLiteV1Reader(args.source_sqlite)
    metadata = reader.inspect()
    report: dict[str, object]
    if args.dry_run:
        report = {
            "status": "dry_run",
            "source_fingerprint": metadata.fingerprint,
            "schema_version": "v1.9",
            "tables": {
                table: {"source_row_count": count}
                for table, count in metadata.row_counts.items()
            },
        }
        reader.assert_unchanged()
    else:
        database_url = os.getenv(args.target_database_url_env, "").strip()
        if not database_url:
            raise ValueError("Target database URL environment variable is not configured.")
        parsed = make_url(database_url)
        database_name = (parsed.database or "").lower()
        if not args.allow_production_target and "test" not in database_name:
            raise ValueError("Migration execution is limited to an explicitly named test database.")
        writer = PostgreSQLV1Writer(database_url)
        if args.verify_only:
            report = writer.verify(metadata)
        else:
            report = writer.migrate(reader, metadata, args.owner_email)
        reader.assert_unchanged()
    if args.report:
        _write_report(args.report, report)
    print(json.dumps(report, sort_keys=True, default=str))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m app.cli")
    domains = root.add_subparsers(dest="domain", required=True)
    users = domains.add_parser("users")
    user_actions = users.add_subparsers(dest="action", required=True)
    create = user_actions.add_parser("create-admin")
    create.add_argument("--email", required=True)
    create.add_argument("--display-name", required=True)
    create.set_defaults(handler=create_admin)
    change = user_actions.add_parser("change-password")
    change.add_argument("--email", required=True)
    change.set_defaults(handler=change_password)
    disable = user_actions.add_parser("deactivate")
    disable.add_argument("--email", required=True)
    disable.set_defaults(handler=deactivate)
    sessions = domains.add_parser("sessions")
    session_actions = sessions.add_subparsers(dest="action", required=True)
    revoke = session_actions.add_parser("revoke-all")
    revoke.add_argument("--email", required=True)
    revoke.set_defaults(handler=revoke_all)
    migrate = domains.add_parser("migrate-v1")
    migrate.add_argument("--source-sqlite", type=Path, required=True)
    migrate.add_argument("--target-database-url-env", default="DATABASE_URL")
    migrate.add_argument("--owner-email", required=True)
    mode = migrate.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--verify-only", action="store_true")
    migrate.add_argument("--report", type=Path)
    migrate.add_argument("--allow-production-target", action="store_true", help=argparse.SUPPRESS)
    migrate.set_defaults(handler=migrate_v1)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
    except Exception as exc:
        print(f"Command failed safely: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
