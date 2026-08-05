# Markwise — Project Context

_Last updated: 2026-08-05_

---

## What the project is

Markwise is a full-stack web app for grading paper-based multiple-choice exams. Teachers upload bubble sheets (images, ZIP, or PDF), an OpenCV engine detects filled bubbles, grades them against a stored answer key, and exports results as CSV.

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL |
| CV engine | OpenCV (headless), NumPy, Pillow, pdf2image |
| Auth | PyJWT HS256 — single admin account, no password required |
| Frontend | Next.js 15 (App Router), React 19, TypeScript 5, Tailwind CSS 3 |
| HTTP client | Axios |
| Infra | Docker, docker-compose, Neon PostgreSQL (production) |

---

## Architecture

```
backend/
  main.py              FastAPI app, middleware, lifespan
  config.py            Typed Settings dataclass, validated at startup
  auth.py              HS256 JWT — no password, just a JWT secret
  models.py            Exam, AnswerKey, Student, Result, ScanBatch
  schemas.py           Pydantic v2 request/response models
  routers/             auth, exams, answer_keys, scanner, results, sheets
  services/
    omr_engine.py      Pure CV pipeline (no DB coupling)
    file_processing.py Upload storage, ZIP/PDF expansion, safety validation
    data_access.py     DB query helpers
    storage_maintenance.py  Startup cleanup of orphaned files
  alembic/             Versioned migrations

frontend/
  app/
    (workspace)/       Authenticated route group
      dashboard/       Exam list
      exams/           Exam detail + answer key setup
      results/         Results analytics
      sheets/          Scan workspace
    admin/             Login page (no password — one-click sign-in)
  components/          11 shared components, no external UI lib
  lib/                 api.ts, types.ts, upload-policy.ts, utils.ts
```

---

## Auth model

- Single admin account. No teacher accounts, no per-exam ownership.
- Login hits `POST /auth/login` — **no password required**, just issues a JWT.
- JWT is signed with `AUTH_JWT_SECRET` (env var). Required in production.
- `AUTH_REQUIRED=true` (default) enforces Bearer token on all routes.
- Development bypass: if `AUTH_JWT_SECRET` is unset, requests without a token get a local-dev admin identity automatically.

---

## Key decisions & changes made

| Date | Change |
|---|---|
| 2026-08-05 | Removed `ADMIN_PASSWORD` requirement entirely. Login now issues a JWT without checking a password. Removed `verify_admin_password`, `AdminLoginRequest`, and `admin_password` from `config.py`, `auth.py`, `schemas.py`, `routers/auth.py`. Frontend login page (`app/admin/page.tsx`) and `auth-provider.tsx` updated to match — `signIn()` takes no arguments. API endpoint changed from `POST /auth/admin/login` to `POST /auth/login`. |

---

## Known issues / deferred work

- **CORS**: `allow_origin_regex=".*"` with `allow_credentials=True` in `main.py` echoes any origin — defeats the CORS allowlist. Should be removed.
- **Root clutter**: `debug_*.py`, `test_*.py`, sample images at project root — not gitignored, should be moved or deleted.
- **Idempotency fingerprint** uses filenames + declared sizes, not file content. Same-named files with different content won't be detected as a mismatch.
- **Stale docs**: `omr-system-build.md` references Supabase JWT; implementation uses self-signed HS256.
- **No teacher accounts**: README describes per-teacher access control that doesn't exist. Docs need updating or the feature needs implementing.

---

## Environment variables (backend)

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Pooled Neon connection string |
| `DATABASE_URL_DIRECT` | No | Direct URL for migrations |
| `AUTH_JWT_SECRET` | Production | ≥32 chars; omit for local dev bypass |
| `AUTH_REQUIRED` | No | Default `true` |
| `CORS_ORIGINS` | No | Default `http://localhost:3000` |
| `TRUSTED_HOSTS` | No | Default `localhost,127.0.0.1,testserver` |
| `ENVIRONMENT` | No | `development` (default) or `production` |

`ADMIN_PASSWORD` — **removed, no longer used.**
