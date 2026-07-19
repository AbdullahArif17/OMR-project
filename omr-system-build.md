# OMR System Build Plan

## Objective

Build a production-shaped, locally runnable web OMR system in this existing workspace with a Next.js/TypeScript/Tailwind frontend, a FastAPI/SQLAlchemy/PostgreSQL backend, Supabase JWT role authorization, local upload storage, and an OpenCV grading engine.

## Architecture decisions

- Keep the requested `frontend/` and `backend/` split at the workspace root.
- Use SQLAlchemy 2.x sessions with Neon PostgreSQL for normal runtime; tests may explicitly inject an in-memory SQLite URL.
- Keep API responses consistent as `{ success, data, message }`, except streaming export responses where the file itself is the response body.
- Verify Supabase JWTs and enforce `teacher`/`admin` roles when auth is configured; support an explicit local development bypass rather than silently accepting invalid tokens.
- Normalize scanned uploads to images, supporting JPG/JPEG/PNG, PDF pages, ZIP archives, and multiple files while enforcing extension and size limits.
- Store scan files beneath `backend/uploads/` using generated names and clean temporary processing artifacts after use.
- Use a responsive, accessible visual system built entirely with Tailwind utilities and local CSS; no UI component library.

## Work breakdown

1. Foundation
   - Add root ignore rules, environment examples, and project documentation.
   - Configure frontend and backend package manifests.
2. Database and API
   - Implement configuration, database engine/session lifecycle, models, and schemas.
   - Implement exam CRUD and all answer-key methods.
   - Implement student-sheet scanning, grading, persistence, result detail, analytics, and CSV export.
   - Implement Supabase JWT verification and teacher/admin authorization.
3. OMR processing
   - Preprocess images with grayscale, blur, and Otsu inverse thresholding.
   - Detect and group circular answer bubbles robustly by contour geometry and row proximity.
   - Detect unanswered and ambiguous rows and produce actionable validation errors.
   - Convert PDF pages and expand ZIP/multi-file inputs safely.
4. Frontend
   - Build sign-in/landing, authenticated app shell, dashboard, exam creation and answer-key setup, scan workspace, and results analytics.
   - Connect every workflow to FastAPI through a typed Axios client with Supabase bearer tokens.
   - Add drag/drop, progress/loading states, validation, empty states, error recovery, and responsive layouts.
5. Verification
   - Add backend tests for grading, contour-based OMR recognition, and API workflows.
   - Run Python tests/compilation and frontend lint/type/build checks.
   - Review security-sensitive upload, archive, auth, and database behavior.
   - Resolve integration mismatches and document exact setup/run commands.

## Acceptance criteria

- All routes in the supplied specification are implemented and database-backed.
- Manual, scanned-sheet, and CSV answer keys work.
- Single, multi-file, ZIP, and PDF student uploads are handled.
- OMR detection performs real OpenCV contour and fill analysis.
- Saved scan results include per-question breakdown and student metadata.
- Dashboard, exam detail, and results pages use live API data.
- Results page includes summary statistics, grade coloring, detail access, and CSV export.
- Supabase authentication and teacher/admin role checks are wired end to end.
- No TODO/placeholder implementation comments remain.
- README and example environment files are sufficient to run the system.
