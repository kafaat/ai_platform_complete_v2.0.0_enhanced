-- M4 governed variable-rate irrigation prescription.
CREATE TABLE IF NOT EXISTS vri_prescriptions (
    tenant_id UUID NOT NULL,
    prescription_id UUID NOT NULL DEFAULT gen_random_uuid(),
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    machine_id UUID NOT NULL,
    hourly_mpc_schedule_digest CHAR(64) NOT NULL,
    irrigation_capability_digest CHAR(64) NOT NULL,
    commissioning_executability_digest CHAR(64) NOT NULL,
    management_zone_set_digest CHAR(64) NOT NULL,
    machine_geometry_digest CHAR(64) NOT NULL,
    sprinkler_capability_digest CHAR(64) NOT NULL,
    terrain_profile_digest CHAR(64) NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified', 'degraded', 'blocked')),
    decision TEXT NOT NULL CHECK (decision IN ('prescribe', 'hold', 'blocked')),
    recommendation_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (recommendation_only = TRUE),
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (execution_allowed = FALSE),
    translation_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (translation_allowed = FALSE),
    planned_uniform_depth_mm DOUBLE PRECISION NOT NULL CHECK (planned_uniform_depth_mm >= 0),
    prescribed_average_depth_mm DOUBLE PRECISION NOT NULL CHECK (prescribed_average_depth_mm >= 0),
    prescribed_volume_m3 DOUBLE PRECISION NOT NULL CHECK (prescribed_volume_m3 >= 0),
    uncovered_budget_mm DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (uncovered_budget_mm >= 0),
    payload JSONB NOT NULL,
    prescription_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, prescription_id),
    UNIQUE (tenant_id, prescription_digest)
);

CREATE TABLE IF NOT EXISTS vri_prescription_zones (
    tenant_id UUID NOT NULL,
    prescription_id UUID NOT NULL,
    zone_id TEXT NOT NULL,
    area_ha DOUBLE PRECISION NOT NULL CHECK (area_ha > 0),
    start_angle_deg DOUBLE PRECISION NOT NULL CHECK (start_angle_deg >= 0 AND start_angle_deg < 360),
    end_angle_deg DOUBLE PRECISION NOT NULL CHECK (end_angle_deg > 0 AND end_angle_deg <= 360),
    inner_radius_m DOUBLE PRECISION NOT NULL CHECK (inner_radius_m >= 0),
    outer_radius_m DOUBLE PRECISION NOT NULL CHECK (outer_radius_m > inner_radius_m),
    target_depth_mm DOUBLE PRECISION NOT NULL CHECK (target_depth_mm >= 0),
    target_volume_m3 DOUBLE PRECISION NOT NULL CHECK (target_volume_m3 >= 0),
    application_percent DOUBLE PRECISION NOT NULL CHECK (application_percent >= 0 AND application_percent <= 200),
    priority_score DOUBLE PRECISION NOT NULL CHECK (priority_score >= 0),
    source_zone_digest CHAR(64) NOT NULL,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (tenant_id, prescription_id, zone_id),
    FOREIGN KEY (tenant_id, prescription_id)
      REFERENCES vri_prescriptions (tenant_id, prescription_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vri_machine_translation_artifacts (
    tenant_id UUID NOT NULL,
    artifact_id UUID NOT NULL DEFAULT gen_random_uuid(),
    prescription_id UUID NOT NULL,
    adapter_name TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    artifact_status TEXT NOT NULL CHECK (artifact_status IN ('draft', 'validated', 'rejected')),
    translation_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (translation_allowed = FALSE),
    dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (dispatch_allowed = FALSE),
    artifact_digest CHAR(64) NOT NULL,
    artifact_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, artifact_id),
    FOREIGN KEY (tenant_id, prescription_id)
      REFERENCES vri_prescriptions (tenant_id, prescription_id) ON DELETE RESTRICT,
    UNIQUE (tenant_id, artifact_digest)
);

CREATE TABLE IF NOT EXISTS vri_as_applied_variances (
    tenant_id UUID NOT NULL,
    variance_id UUID NOT NULL DEFAULT gen_random_uuid(),
    prescription_id UUID NOT NULL,
    as_applied_truth_digest CHAR(64) NOT NULL,
    prescribed_volume_m3 DOUBLE PRECISION NOT NULL CHECK (prescribed_volume_m3 >= 0),
    applied_volume_m3 DOUBLE PRECISION NOT NULL CHECK (applied_volume_m3 >= 0),
    volume_variance_percent DOUBLE PRECISION,
    spatial_coverage_percent DOUBLE PRECISION CHECK (spatial_coverage_percent BETWEEN 0 AND 100),
    verification_status TEXT NOT NULL CHECK (verification_status IN ('pending', 'verified', 'degraded', 'rejected')),
    variance_digest CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, variance_id),
    FOREIGN KEY (tenant_id, prescription_id)
      REFERENCES vri_prescriptions (tenant_id, prescription_id) ON DELETE RESTRICT,
    UNIQUE (tenant_id, variance_digest)
);

CREATE INDEX IF NOT EXISTS idx_vri_prescriptions_field_season
  ON vri_prescriptions (tenant_id, field_id, season_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vri_prescriptions_machine
  ON vri_prescriptions (tenant_id, machine_id, created_at DESC);

ALTER TABLE vri_prescriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE vri_prescriptions FORCE ROW LEVEL SECURITY;
ALTER TABLE vri_prescription_zones ENABLE ROW LEVEL SECURITY;
ALTER TABLE vri_prescription_zones FORCE ROW LEVEL SECURITY;
ALTER TABLE vri_machine_translation_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE vri_machine_translation_artifacts FORCE ROW LEVEL SECURITY;
ALTER TABLE vri_as_applied_variances ENABLE ROW LEVEL SECURITY;
ALTER TABLE vri_as_applied_variances FORCE ROW LEVEL SECURITY;

CREATE POLICY vri_prescriptions_tenant_policy ON vri_prescriptions
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY vri_prescription_zones_tenant_policy ON vri_prescription_zones
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY vri_translation_artifacts_tenant_policy ON vri_machine_translation_artifacts
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY vri_as_applied_variances_tenant_policy ON vri_as_applied_variances
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
