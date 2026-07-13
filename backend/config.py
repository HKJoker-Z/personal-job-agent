"""Environment-backed application configuration with production safety validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_VERSION = "2.0.0-alpha.2"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DEVELOPMENT_DATABASE_PATH = (BACKEND_DIR / "data" / "app.db").resolve(strict=False)
DEFAULT_DEVELOPMENT_KNOWLEDGE_PATH = (PROJECT_ROOT / "docs" / "PROJECT_KNOWLEDGE.md").resolve(strict=False)
DEFAULT_PRODUCTION_DATABASE_PATH = Path("/app/data/app.db")
DEFAULT_PRODUCTION_KNOWLEDGE_PATH = Path("/app/project-knowledge/PROJECT_KNOWLEDGE.md")
DEFAULT_SEED_PATH = Path("/app/seed/PROJECT_KNOWLEDGE.md")
ALLOWED_APP_ENVS = ("development", "production", "test")
ALLOWED_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


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
    enable_api_docs: bool
    log_level: str
    monitoring_admin_token_configured: bool
    monitoring_allow_remote_admin: bool

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


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
        max_upload_size_mb=parse_int("MAX_UPLOAD_SIZE_MB", os.getenv("MAX_UPLOAD_SIZE_MB"), 8, 1, 8),
        request_timeout_seconds=parse_int(
            "REQUEST_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS"), 60, 5, 300
        ),
        enable_api_docs=parse_bool("ENABLE_API_DOCS", os.getenv("ENABLE_API_DOCS"), not production),
        log_level=log_level,
        monitoring_admin_token_configured=bool(os.getenv("MONITORING_ADMIN_TOKEN", "")),
        monitoring_allow_remote_admin=parse_bool(
            "MONITORING_ALLOW_REMOTE_ADMIN", os.getenv("MONITORING_ALLOW_REMOTE_ADMIN"), False
        ),
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
    return config


def safe_config_status(config: AppConfig) -> dict[str, object]:
    return {
        "app_env": config.app_env,
        "api_docs_enabled": config.enable_api_docs,
        "allowed_origin_count": len(config.allowed_origins),
        "trusted_host_count": len(config.trusted_hosts),
        "max_upload_size_mb": config.max_upload_size_mb,
        "request_timeout_seconds": config.request_timeout_seconds,
        "monitoring_admin_configured": config.monitoring_admin_token_configured,
        "monitoring_remote_admin_allowed": config.monitoring_allow_remote_admin,
    }
