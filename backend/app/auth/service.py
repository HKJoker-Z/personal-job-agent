"""Authentication and Session transaction rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.rate_limit import LoginRateLimiter
from app.core.config import V2Settings
from app.core.security import (
    hash_password,
    keyed_fingerprint,
    normalize_email,
    random_token,
    token_hash,
    tokens_match,
    validate_password,
    verify_password,
)
from app.db.models import User, UserSession, ensure_utc, utc_now
from app.db.repositories.auth import AuthRepository


class InvalidCredentials(RuntimeError):
    pass


class InvalidSession(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionCredentials:
    token: str
    csrf_token: str
    session: UserSession
    user: User


class AuthService:
    def __init__(self, db: Session, settings: V2Settings):
        self.db = db
        self.settings = settings
        self.repository = AuthRepository(db)

    def fingerprint(self, value: str) -> str:
        return keyed_fingerprint(value or "unknown", self.settings.auth_fingerprint_key)

    def login(self, email: str, password: str, client_value: str, user_agent: str) -> SessionCredentials:
        try:
            normalized = normalize_email(email)
        except ValueError:
            normalized = email.strip().lower()[:320]
        subject_hash = self.fingerprint(f"email:{normalized}")
        client_hash = self.fingerprint(f"client:{client_value}")
        limiter = LoginRateLimiter(self.repository, self.settings)
        limiter.check(subject_hash, client_hash)
        user = self.repository.user_by_email(normalized)
        valid = bool(user and user.is_active and verify_password(password, user.password_hash))
        if not valid:
            limiter.failure(subject_hash, client_hash)
            self.repository.audit("auth.login_failed", outcome="failure")
            raise InvalidCredentials("Invalid email or password.")
        limiter.success(subject_hash)
        credentials = self._new_session(user, user_agent)
        user.last_login_at = utc_now()
        self.repository.audit("auth.login_succeeded", user_id=user.id)
        return credentials

    def _new_session(self, user: User, user_agent: str) -> SessionCredentials:
        now = utc_now()
        raw_token = random_token()
        csrf_token = random_token()
        user_session = UserSession(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            csrf_token_hash=token_hash(csrf_token),
            created_at=now,
            last_seen_at=now,
            idle_expires_at=now + timedelta(minutes=self.settings.session_idle_timeout_minutes),
            absolute_expires_at=now + timedelta(hours=self.settings.session_absolute_timeout_hours),
            user_agent_hash=self.fingerprint(f"ua:{user_agent}"),
        )
        self.repository.add_session(user_session)
        return SessionCredentials(raw_token, csrf_token, user_session, user)

    def authenticate(self, raw_token: str | None, *, touch: bool = True) -> tuple[UserSession, User]:
        if not raw_token or len(raw_token) > 256:
            raise InvalidSession("Authentication required.")
        digest = token_hash(raw_token)
        user_session = self.repository.session_by_hash(digest)
        if user_session is None or not tokens_match(raw_token, user_session.token_hash):
            raise InvalidSession("Authentication required.")
        now = utc_now()
        if user_session.revoked_at is not None:
            raise InvalidSession("Authentication required.")
        idle_expires_at = ensure_utc(user_session.idle_expires_at)
        absolute_expires_at = ensure_utc(user_session.absolute_expires_at)
        last_seen_at = ensure_utc(user_session.last_seen_at)
        if idle_expires_at <= now or absolute_expires_at <= now:
            user_session.revoked_at = now
            user_session.revoke_reason = "expired"
            raise InvalidSession("Authentication required.")
        user = self.repository.user_by_id(user_session.user_id)
        if user is None or not user.is_active:
            raise InvalidSession("Authentication required.")
        if touch and (now - last_seen_at).total_seconds() >= self.settings.session_touch_interval_seconds:
            user_session.last_seen_at = now
            user_session.idle_expires_at = min(
                now + timedelta(minutes=self.settings.session_idle_timeout_minutes),
                absolute_expires_at,
            )
        return user_session, user

    def rotate_csrf(self, user_session: UserSession) -> str:
        value = random_token()
        user_session.csrf_token_hash = token_hash(value)
        return value

    def validate_csrf(self, user_session: UserSession, value: str | None) -> bool:
        return bool(value and len(value) <= 256 and tokens_match(value, user_session.csrf_token_hash))

    def revoke_current(self, user_session: UserSession, reason: str = "logout") -> None:
        if user_session.revoked_at is None:
            user_session.revoked_at = utc_now()
            user_session.revoke_reason = reason
            self.repository.audit("auth.logout", user_id=user_session.user_id)

    def revoke_all(self, user: User, reason: str = "logout_all") -> int:
        count = self.repository.revoke_user_sessions(user.id, utc_now(), reason)
        self.repository.audit("auth.logout_all", user_id=user.id, safe_metadata={"revoked_count": count})
        return count

    def change_password(
        self,
        user: User,
        current_session: UserSession,
        current_password: str,
        new_password: str,
    ) -> str:
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentials("Current password is incorrect.")
        validate_password(new_password)
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utc_now()
        user.version += 1
        self.repository.revoke_user_sessions(
            user.id,
            utc_now(),
            "password_changed",
            exclude_session_id=current_session.id,
        )
        csrf = self.rotate_csrf(current_session)
        self.repository.audit("auth.password_changed", user_id=user.id)
        return csrf

    def create_user(self, email: str, password: str, display_name: str, role: str) -> User:
        normalized = normalize_email(email)
        if role not in {"admin", "user"}:
            raise ValueError("Unsupported role.")
        if self.repository.user_by_email(normalized):
            raise ValueError("A user with that email already exists.")
        user = User(
            email=normalized,
            normalized_email=normalized,
            password_hash=hash_password(password),
            display_name=display_name.strip()[:120] or "User",
            role=role,
        )
        self.repository.add_user(user)
        self.repository.audit("auth.admin_created" if role == "admin" else "auth.user_created", user_id=user.id)
        return user
