-- M2.2 Canonical Root-Zone Hydraulic Profile
-- Unifies soil hydraulics + crop root policy into one tenant-bound irrigation truth.

CREATE TABLE IF NOT EXISTS crop_root_policies (
    policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    crop_id text NOT NULL,
    variety text NOT NULL DEFAULT '',
    initial_depth_m double precision NOT NULL CHECK (initial_depth_m > 0),
    maximum_depth_m double precision NOT NULL CHECK (maximum_depth_m >= initial_depth_m),
    effective_fraction double precision NOT NULL DEFAULT 0.80
        CHECK (effective_fraction > 0 AND effective_fraction <= 1),
    policy_version text NOT NULL,
    evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','validated','retired')),
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, crop_id, variety, policy_version),
    UNIQUE (tenant_id, policy_id)
);

CREATE TABLE IF NOT EXISTS canonical_root_zone_profiles (
    root_zone_profile_id text PRIMARY KEY,
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    season_id text NOT NULL,
    soil_hydraulic_profile_id text NOT NULL,
    source_soil_profile_hash text NOT NULL,
    root_policy_id uuid NOT NULL,
    effective_at timestamptz NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    quality_status text NOT NULL
        CHECK (quality_status IN ('verified','degraded','blocked')),
    operational_eligible boolean NOT NULL DEFAULT false,
    root_depth_m double precision,
    effective_root_zone_m double precision,
    taw_mm double precision,
    raw_fraction double precision,
    raw_mm double precision,
    infiltration_mm_h double precision,
    ksat_mm_h double precision,
    soil_ec_ds_m double precision,
    profile_digest char(64) NOT NULL CHECK (profile_digest ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, field_id, season_id, profile_digest),
    FOREIGN KEY (tenant_id, root_policy_id)
        REFERENCES crop_root_policies(tenant_id, policy_id)
);

CREATE INDEX IF NOT EXISTS idx_crop_root_policies_lookup
    ON crop_root_policies (tenant_id, crop_id, variety, status, valid_from DESC);
CREATE INDEX IF NOT EXISTS idx_root_zone_profiles_lookup
    ON canonical_root_zone_profiles (tenant_id, field_id, season_id, generated_at DESC);

ALTER TABLE crop_root_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE crop_root_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE canonical_root_zone_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_root_zone_profiles FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS crop_root_policies_tenant_isolation ON crop_root_policies;
CREATE POLICY crop_root_policies_tenant_isolation ON crop_root_policies
    USING (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));

DROP POLICY IF EXISTS canonical_root_zone_profiles_tenant_isolation ON canonical_root_zone_profiles;
CREATE POLICY canonical_root_zone_profiles_tenant_isolation ON canonical_root_zone_profiles
    USING (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));
