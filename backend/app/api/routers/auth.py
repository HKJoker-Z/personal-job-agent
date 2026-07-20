"""Authentication endpoints. No public registration endpoint exists."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.api.dependencies import CurrentSession, CurrentUser, DbSession
from app.auth.rate_limit import LoginRateLimited
from app.auth.service import AuthService, InvalidCredentials, InvalidSession
from app.core.config import load_v2_settings
from app.db.repositories.auth import AuthRepository


router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)
    remember_me: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


def _user_response(user: CurrentUser) -> dict[str, str]:
    return {"id": str(user.id), "display_name": user.display_name, "role": user.role}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> dict[str, object]:
    settings = load_v2_settings()
    service = AuthService(db, settings)
    client_host = request.client.host if request.client else "unknown"
    try:
        credentials = service.login(
            str(payload.email),
            payload.password,
            client_host,
            request.headers.get("user-agent", ""),
            remember_me=payload.remember_me,
            previous_token=request.cookies.get(settings.session_cookie_name),
        )
    except LoginRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc
    response.set_cookie(
        key=settings.session_cookie_name,
        value=credentials.token,
        max_age=(settings.remember_me_session_ttl_days * 86400) if payload.remember_me else None,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {
        "authenticated": True,
        "user": _user_response(credentials.user),
        "csrf_token": credentials.csrf_token,
    }


@router.get("/session")
def session_status(request: Request, db: DbSession) -> dict[str, object]:
    settings = load_v2_settings()
    repository = AuthRepository(db)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return {"authenticated": False, "auth_initialized": repository.users_exist()}
    service = AuthService(db, settings)
    try:
        user_session, user = service.authenticate(raw_token)
    except InvalidSession:
        return {"authenticated": False, "auth_initialized": repository.users_exist()}
    csrf = service.rotate_csrf(user_session)
    return {
        "authenticated": True,
        "user": _user_response(user),
        "csrf_token": csrf,
        "auth_initialized": True,
    }


@router.post("/logout")
def logout(response: Response, db: DbSession, user_session: CurrentSession) -> dict[str, bool]:
    settings = load_v2_settings()
    AuthService(db, settings).revoke_current(user_session)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"logged_out": True}


@router.post("/logout-all")
def logout_all(response: Response, db: DbSession, user: CurrentUser) -> dict[str, object]:
    settings = load_v2_settings()
    count = AuthService(db, settings).revoke_all(user)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"logged_out": True, "revoked_sessions": count}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: DbSession,
    user: CurrentUser,
    user_session: CurrentSession,
) -> dict[str, object]:
    try:
        settings = load_v2_settings()
        credentials = AuthService(db, settings).change_password(
            user,
            user_session,
            payload.current_password,
            payload.new_password,
            request.headers.get("user-agent", ""),
        )
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.set_cookie(
        key=settings.session_cookie_name,
        value=credentials.token,
        max_age=None,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"password_changed": True, "csrf_token": credentials.csrf_token}
