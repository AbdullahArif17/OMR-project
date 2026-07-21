from __future__ import annotations

import pytest

import config


def _set_valid_production_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://role:password@ep-project-pooler.example.neon.tech/neondb",
    )
    monkeypatch.setenv(
        "DATABASE_URL_DIRECT",
        "postgresql://role:password@ep-project.example.neon.tech/neondb",
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv(
        "AUTH_JWT_SECRET", "a-production-signing-secret-32-chars-min"
    )
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-console-password")
    monkeypatch.setenv("CORS_ORIGINS", "https://markwise.example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "api.markwise.example.com")


def test_production_settings_accept_neon_and_exact_https_origins(monkeypatch) -> None:
    _set_valid_production_environment(monkeypatch)
    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
    finally:
        config.get_settings.cache_clear()

    assert settings.database_url.startswith("postgresql+psycopg2://")
    assert settings.database_url_direct.startswith("postgresql+psycopg2://")
    assert settings.cors_origins == ("https://markwise.example.com",)
    assert settings.trusted_hosts == ("api.markwise.example.com",)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AUTH_REQUIRED", "false", "AUTH_REQUIRED must be true"),
        ("CORS_ORIGINS", "http://markwise.example.com", "must use HTTPS"),
        ("TRUSTED_HOSTS", "*", "cannot contain a wildcard"),
        ("AUTH_JWT_SECRET", "", "requires AUTH_JWT_SECRET"),
        ("AUTH_JWT_SECRET", "too-short", "at least 32 characters"),
        ("ADMIN_PASSWORD", "", "requires ADMIN_PASSWORD"),
        ("ADMIN_PASSWORD", "short", "at least 12 characters"),
        ("DATABASE_URL_DIRECT", "sqlite:///wrong.db", "must use PostgreSQL"),
    ],
)
def test_production_settings_reject_insecure_configuration(
    monkeypatch, name: str, value: str, message: str
) -> None:
    _set_valid_production_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match=message):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()


def test_upload_limits_must_be_internally_consistent(monkeypatch) -> None:
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "20")
    monkeypatch.setenv("MAX_BATCH_SIZE_MB", "10")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="MAX_BATCH_SIZE_MB"):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()
