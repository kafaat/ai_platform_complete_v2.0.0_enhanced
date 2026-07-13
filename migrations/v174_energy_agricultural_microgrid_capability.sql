-- M2.7 Energy and Agricultural Microgrid Capability
BEGIN;

CREATE TABLE IF NOT EXISTS irrigation_pv_arrays (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    energy_system_id UUID NOT NULL,
    name TEXT NOT NULL,
    capacity_kwp NUMERIC NOT NULL CHECK (capacity_kwp > 0),
    system_derate NUMERIC NOT NULL DEFAULT 0.82 CHECK (system_derate > 0 AND system_derate <= 1),
    temperature_coefficient_per_c NUMERIC NOT NULL DEFAULT -0.004 CHECK (temperature_coefficient_per_c BETWEEN -0.02 AND 0),
    orientation_azimuth_deg NUMERIC CHECK (orientation_azimuth_deg IS NULL OR orientation_azimuth_deg BETWEEN 0 AND 360),
    tilt_deg NUMERIC CHECK (tilt_deg IS NULL OR tilt_deg BETWEEN 0 AND 90),
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    evidence_digest CHAR(64) CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_hybrid_inverters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    energy_system_id UUID NOT NULL,
    continuous_kw NUMERIC NOT NULL CHECK (continuous_kw > 0),
    peak_kva NUMERIC NOT NULL CHECK (peak_kva > 0),
    maximum_charge_kw NUMERIC CHECK (maximum_charge_kw IS NULL OR maximum_charge_kw >= 0),
    maximum_discharge_kw NUMERIC CHECK (maximum_discharge_kw IS NULL OR maximum_discharge_kw >= 0),
    nominal_voltage_v NUMERIC CHECK (nominal_voltage_v IS NULL OR nominal_voltage_v > 0),
    nominal_frequency_hz NUMERIC CHECK (nominal_frequency_hz IS NULL OR nominal_frequency_hz > 0),
    phases SMALLINT CHECK (phases IS NULL OR phases IN (1,3)),
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    evidence_digest CHAR(64) CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_battery_systems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    energy_system_id UUID NOT NULL,
    chemistry TEXT NOT NULL CHECK (chemistry IN ('lifepo4','nmc','lto','other')),
    nominal_energy_kwh NUMERIC NOT NULL CHECK (nominal_energy_kwh > 0),
    usable_energy_kwh NUMERIC NOT NULL CHECK (usable_energy_kwh > 0 AND usable_energy_kwh <= nominal_energy_kwh),
    continuous_power_kw NUMERIC NOT NULL CHECK (continuous_power_kw > 0),
    peak_power_kw NUMERIC NOT NULL CHECK (peak_power_kw >= continuous_power_kw),
    maximum_charge_kw NUMERIC NOT NULL CHECK (maximum_charge_kw >= 0),
    maximum_discharge_kw NUMERIC NOT NULL CHECK (maximum_discharge_kw >= 0),
    minimum_soc_percent NUMERIC NOT NULL CHECK (minimum_soc_percent BETWEEN 0 AND 100),
    emergency_reserve_percent NUMERIC NOT NULL CHECK (emergency_reserve_percent BETWEEN 0 AND 100),
    live_soc_percent NUMERIC CHECK (live_soc_percent IS NULL OR live_soc_percent BETWEEN 0 AND 100),
    state_of_health_percent NUMERIC CHECK (state_of_health_percent IS NULL OR state_of_health_percent BETWEEN 0 AND 100),
    temperature_c NUMERIC,
    bms_status TEXT,
    measured_at TIMESTAMPTZ,
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    evidence_digest CHAR(64) CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_generators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL, energy_system_id UUID NOT NULL,
    continuous_kw NUMERIC NOT NULL CHECK (continuous_kw > 0), starting_kva NUMERIC NOT NULL CHECK (starting_kva > 0),
    fuel_type TEXT, energy_cost_per_kwh NUMERIC CHECK (energy_cost_per_kwh IS NULL OR energy_cost_per_kwh >= 0),
    available BOOLEAN NOT NULL DEFAULT false,
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    evidence_digest CHAR(64) CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'), evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (id, tenant_id),
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_grid_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL, energy_system_id UUID NOT NULL,
    contracted_kw NUMERIC NOT NULL CHECK (contracted_kw > 0), starting_kva NUMERIC CHECK (starting_kva IS NULL OR starting_kva > 0),
    nominal_voltage_v NUMERIC NOT NULL CHECK (nominal_voltage_v > 0), nominal_frequency_hz NUMERIC NOT NULL CHECK (nominal_frequency_hz > 0),
    voltage_within_limits BOOLEAN NOT NULL DEFAULT false, frequency_within_limits BOOLEAN NOT NULL DEFAULT false,
    available BOOLEAN NOT NULL DEFAULT false, energy_cost_per_kwh NUMERIC CHECK (energy_cost_per_kwh IS NULL OR energy_cost_per_kwh >= 0),
    evidence_digest CHAR(64) CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'), evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    measured_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (id, tenant_id),
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_energy_loads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL, energy_system_id UUID NOT NULL,
    asset_id UUID, load_type TEXT NOT NULL CHECK (load_type IN ('main_pump','pivot_drive','booster_pump','mister_pump','fan_blower','fertigation','control_iot','other')),
    rated_kw NUMERIC NOT NULL CHECK (rated_kw > 0), measured_kw NUMERIC CHECK (measured_kw IS NULL OR measured_kw > 0),
    starting_kva NUMERIC CHECK (starting_kva IS NULL OR starting_kva > 0), power_factor NUMERIC CHECK (power_factor IS NULL OR (power_factor > 0 AND power_factor <= 1)),
    start_method TEXT CHECK (start_method IS NULL OR start_method IN ('vfd','soft_starter','star_delta','direct_on_line')),
    starting_multiplier NUMERIC CHECK (starting_multiplier IS NULL OR starting_multiplier > 0), priority SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 99),
    interruptible BOOLEAN NOT NULL DEFAULT false, minimum_runtime_minutes INTEGER CHECK (minimum_runtime_minutes IS NULL OR minimum_runtime_minutes >= 0),
    minimum_off_minutes INTEGER CHECK (minimum_off_minutes IS NULL OR minimum_off_minutes >= 0),
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    evidence_digest CHAR(64) CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'), evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (id, tenant_id),
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS canonical_energy_capabilities (
    capability_id TEXT PRIMARY KEY, tenant_id UUID NOT NULL, project_id UUID NOT NULL, energy_system_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified','degraded','blocked')), operational_eligible BOOLEAN NOT NULL DEFAULT false,
    battery_soc_percent NUMERIC, reserve_soc_percent NUMERIC, inverter_continuous_kw NUMERIC, inverter_peak_kva NUMERIC,
    capability_digest CHAR(64) NOT NULL CHECK (capability_digest ~ '^[0-9a-f]{64}$'), payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (tenant_id, energy_system_id, capability_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS hourly_energy_envelopes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL, capability_id TEXT NOT NULL,
    hour TIMESTAMPTZ NOT NULL, pv_available_kw NUMERIC NOT NULL CHECK (pv_available_kw >= 0),
    battery_soc_percent NUMERIC NOT NULL CHECK (battery_soc_percent BETWEEN 0 AND 100),
    maximum_continuous_load_kw NUMERIC NOT NULL CHECK (maximum_continuous_load_kw >= 0), maximum_starting_kva NUMERIC NOT NULL CHECK (maximum_starting_kva >= 0),
    permitted_load_ids JSONB NOT NULL DEFAULT '[]'::jsonb, blocked_loads JSONB NOT NULL DEFAULT '[]'::jsonb,
    energy_cost_per_kwh NUMERIC NOT NULL DEFAULT 0 CHECK (energy_cost_per_kwh >= 0), renewable_fraction NUMERIC NOT NULL CHECK (renewable_fraction BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (tenant_id, capability_id, hour),
    FOREIGN KEY (capability_id) REFERENCES canonical_energy_capabilities(capability_id) ON DELETE CASCADE
);

DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY[
'irrigation_pv_arrays','irrigation_hybrid_inverters','irrigation_battery_systems','irrigation_generators','irrigation_grid_connections','irrigation_energy_loads','canonical_energy_capabilities','hourly_energy_envelopes'
] LOOP
EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t); EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))$p$, t); END LOOP; END $$;
COMMIT;
