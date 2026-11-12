-- v259: a documented observed-zero yield-map point is accepted, and stays pending review.
--
-- v215 bound yield_map_records.yield_kg_ha to (0, 100000]: a monitor zero, a machine stop
-- and a crop that truly yielded nothing were indistinguishable, so all were refused. This
-- keeps refusing the undocumented zero and every negative value, and admits a zero only
-- when the point carries zero_yield_observed=true, a non-blank zero_yield_evidence_id and
-- zero_yield_review_status='pending' (api/yield_map_ingestion.py sets the last one itself).
-- Records stay append-only (v215 trigger), so nothing in the database promotes a pending
-- zero to a reviewed one; a review is a separate record, never an UPDATE of the evidence.
--
-- Ingestion summaries are untouched: the router computes min/max/mean over measured
-- (> 0) points only, so v215's > 0 summary checks still hold and an unreviewed zero never
-- enters a field-level yield statistic.
--
-- Re-run safe: migrations/apply_in_compose.sh re-applies the whole MANIFEST on every
-- deploy. Each step checks the catalogue first, so a second run takes no lock beyond the
-- catalogue read and re-validates nothing.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'yield_map_records'::regclass
           AND conname = 'yield_map_records_yield_kg_ha_observed_zero_check'
    ) THEN
        ALTER TABLE yield_map_records
            ADD CONSTRAINT yield_map_records_yield_kg_ha_observed_zero_check CHECK (
                yield_kg_ha >= 0 AND yield_kg_ha <= 100000 AND (
                    yield_kg_ha > 0 OR (
                        attributes->>'zero_yield_observed' = 'true'
                        AND NULLIF(BTRIM(attributes->>'zero_yield_evidence_id'), '') IS NOT NULL
                        AND attributes->>'zero_yield_review_status' = 'pending'
                    )
                )
            );
    END IF;
    -- Dropped only after the replacement exists, so no window admits a negative value.
    -- v215 named it implicitly (column CHECK => <table>_<column>_check).
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'yield_map_records'::regclass
           AND conname = 'yield_map_records_yield_kg_ha_check'
    ) THEN
        ALTER TABLE yield_map_records DROP CONSTRAINT yield_map_records_yield_kg_ha_check;
    END IF;
END $$;

COMMENT ON CONSTRAINT yield_map_records_yield_kg_ha_observed_zero_check ON yield_map_records IS
    'v259: 0 < yield <= 100000, or a documented observed zero (evidence id) pending review.';

COMMIT;
