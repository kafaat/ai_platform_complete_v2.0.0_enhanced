-- v234: persist agronomic review verdict separately from learning-source traceability.
-- Additive only; no destructive backfill, no RLS change. v206 remains final RLS hardening.
BEGIN;

ALTER TABLE online_learning_updates
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'unreviewed',
    ADD COLUMN IF NOT EXISTS agronomically_approved BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS agronomic_review JSONB;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_oluj_agronomic_review_status'
          AND conrelid = 'online_learning_updates'::regclass
    ) THEN
        ALTER TABLE online_learning_updates
          ADD CONSTRAINT chk_oluj_agronomic_review_status
          CHECK (review_status IN ('unreviewed', 'approved', 'rejected'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_oluj_agronomic_approval_consistency'
          AND conrelid = 'online_learning_updates'::regclass
    ) THEN
        ALTER TABLE online_learning_updates
          ADD CONSTRAINT chk_oluj_agronomic_approval_consistency
          CHECK (
            (agronomically_approved = (review_status = 'approved'))
            AND (
              review_status <> 'approved'
              OR (
                agronomic_review IS NOT NULL
                AND jsonb_typeof(agronomic_review) = 'object'
                AND NULLIF(TRIM(agronomic_review->>'reviewer_id'), '') IS NOT NULL
                AND agronomic_review->>'verdict' = 'approved'
                AND jsonb_typeof(agronomic_review->'evidence_ids') = 'array'
                AND jsonb_array_length(agronomic_review->'evidence_ids') > 0
              )
            )
          );
    END IF;
END $$;

COMMENT ON COLUMN online_learning_updates.review_status IS
    'Agronomic review, independent of source traceability; legacy rows are unreviewed';
COMMENT ON COLUMN online_learning_updates.agronomic_review IS
    'Evidence/reviewer provenance for approved or rejected outcomes; nullable when unreviewed';
COMMIT;
