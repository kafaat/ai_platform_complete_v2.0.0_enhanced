-- AC-6/AC-6.1 (delivered as migrations 019+020, reconciled onto the landed AC-1 schema):
-- direct agronomic lineage on decision_record + a first-class immutable vegetation-evidence
-- store WITH its writer (closes gap VEG-EVIDENCE-STORE) + tenant-safe DB-level integrity:
-- tenant-composite foreign keys, a semantic field/season validation trigger, and tenant RLS.
-- Note: the delivered bundle referenced its own (never-landed) 018 tables
-- decision_agronomic_context_snapshots (weaker shape) / decision_field_history_snapshots;
-- here every reference targets the landed AC-1 contracts instead
-- (decision_field_historical_context_snapshots, decision_feature_manifests).

-- 1) Direct lineage columns (agronomic_context_snapshot_id / field_historical_context_snapshot_id /
--    feature_manifest_id already exist from 018_ac1).
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS season_id text;
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS crop_id text;
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS cultivar_id text;
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS vegetation_snapshot_id text;
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS feature_manifest_hash text;
CREATE INDEX IF NOT EXISTS idx_decision_agronomic_lineage ON decision_record
 (tenant_id, field_id, season_id, crop_id, cultivar_id, created_at DESC);

-- 2) Immutable vegetation evidence snapshots (content-addressed via snapshot_hash; the
--    point-in-time invariant lives in the row: data can never be "available" before capture).
CREATE TABLE IF NOT EXISTS decision_vegetation_snapshots (
 snapshot_id text PRIMARY KEY, tenant_id uuid NOT NULL, field_id text NOT NULL,
 season_id text, contract_version text NOT NULL, snapshot_hash text NOT NULL,
 acquisition_at timestamptz NOT NULL, data_available_at timestamptz NOT NULL,
 quality_gate jsonb NOT NULL, feature_manifest jsonb NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id, snapshot_hash),
 CHECK (snapshot_hash ~ '^[a-fA-F0-9]{64}$'),
 CHECK (data_available_at >= acquisition_at)
);
CREATE INDEX IF NOT EXISTS idx_veg_snapshot_field_time
  ON decision_vegetation_snapshots(tenant_id, field_id, acquisition_at DESC);
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname='decision_wx11_completion_append_only') THEN
    EXECUTE 'DROP TRIGGER IF EXISTS trg_decision_vegetation_snapshots_append_only ON decision_vegetation_snapshots';
    EXECUTE 'CREATE TRIGGER trg_decision_vegetation_snapshots_append_only BEFORE UPDATE OR DELETE ON decision_vegetation_snapshots FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only()';
  END IF;
END $$;

