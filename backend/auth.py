from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import RefreshToken, User


bearer_scheme = HTTPBearer(auto_error=False)
ACCESS_TOKEN_TYPE = "access"
# bcrypt truncates silently past 72 bytes; reject longer secrets so a password
# is never partially validated.
MAX_PASSWORD_BYTES = 72
AUTHORIZED_ROLES = {"teacher", "admin"}
# The single admin has no database account. It is a fixed token identity,
# authenticated by ADMIN_PASSWORD, that never owns exams or students.
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


# --- Password hashing -------------------------------------------------------


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at most 72 bytes",
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed stored hash; treat as a failed match rather than crashing.
        return False


# --- Access tokens (stateless JWT) ------------------------------------------


def _encode_access_token(*, subject: str, role: str, email: str | None) -> tuple[str, int]:
    ttl_seconds = settings.auth_access_token_ttl_minutes * 60
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "role": role,
        "email": email,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    token = jwt.encode(claims, _signing_secret(), algorithm=settings.auth_jwt_algorithm)
    return token, ttl_seconds


def create_access_token(user: User) -> tuple[str, int]:
    """Return a signed access token and its lifetime in seconds."""
    return _encode_access_token(subject=str(user.id), role=user.role, email=user.email)


def create_admin_access_token() -> tuple[str, int]:
    """Access token for the passwordless-in-DB admin identity."""
    return _encode_access_token(subject=ADMIN_SUBJECT, role="admin", email=None)


def _decode_access_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            _signing_secret(),
            algorithms=[settings.auth_jwt_algorithm],
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError as exc:
        raise _authentication_error() from exc
    if not isinstance(claims, dict):
        raise _authentication_error()
    if claims.get("type") != ACCESS_TOKEN_TYPE:
        raise _authentication_error("Authentication token is not an access token")
    return claims


# --- Admin refresh token (stateless, signed) --------------------------------
# The admin has no database row, so its refresh token is a signed JWT rather
# than an opaque DB-backed token. Rotating ADMIN_PASSWORD or AUTH_JWT_SECRET
# invalidates any outstanding admin session.
ADMIN_REFRESH_TOKEN_TYPE = "admin_refresh"


def create_admin_refresh_token() -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": ADMIN_SUBJECT,
        "type": ADMIN_REFRESH_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(days=settings.auth_refresh_token_ttl_days)).timestamp()
        ),
    }
    return jwt.encode(claims, _signing_secret(), algorithm=settings.auth_jwt_algorithm)


def is_admin_refresh_token(token: str) -> bool:
    try:
        claims = jwt.decode(
            token,
            _signing_secret(),
            algorithms=[settings.auth_jwt_algorithm],
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError:
        return False
    return (
        isinstance(claims, dict)
        and claims.get("type") == ADMIN_REFRESH_TOKEN_TYPE
        and claims.get("sub") == ADMIN_SUBJECT
    )


# --- Refresh tokens (opaque, stored hashed, rotated) ------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_refresh_token(db: Session, user: User) -> str:
    raw_token = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.auth_refresh_token_ttl_days
    )
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=expires_at,
        )
    )
    return raw_token


def _as_aware(value: datetime) -> datetime:
    # SQLite round-trips naive datetimes; treat those as UTC for comparison.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def consume_refresh_token(db: Session, raw_token: str) -> User:
    """Validate, revoke, and return the owner of a refresh token.

    Rotation: the presented token is revoked here; the caller issues a new one.
    A token that is expired, already revoked, or unknown is rejected.
    """
    token_hash = hash_refresh_token(raw_token)
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if (
        record is None
        or record.revoked_at is not None
        or _as_aware(record.expires_at) <= now
    ):
        raise _authentication_error("Refresh token is invalid or expired")
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise _authentication_error("Account is no longer active")
    record.revoked_at = now
    return user


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .one_or_none()
    )
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)


def revoke_all_refresh_tokens(db: Session, user_id: uuid.UUID) -> None:
    now = datetime.now(timezone.utc)
    (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .update({RefreshToken.revoked_at: now}, synchronize_session=False)
    )


# --- Authentication and authorization dependencies --------------------------


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    normalized = email.strip().lower()
    user = (
        db.query(User).filter(User.email == normalized).one_or_none()
    )
    if user is None:
        # Hash a throwaway value so a missing account and a wrong password take
        # roughly the same time, limiting user-enumeration by timing.
        verify_password(password, bcrypt.hashpw(b"x", bcrypt.gensalt()).decode())
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


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
    db: Annotated[Session, Depends(get_db)],
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
                role="teacher",
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
    if not isinstance(role, str) or role not in AUTHORIZED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A teacher or admin role is required",
        )
    # The admin is a fixed identity with no database row. Accept its token
    # directly; only a matching signed access token can carry this subject.
    if subject == ADMIN_SUBJECT and role == "admin":
        if not settings.admin_password:
            raise _authentication_error("Admin access is not configured")
        return AuthUser(subject=ADMIN_SUBJECT, role="admin", claims=claims)
    # Confirm the account still exists and is active; a revoked account must not
    # keep working until its short-lived access token happens to expire.
    try:
        user = db.get(User, uuid.UUID(subject))
    except (ValueError, TypeError) as exc:
        raise _authentication_error("Authentication token subject is invalid") from exc
    if user is None or not user.is_active:
        raise _authentication_error("Account is no longer active")
    return AuthUser(subject=subject, role=user.role, claims=claims)


def require_admin(user: AuthUser) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return user


AuthorizedUser = Annotated[AuthUser, Depends(get_current_user)]


def get_current_admin(user: AuthorizedUser) -> AuthUser:
    return require_admin(user)


AdminUser = Annotated[AuthUser, Depends(get_current_admin)]
