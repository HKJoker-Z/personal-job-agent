"""Request-scoped database and authenticated principal dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.models import User, UserSession


def request_db(request: Request) -> Session:
    db = getattr(request.state, "v2_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Version 2 database is unavailable.")
    return db


def current_user(request: Request) -> User:
    user = getattr(request.state, "v2_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def current_session(request: Request) -> UserSession:
    user_session = getattr(request.state, "v2_session", None)
    if user_session is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user_session


DbSession = Annotated[Session, Depends(request_db)]
CurrentUser = Annotated[User, Depends(current_user)]
CurrentSession = Annotated[UserSession, Depends(current_session)]
