"""Authentication persistence operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, AuthLoginAttempt, User, UserSession


class AuthRepository:
    def __init__(self, session: Session):
        self.session = session

    def users_exist(self) -> bool:
        return self.session.scalar(select(User.id).limit(1)) is not None

    def user_by_email(self, normalized_email: str) -> User | None:
        return self.session.scalar(select(User).where(User.normalized_email == normalized_email))

    def user_by_id(self, user_id: UUID) -> User | None:
        return self.session.get(User, user_id)

    def add_user(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def session_by_hash(self, digest: str) -> UserSession | None:
        return self.session.scalar(select(UserSession).where(UserSession.token_hash == digest))

    def add_session(self, user_session: UserSession) -> UserSession:
        self.session.add(user_session)
        self.session.flush()
        return user_session

    def revoke_user_sessions(
        self,
        user_id: UUID,
        when: datetime,
        reason: str,
        exclude_session_id: UUID | None = None,
    ) -> int:
        statement = update(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        if exclude_session_id is not None:
            statement = statement.where(UserSession.id != exclude_session_id)
        result = self.session.execute(statement.values(revoked_at=when, revoke_reason=reason))
        return int(result.rowcount or 0)

    def login_attempt(self, subject_hash: str, client_hash: str) -> AuthLoginAttempt | None:
        return self.session.scalar(
            select(AuthLoginAttempt)
            .where(
                AuthLoginAttempt.subject_hash == subject_hash,
                AuthLoginAttempt.client_hash == client_hash,
            )
            .with_for_update()
        )

    def clear_login_attempts(self, subject_hash: str) -> None:
        self.session.execute(
            delete(AuthLoginAttempt).where(AuthLoginAttempt.subject_hash == subject_hash)
        )

    def cleanup_login_attempts(self, cutoff: datetime) -> int:
        result = self.session.execute(
            delete(AuthLoginAttempt).where(AuthLoginAttempt.last_failed_at < cutoff)
        )
        return int(result.rowcount or 0)

    def audit(
        self,
        event_type: str,
        user_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        outcome: str = "success",
        safe_metadata: dict[str, object] | None = None,
    ) -> None:
        self.session.add(
            AuditEvent(
                user_id=user_id,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                safe_metadata=safe_metadata or {},
            )
        )
