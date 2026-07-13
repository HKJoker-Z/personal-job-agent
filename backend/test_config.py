import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import (
    DEFAULT_DEVELOPMENT_DATABASE_PATH,
    DEFAULT_DEVELOPMENT_KNOWLEDGE_PATH,
    ConfigError,
    load_config,
    parse_bool,
)
from database import assert_safe_test_database


class ConfigTest(unittest.TestCase):
    def load(self, values=None, *, validate=True):
        environment = {"APP_ENV": "development", **(values or {})}
        with patch.dict(os.environ, environment, clear=True):
            return load_config(validate_production=validate)

    def test_development_defaults(self):
        config = self.load()
        self.assertEqual(config.app_env, "development")
        self.assertEqual(config.database_path, DEFAULT_DEVELOPMENT_DATABASE_PATH)
        self.assertTrue(config.enable_api_docs)

    def test_production_requires_deepseek_configuration(self):
        with self.assertRaisesRegex(ConfigError, "DEEPSEEK_API_KEY"):
            self.load({"APP_ENV": "production", "TRUSTED_HOSTS": "example.com"})

    def test_production_rejects_wildcard_origin(self):
        with self.assertRaisesRegex(ConfigError, "ALLOWED_ORIGINS"):
            self.load({
                "APP_ENV": "production",
                "DEEPSEEK_API_KEY": "TEST_ONLY_CONFIGURED",
                "TRUSTED_HOSTS": "example.com",
                "ALLOWED_ORIGINS": "*",
            })

    def test_production_rejects_wildcard_trusted_host(self):
        with self.assertRaisesRegex(ConfigError, "TRUSTED_HOSTS"):
            self.load({
                "APP_ENV": "production",
                "DEEPSEEK_API_KEY": "TEST_ONLY_CONFIGURED",
                "TRUSTED_HOSTS": "*",
            })

    def test_boolean_parser(self):
        self.assertTrue(parse_bool("FLAG", "yes", False))
        self.assertFalse(parse_bool("FLAG", "off", True))
        with self.assertRaises(ConfigError):
            parse_bool("FLAG", "maybe", False)

    def test_integer_range_validation(self):
        with self.assertRaisesRegex(ConfigError, "MAX_UPLOAD_SIZE_MB"):
            self.load({"MAX_UPLOAD_SIZE_MB": "1000"})

    def test_csv_origin_parser(self):
        config = self.load({"ALLOWED_ORIGINS": "https://a.example, https://b.example"})
        self.assertEqual(config.allowed_origins, ("https://a.example", "https://b.example"))

    def test_csv_trusted_host_parser(self):
        config = self.load({"TRUSTED_HOSTS": "a.example,b.example,a.example"})
        self.assertEqual(config.trusted_hosts, ("a.example", "b.example"))

    def test_database_path_compatibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "configured.db"
            config = self.load({"APP_DATABASE_PATH": str(path)})
            self.assertEqual(config.database_path, path.resolve())

    def test_test_environment_default_database_guard_remains_active(self):
        with self.assertRaises(RuntimeError):
            assert_safe_test_database(DEFAULT_DEVELOPMENT_DATABASE_PATH, "test")

    def test_project_knowledge_path_configuration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "PROJECT_KNOWLEDGE.md"
            config = self.load({"PROJECT_KNOWLEDGE_PATH": str(path)})
            self.assertEqual(config.project_knowledge_path, path.resolve())

    def test_configuration_error_does_not_contain_secret_value(self):
        secret = "TEST_ONLY_SENSITIVE_CONFIG_VALUE"
        try:
            self.load({
                "APP_ENV": "production",
                "DEEPSEEK_API_KEY": secret,
                "TRUSTED_HOSTS": "*",
            })
        except ConfigError as exc:
            self.assertNotIn(secret, str(exc))

    def test_production_api_docs_default_disabled(self):
        config = self.load({
            "APP_ENV": "production",
            "DEEPSEEK_API_KEY": "TEST_ONLY_CONFIGURED",
            "TRUSTED_HOSTS": "example.com",
        })
        self.assertFalse(config.enable_api_docs)

    def test_remote_monitoring_admin_default_disabled(self):
        self.assertFalse(self.load().monitoring_allow_remote_admin)

    def test_development_project_knowledge_default(self):
        self.assertEqual(self.load().project_knowledge_path, DEFAULT_DEVELOPMENT_KNOWLEDGE_PATH)

    def production_app_probe(self, expression):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed.md"
            seed.write_text("test seed", encoding="utf-8")
            environment = os.environ.copy()
            environment.update({
                "APP_ENV": "production",
                "APP_DATABASE_PATH": str(root / "app.db"),
                "PROJECT_KNOWLEDGE_PATH": str(root / "PROJECT_KNOWLEDGE.md"),
                "PROJECT_KNOWLEDGE_SEED_PATH": str(seed),
                "DEEPSEEK_API_KEY": "TEST_ONLY_CONFIGURED",
                "TRUSTED_HOSTS": "example.com",
                "ALLOWED_ORIGINS": "https://example.com",
                "ENABLE_API_DOCS": "false",
                "DATABASE_URL": "postgresql+psycopg://" + "pja_app:" + "TEST_ONLY_PASSWORD" + "@database/personal_job_agent_test",
                "SESSION_COOKIE_SECURE": "true",
                "AUTH_TRUSTED_ORIGINS": "https://example.com",
                "AUTH_FINGERPRINT_KEY": "TEST_ONLY_FINGERPRINT_KEY_32_BYTES_LONG",
                "FILE_STORAGE_ROOT": str(root / "files"),
            })
            command = (
                "from fastapi.testclient import TestClient; import json; from main import app; "
                f"print(json.dumps({expression}))"
            )
            result = subprocess.run(
                [sys.executable, "-c", command],
                cwd=Path(__file__).resolve().parent,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(result.stdout.strip().splitlines()[-1])

    def test_phase1_production_api_docs_routes_are_disabled(self):
        result = self.production_app_probe(
            "{'status': TestClient(app).get('/docs', headers={'Host':'example.com'}).status_code}"
        )
        self.assertEqual(result["status"], 404)

    def test_production_trusted_hosts_reject_unknown_host(self):
        result = self.production_app_probe(
            "{'status': TestClient(app).get('/api/health', headers={'Host':'evil.example'}).status_code}"
        )
        self.assertEqual(result["status"], 400)

    def test_production_cors_allows_only_configured_origin(self):
        expression = (
            "{'allowed': TestClient(app).options('/api/health', headers={'Host':'example.com',"
            "'Origin':'https://example.com','Access-Control-Request-Method':'GET'}).headers.get('access-control-allow-origin'),"
            "'blocked': TestClient(app).options('/api/health', headers={'Host':'example.com',"
            "'Origin':'https://evil.example','Access-Control-Request-Method':'GET'}).headers.get('access-control-allow-origin')}"
        )
        result = self.production_app_probe(expression)
        self.assertEqual(result["allowed"], "https://example.com")
        self.assertIsNone(result["blocked"])


if __name__ == "__main__":
    unittest.main()
