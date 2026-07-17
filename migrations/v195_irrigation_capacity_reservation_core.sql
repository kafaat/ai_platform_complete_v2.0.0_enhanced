-- v195: IRR-F01 capacity/reservation core — the confirmed gap.
--
-- Closes the transaction-safe hydraulic reservation gap in the EXISTING runtime
-- (only v136's per-valve "one running" flag existed; no interval/combined-load
-- concurrency). Three tables ONLY, all extending existing stores:
--   * hydraulic_capacity_evaluations  — immutable request-time evaluation over
--     v171 canonical_hydraulic_capabilities + hydraulic nodes.
--   * irrigation_resource_reservations — per-resource-node interval reservation.
--   * irrigation_resource_reservation_events — append-only lifecycle audit.
--
-- Deliberately DOES NOT create: irrigation_assets / irrigation_executions /
-- irrigation_execution_evidence, a competing capability graph, physical
-- graph-version / node-segment-membership / path-closure tables (deferred — the
-- hydraulic path is answered by a query over v171), or a target binding (a later
-- slice). It does NOT ALTER irrigation_water_allocations. Execution aggregates are
-- referenced polymorphically by (execution_ref_type, execution_ref_id) with an
-- application-side validator — no unenforceable multi-column polymorphic FK.
--
-- Reservation lifecycle is reserved/active/released/expired/cancelled ONLY. A
-- committed reservation + outbox record means dispatch_requested; dispatched/
-- acknowledged/started/completed live in the execution/dispatch lineage, not here.
BEGIN;

CREATE TABLE IF NOT EXISTS hydraulic_capacity_evaluations (
    evaluation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    canonical_hydraulic_capability_id TEXT,
    execution_ref_type TEXT NOT NULL
        CHECK (execution_ref_type IN ('manual_execution', 'as_applied_run', 'execution_request')),
    execution_ref_id TEXT NOT NULL,
    requested_interval TSTZRANGE NOT NULL,
    requested_flow_m3h NUMERIC(14, 4) NOT NULL CHECK (requested_flow_m3h > 0),
    maximum_safe_flow_m3h NUMERIC(14, 4) CHECK (maximum_safe_flow_m3h IS NULL OR maximum_safe_flow_m3h >= 0),
    derated_available_flow_m3h NUMERIC(14, 4) CHECK (derated_available_flow_m3h IS NULL OR derated_available_flow_m3h >= 0),
    peak_reserved_flow_m3h NUMERIC(14, 4) NOT NULL DEFAULT 0 CHECK (peak_reserved_flow_m3h >= 0),
    remaining_allocatable_flow_m3h NUMERIC(14, 4),
    bottleneck_node_id UUID,
    eligible BOOLEAN NOT NULL,
    blocking_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    derating_factors JSONB NOT NULL DEFAULT '{}'::jsonb,
    capability_digest CHAR(64) CHECK (capability_digest IS NULL OR capability_digest ~ '^[0-9a-f]{64}$'),
    telemetry_snapshot_version TEXT,
    calculation_model_version TEXT NOT NULL,
    correlation_id UUID,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (evaluation_id, tenant_id),
    FOREIGN KEY (project_id, tenant_id)
        REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (canonical_hydraulic_capability_id)
        REFERENCES canonical_hydraulic_capabilities(capability_id) ON DELETE RESTRICT,
    FOREIGN KEY (bottleneck_node_id, tenant_id)
        REFERENCES irrigation_hydraulic_nodes(id, tenant_id) ON DELETE RESTRICT,
    CHECK (NOT isempty(requested_interval)),
    CHECK (lower(requested_interval) IS NOT NULL AND upper(requested_interval) IS NOT NULL),
    CHECK (upper(requested_interval) > lower(requested_interval))
);

