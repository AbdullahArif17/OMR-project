# Markwise OMR

Markwise is a full-stack optical mark recognition system for teachers and exam administrators. It creates exams and answer keys, reads filled bubble sheets with OpenCV, grades batches of student submissions, stores detailed results, and exports classroom-ready CSV reports.

## What is included

- Next.js App Router frontend with TypeScript and Tailwind CSS
- FastAPI API with SQLAlchemy and PostgreSQL/Neon support
- Supabase JWT authentication with `teacher` and `admin` roles
- OpenCV bubble detection and per-question grading
- Perspective, skew, lighting, scale, and camera-noise normalization with safe low-confidence rejection
- Manual, scanned-master, and CSV answer-key entry
- JPG, JPEG, PNG, PDF, ZIP, and multi-file student submissions
- Signature verification, document/archive resource limits, atomic batches, and retry-safe uploads
- Result analytics, grade bands, individual breakdowns, and CSV export
- Automated backend tests and frontend type/lint/build scripts

## Project layout

```text
.
|-- frontend/                 Next.js application
|-- backend/                  FastAPI application
|   |-- alembic/              Versioned database schema
|   |-- routers/              HTTP endpoints
|   |-- services/             OMR and upload processing
|   |-- tests/                API and image-processing tests
|   `-- uploads/              Local generated upload storage
|-- DEPLOYMENT.md             Neon and container production runbook
|-- omr-system-build.md       Implementation and acceptance plan
`-- README.md
```

## Prerequisites

- Node.js 20 or newer
- Python 3.11 or newer
- A Neon PostgreSQL project
- A Supabase project when authentication is enabled
- Poppler installed and available on `PATH` for PDF uploads (`pdftoppm` must be discoverable)

PNG and JPEG processing does not require Poppler.

## 1. Start the backend

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and create the environment file:

```bash
pip install -r requirements.txt
cp .env.example .env
```

On Windows, copy `.env.example` to `.env` in File Explorer or run:

```powershell
Copy-Item .env.example .env
```

In the Neon Console, open **Connect** and copy both the pooled and direct connection strings. The pooled URL is used by FastAPI; the direct URL is used for schema creation:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@EP-ID-pooler.REGION.aws.neon.tech/neondb?sslmode=require&channel_binding=require
DATABASE_URL_DIRECT=postgresql://USER:PASSWORD@EP-ID.REGION.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

Apply the versioned schema with the direct Neon connection, then start FastAPI.
Runtime requests use the pooled connection:

```bash
alembic -c alembic.ini upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The interactive API reference is available at `http://localhost:8000/docs` outside production. Liveness and database readiness are exposed at `/health/live` and `/health/ready`.

## 2. Configure Supabase authentication

Create users in Supabase Auth and assign each permitted user a role of `teacher` or `admin` in trusted application metadata (`app_metadata.role`, or `app_metadata.roles`). User metadata is profile data and is deliberately never trusted for authorization. Copy the project URL and publishable key into `frontend/.env.local`; configure the same project URL in `backend/.env` so FastAPI can verify access tokens through Supabase's public JWKS endpoint. The legacy shared JWT secret remains supported for older projects. Teachers can access only exams they created; admins can access all exams.

For a deliberately unauthenticated local demo, set the backend's documented auth flag to disabled and enable the frontend demo mode. Never use demo mode in a public deployment.

## 3. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

On Windows:

```powershell
Copy-Item .env.example .env.local
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:3000`.

## Answer-key CSV format

The CSV parser accepts a header followed by one row per question:

```csv
question,answer
1,A
2,C
3,B
```

Answers must fall within the exam's configured option range. All questions must be present exactly once before a key is saved.

## Bubble-sheet scanning guidance

For reliable detection, use evenly spaced circular bubbles arranged in one horizontal row per question. Keep the complete grid visible and reasonably flat, avoid glare and blur, and make dark, complete marks. The engine normalizes scale and illumination, corrects a reliable page perspective, aligns moderate grid skew, and calibrates fill confidence from the current sheet. It rejects incomplete, blank, ambiguous, excessively distorted, or low-contrast sheets instead of guessing.

The same layout rules apply to a scanned master answer key and student sheets. PDF pages are treated as separate sheets. A ZIP archive may contain supported images and PDFs; nested archives and unsafe paths are rejected.

## API overview

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/exams` | Create an exam |
| `GET` | `/exams` | List exams |
| `GET` | `/exams/{id}` | Fetch an exam |
| `DELETE` | `/exams/{id}` | Delete an exam |
| `POST` | `/exams/{id}/answer-key/manual` | Save a manual key |
| `POST` | `/exams/{id}/answer-key/scan` | Detect a key from a master sheet |
| `POST` | `/exams/{id}/answer-key/csv` | Import a key from CSV |
| `GET` | `/exams/{id}/answer-key` | Fetch the stored key |
| `POST` | `/exams/{id}/scan` | Grade one or more student sheets |
| `GET` | `/exams/{id}/results` | List results and analytics |
| `GET` | `/exams/{id}/results/export` | Download results as CSV |
| `GET` | `/results/{id}` | Fetch a full result breakdown |

JSON endpoints use the envelope `{ "success": boolean, "data": any, "message": string }`. File exports return a streamed attachment.

Student scan requests may include an `Idempotency-Key` header. Reusing the same key after a connection failure returns the original committed response without creating duplicate results; use a new key when files or metadata change.

## Verification

Run backend checks from `backend/`:

```bash
pytest
alembic -c alembic.ini check
```

Run frontend checks from `frontend/`:

```bash
npm run lint
npm run typecheck
npm run build
```

## Production notes

Use the supplied non-root Dockerfiles and follow [DEPLOYMENT.md](./DEPLOYMENT.md) for Neon migrations, environment validation, persistent uploads, reverse-proxy limits, health checks, and rollout order. Public deployment must use `ENVIRONMENT=production`, Supabase authentication, exact HTTPS CORS origins, and exact trusted hosts.
