"""Environment-backed application configuration with production safety validation."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


APP_VERSION = os.getenv("APP_VERSION", "2.0.4").strip() or "2.0.4"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DEVELOPMENT_DATABASE_PATH = (BACKEND_DIR / "data" / "app.db").resolve(strict=False)
DEFAULT_DEVELOPMENT_KNOWLEDGE_PATH = (PROJECT_ROOT / "docs" / "PROJECT_KNOWLEDGE.md").resolve(strict=False)
DEFAULT_PRODUCTION_DATABASE_PATH = Path("/app/data/app.db")
DEFAULT_PRODUCTION_KNOWLEDGE_PATH = Path("/app/project-knowledge/PROJECT_KNOWLEDGE.md")
DEFAULT_SEED_PATH = Path("/app/seed/PROJECT_KNOWLEDGE.md")
ALLOWED_APP_ENVS = ("development", "production", "test")
ALLOWED_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
ALLOWED_JD_NORMALIZATION_MODES = ("local", "shadow", "java")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
JAVA_API_KEY_MINIMUM_BYTES = 32
JAVA_API_KEY_MAXIMUM_BYTES = 512


class ConfigError(RuntimeError):
    """A safe configuration error that never embeds configured secret values."""


def parse_bool(name: str, value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false.")


def parse_int(name: str, value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def parse_float(
    name: str,
    value: str | None,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number.") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    items: list[str] = []
    seen: set[str] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if item and item not in seen:
            seen.add(item)
            items.append(item)
    return tuple(items)


def resolve_path(value: str | None, default: Path) -> Path:
    if not value or not value.strip():
        return default.resolve(strict=False)
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path.resolve(strict=False)


@dataclass(frozen=True)
class JavaNormalizationConfig:
    mode: str
    base_url: str | None
    api_key: str | None
    connect_timeout_ms: int
    response_timeout_ms: int
    total_timeout_ms: int
    max_response_bytes: int
    expected_policy_version: str
    expected_dictionary_version: str
    shadow_sample_rate: float
    pool_max_connections: int = 10
    pool_max_keepalive_connections: int = 5


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    database_path: Path
    project_knowledge_path: Path
    project_knowledge_seed_path: Path
    deepseek_api_key: str
    allowed_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    max_upload_size_mb: int
    request_timeout_seconds: int
    model_max_output_tokens: int
    analysis_resume_max_chars: int
    analysis_job_description_max_chars: int
    enable_api_docs: bool
    log_level: str
    monitoring_admin_token_configured: bool
    monitoring_allow_remote_admin: bool
    mock_provider_enabled: bool
    jd_normalization: JavaNormalizationConfig

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


def _normalization_version(name: str, default: str) -> str:
    supplied = os.getenv(name)
    if supplied is not None and not supplied.strip():
        raise ConfigError(f"{name} must be 1-64 safe ASCII characters.")
    value = (supplied or default).strip()
    if not VERSION_PATTERN.fullmatch(value):
        raise ConfigError(f"{name} must be 1-64 safe ASCII characters.")
    return value


def _normalization_base_url() -> str:
    value = os.getenv("JD_NORMALIZATION_BASE_URL", "").strip()
    if not value:
        raise ConfigError("JD_NORMALIZATION_BASE_URL is required in shadow mode.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ConfigError("JD_NORMALIZATION_BASE_URL must be a valid HTTP or HTTPS origin.") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ConfigError(
            "JD_NORMALIZATION_BASE_URL must be an absolute HTTP or HTTPS origin "
            "without userinfo, query, fragment, or endpoint path."
        )
    if port is not None and not 1 <= port <= 65535:
        raise ConfigError("JD_NORMALIZATION_BASE_URL port is invalid.")
    return value.rstrip("/")


def _normalization_api_key() -> str:
    supplied = os.getenv("JD_NORMALIZATION_API_KEY_FILE", "").strip()
    if not supplied:
        raise ConfigError("JD_NORMALIZATION_API_KEY_FILE is required in shadow mode.")
    path = Path(supplied).expanduser()
    if not path.is_absolute():
        raise ConfigError("JD_NORMALIZATION_API_KEY_FILE must be an absolute file path.")
    try:
        if not path.is_file():
            raise ConfigError("JD_NORMALIZATION_API_KEY_FILE must reference a readable file.")
        if path.stat().st_size > JAVA_API_KEY_MAXIMUM_BYTES + 2:
            raise ConfigError("JD_NORMALIZATION_API_KEY_FILE exceeds the safe size limit.")
        key = path.read_text(encoding="utf-8").strip()
    except ConfigError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ConfigError("JD_NORMALIZATION_API_KEY_FILE could not be read safely.") from exc
    encoded = key.encode("utf-8")
    if (
        len(encoded) < JAVA_API_KEY_MINIMUM_BYTES
        or len(encoded) > JAVA_API_KEY_MAXIMUM_BYTES
        or any(character.isspace() for character in key)
        or "\x00" in key
    ):
        raise ConfigError(
            "JD_NORMALIZATION_API_KEY_FILE must contain a 32-512 byte whitespace-free key."
        )
    return key


def load_java_normalization_config() -> JavaNormalizationConfig:
    mode = (
        os.getenv("ANALYSIS_JD_NORMALIZATION_MODE", "local").strip().lower()
        or "local"
    )
    if mode not in ALLOWED_JD_NORMALIZATION_MODES:
        raise ConfigError(
            "ANALYSIS_JD_NORMALIZATION_MODE must be local, shadow, or java."
        )
    if mode == "java":
        raise ConfigError(
            "ANALYSIS_JD_NORMALIZATION_MODE=java is reserved: authoritative Java "
            "normalization requires the Phase III execution-fingerprint contract."
        )

    connect_timeout_ms = parse_int(
        "JD_NORMALIZATION_CONNECT_TIMEOUT_MS",
        os.getenv("JD_NORMALIZATION_CONNECT_TIMEOUT_MS"),
        200,
        1,
        5_000,
    )
    response_timeout_ms = parse_int(
        "JD_NORMALIZATION_RESPONSE_TIMEOUT_MS",
        os.getenv("JD_NORMALIZATION_RESPONSE_TIMEOUT_MS"),
        600,
        1,
        10_000,
    )
    total_timeout_ms = parse_int(
        "JD_NORMALIZATION_TOTAL_TIMEOUT_MS",
        os.getenv("JD_NORMALIZATION_TOTAL_TIMEOUT_MS"),
        800,
        1,
        15_000,
    )
    max_response_bytes = parse_int(
        "JD_NORMALIZATION_MAX_RESPONSE_BYTES",
        os.getenv("JD_NORMALIZATION_MAX_RESPONSE_BYTES"),
        256 * 1024,
        1_024,
        1024 * 1024,
    )
    sample_rate = parse_float(
        "JD_NORMALIZATION_SHADOW_SAMPLE_RATE",
        os.getenv("JD_NORMALIZATION_SHADOW_SAMPLE_RATE"),
        0.0,
        0.0,
        1.0,
    )
    policy_version = _normalization_version(
        "JD_NORMALIZATION_EXPECTED_POLICY_VERSION",
        "jd-normalization-v1",
    )
    dictionary_version = _normalization_version(
        "JD_NORMALIZATION_EXPECTED_DICTIONARY_VERSION",
        "skills-v1",
    )

    base_url = None
    api_key = None
    if mode == "shadow":
        base_url = _normalization_base_url()
        api_key = _normalization_api_key()

    return JavaNormalizationConfig(
        mode=mode,
        base_url=base_url,
        api_key=api_key,
        connect_timeout_ms=connect_timeout_ms,
        response_timeout_ms=response_timeout_ms,
        total_timeout_ms=total_timeout_ms,
        max_response_bytes=max_response_bytes,
        expected_policy_version=policy_version,
        expected_dictionary_version=dictionary_version,
        shadow_sample_rate=sample_rate,
    )


def load_config(*, validate_production: bool = True) -> AppConfig:
    app_env = (os.getenv("APP_ENV", "development").strip().lower() or "development")
    if app_env not in ALLOWED_APP_ENVS:
        raise ConfigError("APP_ENV must be development, production, or test.")

    production = app_env == "production"
    database_default = DEFAULT_PRODUCTION_DATABASE_PATH if production else DEFAULT_DEVELOPMENT_DATABASE_PATH
    knowledge_default = DEFAULT_PRODUCTION_KNOWLEDGE_PATH if production else DEFAULT_DEVELOPMENT_KNOWLEDGE_PATH
    seed_default = DEFAULT_SEED_PATH if production else DEFAULT_DEVELOPMENT_KNOWLEDGE_PATH
    default_origins = () if production else ("http://localhost:5173", "http://127.0.0.1:5173")
    default_hosts = () if production else ("localhost", "127.0.0.1", "testserver")

    allowed_origins = parse_csv(os.getenv("ALLOWED_ORIGINS")) or default_origins
    configured_trusted_hosts = parse_csv(os.getenv("TRUSTED_HOSTS"))
    if production:
        trusted_hosts = tuple(dict.fromkeys((*configured_trusted_hosts, "localhost", "127.0.0.1", "backend")))
    else:
        trusted_hosts = configured_trusted_hosts or default_hosts
    log_level = (os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO")
    if log_level not in ALLOWED_LOG_LEVELS:
        raise ConfigError("LOG_LEVEL is not supported.")

    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    config = AppConfig(
        app_env=app_env,
        database_path=resolve_path(os.getenv("APP_DATABASE_PATH"), database_default),
        project_knowledge_path=resolve_path(os.getenv("PROJECT_KNOWLEDGE_PATH"), knowledge_default),
        project_knowledge_seed_path=resolve_path(os.getenv("PROJECT_KNOWLEDGE_SEED_PATH"), seed_default),
        deepseek_api_key=deepseek_api_key,
        allowed_origins=allowed_origins,
        trusted_hosts=trusted_hosts,
        max_upload_size_mb=parse_int("MAX_UPLOAD_SIZE_MB", os.getenv("MAX_UPLOAD_SIZE_MB"), 10, 1, 32),
        request_timeout_seconds=parse_int(
            "REQUEST_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS"), 60, 5, 300
        ),
        model_max_output_tokens=parse_int(
            "AGENT_MODEL_MAX_OUTPUT_TOKENS",
            os.getenv("AGENT_MODEL_MAX_OUTPUT_TOKENS"),
            1200,
            100,
            5000,
        ),
        analysis_resume_max_chars=parse_int(
            "ANALYSIS_RESUME_MAX_CHARS",
            os.getenv("ANALYSIS_RESUME_MAX_CHARS"),
            100_000,
            1_000,
            200_000,
        ),
        analysis_job_description_max_chars=parse_int(
            "ANALYSIS_JOB_DESCRIPTION_MAX_CHARS",
            os.getenv("ANALYSIS_JOB_DESCRIPTION_MAX_CHARS"),
            60_000,
            1_000,
            120_000,
        ),
        enable_api_docs=parse_bool("ENABLE_API_DOCS", os.getenv("ENABLE_API_DOCS"), not production),
        log_level=log_level,
        monitoring_admin_token_configured=bool(os.getenv("MONITORING_ADMIN_TOKEN", "")),
        monitoring_allow_remote_admin=parse_bool(
            "MONITORING_ALLOW_REMOTE_ADMIN", os.getenv("MONITORING_ALLOW_REMOTE_ADMIN"), False
        ),
        mock_provider_enabled=parse_bool(
            "MOCK_PROVIDER_ENABLED", os.getenv("MOCK_PROVIDER_ENABLED"), False
        ),
        jd_normalization=load_java_normalization_config(),
    )
    if production and validate_production:
        if not config.deepseek_api_key:
            raise ConfigError("DEEPSEEK_API_KEY must be configured in production.")
        if "*" in config.allowed_origins:
            raise ConfigError("ALLOWED_ORIGINS cannot contain a wildcard in production.")
        if not configured_trusted_hosts or "*" in configured_trusted_hosts:
            raise ConfigError("TRUSTED_HOSTS must contain explicit hosts in production.")
        if config.enable_api_docs and os.getenv("ENABLE_API_DOCS") is None:
            raise ConfigError("API documentation must default to disabled in production.")
        if config.mock_provider_enabled:
            raise ConfigError("MOCK_PROVIDER_ENABLED must be false in production.")
    return config


def safe_config_status(config: AppConfig) -> dict[str, object]:
    return {
        "app_env": config.app_env,
        "api_docs_enabled": config.enable_api_docs,
        "allowed_origin_count": len(config.allowed_origins),
        "trusted_host_count": len(config.trusted_hosts),
        "max_upload_size_mb": config.max_upload_size_mb,
        "request_timeout_seconds": config.request_timeout_seconds,
        "model_max_output_tokens": config.model_max_output_tokens,
        "analysis_resume_max_chars": config.analysis_resume_max_chars,
        "analysis_job_description_max_chars": config.analysis_job_description_max_chars,
        "monitoring_admin_configured": config.monitoring_admin_token_configured,
        "monitoring_remote_admin_allowed": config.monitoring_allow_remote_admin,
        "jd_normalization_mode": config.jd_normalization.mode,
        "jd_normalization_shadow_sample_rate": config.jd_normalization.shadow_sample_rate,
    }
