-- v168: Irrigation Engineering Foundation (M2.1) — renumbered from v167 (v167 taken by MPC content_digest lineage)
-- Manufacturer-neutral, tenant-bound design/commissioned/live asset contracts.
-- No controller credentials or secrets are stored here.
BEGIN;

CREATE TABLE IF NOT EXISTS irrigation_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    farm_id TEXT,
    field_id TEXT,
    season_id TEXT,
    name TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL DEFAULT 'draft'
      CHECK (lifecycle_state IN ('draft','designed','procured','installed','commissioning','certified','operational','degraded','blocked','maintenance','retired')),
    schema_version TEXT NOT NULL DEFAULT '1.0',
    timezone TEXT NOT NULL DEFAULT 'Asia/Aden',
    design_basis JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id)
);

CREATE TABLE IF NOT EXISTS irrigation_water_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('well','reservoir','canal','river','municipal','rainwater','other')),
    name TEXT NOT NULL,
    design_max_flow_lps NUMERIC CHECK (design_max_flow_lps IS NULL OR design_max_flow_lps >= 0),
    commissioned_max_flow_lps NUMERIC CHECK (commissioned_max_flow_lps IS NULL OR commissioned_max_flow_lps >= 0),
    live_max_flow_lps NUMERIC CHECK (live_max_flow_lps IS NULL OR live_max_flow_lps >= 0),
    daily_allocation_m3 NUMERIC CHECK (daily_allocation_m3 IS NULL OR daily_allocation_m3 >= 0),
    seasonal_allocation_m3 NUMERIC CHECK (seasonal_allocation_m3 IS NULL OR seasonal_allocation_m3 >= 0),
    water_ec_ds_m NUMERIC CHECK (water_ec_ds_m IS NULL OR water_ec_ds_m >= 0),
    quality_state TEXT NOT NULL DEFAULT 'unknown' CHECK (quality_state IN ('unknown','estimated','measured','field_validated','certified')),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_wells (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    water_source_id UUID NOT NULL,
    name TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    casing_diameter_mm NUMERIC CHECK (casing_diameter_mm IS NULL OR casing_diameter_mm > 0),
    total_depth_m NUMERIC CHECK (total_depth_m IS NULL OR total_depth_m >= 0),
    pump_setting_depth_m NUMERIC CHECK (pump_setting_depth_m IS NULL OR pump_setting_depth_m >= 0),
    static_level_m NUMERIC CHECK (static_level_m IS NULL OR static_level_m >= 0),
    dynamic_level_m NUMERIC CHECK (dynamic_level_m IS NULL OR dynamic_level_m >= 0),
    sustainable_flow_lps NUMERIC CHECK (sustainable_flow_lps IS NULL OR sustainable_flow_lps >= 0),
    last_pumping_test_at TIMESTAMPTZ,
    design_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    commissioned_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (water_source_id, tenant_id) REFERENCES irrigation_water_sources(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_pumps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    water_source_id UUID,
    well_id UUID,
    name TEXT NOT NULL,
    pump_type TEXT NOT NULL CHECK (pump_type IN ('submersible','vertical_turbine','centrifugal','booster','surface','other')),
    manufacturer TEXT,
    model TEXT,
    rated_flow_lps NUMERIC CHECK (rated_flow_lps IS NULL OR rated_flow_lps >= 0),
    rated_head_m NUMERIC CHECK (rated_head_m IS NULL OR rated_head_m >= 0),
    rated_power_kw NUMERIC CHECK (rated_power_kw IS NULL OR rated_power_kw >= 0),
    motor_efficiency NUMERIC CHECK (motor_efficiency IS NULL OR motor_efficiency > 0 AND motor_efficiency <= 1),
    pump_efficiency NUMERIC CHECK (pump_efficiency IS NULL OR pump_efficiency > 0 AND pump_efficiency <= 1),
    drive_type TEXT CHECK (drive_type IS NULL OR drive_type IN ('direct_online','soft_starter','vfd','dc_solar','hydraulic','other')),
    curve_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    design_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    commissioned_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (water_source_id, tenant_id) REFERENCES irrigation_water_sources(id, tenant_id),
    FOREIGN KEY (well_id, tenant_id) REFERENCES irrigation_wells(id, tenant_id)
);

CREATE TABLE IF NOT EXISTS irrigation_mainlines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    pump_id UUID,
    name TEXT NOT NULL,
    geometry JSONB,
    length_m NUMERIC NOT NULL CHECK (length_m >= 0),
    internal_diameter_mm NUMERIC NOT NULL CHECK (internal_diameter_mm > 0),
    material TEXT NOT NULL,
    pressure_rating_bar NUMERIC CHECK (pressure_rating_bar IS NULL OR pressure_rating_bar > 0),
    hazen_williams_c NUMERIC CHECK (hazen_williams_c IS NULL OR hazen_williams_c > 0),
    roughness_m NUMERIC CHECK (roughness_m IS NULL OR roughness_m >= 0),
    elevation_start_m NUMERIC,
    elevation_end_m NUMERIC,
    minor_loss_coefficient NUMERIC NOT NULL DEFAULT 0 CHECK (minor_loss_coefficient >= 0),
    design_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    commissioned_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (pump_id, tenant_id) REFERENCES irrigation_pumps(id, tenant_id)
);

