from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt.exceptions import InvalidTokenError as JWTError

from config import settings

bearer_scheme = HTTPBearer(auto_error=False)
ACCESS_TOKEN_TYPE = "access"
ADMIN_SUBJECT = "admin"

@dataclass(frozen=True, slots=True)
class AuthUser:
    subject: str
    role: str
    claims: dict[str, Any]

def _authentication_error(
    message: str = "Invalid or expired authentication token",
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )

def _configuration_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=message,
    )

def _signing_secret() -> str:
    if not settings.auth_jwt_secret:
        raise _configuration_error("Authentication is not configured")
    return settings.auth_jwt_secret

def create_admin_access_token() -> tuple[str, int]:
    ttl_seconds = settings.auth_access_token_ttl_minutes * 60
    now = datetime.now(timezone.utc)
    claims = {
        "sub": ADMIN_SUBJECT,
        "role": "admin",
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    token = jwt.encode(claims, _signing_secret(), algorithm=settings.auth_jwt_algorithm)
    return token, ttl_seconds

def _decode_access_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            _signing_secret(),
            algorithms=[settings.auth_jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except JWTError as exc:
        raise _authentication_error() from exc
    if not isinstance(claims, dict):
        raise _authentication_error()
    if claims.get("type") != ACCESS_TOKEN_TYPE:
        raise _authentication_error("Authentication token is not an access token")
    return claims

def verify_admin_password(password: str) -> bool:
    """Constant-time check of the admin console password from configuration."""
    configured = settings.admin_password
    if not configured:
        return False
    return secrets.compare_digest(password.encode("utf-8"), configured.encode("utf-8"))

def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> AuthUser:
    if credentials is None or not credentials.credentials.strip():
        if settings.auth_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer authentication is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not settings.auth_jwt_secret:
            return AuthUser(
                subject="local-development",
                role="admin",
                claims={"auth_bypass": True},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = _decode_access_token(credentials.credentials)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise _authentication_error("Authentication token is missing a subject")
    role = claims.get("role")
    
    if subject == ADMIN_SUBJECT and role == "admin":
        if not settings.admin_password:
            raise _authentication_error("Admin access is not configured")
        return AuthUser(subject=ADMIN_SUBJECT, role="admin", claims=claims)
    
    raise _authentication_error("Authentication token subject is invalid")

AuthorizedUser = Annotated[AuthUser, Depends(get_current_user)]
AdminUser = AuthorizedUser
