# Production Scan and Upload Hardening Plan

## Objective

Make the existing OMR workflow dependable for real classroom batches while failing safely on unreadable, incomplete, blank, or ambiguous sheets. The scanner must never silently invent an answer when confidence is inadequate.

## Acceptance criteria

- Detect supported 4- and 5-option sheets under moderate rotation, perspective distortion, uneven lighting, and common phone-camera noise.
- Normalize orientation and perspective when a reliable question grid can be found.
- Distinguish filled, blank, and multi-marked rows using calibrated per-sheet confidence instead of one fixed pixel threshold.
- Return actionable per-file errors and quality diagnostics without discarding successful files in the same batch.
- Validate file signatures as well as extensions; bound bytes, pixels, PDF pages, archive entries, expanded bytes, and total expanded sheets.
- Reject encrypted, malformed, nested, traversal, symlink-like, and compression-bomb archives/documents.
- Keep temporary and persisted files consistent when processing or database writes fail.
- Make result persistence idempotent for a retried source within one exam.
- Keep CPU-heavy image/PDF work off the async event loop.
- Give users accurate limits, upload progress, cancellation, and retry-friendly partial results.
- Provide production configuration, structured logging, health/readiness checks, and deployment guidance.
- Pass backend regression tests, synthetic OMR tests, frontend lint/type checks, and the production build.

## Work streams

1. OMR engine: preprocessing variants, deskew/perspective normalization, grid scoring, adaptive fill confidence, diagnostics.
2. Ingestion: content sniffing, archive/PDF/image limits, secure extraction, atomic cleanup.
3. API and data: bounded batches, transaction behavior, idempotency, consistent partial-failure responses.
4. Frontend: client-side validation aligned with server settings, progress/cancel controls, clearer quality guidance.
5. Operations: environment validation, request limits, logging, health/readiness, documentation.
6. Verification: adversarial upload cases, generated sheets with transformations, API workflow, production build.

## Non-goals

- Handwriting recognition, arbitrary document OCR, and unconstrained bubble layouts are not treated as OMR inputs.
- Low-confidence sheets are rejected for review rather than force-graded.
