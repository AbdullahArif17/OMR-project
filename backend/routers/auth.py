from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import (
    ADMIN_SUBJECT,
    AdminUser,
    AuthorizedUser,
    authenticate_user,
    consume_refresh_token,
    create_access_token,
    create_admin_access_token,
    create_admin_refresh_token,
    hash_password,
    is_admin_refresh_token,
    issue_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    verify_admin_password,
)
from database import get_db
from errors import ApplicationError
from models import User
from schemas import (
    APIResponse,
    AdminLoginRequest,
    CreateUserRequest,
    LoginRequest,
    RefreshRequest,
    TokenData,
    UpdateUserRequest,
    UserRead,
)


router = APIRouter(prefix="/auth", tags=["auth"])
DatabaseSession = Annotated[Session, Depends(get_db)]

# The admin is not a database account. It is represented in API responses by a
# fixed, synthetic user record so the frontend can render it uniformly.
_ADMIN_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _admin_account_view(email: str) -> dict[str, object]:
    from datetime import datetime, timezone

    return {
        "id": _ADMIN_UUID,
        "email": email,
        "name": "Administrator",
        "role": "admin",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }


def _token_payload(db: Session, user: User) -> dict[str, object]:
    access_token, expires_in = create_access_token(user)
    refresh_token = issue_refresh_token(db, user)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user,
    }


def _admin_token_payload() -> dict[str, object]:
    access_token, expires_in = create_admin_access_token()
    return {
        "access_token": access_token,
        "refresh_token": create_admin_refresh_token(),
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": _admin_account_view("admin"),
    }


@router.post("/login", response_model=APIResponse[TokenData])
def login(payload: LoginRequest, db: DatabaseSession) -> dict[str, object]:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise ApplicationError(
            "Incorrect email or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    data = _token_payload(db, user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"success": True, "data": data, "message": "Signed in"}


@router.post("/admin/login", response_model=APIResponse[TokenData])
def admin_login(payload: AdminLoginRequest) -> dict[str, object]:
    # The admin console signs in with only the shared ADMIN_PASSWORD.
    if not verify_admin_password(payload.password):
        raise ApplicationError(
            "Incorrect admin password",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "success": True,
        "data": _admin_token_payload(),
        "message": "Signed in",
    }


@router.post("/refresh", response_model=APIResponse[TokenData])
def refresh(payload: RefreshRequest, db: DatabaseSession) -> dict[str, object]:
    # The admin's refresh token is a stateless signed JWT; teacher tokens are
    # opaque and rotated in the database.
    if is_admin_refresh_token(payload.refresh_token):
        return {
            "success": True,
            "data": _admin_token_payload(),
            "message": "Session refreshed",
        }
    # Rotation: the presented token is revoked inside consume_refresh_token and
    # a fresh pair is issued in the same transaction.
    user = consume_refresh_token(db, payload.refresh_token)
    data = _token_payload(db, user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"success": True, "data": data, "message": "Session refreshed"}


@router.post("/logout", response_model=APIResponse[dict])
def logout(payload: RefreshRequest, db: DatabaseSession) -> dict[str, object]:
    # Admin refresh tokens are stateless, so there is nothing to revoke here;
    # the client simply discards them.
    if not is_admin_refresh_token(payload.refresh_token):
        revoke_refresh_token(db, payload.refresh_token)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"success": True, "data": {}, "message": "Signed out"}


@router.get("/me", response_model=APIResponse[UserRead])
def read_me(db: DatabaseSession, current: AuthorizedUser) -> dict[str, object]:
    if current.subject == ADMIN_SUBJECT:
        return {
            "success": True,
            "data": _admin_account_view("admin"),
            "message": "Account retrieved",
        }
    user = db.get(User, uuid.UUID(current.subject))
    if user is None:
        raise ApplicationError(
            "Account not found", status_code=status.HTTP_404_NOT_FOUND
        )
    return {"success": True, "data": user, "message": "Account retrieved"}


@router.get("/users", response_model=APIResponse[list[UserRead]])
def list_users(db: DatabaseSession, _: AdminUser) -> dict[str, object]:
    # The admin manages teacher accounts only; the sole admin is not listed.
    users = (
        db.query(User)
        .filter(User.role == "teacher")
        .order_by(User.created_at.desc())
        .all()
    )
    return {"success": True, "data": users, "message": "Accounts retrieved"}


@router.post(
    "/users",
    response_model=APIResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: CreateUserRequest,
    db: DatabaseSession,
    _: AdminUser,
) -> dict[str, object]:
    # role is pinned to "teacher" by the schema; the single admin is never
    # created through the API.
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role="teacher",
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise ApplicationError(
            "An account with that email already exists",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    except Exception:
        db.rollback()
        raise
    return {"success": True, "data": user, "message": "Account created"}


@router.patch("/users/{user_id}", response_model=APIResponse[UserRead])
def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    db: DatabaseSession,
    current: AdminUser,
) -> dict[str, object]:
    user = db.get(User, user_id)
    if user is None:
        raise ApplicationError(
            "Account not found", status_code=status.HTTP_404_NOT_FOUND
        )
    # The admin can only manage teacher accounts, never itself or another admin.
    if user.role != "teacher" or str(user.id) == current.subject:
        raise ApplicationError(
            "Only teacher accounts can be managed",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    user.is_active = payload.is_active
    if not payload.is_active:
        # A deactivated teacher must lose any live session immediately.
        revoke_all_refresh_tokens(db, user.id)
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise
    return {"success": True, "data": user, "message": "Account updated"}
