import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import ConfigError, load_config


class JavaNormalizationConfigTest(unittest.TestCase):
    def load(self, values: dict[str, str] | None = None):
        with patch.dict(
            os.environ,
            {"APP_ENV": "test", **(values or {})},
            clear=True,
        ):
            return load_config()

    def shadow_values(self, root: Path) -> dict[str, str]:
        key_file = root / "normalization-key"
        key_file.write_text("T" * 32, encoding="utf-8")
        return {
            "ANALYSIS_JD_NORMALIZATION_MODE": "shadow",
            "JD_NORMALIZATION_BASE_URL": "http://java-normalization:8091",
            "JD_NORMALIZATION_API_KEY_FILE": str(key_file),
            "JD_NORMALIZATION_CONNECT_TIMEOUT_MS": "200",
            "JD_NORMALIZATION_RESPONSE_TIMEOUT_MS": "600",
            "JD_NORMALIZATION_TOTAL_TIMEOUT_MS": "800",
            "JD_NORMALIZATION_MAX_RESPONSE_BYTES": "262144",
            "JD_NORMALIZATION_EXPECTED_POLICY_VERSION": "jd-normalization-v1",
            "JD_NORMALIZATION_EXPECTED_DICTIONARY_VERSION": "skills-v1",
            "JD_NORMALIZATION_SHADOW_SAMPLE_RATE": "0.25",
        }

    def test_default_local_mode_requires_no_java_configuration(self):
        config = self.load().jd_normalization
        self.assertEqual(config.mode, "local")
        self.assertIsNone(config.base_url)
        self.assertIsNone(config.api_key)
        self.assertEqual(config.shadow_sample_rate, 0)

    def test_explicit_local_mode_does_not_read_java_url_or_key_file(self):
        config = self.load(
            {
                "ANALYSIS_JD_NORMALIZATION_MODE": "local",
                "JD_NORMALIZATION_BASE_URL": "not a URL",
                "JD_NORMALIZATION_API_KEY_FILE": "/missing/private/key",
            }
        ).jd_normalization
        self.assertEqual(config.mode, "local")
        self.assertIsNone(config.base_url)
        self.assertIsNone(config.api_key)

    def test_valid_shadow_configuration_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.load(
                self.shadow_values(Path(directory))
            ).jd_normalization
        self.assertEqual(config.mode, "shadow")
        self.assertEqual(config.base_url, "http://java-normalization:8091")
        self.assertEqual(len(config.api_key or ""), 32)
        self.assertEqual(config.connect_timeout_ms, 200)
        self.assertEqual(config.response_timeout_ms, 600)
        self.assertEqual(config.total_timeout_ms, 800)
        self.assertEqual(config.max_response_bytes, 262144)
        self.assertEqual(config.pool_max_connections, 10)
        self.assertEqual(config.pool_max_keepalive_connections, 5)

    def test_shadow_requires_base_url(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.shadow_values(Path(directory))
            values.pop("JD_NORMALIZATION_BASE_URL")
            with self.assertRaisesRegex(ConfigError, "BASE_URL"):
                self.load(values)

    def test_shadow_requires_key_file(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.shadow_values(Path(directory))
            values.pop("JD_NORMALIZATION_API_KEY_FILE")
            with self.assertRaisesRegex(ConfigError, "API_KEY_FILE"):
                self.load(values)

    def test_short_missing_relative_and_oversized_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = self.shadow_values(root)
            key_file = Path(values["JD_NORMALIZATION_API_KEY_FILE"])
            key_file.write_text("short", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "32-512"):
                self.load(values)

            values["JD_NORMALIZATION_API_KEY_FILE"] = str(root / "missing")
            with self.assertRaisesRegex(ConfigError, "readable file"):
                self.load(values)

            values["JD_NORMALIZATION_API_KEY_FILE"] = "relative-key"
            with self.assertRaisesRegex(ConfigError, "absolute"):
                self.load(values)

            key_file.write_text("X" * 600, encoding="utf-8")
            values["JD_NORMALIZATION_API_KEY_FILE"] = str(key_file)
            with self.assertRaisesRegex(ConfigError, "size limit"):
                self.load(values)

    def test_key_whitespace_and_invalid_utf8_are_rejected_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = self.shadow_values(root)
            key_file = Path(values["JD_NORMALIZATION_API_KEY_FILE"])
            key_file.write_text("X" * 31 + " internal", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "whitespace-free"):
                self.load(values)
            key_file.write_bytes(b"\xff" * 40)
            with self.assertRaisesRegex(ConfigError, "read safely"):
                self.load(values)

    def test_invalid_origins_are_rejected(self):
        invalid = (
            "java-normalization:8091",
            "ftp://java-normalization",
            "http://user:password@java-normalization:8091",
            "http://java-normalization:8091/path",
            "http://java-normalization:8091/../normalize",
            "http://java-normalization:8091?target=other",
            "http://java-normalization:8091#fragment",
            "http://:bad",
        )
        with tempfile.TemporaryDirectory() as directory:
            base = self.shadow_values(Path(directory))
            for value in invalid:
                with self.subTest(value=value):
                    configured = dict(base)
                    configured["JD_NORMALIZATION_BASE_URL"] = value
                    with self.assertRaisesRegex(ConfigError, "BASE_URL"):
                        self.load(configured)

    def test_timeout_bounds_are_validated(self):
        invalid = {
            "JD_NORMALIZATION_CONNECT_TIMEOUT_MS": ("0", "5001"),
            "JD_NORMALIZATION_RESPONSE_TIMEOUT_MS": ("0", "10001"),
            "JD_NORMALIZATION_TOTAL_TIMEOUT_MS": ("0", "15001"),
        }
        with tempfile.TemporaryDirectory() as directory:
            base = self.shadow_values(Path(directory))
            for name, values in invalid.items():
                for value in values:
                    with self.subTest(name=name, value=value):
                        configured = dict(base)
                        configured[name] = value
                        with self.assertRaisesRegex(ConfigError, name):
                            self.load(configured)

    def test_maximum_response_and_sample_rate_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            base = self.shadow_values(Path(directory))
            for value in ("0", "1048577"):
                configured = dict(base)
                configured["JD_NORMALIZATION_MAX_RESPONSE_BYTES"] = value
                with self.assertRaisesRegex(ConfigError, "MAX_RESPONSE_BYTES"):
                    self.load(configured)
            for value in ("-0.1", "1.1", "nan", "inf"):
                configured = dict(base)
                configured["JD_NORMALIZATION_SHADOW_SAMPLE_RATE"] = value
                with self.assertRaisesRegex(ConfigError, "SHADOW_SAMPLE_RATE"):
                    self.load(configured)

    def test_expected_versions_must_be_nonblank_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            base = self.shadow_values(Path(directory))
            for name in (
                "JD_NORMALIZATION_EXPECTED_POLICY_VERSION",
                "JD_NORMALIZATION_EXPECTED_DICTIONARY_VERSION",
            ):
                for value in ("", " ", "x" * 65, "unsafe value"):
                    with self.subTest(name=name, value=value):
                        configured = dict(base)
                        configured[name] = value
                        with self.assertRaisesRegex(ConfigError, name):
                            self.load(configured)

    def test_unknown_and_reserved_java_modes_fail_startup_safely(self):
        with self.assertRaisesRegex(ConfigError, "local, shadow, or java"):
            self.load({"ANALYSIS_JD_NORMALIZATION_MODE": "unknown"})
        with self.assertRaisesRegex(
            ConfigError,
            "Phase III execution-fingerprint contract",
        ):
            self.load({"ANALYSIS_JD_NORMALIZATION_MODE": "java"})

    def test_configuration_errors_do_not_expose_key_or_path(self):
        secret = "TEST_ONLY_DO_NOT_EXPOSE_" + "X" * 40
        sensitive_path = "/private/secrets/normalization-" + secret
        try:
            self.load(
                {
                    "ANALYSIS_JD_NORMALIZATION_MODE": "shadow",
                    "JD_NORMALIZATION_BASE_URL": "http://java-normalization:8091",
                    "JD_NORMALIZATION_API_KEY_FILE": sensitive_path,
                }
            )
        except ConfigError as exc:
            self.assertNotIn(secret, str(exc))
            self.assertNotIn(sensitive_path, str(exc))
        else:
            self.fail("Expected a safe configuration failure.")


if __name__ == "__main__":
    unittest.main()