-- 3) Composite (tenant_id, id) uniqueness so foreign keys can be tenant-scoped: a guessed or
--    replayed snapshot ID from another tenant can never satisfy the reference.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ag_context_tenant_snapshot
  ON decision_agronomic_context_snapshots (tenant_id, snapshot_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_history_tenant_snapshot
  ON decision_field_historical_context_snapshots (tenant_id, historical_snapshot_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_manifest_tenant_id
  ON decision_feature_manifests (tenant_id, feature_manifest_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_vegetation_tenant_snapshot
  ON decision_vegetation_snapshots (tenant_id, snapshot_id);

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_decision_ag_context_tenant') THEN
    ALTER TABLE decision_record
      ADD CONSTRAINT fk_decision_ag_context_tenant
      FOREIGN KEY (tenant_id, agronomic_context_snapshot_id)
      REFERENCES decision_agronomic_context_snapshots (tenant_id, snapshot_id)
      NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_decision_history_snapshot_tenant') THEN
    ALTER TABLE decision_record
      ADD CONSTRAINT fk_decision_history_snapshot_tenant
      FOREIGN KEY (tenant_id, field_historical_context_snapshot_id)
      REFERENCES decision_field_historical_context_snapshots (tenant_id, historical_snapshot_id)
      NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_decision_feature_manifest_tenant') THEN
    ALTER TABLE decision_record
      ADD CONSTRAINT fk_decision_feature_manifest_tenant
      FOREIGN KEY (tenant_id, feature_manifest_id)
      REFERENCES decision_feature_manifests (tenant_id, feature_manifest_id)
      NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_decision_vegetation_snapshot_tenant') THEN
    ALTER TABLE decision_record
      ADD CONSTRAINT fk_decision_vegetation_snapshot_tenant
      FOREIGN KEY (tenant_id, vegetation_snapshot_id)
      REFERENCES decision_vegetation_snapshots (tenant_id, snapshot_id)
      NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_decision_feature_manifest_hash') THEN
    ALTER TABLE decision_record
      ADD CONSTRAINT ck_decision_feature_manifest_hash
      CHECK (feature_manifest_hash IS NULL OR feature_manifest_hash ~ '^[a-fA-F0-9]{64}$')
      NOT VALID;
  END IF;
END $$;

-- 4) Semantic evidence consistency: a decision may never bind evidence captured for a different
--    field, a contradicting season, or a manifest whose content hash disagrees with the claim.
--    Season policy: a mismatch requires BOTH sides to declare a season (legacy decisions without
--    season_id keep working; a decision that declares a season must match its evidence).
CREATE OR REPLACE FUNCTION decision_validate_agronomic_lineage()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  ev_field text;
  ev_season text;
  manifest_hash text;
BEGIN
  IF NEW.agronomic_context_snapshot_id IS NOT NULL THEN
    SELECT field_id, season_id INTO ev_field, ev_season
      FROM decision_agronomic_context_snapshots
      WHERE tenant_id = NEW.tenant_id AND snapshot_id = NEW.agronomic_context_snapshot_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'agronomic context snapshot not found for tenant' USING ERRCODE = '23503';
    END IF;
    IF NEW.field_id IS DISTINCT FROM ev_field
       OR (NEW.season_id IS NOT NULL AND ev_season IS NOT NULL AND NEW.season_id <> ev_season) THEN
      RAISE EXCEPTION 'agronomic context field/season mismatch' USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.vegetation_snapshot_id IS NOT NULL THEN
    SELECT field_id, season_id INTO ev_field, ev_season
      FROM decision_vegetation_snapshots
      WHERE tenant_id = NEW.tenant_id AND snapshot_id = NEW.vegetation_snapshot_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'vegetation snapshot not found for tenant' USING ERRCODE = '23503';
    END IF;
    IF NEW.field_id IS DISTINCT FROM ev_field
       OR (NEW.season_id IS NOT NULL AND ev_season IS NOT NULL AND NEW.season_id <> ev_season) THEN
      RAISE EXCEPTION 'vegetation snapshot field/season mismatch' USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.field_historical_context_snapshot_id IS NOT NULL THEN
    SELECT field_id, season_id INTO ev_field, ev_season
      FROM decision_field_historical_context_snapshots
      WHERE tenant_id = NEW.tenant_id
        AND historical_snapshot_id = NEW.field_historical_context_snapshot_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'field history snapshot not found for tenant' USING ERRCODE = '23503';
    END IF;
    IF NEW.field_id IS DISTINCT FROM ev_field
       OR (NEW.season_id IS NOT NULL AND ev_season IS NOT NULL AND NEW.season_id <> ev_season) THEN
      RAISE EXCEPTION 'field history snapshot field/season mismatch' USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.feature_manifest_id IS NOT NULL AND NEW.feature_manifest_hash IS NOT NULL THEN
    SELECT content_hash INTO manifest_hash
      FROM decision_feature_manifests
      WHERE tenant_id = NEW.tenant_id AND feature_manifest_id = NEW.feature_manifest_id;
    IF FOUND AND lower(NEW.feature_manifest_hash) <> lower(manifest_hash) THEN
      RAISE EXCEPTION 'feature manifest hash mismatch' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_decision_validate_agronomic_lineage ON decision_record;
CREATE TRIGGER trg_decision_validate_agronomic_lineage
BEFORE INSERT OR UPDATE OF tenant_id, field_id, season_id,
  agronomic_context_snapshot_id, vegetation_snapshot_id,
  field_historical_context_snapshot_id, feature_manifest_id, feature_manifest_hash
ON decision_record
FOR EACH ROW EXECUTE FUNCTION decision_validate_agronomic_lineage();

-- 5) Tenant isolation for the authoritative decision + evidence tables. NOTE (honesty): the
--    service currently connects as the table owner, and owners bypass non-FORCE RLS — these
--    policies become enforcing once a dedicated non-owner runtime role is provisioned
--    (operator cutover step). Persistence binds app.current_tenant on every write already.
DO $$ DECLARE t text; BEGIN
 FOR t IN SELECT unnest(ARRAY[
   'decision_record',
   'decision_agronomic_context_snapshots',
   'decision_field_historical_context_snapshots',
   'decision_feature_manifests',
   'decision_feature_manifest_entries',
   'decision_vegetation_snapshots'
 ]) LOOP
   EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
   EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
   EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = nullif(current_setting(''app.current_tenant'', true), '''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.current_tenant'', true), '''')::uuid)', t);
 END LOOP;
END $$;
