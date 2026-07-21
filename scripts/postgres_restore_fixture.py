#!/usr/bin/env python3
"""Preflight synthetic Restore fixtures without database or network access."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALIDATION_CODE = "SYNTHETIC_FIXTURE_VALIDATION_FAILED"
RUN_ID_PATTERN = re.compile(r"^[0-9]+-[0-9]+$")
APPROVED_SYNTHETIC_DOMAIN = "example.com"
BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass(frozen=True)
class FixtureValidationError(ValueError):
    field: str
    safe_message: str
    cause_type: str = "ValueError"

    def __str__(self) -> str:
        return self.safe_message


def _failure(error: FixtureValidationError) -> dict[str, Any]:
    return {
        "status": "failed",
        "stage": "synthetic_admin_fixture_preflight",
        "exception_type": "ValueError",
        "validation_code": VALIDATION_CODE,
        "safe_message": error.safe_message,
        "failure_field": error.field,
        "cause_type": error.cause_type,
        "backup_started": False,
        "restore_started": False,
        "secrets_included": False,
    }


def validate_fixture(
    *,
    email: str,
    password: str,
    display_name: str,
    run_id: str,
) -> tuple[str, dict[str, Any]]:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise FixtureValidationError("run_id", "Synthetic fixture run ID is invalid.")

    try:
        from app.core.security import normalize_email, validate_password
    except Exception as exc:
        raise FixtureValidationError(
            "python_modules",
            "Synthetic fixture validation modules are unavailable.",
            type(exc).__name__,
        ) from exc

    try:
        normalized_email = normalize_email(email)
    except ValueError as exc:
        cause = exc.__cause__
        raise FixtureValidationError(
            "email",
            "Synthetic fixture email was rejected by production validation.",
            type(cause).__name__ if cause is not None else type(exc).__name__,
        ) from exc
    domain = normalized_email.rsplit("@", 1)[-1]
    if domain != APPROVED_SYNTHETIC_DOMAIN:
        raise FixtureValidationError(
            "email",
            "Synthetic fixture email is not in the approved documentation domain.",
        )

    try:
        validate_password(password)
    except ValueError as exc:
        raise FixtureValidationError(
            "password",
            "Synthetic fixture password was rejected by production validation.",
            type(exc).__name__,
        ) from exc

    normalized_display_name = display_name.strip()[:120] or "User"
    if normalized_display_name != display_name or len(display_name) > 120:
        raise FixtureValidationError(
            "display_name",
            "Synthetic fixture display name is invalid.",
        )

    safe_payload = {
        "status": "passed",
        "stage": "synthetic_admin_fixture_preflight",
        "synthetic_fixture_preflight": "passed",
        "fixture_email_domain_category": "reserved_documentation_example_com",
        "email_normalization": "passed",
        "password_policy": "passed",
        "display_name_validation": "passed",
        "fixture_serialization": "passed",
        "python_modules": "passed",
        "run_id_validation": "passed",
        "backup_started": False,
        "restore_started": False,
        "secrets_included": False,
    }
    json.dumps(safe_payload, sort_keys=True)
    return normalized_email, safe_payload


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--email", required=True)
    root.add_argument("--password-env", default="PJA_TEST_ADMIN_PASSWORD")
    root.add_argument("--display-name", required=True)
    root.add_argument("--run-id", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        import os

        password = os.getenv(args.password_env, "")
        _normalized_email, report = validate_fixture(
            email=args.email,
            password=password,
            display_name=args.display_name,
            run_id=args.run_id,
        )
    except FixtureValidationError as exc:
        print(json.dumps(_failure(exc), sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
