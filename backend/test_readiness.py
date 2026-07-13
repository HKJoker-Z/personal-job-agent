import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from config import load_config
from database import get_connection
from project_knowledge_runtime import PROJECT_KNOWLEDGE_LOGICAL_NAME
from readiness import readiness_status
from test_support import temporary_test_database


class ReadinessTest(unittest.TestCase):
    def configured_runtime(self, temporary_directory, *, create_target=True):
        root = Path(temporary_directory)
        knowledge = root / "runtime" / "PROJECT_KNOWLEDGE.md"
        seed = root / "seed" / "PROJECT_KNOWLEDGE.md"
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_text("# Test-only Project Knowledge\n", encoding="utf-8")
        if create_target:
            knowledge.parent.mkdir(parents=True, exist_ok=True)
            knowledge.write_text("# Existing test knowledge\n", encoding="utf-8")
        os.environ["PROJECT_KNOWLEDGE_PATH"] = str(knowledge)
        os.environ["PROJECT_KNOWLEDGE_SEED_PATH"] = str(seed)
        return load_config(validate_production=False), knowledge

    def test_database_available_is_ready_with_possible_warning(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            payload, status = readiness_status(config)
            self.assertEqual(status, 200)
            self.assertTrue(payload["ready"])

    def test_database_unavailable_returns_503(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            invalid = Path(directory) / "database-as-directory"
            invalid.mkdir()
            payload, status = readiness_status(replace(config, database_path=invalid))
            self.assertEqual(status, 503)
            self.assertFalse(payload["ready"])

    def test_missing_required_tables_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            root = Path(directory)
            database_path = root / "empty.db"
            sqlite3.connect(database_path).close()
            os.environ["APP_ENV"] = "test"
            os.environ["APP_DATABASE_PATH"] = str(database_path)
            config, _ = self.configured_runtime(directory)
            payload, status = readiness_status(config)
            self.assertEqual(status, 503)
            self.assertEqual(payload["database_schema"], "not_ready")

    def test_missing_project_knowledge_is_initialized_from_seed(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, knowledge = self.configured_runtime(directory, create_target=False)
            payload, status = readiness_status(config)
            self.assertEqual(status, 200)
            self.assertTrue(knowledge.is_file())
            self.assertEqual(payload["project_knowledge_file"], "ready")

    def test_unindexed_project_knowledge_is_warning(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            payload, status = readiness_status(config)
            self.assertEqual(status, 200)
            self.assertEqual(payload["project_knowledge_index"], "degraded")
            self.assertEqual(payload["status"], "ready_with_warnings")

    def test_indexed_project_knowledge_is_ready(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO knowledge_documents (
                        created_at, updated_at, title, category, source_filename, chunk_count
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", "PK", "Other", PROJECT_KNOWLEDGE_LOGICAL_NAME, 1),
                )
            payload, status = readiness_status(config)
            self.assertEqual(status, 200)
            self.assertEqual(payload["project_knowledge_index"], "ready")

    def test_production_without_llm_configuration_is_not_ready(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            payload, status = readiness_status(replace(config, app_env="production", deepseek_api_key=""))
            self.assertEqual(status, 503)
            self.assertEqual(payload["llm_configuration"], "not_configured")

    def test_readiness_does_not_call_external_llm(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            with patch("socket.create_connection", side_effect=AssertionError("network call attempted")):
                _payload, status = readiness_status(config)
            self.assertEqual(status, 200)

    def test_readiness_response_excludes_paths_and_secrets(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            secret = "TEST_ONLY_READINESS_SECRET"
            payload, _status = readiness_status(replace(config, deepseek_api_key=secret))
            serialized = json.dumps(payload)
            self.assertNotIn(str(config.database_path), serialized)
            self.assertNotIn(str(config.project_knowledge_path), serialized)
            self.assertNotIn(secret, serialized)

    def test_health_is_lightweight_and_v202_alpha_version(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            self.configured_runtime(directory)
            from main import health_check

            self.assertEqual(health_check(), {"status": "ok", "service": "personal-job-agent", "version": "2.0.0-alpha.2"})

    def test_readiness_version_is_v202_alpha(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            config, _ = self.configured_runtime(directory)
            payload, _status = readiness_status(config)
            self.assertEqual(payload["version"], "2.0.0-alpha.2")

    def test_ready_endpoint_returns_safe_status(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            self.configured_runtime(directory)
            from fastapi.testclient import TestClient
            from main import app

            response = TestClient(app).get("/api/ready")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["ready"])


if __name__ == "__main__":
    unittest.main()
