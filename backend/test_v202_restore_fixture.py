import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT / "backend", ROOT / "scripts"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from app.core.security import hash_password, normalize_email, verify_password
from postgres_restore_fixture import (
    FixtureValidationError,
    VALIDATION_CODE,
    _failure,
    validate_fixture,
)


class SyntheticRestoreFixtureTest(unittest.TestCase):
    password = "synthetic fixture password 2026"

    def test_restore_fixture_email_passes_production_validator(self):
        email = "restore-regression+1784543184-959701@example.com"
        normalized, report = validate_fixture(
            email=email,
            password=self.password,
            display_name="Restore Regression",
            run_id="1784543184-959701",
        )
        self.assertEqual(normalized, normalize_email(email))
        self.assertEqual(report["synthetic_fixture_preflight"], "passed")
        self.assertNotIn(email, json.dumps(report))

    def test_special_use_email_fails_preflight_safely(self):
        with self.assertRaises(FixtureValidationError) as raised:
            validate_fixture(
                email="restore-regression@example.test",
                password=self.password,
                display_name="Restore Regression",
                run_id="1784543184-959701",
            )
        report = _failure(raised.exception)
        self.assertEqual(report["validation_code"], VALIDATION_CODE)
        self.assertEqual(report["failure_field"], "email")
        self.assertEqual(report["cause_type"], "EmailSyntaxError")
        self.assertFalse(report["backup_started"])
        self.assertFalse(report["restore_started"])

    def test_fixture_failure_report_has_no_password_or_secret(self):
        error = FixtureValidationError("password", "Synthetic password is invalid.")
        rendered = json.dumps(_failure(error), sort_keys=True)
        self.assertNotIn(self.password, rendered)
        self.assertNotIn("DATABASE_URL", rendered)
        self.assertNotIn("password_hash", rendered)
        self.assertNotIn("Session", rendered)
        self.assertNotIn("CSRF", rendered)

    def test_fixture_password_uses_formal_hash_primitives(self):
        encoded = hash_password(self.password)
        self.assertNotEqual(encoded, self.password)
        self.assertTrue(verify_password(self.password, encoded))

    def test_cli_failure_emits_only_safe_json(self):
        from unittest import mock

        from postgres_restore_fixture import main

        output = io.StringIO()
        with mock.patch.dict("os.environ", {"PJA_TEST_ADMIN_PASSWORD": self.password}):
            with mock.patch(
                "sys.argv",
                [
                    "postgres_restore_fixture.py",
                    "--email",
                    "restore-regression@example.test",
                    "--display-name",
                    "Restore Regression",
                    "--run-id",
                    "1784543184-959701",
                ],
            ):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["validation_code"], VALIDATION_CODE)
        self.assertNotIn(self.password, output.getvalue())

    def test_standalone_preflight_resolves_production_modules(self):
        environment = os.environ.copy()
        environment["PJA_TEST_ADMIN_PASSWORD"] = self.password
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "postgres_restore_fixture.py"),
                    "--email",
                    "restore-regression+1784543184-959701@example.com",
                    "--display-name",
                    "Restore Regression",
                    "--run-id",
                    "1784543184-959701",
                ],
                cwd=directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
        report = json.loads(completed.stdout)
        self.assertEqual(report["python_modules"], "passed")
        self.assertNotIn(self.password, completed.stdout)

    def test_regression_preflight_precedes_compose_and_postgres_tools(self):
        content = (ROOT / "scripts" / "postgres16-restore-regression.sh").read_text(
            encoding="utf-8"
        )
        preflight = content.index("postgres_restore_fixture.py")
        compose_up = content.index('up --detach --wait source-db target-db')
        backup = content.index('v2_backup_restore.py backup')
        restore = content.index('v2_backup_restore.py restore')
        self.assertLess(preflight, compose_up)
        self.assertLess(preflight, backup)
        self.assertLess(preflight, restore)


if __name__ == "__main__":
    unittest.main()
