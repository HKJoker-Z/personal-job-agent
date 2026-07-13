"""Database-backed login failure accounting, safe across PostgreSQL workers."""

from __future__ import annotations

from datetime import timedelta

from app.core.config import V2Settings
from app.db.models import AuthLoginAttempt, ensure_utc, utc_now
from app.db.repositories.auth import AuthRepository


class LoginRateLimited(RuntimeError):
    pass


class LoginRateLimiter:
    def __init__(self, repository: AuthRepository, settings: V2Settings):
        self.repository = repository
        self.settings = settings

    def check(self, subject_hash: str, client_hash: str) -> None:
        attempt = self.repository.login_attempt(subject_hash, client_hash)
        now = utc_now()
        locked_until = ensure_utc(attempt.locked_until) if attempt and attempt.locked_until else None
        if attempt and locked_until and locked_until > now:
            raise LoginRateLimited("Too many login attempts. Try again later.")
        if attempt and locked_until and locked_until <= now:
            attempt.failed_count = 0
            attempt.locked_until = None

    def failure(self, subject_hash: str, client_hash: str) -> None:
        now = utc_now()
        attempt = self.repository.login_attempt(subject_hash, client_hash)
        if attempt is None:
            attempt = AuthLoginAttempt(
                subject_hash=subject_hash,
                client_hash=client_hash,
                failed_count=0,
                first_failed_at=now,
                last_failed_at=now,
            )
            self.repository.session.add(attempt)
        attempt.failed_count += 1
        attempt.last_failed_at = now
        if attempt.failed_count >= self.settings.auth_max_failed_attempts:
            attempt.locked_until = now + timedelta(minutes=self.settings.auth_lockout_minutes)

    def success(self, subject_hash: str) -> None:
        self.repository.clear_login_attempts(subject_hash)

    def cleanup(self) -> int:
        cutoff = utc_now() - timedelta(days=2)
        return self.repository.cleanup_login_attempts(cutoff)
