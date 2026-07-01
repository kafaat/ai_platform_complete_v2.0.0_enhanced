-- v132 (v57.5 line) — field_state recompute provenance (completes the v53 gap).
-- field_state (v53) is the canonical read model (one row per field, UPSERT on recompute) but
-- carried no provenance: you couldn't tell WHICH event produced a projection, nor guard a
-- stale recompute from overwriting a newer one. This adds:
--   • version — monotonic per-field recompute counter (the recompute service sets = old+1;
--     a stale writer with a lower version can be rejected by the app: WHERE version < $new).
--   • source_event_id — the event that triggered this projection (forensics + drift checks:
--     "which fields were recomputed from event X", "projections with no source event").
--   • recomputed_at — wall-clock of the last recompute (distinct from the row's computed_at).
-- Additive + idempotent. RLS already on field_state (tenant_id). Applied after v131.

ALTER TABLE field_state ADD COLUMN IF NOT EXISTS version         BIGINT NOT NULL DEFAULT 1;
ALTER TABLE field_state ADD COLUMN IF NOT EXISTS source_event_id TEXT;
ALTER TABLE field_state ADD COLUMN IF NOT EXISTS recomputed_at   TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_field_state_version') THEN
        ALTER TABLE field_state ADD CONSTRAINT chk_field_state_version
            CHECK (version >= 1) NOT VALID;
    END IF;
END $$;

-- drift/forensics: fields recomputed from a given event (partial — only rows with a source).
CREATE INDEX IF NOT EXISTS idx_field_state_source_event
    ON field_state (source_event_id) WHERE source_event_id IS NOT NULL;

COMMENT ON COLUMN field_state.version IS
    'عدّاد إعادة حساب أحاديّ التزايد لكلّ حقل — يمنع كتابة إعادة حساب قديمة فوق أحدث (WHERE version < $new).';
COMMENT ON COLUMN field_state.source_event_id IS
    'مُعرّف الحدث الذي أنتج هذا الإسقاط — تتبّع جنائيّ + كشف الانحراف (إسقاط بلا حدث مصدر).';
