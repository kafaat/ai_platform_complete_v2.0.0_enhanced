-- v273: soil-service's stored copies of AI soil-sampling plans (gap P6, sampling plan provenance).
-- Owner and only writer: soil-service (owner decision 2026-11-13; it already owns
-- soil_sampling_plans). The platform never reads this table: its lab-sample route asks
-- soil-service to resolve a plan point, and stores the origin soil-service returns.
-- A copy is immutable once recorded (the plan id is a digest of the plan's points), so a stored
-- plan point cannot be moved after a sample has been taken against it. The table is append-only:
-- the trigger refuses UPDATE and DELETE, because a DELETE followed by a new INSERT under the same
-- plan_id would move the point as surely as an UPDATE (lab receipt on #1456).
-- Re-run safe: IF NOT EXISTS, policy and trigger dropped before they are created.
BEGIN;
SET LOCAL lock_timeout='15s';
CREATE TABLE IF NOT EXISTS soil_sampling_plan_copies (
  tenant_id UUID NOT NULL,
  plan_id VARCHAR(64) NOT NULL CHECK (length(btrim(plan_id)) BETWEEN 1 AND 64),
  field_id VARCHAR(64) NOT NULL CHECK (length(btrim(field_id)) BETWEEN 1 AND 64),
  plan JSONB NOT NULL CHECK (jsonb_typeof(plan) = 'object'),
  sample_points JSONB NOT NULL
    CHECK (jsonb_typeof(sample_points) = 'array' AND jsonb_array_length(sample_points) BETWEEN 1 AND 500),
  plan_digest CHAR(64) NOT NULL CHECK (plan_digest ~ '^[0-9a-f]{64}$'),
  source VARCHAR(64) NOT NULL CHECK (length(btrim(source)) BETWEEN 1 AND 64),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, plan_id)
);
CREATE INDEX IF NOT EXISTS idx_soil_sampling_plan_copies_field
  ON soil_sampling_plan_copies(tenant_id, field_id, recorded_at DESC);
ALTER TABLE soil_sampling_plan_copies ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_sampling_plan_copies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS soil_sampling_plan_copies_tenant ON soil_sampling_plan_copies;
CREATE POLICY soil_sampling_plan_copies_tenant ON soil_sampling_plan_copies
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
CREATE OR REPLACE FUNCTION soil_sampling_plan_copy_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  RAISE EXCEPTION 'soil_sampling_plan_copy_immutable' USING ERRCODE = '55000';
END; $$;
DROP TRIGGER IF EXISTS soil_sampling_plan_copies_immutable ON soil_sampling_plan_copies;
CREATE TRIGGER soil_sampling_plan_copies_immutable BEFORE UPDATE OR DELETE ON soil_sampling_plan_copies
  FOR EACH ROW EXECUTE FUNCTION soil_sampling_plan_copy_immutable();
REVOKE ALL ON soil_sampling_plan_copies FROM PUBLIC;
-- A plan copy is stored only if every plan point lies inside the field's stored geometry
-- (review of #1456: the planner takes its bbox/boundary from tool-call parameters, so without this
-- check a tenant user could have a plan 66 km away stored as trusted). soil-service cannot read
-- fields (RLS), so this SECURITY DEFINER function answers one boolean and returns no field data.
-- It answers only for a field of p_tenant_id, so it is no oracle on another tenant's geometry.
-- p_points is a JSON array of [lon, lat]. A missing or foreign field, a field without geometry, an
-- empty or malformed list ⇒ false (fail closed). search_path is pg_catalog, pg_temp: every PostGIS
-- name is public-qualified and literals are typed, so nothing planted in public can be resolved
-- while the function runs as its owner (lab receipt on #1456: a planted public.>= ran as owner).
-- An earlier draft of v273 created a 3-argument form with public in its search_path and no
-- tenant check; drop it so no database that ran that draft keeps it beside this one.
DROP FUNCTION IF EXISTS sahool_field_covers_points(text, jsonb, double precision);
CREATE OR REPLACE FUNCTION sahool_field_covers_points(
  p_tenant_id text, p_field_id text, p_points jsonb, p_buffer_m double precision
) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT COALESCE(
    pg_catalog.jsonb_typeof(p_points) = 'array'::text
    AND pg_catalog.jsonb_array_length(p_points) >= 1::integer
    AND pg_catalog.jsonb_array_length(p_points) <= 500::integer
    AND p_buffer_m >= 0::double precision
    AND p_buffer_m <= 500::double precision
    AND (
      SELECT pg_catalog.bool_and(
        pg_catalog.jsonb_typeof(pt) = 'array'::text
        AND pg_catalog.jsonb_array_length(pt) = 2::integer
        AND public.ST_DWithin(
          f.geom::public.geography,
          public.ST_SetSRID(
            public.ST_MakePoint(
              (pt OPERATOR(pg_catalog.->>) 0)::double precision,
              (pt OPERATOR(pg_catalog.->>) 1)::double precision
            ),
            4326::integer
          )::public.geography,
          p_buffer_m
        )
      )
      FROM public.fields f
      CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(p_points) AS pt
      WHERE f.field_id::text OPERATOR(pg_catalog.=) p_field_id
        AND f.tenant_id::text OPERATOR(pg_catalog.=) p_tenant_id
        -- The argument alone is caller-chosen: any connection holding EXECUTE could pass
        -- another tenant's id and learn whether a point lies in its field (lab, main
        -- 8b5300c40). The tenant must also be the connection's own app.current_tenant;
        -- with none set, nothing matches.
        AND p_tenant_id OPERATOR(pg_catalog.=)
            NULLIF(pg_catalog.current_setting('app.current_tenant'::text, true), ''::text)
        AND f.geom IS NOT NULL
    ),
    false
  )
$$;
REVOKE ALL ON FUNCTION sahool_field_covers_points(text, text, jsonb, double precision) FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_app') THEN
    GRANT EXECUTE ON FUNCTION sahool_field_covers_points(text, text, jsonb, double precision)
      TO sahool_app;
  END IF;
END $$;
COMMENT ON TABLE soil_sampling_plan_copies IS
  'soil-service copy of each AI soil-sampling plan; lab-sample plan origins are resolved from it. v273.';
COMMIT;
