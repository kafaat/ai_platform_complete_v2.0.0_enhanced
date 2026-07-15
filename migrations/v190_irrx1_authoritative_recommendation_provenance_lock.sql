-- IRR-X1.5: authoritative recommendation/execution-plan provenance lock.
-- Manual execution may only be created from a decision-service plan registered by the BFF
-- after authoritative=true, persisted=true, approved review lineage, and plan digest proof.

CREATE TABLE IF NOT EXISTS irrigation_manual_execution_sources (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    execution_plan_id text NOT NULL,
    decision_id text NOT NULL,
    review_id text NOT NULL,
    candidate_lineage_id text NOT NULL,
    field_id text NOT NULL,
    season_id text NOT NULL,
    system_id text NOT NULL,
    target_depth_mm numeric NOT NULL CHECK (target_depth_mm > 0),
    target_volume_m3 numeric NOT NULL CHECK (target_volume_m3 > 0),
    nominal_flow_m3_h numeric CHECK (nominal_flow_m3_h IS NULL OR nominal_flow_m3_h > 0),
    valid_from timestamptz NOT NULL,
    valid_until timestamptz NOT NULL,
    water_truth_digest char(64) NOT NULL,
    plan_digest char(64) NOT NULL,
    source_payload jsonb NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_until > valid_from),
    CHECK (water_truth_digest ~ '^[0-9a-f]{64}$'),
    CHECK (plan_digest ~ '^[0-9a-f]{64}$'),
    UNIQUE (tenant_id, execution_plan_id),
    UNIQUE (tenant_id, plan_digest)
);

ALTER TABLE irrigation_manual_execution_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_manual_execution_sources FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS irrigation_manual_execution_sources_tenant ON irrigation_manual_execution_sources;
CREATE POLICY irrigation_manual_execution_sources_tenant ON irrigation_manual_execution_sources
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE OR REPLACE FUNCTION prevent_manual_execution_source_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'manual execution sources are append-only';
END; $$;
DROP TRIGGER IF EXISTS manual_execution_sources_append_only ON irrigation_manual_execution_sources;
CREATE TRIGGER manual_execution_sources_append_only
BEFORE UPDATE OR DELETE ON irrigation_manual_execution_sources
FOR EACH ROW EXECUTE FUNCTION prevent_manual_execution_source_mutation();

ALTER TABLE irrigation_manual_executions
    ADD COLUMN IF NOT EXISTS decision_id text,
    ADD COLUMN IF NOT EXISTS execution_plan_id text,
    ADD COLUMN IF NOT EXISTS plan_digest char(64),
    ADD COLUMN IF NOT EXISTS water_truth_digest char(64);

CREATE UNIQUE INDEX IF NOT EXISTS irrigation_manual_execution_plan_once_uq
    ON irrigation_manual_executions (tenant_id, execution_plan_id)
    WHERE execution_plan_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'irrigation_manual_execution_source_fk'
    ) THEN
        ALTER TABLE irrigation_manual_executions
        ADD CONSTRAINT irrigation_manual_execution_source_fk
        FOREIGN KEY (tenant_id, execution_plan_id)
        REFERENCES irrigation_manual_execution_sources (tenant_id, execution_plan_id);
    END IF;
END $$;

CREATE OR REPLACE FUNCTION sahool_irrx1_provenance_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    src irrigation_manual_execution_sources%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.decision_id IS NULL OR NEW.execution_plan_id IS NULL
           OR NEW.plan_digest IS NULL OR NEW.water_truth_digest IS NULL THEN
            RAISE EXCEPTION 'IRRX1_AUTHORITATIVE_PROVENANCE_REQUIRED';
        END IF;
        SELECT * INTO src
          FROM irrigation_manual_execution_sources
         WHERE tenant_id = NEW.tenant_id
           AND execution_plan_id = NEW.execution_plan_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'IRRX1_AUTHORITATIVE_SOURCE_NOT_FOUND';
        END IF;
        IF (NEW.decision_id, NEW.plan_digest, NEW.water_truth_digest,
            NEW.field_id, NEW.season_id, NEW.system_id,
            NEW.target_depth_mm, NEW.target_volume_m3, NEW.nominal_flow_m3_h,
            NEW.valid_from, NEW.valid_until)
           IS DISTINCT FROM
           (src.decision_id, src.plan_digest, src.water_truth_digest,
            src.field_id, src.season_id, src.system_id,
            src.target_depth_mm, src.target_volume_m3, src.nominal_flow_m3_h,
            src.valid_from, src.valid_until) THEN
            RAISE EXCEPTION 'IRRX1_EXECUTION_SOURCE_MISMATCH';
        END IF;
        RETURN NEW;
    END IF;

    IF (NEW.decision_id, NEW.execution_plan_id, NEW.plan_digest, NEW.water_truth_digest)
       IS DISTINCT FROM
       (OLD.decision_id, OLD.execution_plan_id, OLD.plan_digest, OLD.water_truth_digest) THEN
        RAISE EXCEPTION 'IRRX1_PROVENANCE_IS_IMMUTABLE';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS irrigation_manual_execution_provenance_guard
    ON irrigation_manual_executions;
CREATE TRIGGER irrigation_manual_execution_provenance_guard
BEFORE INSERT OR UPDATE ON irrigation_manual_executions
FOR EACH ROW EXECUTE FUNCTION sahool_irrx1_provenance_guard();
