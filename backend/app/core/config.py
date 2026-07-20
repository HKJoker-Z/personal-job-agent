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


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise V2ConfigError(f"{name} must be a number.") from exc
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
    remember_me_session_ttl_days: int
    session_touch_interval_seconds: int
    auth_max_failed_attempts: int
    auth_lockout_minutes: int
    auth_trusted_origins: tuple[str, ...]
    auth_fingerprint_key: str
    auth_enabled: bool
    file_storage_root: Path
    max_stored_file_size_mb: int
    database_connect_timeout_seconds: int
    database_pool_size: int
    database_max_overflow: int
    redis_url: str
    redis_queue_namespace: str
    worker_concurrency: int
    worker_heartbeat_seconds: int
    worker_stale_seconds: int
    worker_step_lease_seconds: int
    agent_max_auto_retries: int
    agent_user_concurrency_limit: int
    agent_daily_token_limit: int
    agent_daily_cost_limit_usd: float
    agent_run_token_limit: int
    agent_step_token_limit: int
    agent_run_cost_limit_usd: float
    agent_high_cost_approval_usd: float
    sse_max_connections_per_user: int
    sse_heartbeat_seconds: int
    request_max_body_mb: int
    minimum_free_disk_mb: int
    readiness_require_redis: bool
    readiness_require_worker: bool
    model_max_output_tokens: int
    model_input_cost_per_million_usd: float
    model_output_cost_per_million_usd: float

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
    configured_redis_url = os.getenv("REDIS_URL", "").strip()
    if production and not configured_redis_url:
        raise V2ConfigError("REDIS_URL must be explicitly configured in production.")
    redis_url = configured_redis_url or "redis://127.0.0.1:6379/0"
    if not redis_url.startswith(("redis://", "rediss://")):
        raise V2ConfigError("REDIS_URL must use redis:// or rediss://.")
    if production and any(value in redis_url for value in ("localhost", "127.0.0.1")):
        raise V2ConfigError("Production REDIS_URL must use the private Redis service hostname.")
    try:
        daily_cost = float(os.getenv("AGENT_DAILY_COST_LIMIT_USD", "5"))
        run_cost = float(os.getenv("AGENT_RUN_COST_LIMIT_USD", "2"))
        high_cost = float(os.getenv("AGENT_HIGH_COST_APPROVAL_USD", "0.50"))
    except ValueError as exc:
        raise V2ConfigError("Agent cost limits must be numbers.") from exc
    if daily_cost <= 0 or run_cost <= 0 or high_cost <= 0:
        raise V2ConfigError("Agent cost limits must be positive.")
    if run_cost > daily_cost:
        raise V2ConfigError("AGENT_RUN_COST_LIMIT_USD cannot exceed the daily cost limit.")
    input_rate = _float("MODEL_INPUT_COST_PER_MILLION_USD", 0, 0, 1000)
    output_rate = _float("MODEL_OUTPUT_COST_PER_MILLION_USD", 0, 0, 1000)
    if production and (input_rate <= 0 or output_rate <= 0):
        raise V2ConfigError("Production model cost rates must be configured for budget enforcement.")
    return V2Settings(
        app_env=app_env,
        database_url=_database_url(app_env),
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "pja_session").strip() or "pja_session",
        session_cookie_secure=secure_cookie,
        session_idle_timeout_minutes=_int("SESSION_IDLE_TIMEOUT_MINUTES", 30, 5, 1440),
        session_absolute_timeout_hours=_int("SESSION_ABSOLUTE_TIMEOUT_HOURS", 24, 1, 720),
        remember_me_session_ttl_days=_int("REMEMBER_ME_SESSION_TTL_DAYS", 30, 1, 30),
        session_touch_interval_seconds=_int("SESSION_TOUCH_INTERVAL_SECONDS", 60, 15, 900),
        auth_max_failed_attempts=_int("AUTH_MAX_FAILED_ATTEMPTS", 5, 2, 50),
        auth_lockout_minutes=_int("AUTH_LOCKOUT_MINUTES", 15, 1, 1440),
        auth_trusted_origins=origins,
        auth_fingerprint_key=fingerprint_key or "development-only-fingerprint-key-not-for-production",
        auth_enabled=_bool("AUTH_ENABLED", app_env != "test"),
        file_storage_root=storage_root,
        max_stored_file_size_mb=_int("MAX_STORED_FILE_SIZE_MB", 8, 1, 32),
        database_connect_timeout_seconds=_int("DATABASE_CONNECT_TIMEOUT_SECONDS", 10, 1, 60),
        database_pool_size=_int("DATABASE_POOL_SIZE", 10, 1, 100),
        database_max_overflow=_int("DATABASE_MAX_OVERFLOW", 10, 0, 100),
        redis_url=redis_url,
        redis_queue_namespace=os.getenv("REDIS_QUEUE_NAMESPACE", "personal-job-agent-v2").strip()[:80]
        or "personal-job-agent-v2",
        worker_concurrency=_int("AGENT_WORKER_CONCURRENCY", 4, 1, 32),
        worker_heartbeat_seconds=_int("AGENT_WORKER_HEARTBEAT_SECONDS", 15, 5, 120),
        worker_stale_seconds=_int("AGENT_WORKER_STALE_SECONDS", 90, 30, 900),
        worker_step_lease_seconds=_int("AGENT_WORKER_STEP_LEASE_SECONDS", 900, 60, 7200),
        agent_max_auto_retries=_int("AGENT_MAX_AUTO_RETRIES", 3, 0, 10),
        agent_user_concurrency_limit=_int("AGENT_USER_CONCURRENCY_LIMIT", 2, 1, 20),
        agent_daily_token_limit=_int("AGENT_DAILY_TOKEN_LIMIT", 100000, 1000, 100000000),
        agent_daily_cost_limit_usd=daily_cost,
        agent_run_token_limit=_int("AGENT_RUN_TOKEN_LIMIT", 30000, 500, 1000000),
        agent_step_token_limit=_int("AGENT_STEP_TOKEN_LIMIT", 8000, 100, 200000),
        agent_run_cost_limit_usd=run_cost,
        agent_high_cost_approval_usd=high_cost,
        sse_max_connections_per_user=_int("SSE_MAX_CONNECTIONS_PER_USER", 3, 1, 20),
        sse_heartbeat_seconds=_int("SSE_HEARTBEAT_SECONDS", 15, 5, 60),
        request_max_body_mb=_int("REQUEST_MAX_BODY_MB", 10, 1, 32),
        minimum_free_disk_mb=_int("MINIMUM_FREE_DISK_MB", 256, 16, 102400),
        readiness_require_redis=_bool("READINESS_REQUIRE_REDIS", production),
        readiness_require_worker=_bool("READINESS_REQUIRE_WORKER", production),
        model_max_output_tokens=_int("AGENT_MODEL_MAX_OUTPUT_TOKENS", 1200, 100, 5000),
        model_input_cost_per_million_usd=input_rate,
        model_output_cost_per_million_usd=output_rate,
    )


def safe_database_status(settings: V2Settings) -> dict[str, object]:
    url = make_url(settings.database_url)
    return {
        "backend": url.get_backend_name(),
        "driver": url.get_driver_name(),
        "host_configured": bool(url.host),
    }
