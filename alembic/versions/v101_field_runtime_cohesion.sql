-- v101: Field runtime cohesion tables
-- Purpose: make CanonicalFieldState the persisted source of truth for field brain outputs.

CREATE TABLE IF NOT EXISTS canonical_field_state_snapshots (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    farm_id TEXT,
    field_id TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    fusion_strategy_version TEXT NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_canonical_field_state_tenant_field_time
    ON canonical_field_state_snapshots (tenant_id, field_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS field_digital_twin_views (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    field_id TEXT NOT NULL,
    source_state_id TEXT NOT NULL REFERENCES canonical_field_state_snapshots(id) ON DELETE CASCADE,
    view JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_field_digital_twin_source_state
    ON field_digital_twin_views (source_state_id);

CREATE TABLE IF NOT EXISTS recommendation_lifecycle_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    field_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    source_state_id TEXT NOT NULL REFERENCES canonical_field_state_snapshots(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    event JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_lifecycle_rec_time
    ON recommendation_lifecycle_events (recommendation_id, occurred_at ASC);
