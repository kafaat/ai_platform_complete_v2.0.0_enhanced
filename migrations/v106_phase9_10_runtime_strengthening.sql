-- v106: Phase 9/10 runtime strengthening.
-- Adds a unified event outbox and an online feature table so Phase 9 autonomy
-- cycles and Phase 10 learning cycles can be persisted and replayed without
-- relying only on facade return payloads.

CREATE TABLE IF NOT EXISTS runtime_event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL,
    field_id UUID NULL,
    event_id TEXT NOT NULL UNIQUE,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','published','failed','dead_letter')),
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS online_feature_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    feature_set_id TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    values JSONB NOT NULL DEFAULT '{}'::jsonb,
    labels JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, entity_type, entity_id, feature_set_id, event_time)
);

CREATE INDEX IF NOT EXISTS idx_runtime_event_outbox_pending
    ON runtime_event_outbox(status, created_at)
    WHERE status IN ('pending','failed');
CREATE INDEX IF NOT EXISTS idx_runtime_event_outbox_aggregate
    ON runtime_event_outbox(aggregate_type, aggregate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_online_feature_values_lookup
    ON online_feature_values(tenant_id, entity_type, entity_id, feature_set_id, event_time DESC);

ALTER TABLE runtime_event_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime_event_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE online_feature_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE online_feature_values FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY runtime_event_outbox_tenant_isolation ON runtime_event_outbox
        USING (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY online_feature_values_tenant_isolation ON online_feature_values
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
