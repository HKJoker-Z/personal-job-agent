"""Environment-only Version 2 settings with production and test safety gates."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url


class V2ConfigError(RuntimeError):
    """Configuration error whose message never includes configured values."""


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise V2ConfigError(f"{name} must be true or false.")


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise V2ConfigError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise V2ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(dict.fromkeys(item.strip().rstrip("/") for item in value.split(",") if item.strip()))


def _database_url(app_env: str) -> str:
    if app_env == "test":
        value = os.getenv("TEST_DATABASE_URL", "").strip()
        if not value:
            return "sqlite+pysqlite:///:memory:"
        parsed = make_url(value)
        if parsed.get_backend_name() == "postgresql":
            database = (parsed.database or "").lower()
            if "test" not in database:
                raise V2ConfigError("PostgreSQL TEST_DATABASE_URL database name must contain 'test'.")
        if "runtime/data/app.db" in value or ".env.production" in value:
            raise V2ConfigError("TEST_DATABASE_URL points to a forbidden production-like resource.")
        return value
    value = os.getenv("DATABASE_URL", "").strip()
    if app_env == "production":
        if not value:
            raise V2ConfigError("DATABASE_URL must be explicitly configured in production.")
        if make_url(value).get_backend_name() != "postgresql":
            raise V2ConfigError("Production DATABASE_URL must use PostgreSQL.")
        return value
    return value or "sqlite+pysqlite:////tmp/pja-v2-development.db"


@dataclass(frozen=True)
class V2Settings:
    app_env: str
    database_url: str
    session_cookie_name: str
    session_cookie_secure: bool
    session_idle_timeout_minutes: int
    session_absolute_timeout_hours: int
    session_touch_interval_seconds: int
    auth_max_failed_attempts: int
    auth_lockout_minutes: int
    auth_trusted_origins: tuple[str, ...]
    auth_fingerprint_key: str
    auth_enabled: bool
    file_storage_root: Path
    max_stored_file_size_mb: int
    database_connect_timeout_seconds: int

    @property
    def max_stored_file_size_bytes(self) -> int:
        return self.max_stored_file_size_mb * 1024 * 1024


def load_v2_settings() -> V2Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower() or "development"
    if app_env not in {"development", "test", "production"}:
        raise V2ConfigError("APP_ENV must be development, test, or production.")
    production = app_env == "production"
    secure_cookie = _bool("SESSION_COOKIE_SECURE", production)
    if production and not secure_cookie:
        raise V2ConfigError("SESSION_COOKIE_SECURE must be true in production.")
    origins = _csv(
        "AUTH_TRUSTED_ORIGINS",
        ("http://localhost:5173", "http://127.0.0.1:5173") if not production else (),
    )
    if production and (not origins or "*" in origins):
        raise V2ConfigError("AUTH_TRUSTED_ORIGINS must contain explicit origins in production.")
    fingerprint_key = os.getenv("AUTH_FINGERPRINT_KEY", "")
    if production and len(fingerprint_key) < 32:
        raise V2ConfigError("AUTH_FINGERPRINT_KEY must be configured securely in production.")
    storage_default = Path("/app/runtime/files") if production else Path("/tmp/pja-v2-files")
    storage_root = Path(os.getenv("FILE_STORAGE_ROOT", str(storage_default))).expanduser().resolve(False)
    return V2Settings(
        app_env=app_env,
        database_url=_database_url(app_env),
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "pja_session").strip() or "pja_session",
        session_cookie_secure=secure_cookie,
        session_idle_timeout_minutes=_int("SESSION_IDLE_TIMEOUT_MINUTES", 30, 5, 1440),
        session_absolute_timeout_hours=_int("SESSION_ABSOLUTE_TIMEOUT_HOURS", 24, 1, 720),
        session_touch_interval_seconds=_int("SESSION_TOUCH_INTERVAL_SECONDS", 60, 15, 900),
        auth_max_failed_attempts=_int("AUTH_MAX_FAILED_ATTEMPTS", 5, 2, 50),
        auth_lockout_minutes=_int("AUTH_LOCKOUT_MINUTES", 15, 1, 1440),
        auth_trusted_origins=origins,
        auth_fingerprint_key=fingerprint_key or "development-only-fingerprint-key-not-for-production",
        auth_enabled=_bool("AUTH_ENABLED", app_env != "test"),
        file_storage_root=storage_root,
        max_stored_file_size_mb=_int("MAX_STORED_FILE_SIZE_MB", 8, 1, 32),
        database_connect_timeout_seconds=_int("DATABASE_CONNECT_TIMEOUT_SECONDS", 10, 1, 60),
    )


def safe_database_status(settings: V2Settings) -> dict[str, object]:
    url = make_url(settings.database_url)
    return {
        "backend": url.get_backend_name(),
        "driver": url.get_driver_name(),
        "host_configured": bool(url.host),
    }
