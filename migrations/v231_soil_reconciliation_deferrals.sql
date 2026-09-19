-- v231 — RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01
--
-- The v157 cursor is a single high-water mark over a FILTERED stream: the scan drops
-- rows whose device carries no field, and the loop skips sensor types with no mapping.
-- Both reasons can disappear later (a device gets bound; a mapping gets added), yet a
-- later eligible row in the same batch raises the mark past the skipped one, and no
-- round ever returns to it. The loss is silent: no error, no backlog, and the next run
-- reports zero.
--
-- The cursor is not the thing to fix. A mark that refuses to pass an unresolved row
-- stalls the whole backfill on the first sensor type nobody will ever map — progress
-- becomes impossible, which is the defect class this repository closed in #1026.
--
-- So the mark keeps advancing and what it passed is WRITTEN DOWN. Every skip is
-- recorded here with the reason that caused it, and every later run re-examines the
-- open deferrals before scanning forward. Acceptance T16 of the sensor-path research
-- states the same rule: a checkpoint may not pass an unresolved row without a record
-- that allows re-matching.
--
-- Resolved rows are KEPT with `resolved_at` set rather than deleted: the ledger is the
-- forensic answer to "was this legacy reading ever considered, and when did it become
-- eligible". Deleting on success would make a clean table indistinguishable from a
-- table nothing ever wrote to.
CREATE TABLE IF NOT EXISTS soil_reconciliation_deferrals (
    source_name         VARCHAR(64) NOT NULL,
    tenant_id           UUID NOT NULL,
    source_id           BIGINT NOT NULL,
    -- The reason is data, not prose: the re-examination pass and any operator report
    -- read it. CHECK keeps the vocabulary closed so a typo cannot invent a category
    -- that nothing re-examines.
    reason              VARCHAR(64) NOT NULL
                        CHECK (reason IN ('device_field_unbound',
                                          'device_not_registered',
                                          'sensor_type_unmapped')),
    first_deferred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_examined_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    examinations        INTEGER NOT NULL DEFAULT 1 CHECK (examinations >= 1),
    resolved_at         TIMESTAMPTZ,
    PRIMARY KEY (source_name, tenant_id, source_id)
);

-- The re-examination pass reads exactly this: open deferrals of one source for one
-- tenant, oldest first. Partial index — resolved rows are the majority over time and
-- never re-examined.
CREATE INDEX IF NOT EXISTS idx_soil_reconciliation_deferrals_open
    ON soil_reconciliation_deferrals(source_name, tenant_id, source_id)
    WHERE resolved_at IS NULL;

ALTER TABLE soil_reconciliation_deferrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_reconciliation_deferrals FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  DROP POLICY IF EXISTS tenant_isolation ON soil_reconciliation_deferrals;
  CREATE POLICY tenant_isolation ON soil_reconciliation_deferrals
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
END $$;

COMMENT ON TABLE soil_reconciliation_deferrals IS
  'Rows the reconciliation cursor passed without processing, with the reason, so a later run can re-match them. v231.';
COMMENT ON COLUMN soil_reconciliation_deferrals.resolved_at IS
  'Set when a later run processed the row. The entry is kept: an empty table must not be able to mean "nothing was ever deferred" and "everything was silently dropped" at once.';