CREATE INDEX IF NOT EXISTS idx_hydraulic_capacity_eval_execution
    ON hydraulic_capacity_evaluations (tenant_id, execution_ref_type, execution_ref_id, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS irrigation_resource_reservations (
    reservation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    evaluation_id UUID NOT NULL,
    execution_ref_type TEXT NOT NULL
        CHECK (execution_ref_type IN ('manual_execution', 'as_applied_run', 'execution_request')),
    execution_ref_id TEXT NOT NULL,
    resource_node_id UUID NOT NULL,
    resource_policy TEXT NOT NULL CHECK (resource_policy IN ('exclusive', 'shared_capacity')),
    reserved_flow_m3h NUMERIC(14, 4) NOT NULL CHECK (reserved_flow_m3h > 0),
    active_interval TSTZRANGE NOT NULL,
    state TEXT NOT NULL DEFAULT 'reserved'
        CHECK (state IN ('reserved', 'active', 'released', 'expired', 'cancelled')),
    idempotency_key TEXT NOT NULL,
    correlation_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    release_reason TEXT,
    UNIQUE (reservation_id, tenant_id),
    UNIQUE (tenant_id, idempotency_key, resource_node_id),
    FOREIGN KEY (project_id, tenant_id)
        REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (evaluation_id, tenant_id)
        REFERENCES hydraulic_capacity_evaluations(evaluation_id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (resource_node_id, tenant_id)
        REFERENCES irrigation_hydraulic_nodes(id, tenant_id) ON DELETE RESTRICT,
    CHECK (NOT isempty(active_interval)),
    CHECK (lower(active_interval) IS NOT NULL AND upper(active_interval) IS NOT NULL),
    CHECK (upper(active_interval) > lower(active_interval)),
    CHECK ((state = 'active') = (activated_at IS NOT NULL) OR state IN ('released', 'expired', 'cancelled')),
    CHECK (state NOT IN ('released', 'expired', 'cancelled') OR released_at IS NOT NULL)
);

-- Cheap UUID filtering plus indexable range overlap without a composite-UUID GiST
-- opclass; query plans bitmap-AND these two partial indexes.
CREATE INDEX IF NOT EXISTS idx_irrigation_reservation_resource_state
    ON irrigation_resource_reservations (tenant_id, resource_node_id, state)
    WHERE state IN ('reserved', 'active');
CREATE INDEX IF NOT EXISTS idx_irrigation_reservation_interval
    ON irrigation_resource_reservations USING GIST (active_interval)
    WHERE state IN ('reserved', 'active');
CREATE INDEX IF NOT EXISTS idx_irrigation_reservation_execution
    ON irrigation_resource_reservations (tenant_id, execution_ref_type, execution_ref_id);

CREATE TABLE IF NOT EXISTS irrigation_resource_reservation_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    reservation_id UUID NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('reserved', 'activated', 'released', 'expired', 'cancelled')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    causation_id UUID,
    correlation_id UUID NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, reservation_id, event_type, causation_id),
    FOREIGN KEY (reservation_id, tenant_id)
        REFERENCES irrigation_resource_reservations(reservation_id, tenant_id) ON DELETE RESTRICT
);

-- Fail-closed tenant RLS (same posture as v192/v194): missing, empty, malformed,
-- or wrong app.current_tenant can neither read nor write.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'hydraulic_capacity_evaluations',
        'irrigation_resource_reservations',
        'irrigation_resource_reservation_events'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I '
            'USING (tenant_id::TEXT = NULLIF(current_setting(''app.current_tenant'', true), '''')) '
            'WITH CHECK (tenant_id::TEXT = NULLIF(current_setting(''app.current_tenant'', true), ''''))',
            t
        );
    END LOOP;
END $$;

COMMENT ON TABLE hydraulic_capacity_evaluations IS
    'IRR-F01: immutable request-time capacity evaluation over v171 canonical capability + hydraulic nodes; no duplicate capability SoR.';
COMMENT ON TABLE irrigation_resource_reservations IS
    'IRR-F01: transaction-safe per-resource-node interval reservation; references existing execution aggregates polymorphically; lifecycle reserved/active/released/expired/cancelled only.';
COMMENT ON TABLE irrigation_resource_reservation_events IS
    'IRR-F01: append-only reservation lifecycle audit for crash recovery and provenance.';

COMMIT;
