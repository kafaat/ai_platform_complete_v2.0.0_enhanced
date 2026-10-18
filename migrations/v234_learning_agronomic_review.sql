-- U07: preserve review separately from source traceability. Additive and idempotent.
-- No approval backfill, tenant policy change, or physical execution activation.
BEGIN;

ALTER TABLE online_learning_updates
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'unreviewed';
ALTER TABLE online_learning_updates
    ADD COLUMN IF NOT EXISTS agronomically_approved BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE online_learning_updates
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
          CHECK ((
            agronomically_approved = (review_status = 'approved')
            AND CASE WHEN review_status IN ('approved', 'rejected') THEN
              jsonb_typeof(agronomic_review) = 'object'
              AND jsonb_typeof(agronomic_review->'reviewer_id') = 'string'
              AND (agronomic_review->>'reviewer_id') ~ '\S'
              AND agronomic_review->>'verdict' = review_status
              AND CASE WHEN review_status = 'approved' THEN
                CASE WHEN jsonb_typeof(agronomic_review->'evidence_ids') = 'array' THEN
                  jsonb_array_length(agronomic_review->'evidence_ids') > 0
                  AND NOT jsonb_path_exists(
                    agronomic_review->'evidence_ids',
                    '$[*] ? (@.type() != "string" || @ like_regex "^\\s*$")'
                  )
                ELSE FALSE END
              ELSE TRUE END
            ELSE TRUE END
          ) IS TRUE);
    END IF;
END $$;

COMMENT ON COLUMN online_learning_updates.review_status IS
    'Agronomic review independent of traceability; historical rows are unreviewed';
COMMENT ON COLUMN online_learning_updates.agronomic_review IS
    'Normalized supplied reviewer/verdict/evidence; persistence is not reviewer authentication';
COMMIT;
