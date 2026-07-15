-- IRR-X1.2 governed manual irrigation lifecycle.
CREATE TABLE IF NOT EXISTS irrigation_manual_executions (
    execution_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    season_id text NOT NULL,
    system_id text NOT NULL,
    recommendation_id text NOT NULL,
    recommendation_digest char(64) NOT NULL,
    execution_mode text NOT NULL CHECK (execution_mode IN ('recommendation_only','manual_estimated','manual_measured')),
    state text NOT NULL CHECK (state IN ('recommended','approved','started','stopped','confirmed','verified','reconciled','cancelled')),
    target_depth_mm numeric NOT NULL CHECK (target_depth_mm > 0),
    target_volume_m3 numeric NOT NULL CHECK (target_volume_m3 > 0),
    nominal_flow_m3_h numeric,
    valid_from timestamptz NOT NULL,
    valid_until timestamptz NOT NULL,
    approved_at timestamptz,
    started_at timestamptz,
    stopped_at timestamptz,
    confirmed_at timestamptz,
    verified_at timestamptz,
    reconciled_at timestamptz,
    completion_ratio numeric,
    confirmation jsonb,
    as_applied jsonb,
    as_applied_digest char(64),
    ledger_eligible boolean NOT NULL DEFAULT false,
    idempotency_key text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, as_applied_digest)
);

CREATE TABLE IF NOT EXISTS irrigation_manual_execution_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    execution_id uuid NOT NULL REFERENCES irrigation_manual_executions(execution_id),
    from_state text,
    to_state text NOT NULL,
    actor_id text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    event_digest char(64) NOT NULL,
    UNIQUE (tenant_id, event_digest)
);

ALTER TABLE irrigation_manual_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_manual_executions FORCE ROW LEVEL SECURITY;
ALTER TABLE irrigation_manual_execution_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_manual_execution_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS irrigation_manual_executions_tenant ON irrigation_manual_executions;
CREATE POLICY irrigation_manual_executions_tenant ON irrigation_manual_executions
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
DROP POLICY IF EXISTS irrigation_manual_execution_events_tenant ON irrigation_manual_execution_events;
CREATE POLICY irrigation_manual_execution_events_tenant ON irrigation_manual_execution_events
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE OR REPLACE FUNCTION prevent_manual_execution_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'manual execution events are append-only'; END; $$;
DROP TRIGGER IF EXISTS manual_execution_events_append_only ON irrigation_manual_execution_events;
CREATE TRIGGER manual_execution_events_append_only BEFORE UPDATE OR DELETE ON irrigation_manual_execution_events
FOR EACH ROW EXECUTE FUNCTION prevent_manual_execution_event_mutation();
