# Production deployment

This runbook deploys Markwise with a Neon PostgreSQL database, built-in email/password authentication, a FastAPI container, and a separately built Next.js container.

## 1. Configure secrets and public build values

Copy `backend/.env.example` to a secret-managed production environment and set:

- `ENVIRONMENT=production`
- `DATABASE_URL` to the Neon pooled connection (`-pooler` hostname)
- `DATABASE_URL_DIRECT` to the Neon direct connection, available only to the migration job
- `AUTH_REQUIRED=true`
- `AUTH_JWT_SECRET` to a strong random value of at least 32 characters (e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
- `ADMIN_PASSWORD` to a strong password (≥12 chars) to enable the admin console at `/admin`
- `CORS_ORIGINS` to the exact HTTPS frontend origin
- `TRUSTED_HOSTS` to the API hostname without a scheme or path
- `UPLOAD_DIR=/app/uploads`

Keep both Neon URLs and `AUTH_JWT_SECRET` server-side. Rotating the signing secret invalidates every outstanding access token. Size the total database connections as `(pool size + overflow) × API processes or replicas` within the Neon plan limit. Neon recommends pooled connections for concurrent application traffic; use the direct URL for schema migrations.

The values in `frontend/.env.example` prefixed with `NEXT_PUBLIC_` are intentionally browser-visible and are compiled into the frontend image. Never place a Neon URL or `AUTH_JWT_SECRET` there.

## 2. Apply the database schema

Run migrations as a one-off release job before starting the new API version:

```bash
cd backend
alembic -c alembic.ini upgrade head
```

For a database previously initialized by this project's old `python database.py` command, first apply `backend/migrations/001_add_scan_batches.sql` in the Neon SQL Editor, then establish the Alembic baseline once:

```bash
cd backend
alembic -c alembic.ini stamp 20260719_0001
```

Do not stamp a fresh or empty database; use `upgrade head` for it. Back up or branch the Neon database before any production migration.

## 3. Build and run the API

```bash
docker build -t markwise-api:1.0 ./backend
docker run --rm --env-file backend/.env markwise-api:1.0 \
  alembic -c alembic.ini upgrade head
docker run -d --name markwise-api --restart unless-stopped \
  --env-file backend/.env \
  -p 8000:8000 \
  -v markwise-uploads:/app/uploads \
  markwise-api:1.0
```

The API image includes Poppler for PDF rendering, runs as a non-root user, and exposes a readiness health check. The upload volume must be writable by the container user. Use one API replica with this local-volume storage design; replace it with shared object storage before horizontal scaling.

## 4. Build and run the frontend

Public variables are build arguments because Next.js embeds them into browser bundles:

```bash
docker build -t markwise-web:1.0 \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  --build-arg NEXT_PUBLIC_MAX_FILE_SIZE_MB=10 \
  --build-arg NEXT_PUBLIC_MAX_FILES_PER_REQUEST=50 \
  --build-arg NEXT_PUBLIC_MAX_BATCH_SIZE_MB=100 \
  ./frontend

docker run -d --name markwise-web --restart unless-stopped \
  -p 3000:3000 markwise-web:1.0
```

Rebuild the frontend whenever a `NEXT_PUBLIC_*` value changes. Keep its three upload limits aligned with the backend; the backend remains authoritative.

## 5. Configure the edge proxy

Terminate TLS at the proxy or platform edge and configure:

- an allowlisted hostname and HTTPS redirect;
- a request-body limit slightly above `MAX_BATCH_SIZE_MB` for multipart overhead;
- an upload/read timeout long enough for the configured PDF and scan limits;
- per-user or per-IP rate limits on scan and answer-key upload routes;
- forwarded proxy headers only from trusted proxies.

The application enforces file, batch, image-pixel, PDF-page, archive-entry, expansion, compression-ratio, and expanded-sheet limits as a second layer. It also validates file signatures and rejects encrypted or unsafe archives.

## 6. Health, rollout, and retention

- `GET /health/live` verifies that the API process is alive.
- `GET /health/ready` verifies database connectivity and should gate traffic.
- Roll out the API only after the migration job succeeds, then deploy the frontend.
- Monitor 4xx/5xx rates, scan latency, rejected-sheet reasons, Neon connections, container memory, and upload-volume usage.
- Define a retention policy for uploaded student documents and database results. Treat both as sensitive educational records and back them up according to local requirements.
- Retry a disconnected scan with the same `Idempotency-Key`; generate a new key if its files or student metadata change.

The detector is intentionally fail-safe. It handles regular 4- or 5-option bubble grids under moderate perspective, skew, uneven lighting, scale changes, and common JPEG noise, but it rejects heavily cropped, arbitrary-layout, very faint, or highly distorted documents for manual review.
