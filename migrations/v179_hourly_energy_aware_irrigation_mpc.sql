-- M3: governed hourly energy-aware irrigation MPC candidates.
CREATE TABLE IF NOT EXISTS hourly_irrigation_mpc_schedules (
    tenant_id UUID NOT NULL,
    schedule_id UUID NOT NULL DEFAULT gen_random_uuid(),
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    decision_id UUID,
    solver_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified','degraded','blocked')),
    recommendation_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (recommendation_only = TRUE),
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (execution_allowed = FALSE),
    horizon_start TIMESTAMPTZ,
    horizon_hours INTEGER NOT NULL CHECK (horizon_hours BETWEEN 0 AND 72),
    initial_depletion_mm DOUBLE PRECISION NOT NULL CHECK (initial_depletion_mm >= 0),
    final_depletion_mm DOUBLE PRECISION NOT NULL CHECK (final_depletion_mm >= 0),
    required_refill_mm DOUBLE PRECISION NOT NULL CHECK (required_refill_mm >= 0),
    scheduled_irrigation_mm DOUBLE PRECISION NOT NULL CHECK (scheduled_irrigation_mm >= 0),
    scheduled_volume_m3 DOUBLE PRECISION NOT NULL CHECK (scheduled_volume_m3 >= 0),
    water_state_digest CHAR(64) NOT NULL,
    irrigation_capability_digest CHAR(64) NOT NULL,
    commissioning_executability_digest CHAR(64) NOT NULL,
    schedule_digest CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, schedule_id),
    UNIQUE (tenant_id, schedule_digest)
);

CREATE TABLE IF NOT EXISTS hourly_irrigation_mpc_actions (
    tenant_id UUID NOT NULL,
    action_id UUID NOT NULL DEFAULT gen_random_uuid(),
    schedule_id UUID NOT NULL,
    action_hour TIMESTAMPTZ NOT NULL,
    irrigation_depth_mm DOUBLE PRECISION NOT NULL CHECK (irrigation_depth_mm >= 0),
    irrigation_volume_m3 DOUBLE PRECISION NOT NULL CHECK (irrigation_volume_m3 >= 0),
    runtime_minutes DOUBLE PRECISION NOT NULL CHECK (runtime_minutes >= 0),
    expected_energy_kwh DOUBLE PRECISION NOT NULL CHECK (expected_energy_kwh >= 0),
    energy_cost DOUBLE PRECISION NOT NULL CHECK (energy_cost >= 0),
    renewable_fraction DOUBLE PRECISION NOT NULL CHECK (renewable_fraction BETWEEN 0 AND 1),
    source_window_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, action_id),
    FOREIGN KEY (tenant_id, schedule_id)
      REFERENCES hourly_irrigation_mpc_schedules (tenant_id, schedule_id) ON DELETE CASCADE,
    UNIQUE (tenant_id, schedule_id, action_hour)
);

ALTER TABLE hourly_irrigation_mpc_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE hourly_irrigation_mpc_schedules FORCE ROW LEVEL SECURITY;
ALTER TABLE hourly_irrigation_mpc_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE hourly_irrigation_mpc_actions FORCE ROW LEVEL SECURITY;

CREATE POLICY hourly_irrigation_mpc_schedules_tenant ON hourly_irrigation_mpc_schedules
USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY hourly_irrigation_mpc_actions_tenant ON hourly_irrigation_mpc_actions
USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
