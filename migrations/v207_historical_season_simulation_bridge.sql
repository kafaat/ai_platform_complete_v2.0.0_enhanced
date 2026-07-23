-- v207: HISTORICAL-SEASON-BRIDGE-01
-- جسر صغير بين سجلّ الدفتر التاريخي (v201) والموسم التشغيلي (v32)، مع سجلّ
-- append-only لتشغيلات المحاكاة. لا خدمة/محرك جديد ولا نسخ لبيانات المصادر.
--
-- يُدرج قبل v206 في MANIFEST رغم رقمه: v206 حارس catalog نهائي ويجب أن يبقى
-- آخر ملف مطبّق دائمًا كي يفحص RLS للجداول الجديدة.

CREATE TABLE IF NOT EXISTS season_record_links (
    link_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    season_record_id     UUID NOT NULL REFERENCES season_records(id),
    canonical_season_id  VARCHAR(50) NOT NULL REFERENCES seasons(season_id),
    field_id             VARCHAR(50) NOT NULL,
    link_status          TEXT NOT NULL DEFAULT 'active'
                         CHECK (link_status IN ('active', 'superseded')),
    linkage_reason       TEXT,
    linked_by            TEXT NOT NULL,
    linked_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes_link_id   UUID REFERENCES season_record_links(link_id),
    UNIQUE (tenant_id, season_record_id, canonical_season_id)
);
CREATE INDEX IF NOT EXISTS ix_season_record_links_tenant_season
    ON season_record_links (tenant_id, canonical_season_id, link_status);

CREATE OR REPLACE FUNCTION validate_season_record_link() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  record_row record;
  canonical_row record;
  previous_row record;
BEGIN
  SELECT tenant_id, field_id, trust_status
    INTO record_row
    FROM season_records
   WHERE id = NEW.season_record_id;
  IF NOT FOUND OR record_row.trust_status <> 'accepted' THEN
    RAISE EXCEPTION 'season_record_link: only an accepted season record may be linked';
  END IF;

  SELECT tenant_id, field_id
    INTO canonical_row
    FROM seasons
   WHERE season_id = NEW.canonical_season_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'season_record_link: canonical season not found';
  END IF;

  IF record_row.tenant_id <> NEW.tenant_id
     OR canonical_row.tenant_id <> NEW.tenant_id
     OR record_row.field_id <> canonical_row.field_id
     OR NEW.field_id <> canonical_row.field_id THEN
    RAISE EXCEPTION 'season_record_link: tenant/field ownership mismatch';
  END IF;
  IF NEW.supersedes_link_id IS NOT NULL THEN
    SELECT tenant_id, field_id INTO previous_row
      FROM season_record_links WHERE link_id = NEW.supersedes_link_id;
    IF NOT FOUND OR previous_row.tenant_id <> NEW.tenant_id
       OR previous_row.field_id <> NEW.field_id THEN
      RAISE EXCEPTION 'season_record_link: invalid cross-tenant/field supersession';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_validate_season_record_link ON season_record_links;
CREATE TRIGGER trg_validate_season_record_link
  BEFORE INSERT ON season_record_links
  FOR EACH ROW EXECUTE FUNCTION validate_season_record_link();

CREATE OR REPLACE FUNCTION historical_season_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only; correction requires a superseding record', TG_TABLE_NAME;
END;
$$;
DROP TRIGGER IF EXISTS trg_season_record_links_append_only ON season_record_links;
CREATE TRIGGER trg_season_record_links_append_only
  BEFORE UPDATE OR DELETE ON season_record_links
  FOR EACH ROW EXECUTE FUNCTION historical_season_append_only();

CREATE TABLE IF NOT EXISTS season_simulation_runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    field_id            VARCHAR(50) NOT NULL,
    season_id           VARCHAR(50) NOT NULL REFERENCES seasons(season_id),
    mode                TEXT NOT NULL DEFAULT 'operational'
                        CHECK (mode IN ('operational', 'historical_hindcast', 'what_if')),
    as_of_time          TIMESTAMPTZ,
    input_digest        TEXT NOT NULL CHECK (input_digest ~ '^[a-fA-F0-9]{64}$'),
    context_snapshot    JSONB NOT NULL,
    engine_name         TEXT NOT NULL,
    engine_version      TEXT NOT NULL,
    parameter_version   TEXT NOT NULL,
    result              JSONB NOT NULL,
    confidence          NUMERIC NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    assumptions         JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_season_simulation_runs_tenant_season
    ON season_simulation_runs (tenant_id, season_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_season_simulation_runs_input_digest
    ON season_simulation_runs (tenant_id, input_digest);

DROP TRIGGER IF EXISTS trg_season_simulation_runs_append_only ON season_simulation_runs;
CREATE TRIGGER trg_season_simulation_runs_append_only
  BEFORE UPDATE OR DELETE ON season_simulation_runs
  FOR EACH ROW EXECUTE FUNCTION historical_season_append_only();

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['season_record_links', 'season_simulation_runs']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I '
      'USING (tenant_id::text = public.sahool_effective_tenant_id()) '
      'WITH CHECK (tenant_id::text = public.sahool_effective_tenant_id())',
      t
    );
  END LOOP;
END $$;

COMMENT ON TABLE season_record_links IS
  'HISTORICAL-SEASON-BRIDGE-01: immutable tenant/field-validated link from an accepted manual season record to the canonical operational season.';
COMMENT ON TABLE season_simulation_runs IS
  'HISTORICAL-SEASON-BRIDGE-01: append-only reproducible simulation ledger; seasons.sim_* remains the latest operational projection.';
