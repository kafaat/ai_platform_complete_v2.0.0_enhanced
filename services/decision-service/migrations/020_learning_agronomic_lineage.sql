-- AC-9 (delivered 021, landed as 020): learning rows inherit the exact agronomic evidence
-- of their source decision. Retargeted onto the landed AC-1 contracts
-- (decision_field_historical_context_snapshots / field_historical_context_snapshot_id).
-- Deviation: RLS is ENABLEd with the tenant policy but NOT forced — the service connects
-- as the table owner today; FORCE lands with the non-owner runtime role (operator cutover).

ALTER TABLE decision_learning_attributions
  ADD COLUMN IF NOT EXISTS field_id text,
  ADD COLUMN IF NOT EXISTS season_id text,
  ADD COLUMN IF NOT EXISTS crop_id text,
  ADD COLUMN IF NOT EXISTS cultivar_id text,
  ADD COLUMN IF NOT EXISTS agronomic_context_snapshot_id text,
  ADD COLUMN IF NOT EXISTS vegetation_snapshot_id text,
  ADD COLUMN IF NOT EXISTS field_historical_context_snapshot_id text,
  ADD COLUMN IF NOT EXISTS feature_manifest_id text,
  ADD COLUMN IF NOT EXISTS feature_manifest_hash text;

CREATE INDEX IF NOT EXISTS idx_learning_attribution_agronomic_cohort
  ON decision_learning_attributions
  (tenant_id, model_id, crop_id, cultivar_id, season_id, attributed_at DESC);

CREATE INDEX IF NOT EXISTS idx_learning_attribution_context
  ON decision_learning_attributions
  (tenant_id, agronomic_context_snapshot_id, vegetation_snapshot_id, field_historical_context_snapshot_id);

DO $$ BEGIN
  ALTER TABLE decision_learning_attributions
    ADD CONSTRAINT fk_learning_ag_context_tenant
    FOREIGN KEY (tenant_id, agronomic_context_snapshot_id)
    REFERENCES decision_agronomic_context_snapshots (tenant_id, snapshot_id) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE decision_learning_attributions
    ADD CONSTRAINT fk_learning_vegetation_tenant
    FOREIGN KEY (tenant_id, vegetation_snapshot_id)
    REFERENCES decision_vegetation_snapshots (tenant_id, snapshot_id) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE decision_learning_attributions
    ADD CONSTRAINT fk_learning_history_tenant
    FOREIGN KEY (tenant_id, field_historical_context_snapshot_id)
    REFERENCES decision_field_historical_context_snapshots (tenant_id, historical_snapshot_id) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE decision_learning_attributions
    ADD CONSTRAINT ck_learning_feature_manifest_hash
    CHECK (feature_manifest_hash IS NULL OR feature_manifest_hash ~ '^[a-fA-F0-9]{64}$') NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE OR REPLACE FUNCTION enforce_learning_agronomic_lineage()
RETURNS trigger AS $$
DECLARE
  d decision_record%ROWTYPE;
BEGIN
  SELECT * INTO d
    FROM decision_record
   WHERE tenant_id = NEW.tenant_id AND decision_id = NEW.decision_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source decision not found for learning attribution';
  END IF;

  IF NEW.field_id IS DISTINCT FROM d.field_id
     OR NEW.season_id IS DISTINCT FROM d.season_id
     OR NEW.crop_id IS DISTINCT FROM d.crop_id
     OR NEW.cultivar_id IS DISTINCT FROM d.cultivar_id
     OR NEW.agronomic_context_snapshot_id IS DISTINCT FROM d.agronomic_context_snapshot_id
     OR NEW.vegetation_snapshot_id IS DISTINCT FROM d.vegetation_snapshot_id
     OR NEW.field_historical_context_snapshot_id IS DISTINCT FROM d.field_historical_context_snapshot_id
     OR NEW.feature_manifest_id IS DISTINCT FROM d.feature_manifest_id
     OR NEW.feature_manifest_hash IS DISTINCT FROM d.feature_manifest_hash THEN
    RAISE EXCEPTION 'learning attribution agronomic lineage must exactly match source decision';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_learning_agronomic_lineage ON decision_learning_attributions;
CREATE TRIGGER trg_learning_agronomic_lineage
  BEFORE INSERT ON decision_learning_attributions
  FOR EACH ROW EXECUTE FUNCTION enforce_learning_agronomic_lineage();

ALTER TABLE decision_learning_attributions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS learning_attribution_tenant_isolation ON decision_learning_attributions;
CREATE POLICY learning_attribution_tenant_isolation ON decision_learning_attributions
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
