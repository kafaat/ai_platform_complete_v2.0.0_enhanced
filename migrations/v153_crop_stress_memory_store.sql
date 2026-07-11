-- v153: durable crop stress memory store
-- Append-only raw events + versioned snapshots for Crop Intelligence.
-- Values are persisted as supplied by validated producers; no stress is fabricated here.

BEGIN;

CREATE TABLE IF NOT EXISTS crop_stress_events (
    event_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL,
    field_id          TEXT        NOT NULL,
    season_id         TEXT        NOT NULL,
    stress_type       TEXT        NOT NULL CHECK (stress_type IN ('water','heat','cold','nutrient','disease')),
    severity          DOUBLE PRECISION NOT NULL CHECK (severity >= 0 AND severity <= 1),
    observed_at       TIMESTAMPTZ NOT NULL,
    evidence_id       TEXT,
    source_service    TEXT        NOT NULL,
    source_product_id TEXT,
    source_version    TEXT,
    payload           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    dedup_key         TEXT        NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_crop_stress_events_scope_time
    ON crop_stress_events (tenant_id, field_id, season_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_crop_stress_events_type_time
    ON crop_stress_events (tenant_id, field_id, season_id, stress_type, observed_at DESC);

CREATE TABLE IF NOT EXISTS crop_stress_memory_snapshots (
    snapshot_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL,
    field_id          TEXT        NOT NULL,
    season_id         TEXT        NOT NULL,
    as_of              TIMESTAMPTZ NOT NULL,
    schema_version     TEXT        NOT NULL,
    product_version    TEXT        NOT NULL,
    status             TEXT        NOT NULL,
    overall_burden     DOUBLE PRECISION,
    recovery_state     TEXT        NOT NULL,
    observation_count  INTEGER     NOT NULL DEFAULT 0 CHECK (observation_count >= 0),
    snapshot            JSONB       NOT NULL,
    evidence_digest     TEXT        NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, field_id, season_id, as_of, product_version, evidence_digest)
);

CREATE INDEX IF NOT EXISTS idx_crop_stress_memory_latest
    ON crop_stress_memory_snapshots (tenant_id, field_id, season_id, as_of DESC);

COMMENT ON TABLE crop_stress_events IS
    'Append-only raw crop stress observations for deterministic stress-memory recomputation. RLS tenant isolated. v153.';
COMMENT ON TABLE crop_stress_memory_snapshots IS
    'Versioned derived crop stress-memory snapshots. Raw events remain source of truth. RLS tenant isolated. v153.';

-- Both tables are immutable audit products; corrections arrive as new rows.
DO $$
BEGIN
    IF to_regprocedure('sahool_block_mutation()') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS trg_append_only_crop_stress_events ON crop_stress_events;
        CREATE TRIGGER trg_append_only_crop_stress_events
            BEFORE UPDATE OR DELETE ON crop_stress_events
            FOR EACH ROW EXECUTE FUNCTION sahool_block_mutation();
        DROP TRIGGER IF EXISTS trg_append_only_crop_stress_memory_snapshots ON crop_stress_memory_snapshots;
        CREATE TRIGGER trg_append_only_crop_stress_memory_snapshots
            BEFORE UPDATE OR DELETE ON crop_stress_memory_snapshots
            FOR EACH ROW EXECUTE FUNCTION sahool_block_mutation();
    END IF;
END $$;

ALTER TABLE crop_stress_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE crop_stress_events FORCE ROW LEVEL SECURITY;
ALTER TABLE crop_stress_memory_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE crop_stress_memory_snapshots FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON crop_stress_events;
CREATE POLICY tenant_isolation ON crop_stress_events
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

DROP POLICY IF EXISTS tenant_isolation ON crop_stress_memory_snapshots;
CREATE POLICY tenant_isolation ON crop_stress_memory_snapshots
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMIT;
