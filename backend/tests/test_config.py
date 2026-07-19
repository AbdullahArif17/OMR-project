from __future__ import annotations

import pytest

import config


def test_supabase_url_derives_issuer_and_jwks_url(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co/")
    monkeypatch.delenv("SUPABASE_JWT_ISSUER", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)

    base_url, issuer, jwks_url = config._supabase_auth_urls()

    assert base_url == "https://project.supabase.co"
    assert issuer == "https://project.supabase.co/auth/v1"
    assert jwks_url == (
        "https://project.supabase.co/auth/v1/.well-known/jwks.json"
    )


def test_explicit_jwks_url_derives_standard_issuer(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_ISSUER", raising=False)
    monkeypatch.setenv(
        "SUPABASE_JWKS_URL",
        "https://auth.example.com/auth/v1/.well-known/jwks.json",
    )

    base_url, issuer, jwks_url = config._supabase_auth_urls()

    assert base_url is None
    assert issuer == "https://auth.example.com/auth/v1"
    assert jwks_url == "https://auth.example.com/auth/v1/.well-known/jwks.json"


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
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
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
        ("SUPABASE_URL", "http://project.supabase.co", "must use HTTPS"),
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
