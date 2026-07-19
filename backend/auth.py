from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWKError, JWTError

from config import settings


bearer_scheme = HTTPBearer(auto_error=False)
ASYMMETRIC_ALGORITHMS = {"ES256": "EC", "RS256": "RSA"}
MAX_JWKS_RESPONSE_BYTES = 1024 * 1024
MAX_JWKS_KEYS = 50
UNKNOWN_KID_REFRESH_INTERVAL_SECONDS = 30


@dataclass(frozen=True, slots=True)
class AuthUser:
    subject: str
    role: str
    claims: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _JWKSCacheEntry:
    keys: tuple[dict[str, Any], ...]
    fetched_at: float
    expires_at: float


_jwks_cache: dict[str, _JWKSCacheEntry] = {}
_jwks_cache_lock = threading.Lock()


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


def _fetch_jwks(jwks_url: str) -> tuple[dict[str, Any], ...]:
    try:
        with httpx.Client(
            timeout=settings.supabase_jwks_timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = client.get(
                jwks_url,
                headers={"Accept": "application/json"},
            )
    except httpx.RequestError as exc:
        raise _configuration_error(
            "Supabase signing keys are temporarily unavailable"
        ) from exc
    if response.status_code != 200:
        raise _configuration_error(
            "Supabase signing key endpoint returned an unexpected response"
        )
    if len(response.content) > MAX_JWKS_RESPONSE_BYTES:
        raise _configuration_error("Supabase signing key response is too large")
    try:
        payload = response.json()
    except ValueError as exc:
        raise _configuration_error(
            "Supabase signing key endpoint returned invalid JSON"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise _configuration_error("Supabase signing key response is malformed")
    raw_keys = payload["keys"]
    if not raw_keys:
        raise _configuration_error("Supabase signing key response contains no keys")
    if len(raw_keys) > MAX_JWKS_KEYS or not all(
        isinstance(key, dict) for key in raw_keys
    ):
        raise _configuration_error("Supabase signing key response is malformed")
    return tuple(dict(key) for key in raw_keys)


def _get_jwks(jwks_url: str, *, force_refresh: bool = False) -> tuple[dict[str, Any], ...]:
    now = time.monotonic()
    with _jwks_cache_lock:
        cached = _jwks_cache.get(jwks_url)
        if cached is not None and now < cached.expires_at:
            cache_is_too_fresh_to_refresh = (
                now - cached.fetched_at < UNKNOWN_KID_REFRESH_INTERVAL_SECONDS
            )
            if not force_refresh or cache_is_too_fresh_to_refresh:
                return cached.keys

        keys = _fetch_jwks(jwks_url)
        fetched_at = time.monotonic()
        _jwks_cache[jwks_url] = _JWKSCacheEntry(
            keys=keys,
            fetched_at=fetched_at,
            expires_at=fetched_at + settings.supabase_jwks_cache_ttl_seconds,
        )
        return keys


def _clear_jwks_cache() -> None:
    with _jwks_cache_lock:
        _jwks_cache.clear()


def _validate_jwk(key: dict[str, Any], *, kid: str, algorithm: str) -> None:
    expected_key_type = ASYMMETRIC_ALGORITHMS[algorithm]
    if key.get("kid") != kid or key.get("alg") != algorithm:
        raise _configuration_error("Supabase signing key metadata is inconsistent")
    if key.get("kty") != expected_key_type:
        raise _configuration_error("Supabase signing key type is invalid")
    if key.get("use") not in {None, "sig"}:
        raise _configuration_error("Supabase signing key is not a signature key")
    key_operations = key.get("key_ops")
    if key_operations is not None and (
        not isinstance(key_operations, list) or "verify" not in key_operations
    ):
        raise _configuration_error("Supabase signing key cannot verify signatures")
    if algorithm == "ES256":
        if key.get("crv") != "P-256" or not all(
            isinstance(key.get(field), str) and key[field]
            for field in ("x", "y")
        ):
            raise _configuration_error("Supabase ES256 signing key is malformed")
    elif not all(
        isinstance(key.get(field), str) and key[field] for field in ("n", "e")
    ):
        raise _configuration_error("Supabase RS256 signing key is malformed")


def _select_jwk(
    keys: tuple[dict[str, Any], ...], *, kid: str, algorithm: str
) -> dict[str, Any] | None:
    matching = [
        key
        for key in keys
        if key.get("kid") == kid and key.get("alg") == algorithm
    ]
    if not matching:
        return None
    if len(matching) != 1:
        raise _configuration_error("Supabase signing key response contains duplicates")
    selected = matching[0]
    _validate_jwk(selected, kid=kid, algorithm=algorithm)
    return selected


def _asymmetric_verification_key(header: dict[str, Any]) -> dict[str, Any]:
    algorithm = header["alg"]
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid or len(kid) > 255:
        raise _authentication_error("Authentication token is missing a valid key ID")
    if not settings.supabase_jwks_url:
        raise _configuration_error(
            "Asymmetric authentication requires SUPABASE_URL or SUPABASE_JWKS_URL"
        )
    if not settings.supabase_jwt_issuer:
        raise _configuration_error(
            "Asymmetric authentication requires a Supabase JWT issuer"
        )

    keys = _get_jwks(settings.supabase_jwks_url)
    selected = _select_jwk(keys, kid=kid, algorithm=algorithm)
    if selected is None:
        refreshed_keys = _get_jwks(
            settings.supabase_jwks_url,
            force_refresh=True,
        )
        selected = _select_jwk(refreshed_keys, kid=kid, algorithm=algorithm)
    if selected is None:
        raise _authentication_error("Authentication token signing key is not recognized")
    return selected


def _roles_from_claims(claims: dict[str, Any]) -> list[str]:
    candidates: list[Any] = [
        claims.get("user_role"),
        claims.get("roles"),
        claims.get("role"),
    ]
    app_metadata = claims.get("app_metadata")
    if isinstance(app_metadata, dict):
        candidates.insert(0, app_metadata.get("role"))
        candidates.insert(1, app_metadata.get("roles"))

    roles: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str):
            roles.extend(part.strip().lower() for part in candidate.split(","))
        elif isinstance(candidate, (list, tuple, set)):
            roles.extend(str(part).strip().lower() for part in candidate)
    return [role for role in roles if role]


def _authorized_role(roles: list[str]) -> str | None:
    if "admin" in roles:
        return "admin"
    if "teacher" in roles:
        return "teacher"
    return None


def _decode_token(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except (JWTError, ValueError, TypeError) as exc:
        raise _authentication_error() from exc
    if not isinstance(header, dict):
        raise _authentication_error()
    token_type = header.get("typ")
    if token_type is not None and (
        not isinstance(token_type, str) or token_type.upper() != "JWT"
    ):
        raise _authentication_error("Authentication token type is invalid")
    algorithm = header.get("alg")
    if not isinstance(algorithm, str):
        raise _authentication_error("Authentication token algorithm is invalid")

    if algorithm in ASYMMETRIC_ALGORITHMS:
        verification_key: str | dict[str, Any] = _asymmetric_verification_key(header)
        allowed_algorithm = algorithm
    elif algorithm == "HS256":
        if not settings.supabase_jwt_secret:
            raise _configuration_error(
                "Legacy HS256 authentication is not configured"
            )
        verification_key = settings.supabase_jwt_secret
        allowed_algorithm = settings.supabase_jwt_algorithm
    else:
        raise _authentication_error("Authentication token algorithm is not supported")

    has_audience = settings.supabase_jwt_audience is not None
    has_issuer = settings.supabase_jwt_issuer is not None
    options = {
        "verify_aud": has_audience,
        "verify_iss": has_issuer,
        "require_aud": has_audience,
        "require_iss": has_issuer,
        "require_exp": True,
        "require_sub": True,
    }
    try:
        claims = jwt.decode(
            token,
            verification_key,
            algorithms=[allowed_algorithm],
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_jwt_issuer,
            options=options,
        )
    except (JWKError, ValueError, TypeError) as exc:
        if algorithm in ASYMMETRIC_ALGORITHMS:
            raise _configuration_error(
                "Supabase signing key could not be loaded"
            ) from exc
        raise _authentication_error() from exc
    except JWTError as exc:
        raise _authentication_error() from exc
    if not isinstance(claims, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> AuthUser:
    if credentials is None:
        if settings.auth_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer authentication is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthUser(
            subject="local-development",
            role="teacher",
            claims={"auth_bypass": True},
        )

    if not settings.auth_required and not (
        settings.supabase_jwt_secret or settings.supabase_jwks_url
    ):
        return AuthUser(
            subject="local-development",
            role="teacher",
            claims={"auth_bypass": True},
        )

    claims = _decode_token(credentials.credentials)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing a subject",
        )
    roles = _roles_from_claims(claims)
    role = _authorized_role(roles)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A teacher or admin role is required",
        )
    return AuthUser(subject=subject, role=role, claims=claims)


AuthorizedUser = Annotated[AuthUser, Depends(get_current_user)]
