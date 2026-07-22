from __future__ import annotations

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, status

from auth import (
    ADMIN_SUBJECT,
    AuthorizedUser,
    create_admin_access_token,
    verify_admin_password,
)
from errors import ApplicationError
from schemas import (
    APIResponse,
    AdminLoginRequest,
    TokenData,
    AdminUserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_ADMIN_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

def _admin_account_view() -> AdminUserRead:
    return AdminUserRead(
        id=_ADMIN_UUID,
        created_at=datetime.now(timezone.utc),
    )

def _admin_token_payload() -> TokenData:
    access_token, expires_in = create_admin_access_token()
    return TokenData(
        access_token=access_token,
        expires_in=expires_in,
        user=_admin_account_view(),
    )

@router.post("/admin/login", response_model=APIResponse[TokenData])
def admin_login(payload: AdminLoginRequest) -> dict[str, object]:
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

@router.get("/me", response_model=APIResponse[AdminUserRead])
def read_me(current: AuthorizedUser) -> dict[str, object]:
    if current.subject == ADMIN_SUBJECT:
        return {
            "success": True,
            "data": _admin_account_view(),
            "message": "Account retrieved",
        }
    raise ApplicationError(
        "Account not found", status_code=status.HTTP_404_NOT_FOUND
    )