CREATE TABLE IF NOT EXISTS irrigation_machines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    field_id TEXT,
    name TEXT NOT NULL,
    machine_type TEXT NOT NULL CHECK (machine_type IN ('center_pivot','sector_pivot','linear_move','towable_linear','ditch_feed','hose_feed','swing_around','corner_arm','drip','fixed_sprinkler','other')),
    manufacturer TEXT,
    model TEXT,
    drive_type TEXT CHECK (drive_type IS NULL OR drive_type IN ('electric_stop_start','electric_variable_speed','hydrostatic_continuous','hydraulic','other')),
    center_geometry JSONB,
    travel_path_geometry JSONB,
    coverage_geometry JSONB,
    length_m NUMERIC CHECK (length_m IS NULL OR length_m >= 0),
    design_flow_lps NUMERIC CHECK (design_flow_lps IS NULL OR design_flow_lps >= 0),
    design_inlet_pressure_bar NUMERIC CHECK (design_inlet_pressure_bar IS NULL OR design_inlet_pressure_bar >= 0),
    full_revolution_hours NUMERIC CHECK (full_revolution_hours IS NULL OR full_revolution_hours > 0),
    capability_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    lifecycle_state TEXT NOT NULL DEFAULT 'draft' CHECK (lifecycle_state IN ('draft','configured','connected','calibrated','certified','operational','degraded','blocked','offline','maintenance','retired')),
    design_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    commissioned_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_controllers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    machine_id UUID,
    pump_id UUID,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    controller_model TEXT,
    serial_number TEXT,
    firmware_version TEXT,
    protocol TEXT CHECK (protocol IS NULL OR protocol IN ('mqtt','modbus_tcp','modbus_rtu','http','opcua','vendor_api','local_plc','other')),
    integration_mode TEXT NOT NULL DEFAULT 'read_only' CHECK (integration_mode IN ('read_only','dry_run','human_approved_control','guarded_automation')),
    credential_reference TEXT,
    capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
    connection_state TEXT NOT NULL DEFAULT 'unconfigured' CHECK (connection_state IN ('unconfigured','configured','connected','degraded','offline','revoked')),
    last_verified_at TIMESTAMPTZ,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id),
    FOREIGN KEY (pump_id, tenant_id) REFERENCES irrigation_pumps(id, tenant_id),
    CHECK (credential_reference IS NULL OR credential_reference !~* '(password|secret|token)=')
);

