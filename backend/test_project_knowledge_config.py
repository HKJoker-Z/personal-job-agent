import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import load_config
from project_knowledge_runtime import get_project_knowledge_path, initialize_project_knowledge
from test_support import temporary_test_database


class ProjectKnowledgeConfigTest(unittest.TestCase):
    def test_configurable_project_knowledge_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "custom" / "PROJECT_KNOWLEDGE.md"
            with patch.dict(os.environ, {"PROJECT_KNOWLEDGE_PATH": str(target)}, clear=False):
                self.assertEqual(get_project_knowledge_path(), target.resolve())

    def test_seed_initializes_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed.md"
            target = root / "runtime" / "PROJECT_KNOWLEDGE.md"
            seed.write_text("seed content", encoding="utf-8")
            with patch.dict(os.environ, {
                "PROJECT_KNOWLEDGE_PATH": str(target),
                "PROJECT_KNOWLEDGE_SEED_PATH": str(seed),
            }, clear=False):
                self.assertTrue(initialize_project_knowledge())
            self.assertEqual(target.read_text(encoding="utf-8"), "seed content")

    def test_seed_does_not_overwrite_existing_user_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed.md"
            target = root / "runtime" / "PROJECT_KNOWLEDGE.md"
            target.parent.mkdir()
            seed.write_text("seed content", encoding="utf-8")
            target.write_text("user content", encoding="utf-8")
            config_env = {
                "PROJECT_KNOWLEDGE_PATH": str(target),
                "PROJECT_KNOWLEDGE_SEED_PATH": str(seed),
            }
            with patch.dict(os.environ, config_env, clear=False):
                self.assertTrue(initialize_project_knowledge(load_config(validate_production=False)))
            self.assertEqual(target.read_text(encoding="utf-8"), "user content")

    def test_upload_writer_uses_configured_path_and_status_is_logical(self):
        with temporary_test_database(), tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "writable" / "PROJECT_KNOWLEDGE.md"
            with patch.dict(os.environ, {"PROJECT_KNOWLEDGE_PATH": str(target)}, clear=False):
                from main import project_knowledge_status_data, write_project_knowledge_file

                write_project_knowledge_file("configured content")
                status = project_knowledge_status_data()
            self.assertEqual(target.read_text(encoding="utf-8"), "configured content")
            self.assertEqual(status["path"], "PROJECT_KNOWLEDGE.md")
            self.assertNotIn(str(target.parent), str(status))

    def test_evaluation_rag_runner_uses_configured_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "PROJECT_KNOWLEDGE.md"
            target.write_text("RAG Retrieval-Augmented Generation FastAPI evidence", encoding="utf-8")
            with patch.dict(os.environ, {"PROJECT_KNOWLEDGE_PATH": str(target)}, clear=False):
                from evaluation_service import runner_rag_retrieval

                result = runner_rag_retrieval({"input": {"query": "rag fastapi"}, "expected": {}})
            self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()
