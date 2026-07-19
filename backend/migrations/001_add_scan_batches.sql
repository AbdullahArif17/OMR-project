-- Apply with the direct Neon connection before deploying the scanner update.
-- Safe to run more than once on PostgreSQL.

CREATE TABLE IF NOT EXISTS scan_batches (
    id UUID NOT NULL,
    exam_id UUID NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    response_data JSONB NOT NULL,
    response_message VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_scan_batches PRIMARY KEY (id),
    CONSTRAINT fk_scan_batches_exam_id_exams
        FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    CONSTRAINT scan_batch_exam_idempotency UNIQUE (exam_id, idempotency_key)
);
