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
    if os.getenv("VERCEL") == "1":
        return Path("/tmp/uploads").resolve()
    configured = Path(os.getenv("UPLOAD_DIR", "uploads")).expanduser()
    if not configured.is_absolute():
        configured = BASE_DIR / configured
    return configured.resolve()


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
    auth_jwt_secret: str | None
    auth_jwt_algorithm: str
    auth_access_token_ttl_minutes: int
    auth_refresh_token_ttl_days: int
    admin_password: str | None
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
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    secret = os.getenv("AUTH_JWT_SECRET", "").strip() or None
    auth_setting = os.getenv("AUTH_REQUIRED")
    auth_required = _parse_bool(auth_setting, default=True)
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip() or None
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
        if not secret:
            raise ValueError(
                "Production authentication requires AUTH_JWT_SECRET"
            )
        if len(secret) < 32:
            raise ValueError(
                "Production AUTH_JWT_SECRET must be at least 32 characters"
            )
        if not admin_password:
            raise ValueError(
                "Production requires ADMIN_PASSWORD to enable the admin console"
            )
        insecure_origins = [origin for origin in origins if not origin.startswith("https://")]
        if insecure_origins:
            raise ValueError("Production CORS_ORIGINS must use HTTPS")
        if any("*" in host for host in trusted_hosts):
            raise ValueError("Production TRUSTED_HOSTS cannot contain a wildcard")
    auth_algorithm = os.getenv("AUTH_JWT_ALGORITHM", "HS256").strip().upper()
    if auth_algorithm != "HS256":
        raise ValueError("AUTH_JWT_ALGORITHM only supports HS256")
    access_ttl_minutes = _positive_int("AUTH_ACCESS_TOKEN_TTL_MINUTES", 30)
    if access_ttl_minutes > 24 * 60:
        raise ValueError("AUTH_ACCESS_TOKEN_TTL_MINUTES cannot exceed 1440")
    refresh_ttl_days = _positive_int("AUTH_REFRESH_TOKEN_TTL_DAYS", 30)
    if refresh_ttl_days > 365:
        raise ValueError("AUTH_REFRESH_TOKEN_TTL_DAYS cannot exceed 365")
    if admin_password is not None and len(admin_password) < 12:
        raise ValueError("ADMIN_PASSWORD must be at least 12 characters")
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
        auth_jwt_secret=secret,
        auth_jwt_algorithm=auth_algorithm,
        auth_access_token_ttl_minutes=access_ttl_minutes,
        auth_refresh_token_ttl_days=refresh_ttl_days,
        admin_password=admin_password,
        cors_origins=origins,
        trusted_hosts=trusted_hosts,
        environment=environment,
    )


settings = get_settings()
