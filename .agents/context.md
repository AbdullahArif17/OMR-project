# Project Context: MarkWise OMR System

This document is intended for AI agents working on this project. It provides a comprehensive overview of the architecture, stack, constraints, and features implemented so far.

## Architecture & Tech Stack

This project is a monolithic web application split into two main directories: `frontend` and `backend`.

**Frontend (`/frontend`)**
*   **Framework:** Next.js (App Router), React, TypeScript.
*   **Styling:** Tailwind CSS. No external UI component library (components are custom-built in `@/components`).
*   **State/Data Fetching:** Custom React hooks, standard `useState`/`useEffect`.
*   **API Client:** Axios (configured in `frontend/lib/api.ts`).

**Backend (`/backend`)**
*   **Framework:** FastAPI (Python 3.x).
*   **Database:** PostgreSQL (Neon) managed with SQLAlchemy 2.x ORM.
*   **Core Logic (OMR):** OpenCV (`cv2`) and NumPy are used heavily in `services/omr_engine.py` to process scanned images, detect answer bubbles, and grade them against an answer key.
*   **Authentication:** Supabase JWT for standard users (Teachers). There is a hidden master admin login route (`/auth/admin/login`) governed by an `ADMIN_PASSWORD` environment variable.

## Key Constraints & Quirks

*   **Vercel Read-Only Filesystem:** The backend is deployed on Vercel as a Serverless Function. Vercel enforces a strictly read-only filesystem except for the `/tmp` directory. 
    *   *Implementation Detail:* `backend/config.py` checks for the `VERCEL` environment variable. If present, it forcefully overrides the `UPLOAD_DIR` to `/tmp/uploads`. Any agent writing file I/O operations must ensure they adhere to this configuration.
*   **OMR Grid Clustering:** The OMR engine relies on strict physical gaps (X-gap and Y-gap) between the Name, Roll Number, and Answer grids on the printed page to distinguish them. `generate_template.py` and `services/sheet_generator.py` are specifically calibrated to these gaps.
*   **API Envelopes:** All API responses (except file downloads) are wrapped in a standard JSON envelope: `{ "success": true/false, "data": ..., "message": "..." }`.

## Features Implemented

1.  **Core Exam & Answer Key Management:** CRUD operations for Exams and configuring Answer Keys manually, via CSV, or by scanning a master sheet.
2.  **OMR Engine (OpenCV):**
    *   Image preprocessing (grayscale, blur, Otsu thresholding).
    *   Contour detection to find circular bubbles.
    *   K-Means / hierarchical clustering to separate Name, Roll Number, and Question grids.
    *   Calculates pixel intensity inside bubbles to determine filled answers vs empty.
3.  **Authentication:**
    *   Standard Teacher login via Supabase JWT.
    *   Master Admin backdoor (`/admin` on frontend, `/auth/admin/login` on backend).
4.  **Result Editing:**
    *   Admins/Teachers can edit the parsed Student Name, Roll Number, and Class from a scanned result (PATCH `/results/{id}`).
    *   The backend automatically resolves/creates `Student` database records to maintain referential integrity when these edits occur.
5.  **Dynamic OMR Sheet Generation:**
    *   Users can generate printable OMR bubble sheets (PNG format).
    *   Available for specific saved exams (`/exams/{id}/sheet`) where it automatically sizes to the exam's questions/options.
    *   Available for custom generation without an exam (`/sheets/preview` -> `/sheets/generate` on frontend).

## Testing

*   **Frontend:** Standard Next.js `npm run build` and TypeScript compiler checks.
*   **Backend:** `pytest` is used for end-to-end and unit testing (`test_e2e.py`, `test_cors_500.py`, etc.). Tests inject an in-memory SQLite database to avoid touching production PostgreSQL.

## Environment Variables

**Frontend (`.env.local`)**
*   `NEXT_PUBLIC_API_URL`: Points to the FastAPI backend.
*   `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Standard Supabase config.

**Backend (`.env`)**
*   `DATABASE_URL`: The PostgreSQL connection string.
*   `SUPABASE_JWT_SECRET`: For decoding standard user tokens.
*   `ADMIN_PASSWORD`: For the master admin bypass.
*   `VERCEL`: Automatically set by Vercel; triggers `/tmp` storage pathing.

## Typical Agent Workflow

When making modifications:
1.  **Search the API client:** Before adding a route, check `frontend/lib/api.ts` to see how the frontend expects to communicate.
2.  **Respect the envelope:** Ensure backend routes return `{"success": true, "data": ...}`.
3.  **Verify UI:** The system is built with Tailwind. Maintain the established aesthetic (glassmorphism, clean layouts, `#15203a` cards, etc.).
4.  **Test builds:** Always run `cmd /c npm run build` (Windows) in the `frontend/` directory to catch TypeScript errors after modifications.