CREATE TABLE IF NOT EXISTS irrigation_energy_systems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    name TEXT NOT NULL,
    system_type TEXT NOT NULL CHECK (system_type IN ('grid','generator','solar_direct','solar_battery','solar_generator_hybrid','solar_grid_hybrid','multi_source')),
    pv_capacity_kwp NUMERIC CHECK (pv_capacity_kwp IS NULL OR pv_capacity_kwp >= 0),
    inverter_continuous_kw NUMERIC CHECK (inverter_continuous_kw IS NULL OR inverter_continuous_kw >= 0),
    inverter_peak_kw NUMERIC CHECK (inverter_peak_kw IS NULL OR inverter_peak_kw >= 0),
    battery_chemistry TEXT CHECK (battery_chemistry IS NULL OR battery_chemistry IN ('lifepo4','nmc','lead_acid','other')),
    battery_nominal_kwh NUMERIC CHECK (battery_nominal_kwh IS NULL OR battery_nominal_kwh >= 0),
    battery_usable_kwh NUMERIC CHECK (battery_usable_kwh IS NULL OR battery_usable_kwh >= 0),
    battery_continuous_kw NUMERIC CHECK (battery_continuous_kw IS NULL OR battery_continuous_kw >= 0),
    battery_peak_kw NUMERIC CHECK (battery_peak_kw IS NULL OR battery_peak_kw >= 0),
    minimum_soc_percent NUMERIC CHECK (minimum_soc_percent IS NULL OR minimum_soc_percent BETWEEN 0 AND 100),
    emergency_reserve_percent NUMERIC CHECK (emergency_reserve_percent IS NULL OR emergency_reserve_percent BETWEEN 0 AND 100),
    generator_continuous_kw NUMERIC CHECK (generator_continuous_kw IS NULL OR generator_continuous_kw >= 0),
    generator_starting_kva NUMERIC CHECK (generator_starting_kva IS NULL OR generator_starting_kva >= 0),
    nominal_voltage_v NUMERIC CHECK (nominal_voltage_v IS NULL OR nominal_voltage_v > 0),
    frequency_hz NUMERIC CHECK (frequency_hz IS NULL OR frequency_hz > 0),
    phases SMALLINT CHECK (phases IS NULL OR phases IN (1,3)),
    design_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    commissioned_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    CHECK (battery_usable_kwh IS NULL OR battery_nominal_kwh IS NULL OR battery_usable_kwh <= battery_nominal_kwh)
);

CREATE INDEX IF NOT EXISTS idx_irrigation_projects_scope ON irrigation_projects (tenant_id, farm_id, field_id, season_id);
CREATE INDEX IF NOT EXISTS idx_irrigation_sources_project ON irrigation_water_sources (tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_irrigation_wells_source ON irrigation_wells (tenant_id, water_source_id);
CREATE INDEX IF NOT EXISTS idx_irrigation_pumps_project ON irrigation_pumps (tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_irrigation_mainlines_project ON irrigation_mainlines (tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_irrigation_machines_field ON irrigation_machines (tenant_id, field_id);
CREATE INDEX IF NOT EXISTS idx_irrigation_controllers_machine ON irrigation_controllers (tenant_id, machine_id);
CREATE INDEX IF NOT EXISTS idx_irrigation_energy_project ON irrigation_energy_systems (tenant_id, project_id);

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'irrigation_projects','irrigation_water_sources','irrigation_wells','irrigation_pumps',
    'irrigation_mainlines','irrigation_machines','irrigation_controllers','irrigation_energy_systems'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    -- Fail-closed on BOTH read and write: an empty/unset app.current_tenant makes NULLIF
    -- return NULL, so `tenant_id = NULL` is never true → no cross-tenant read OR write. The
    -- prior WITH CHECK had an `IS NULL OR …` escape that let a session with no tenant context
    -- INSERT any tenant_id (fail-open write injection). Matches the canonical soil pattern.
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
      USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
      WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))$p$, t);
  END LOOP;
END $$;

COMMENT ON TABLE irrigation_projects IS 'M2.1 irrigation engineering project root; tenant-bound, manufacturer-neutral, versioned.';
COMMENT ON COLUMN irrigation_controllers.credential_reference IS 'Opaque reference to an external secret manager; never a raw password/token/secret.';
COMMENT ON COLUMN irrigation_machines.capability_profile IS 'Versioned vendor-neutral declared capabilities; certification occurs separately.';

COMMIT;
