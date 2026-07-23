-- v212: at-most-one reversal per farm-book entry — DB-level enforcement.
--
-- The v211 API layer enforces "each original entry may be reversed at most once"
-- with a SELECT-before-INSERT check; under concurrency two reversals could race
-- past it. This partial unique index makes the invariant transactional at the
-- database level (the app check remains for a friendly 409).
--
-- Shipped as a NEW migration (not an edit of merged v211) so databases that
-- already applied v211 — which is replayed idempotently but tracked as applied
-- in staged environments — converge to the same schema.

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS ux_farm_ledger_entries_one_reversal
    ON farm_ledger_entries (tenant_id, reverses_entry_id)
    WHERE reverses_entry_id IS NOT NULL;

COMMIT;
