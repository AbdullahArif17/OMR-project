from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Expected a boolean value, received {value!r}")


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _validated_auth_url(name: str, value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not contain credentials, a query, or a fragment")
    return normalized


def _supabase_auth_urls() -> tuple[str | None, str | None, str | None]:
    raw_base_url = os.getenv("SUPABASE_URL", "").strip()
    raw_issuer = os.getenv("SUPABASE_JWT_ISSUER", "").strip()
    raw_jwks_url = os.getenv("SUPABASE_JWKS_URL", "").strip()

    base_url = (
        _validated_auth_url("SUPABASE_URL", raw_base_url) if raw_base_url else None
    )
    issuer = (
        _validated_auth_url("SUPABASE_JWT_ISSUER", raw_issuer)
        if raw_issuer
        else None
    )
    jwks_url = (
        _validated_auth_url("SUPABASE_JWKS_URL", raw_jwks_url)
        if raw_jwks_url
        else None
    )

    if issuer is None and base_url is not None:
        issuer = (
            base_url
            if base_url.endswith("/auth/v1")
            else f"{base_url}/auth/v1"
        )
    if issuer is None and jwks_url is not None:
        jwks_suffix = "/.well-known/jwks.json"
        if jwks_url.endswith(jwks_suffix):
            issuer = jwks_url[: -len(jwks_suffix)]
    if jwks_url is None and issuer is not None:
        jwks_url = f"{issuer}/.well-known/jwks.json"
    return base_url, issuer, jwks_url


def _normalize_database_url(configured: str) -> str:
    if configured.startswith("postgres://"):
        return configured.replace("postgres://", "postgresql+psycopg2://", 1)
    if configured.startswith("postgresql://"):
        return configured.replace("postgresql://", "postgresql+psycopg2://", 1)
    return configured


def _database_urls() -> tuple[str, str]:
    configured = os.getenv("DATABASE_URL", "").strip()
    if not configured:
        raise RuntimeError(
            "DATABASE_URL is required. Copy the pooled connection string from "
            "your Neon project into backend/.env."
        )
    direct = os.getenv("DATABASE_URL_DIRECT", "").strip() or configured
    return _normalize_database_url(configured), _normalize_database_url(direct)


def _upload_dir() -> Path:
    configured = Path(os.getenv("UPLOAD_DIR", "uploads")).expanduser()
    if not configured.is_absolute():
        configured = BASE_DIR / configured
    return configured.resolve()


def _auth_urls_are_secure(*urls: str | None) -> bool:
    configured_urls = [url for url in urls if url]
    return bool(configured_urls) and all(
        url.startswith("https://") for url in configured_urls
    )


def _cors_origins() -> tuple[str, ...]:
    origins: list[str] = []
    for raw_origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","):
        origin = raw_origin.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "CORS_ORIGINS entries must be HTTP(S) origins without paths, "
                "credentials, queries, or fragments"
            )
        origins.append(origin)
    if not origins:
        raise ValueError("CORS_ORIGINS must contain at least one origin")
    return tuple(origins)


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    database_url_direct: str
    upload_dir: Path
    max_file_size_mb: int
    max_files_per_request: int
    max_batch_size_mb: int
    max_archive_uncompressed_mb: int
    max_archive_entries: int
    max_archive_compression_ratio: float
    max_image_pixels: int
    max_pdf_pages: int
    pdf_info_timeout_seconds: int
    pdf_conversion_timeout_seconds: int
    pdf_dpi: int
    database_pool_size: int
    database_max_overflow: int
    storage_cleanup_grace_hours: int
    idempotency_retention_hours: int
    auth_required: bool
    supabase_url: str | None
    supabase_jwks_url: str | None
    supabase_jwks_cache_ttl_seconds: int
    supabase_jwks_timeout_seconds: float
    supabase_jwt_secret: str | None
    supabase_jwt_algorithm: str
    supabase_jwt_audience: str | None
    supabase_jwt_issuer: str | None
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    environment: str

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_archive_uncompressed_bytes(self) -> int:
        return self.max_archive_uncompressed_mb * 1024 * 1024

    @property
    def max_batch_size_bytes(self) -> int:
        return self.max_batch_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url, database_url_direct = _database_urls()
    supabase_url, supabase_jwt_issuer, supabase_jwks_url = _supabase_auth_urls()
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    secret = os.getenv("SUPABASE_JWT_SECRET", "").strip() or None
    auth_setting = os.getenv("AUTH_REQUIRED")
    auth_required = _parse_bool(auth_setting, default=True)
    origins = _cors_origins()
    trusted_hosts = tuple(
        host.strip()
        for host in os.getenv(
            "TRUSTED_HOSTS", "localhost,127.0.0.1,testserver"
        ).split(",")
        if host.strip()
    )
    if not trusted_hosts:
        raise ValueError("TRUSTED_HOSTS must contain at least one host")
    if "*" in origins:
        raise ValueError("CORS_ORIGINS cannot contain a wildcard when credentials are enabled")
    if environment == "production":
        if not database_url.startswith("postgresql+psycopg2://"):
            raise ValueError("Production DATABASE_URL must use PostgreSQL")
        explicit_direct_url = os.getenv("DATABASE_URL_DIRECT", "").strip()
        if explicit_direct_url and not database_url_direct.startswith(
            "postgresql+psycopg2://"
        ):
            raise ValueError("Production DATABASE_URL_DIRECT must use PostgreSQL")
        if not auth_required:
            raise ValueError("AUTH_REQUIRED must be true in production")
        if not (supabase_jwks_url or secret):
            raise ValueError("Production authentication requires SUPABASE_URL, SUPABASE_JWKS_URL, or a legacy JWT secret")
        insecure_origins = [origin for origin in origins if not origin.startswith("https://")]
        if insecure_origins:
            raise ValueError("Production CORS_ORIGINS must use HTTPS")
        if any("*" in host for host in trusted_hosts):
            raise ValueError("Production TRUSTED_HOSTS cannot contain a wildcard")
        if not _auth_urls_are_secure(supabase_url, supabase_jwks_url):
            raise ValueError("Production Supabase authentication URLs must use HTTPS")
    legacy_algorithm = os.getenv("SUPABASE_JWT_ALGORITHM", "HS256").strip().upper()
    if legacy_algorithm != "HS256":
        raise ValueError("SUPABASE_JWT_ALGORITHM only supports the legacy HS256 fallback")
    jwks_cache_ttl = _positive_int("SUPABASE_JWKS_CACHE_TTL_SECONDS", 600)
    if jwks_cache_ttl > 600:
        raise ValueError("SUPABASE_JWKS_CACHE_TTL_SECONDS cannot exceed 600")
    jwks_timeout = _positive_float("SUPABASE_JWKS_TIMEOUT_SECONDS", 5.0)
    if jwks_timeout > 30:
        raise ValueError("SUPABASE_JWKS_TIMEOUT_SECONDS cannot exceed 30")
    max_file_size_mb = _positive_int("MAX_FILE_SIZE_MB", 10)
    max_files_per_request = _positive_int("MAX_FILES_PER_REQUEST", 50)
    max_batch_size_mb = _positive_int("MAX_BATCH_SIZE_MB", 100)
    if max_batch_size_mb < max_file_size_mb:
        raise ValueError("MAX_BATCH_SIZE_MB cannot be smaller than MAX_FILE_SIZE_MB")
    max_pdf_pages = _positive_int("MAX_PDF_PAGES", 50)
    if max_pdf_pages > max_files_per_request:
        raise ValueError("MAX_PDF_PAGES cannot exceed MAX_FILES_PER_REQUEST")
    return Settings(
        database_url=database_url,
        database_url_direct=database_url_direct,
        upload_dir=_upload_dir(),
        max_file_size_mb=max_file_size_mb,
        max_files_per_request=max_files_per_request,
        max_batch_size_mb=max_batch_size_mb,
        max_archive_uncompressed_mb=_positive_int(
            "MAX_ARCHIVE_UNCOMPRESSED_MB", 100
        ),
        max_archive_entries=_positive_int("MAX_ARCHIVE_ENTRIES", 100),
        max_archive_compression_ratio=_positive_float(
            "MAX_ARCHIVE_COMPRESSION_RATIO", 100.0
        ),
        max_image_pixels=_positive_int("MAX_IMAGE_PIXELS", 50_000_000),
        max_pdf_pages=max_pdf_pages,
        pdf_info_timeout_seconds=_positive_int("PDF_INFO_TIMEOUT_SECONDS", 15),
        pdf_conversion_timeout_seconds=_positive_int(
            "PDF_CONVERSION_TIMEOUT_SECONDS", 120
        ),
        pdf_dpi=_positive_int("PDF_DPI", 200),
        database_pool_size=_positive_int("DATABASE_POOL_SIZE", 5),
        database_max_overflow=_nonnegative_int("DATABASE_MAX_OVERFLOW", 5),
        storage_cleanup_grace_hours=_positive_int(
            "STORAGE_CLEANUP_GRACE_HOURS", 24
        ),
        idempotency_retention_hours=_positive_int(
            "IDEMPOTENCY_RETENTION_HOURS", 168
        ),
        auth_required=auth_required,
        supabase_url=supabase_url,
        supabase_jwks_url=supabase_jwks_url,
        supabase_jwks_cache_ttl_seconds=jwks_cache_ttl,
        supabase_jwks_timeout_seconds=jwks_timeout,
        supabase_jwt_secret=secret,
        supabase_jwt_algorithm=legacy_algorithm,
        supabase_jwt_audience=os.getenv("SUPABASE_JWT_AUDIENCE", "").strip()
        or None,
        supabase_jwt_issuer=supabase_jwt_issuer,
        cors_origins=origins,
        trusted_hosts=trusted_hosts,
        environment=environment,
    )


settings = get_settings()
