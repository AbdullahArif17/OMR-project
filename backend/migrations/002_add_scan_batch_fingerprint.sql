-- Apply with the direct Neon connection before deploying the scanner update.
-- Safe to run more than once on PostgreSQL.

ALTER TABLE scan_batches
    ADD COLUMN IF NOT EXISTS request_fingerprint VARCHAR(64);
