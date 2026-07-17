"""Default-deny API authentication, Session-bound CSRF, and Origin enforcement."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.auth.service import AuthService, InvalidSession
from app.core.config import V2Settings
from app.db.session import session_factory


PUBLIC_ENDPOINTS = {
    ("GET", "/api/health"),
    ("GET", "/api/ready"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/session"),
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _request_origin(request: Request) -> str | None:
    origin = request.headers.get("origin", "").strip().rstrip("/")
    if origin:
        return origin
    referer = request.headers.get("referer", "").strip()
    if not referer:
        return None
    parsed = urlsplit(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _admin_destructive(request: Request) -> bool:
    path = request.url.path
    if request.method == "DELETE" and (
        path.startswith("/api/monitoring/") or path.startswith("/api/evaluations/")
    ):
        return True
    return path in {
        "/api/monitoring/data/preview",
        "/api/evaluations/data/preview",
    }


class V2SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: V2Settings):
        super().__init__(app)
        self.settings = settings
        self._session_factory = session_factory()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        content_length = request.headers.get("content-length", "").strip()
        if content_length:
            try:
                if int(content_length) > self.settings.request_max_body_mb * 1024 * 1024:
                    return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Content-Length is invalid."})
        db = self._session_factory()
        request.state.v2_db = db
        try:
            if (
                self.settings.auth_enabled
                and request.method != "OPTIONS"
                and (request.method, request.url.path) not in PUBLIC_ENDPOINTS
            ):
                auth = AuthService(db, self.settings)
                try:
                    user_session, user = auth.authenticate(
                        request.cookies.get(self.settings.session_cookie_name)
                    )
                except InvalidSession:
                    db.rollback()
                    return JSONResponse(status_code=401, content={"detail": "Authentication required."})
                request.state.v2_session = user_session
                request.state.v2_user = user
                if request.method not in SAFE_METHODS:
                    origin = _request_origin(request)
                    if origin not in self.settings.auth_trusted_origins:
                        db.rollback()
                        return JSONResponse(status_code=403, content={"detail": "Request origin is not trusted."})
                    if not auth.validate_csrf(user_session, request.headers.get("x-csrf-token")):
                        db.rollback()
                        return JSONResponse(status_code=403, content={"detail": "CSRF validation failed."})
                if _admin_destructive(request) and user.role != "admin":
                    db.rollback()
                    return JSONResponse(status_code=403, content={"detail": "Administrator role required."})
            response = await call_next(request)
            if response.status_code >= 500:
                db.rollback()
            else:
                db.commit()
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
            return response
        except SQLAlchemyError:
            db.rollback()
            return JSONResponse(status_code=503, content={"detail": "Database service is unavailable."})
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
