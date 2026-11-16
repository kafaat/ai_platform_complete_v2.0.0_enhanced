-- SAHOOL v286 — migrations/v286_canonical_observations.sql
-- Canonical satellite-indicator observations as stored facts (plan item W1-11, finding remote-1).
--
-- Owner decision of 2026-11-16: indicators-service owns an append-only canonical observations
-- table, idempotent on the existing stable id (services/indicators-service/observation_runtime.py
-- ``_stable_id``). Owner decision of 2026-11-16 (later the same day): the delivery is a PULL over
-- HTTP (not NATS) — indicators-service drains raster-service's outbox through raster's internal
-- feed (GET /internal/v1/observation-outbox, POST …/acknowledgements); raster-service never calls
-- indicators-service (a push closed a cycle in the architecture graph, architecture:no_cycles).
--
-- What was wrong: an observation existed only while raster-service answered. indicators-service
-- recomputed it from the latest COG on every read (``/observations``, ``/observation-timeline``),
-- so there was no replayable NDVI record and nothing could say what a decision had seen.
--
-- ① canonical_observations (owner indicators-service). One row per published raster product:
--   observation_id is the asset stable id the canonical contract already uses as the asset
--   reference (``observation_runtime.asset_stable_id``: tenant, field, scene, indicator and the
--   acquisition instant). acquisition_day_id is the id raster-service's computed path gives the
--   same asset after a restart, when its layer carries the acquisition DATE only; a read or a
--   join by either id finds the row. revision_key is the product revision raster-service published it under
--   (geometry revision, algorithm version, QA mask version, raster product identity): a field
--   boundary edit or a reprocess publishes the same observation_id under a new revision, and that
--   is a new row, not a conflict. Same id, same revision and same content ⇒ the insert is a no-op
--   (replay); same id, same revision and other content ⇒ the service answers 409 and stores
--   nothing. Append-only: BEFORE UPDATE OR DELETE (row) and BEFORE TRUNCATE (statement) triggers
--   raise 55000. RLS ENABLE + FORCE by app.current_tenant with WITH CHECK.
-- ② raster_observation_outbox (owner raster-service). The durable delivery marker: the publish
--   path writes each published asset's payload here; indicators-service reads the tenant's
--   pending rows over raster's feed and acknowledges each one it settled (delivered, conflict,
--   rejected), from pending only, at the payload_sha256 it names. A row nobody acknowledged stays
--   pending and is read again next cycle; nothing deletes a row. Publication and this write
--   are two transactions (gap RASTER-OBSERVATION-PUBLISH-OUTBOX-NOT-ATOMIC-01, open); raster's
--   reconciliation sweep queues a published asset whose stored payload has no row here. A
--   conflict / rejected row goes back to pending only by an operator's explicit re-queue,
--   recorded in requeue_history. Only raster-service touches the
--   table, on its restricted runtime role under app.current_tenant (RLS ENABLE + FORCE).
--
-- Numbers are NUMERIC columns and JSON numbers in the payload, never decimal text
-- (gap CANONICAL-DECIMAL-ARRIVES-AS-TEXT-AND-DROPS-NDVI-01 stays closed on this path).
-- Idempotent. The schema owner can still correct a row (ALTER TABLE … DISABLE TRIGGER inside a
-- reviewed transaction); the application roles cannot. Before v240.

BEGIN;
SET LOCAL lock_timeout = '15s';

-- ① canonical observations (indicators-service).
CREATE TABLE IF NOT EXISTS canonical_observations (
    tenant_id UUID NOT NULL,
    observation_id TEXT NOT NULL CHECK (observation_id ~ '^ast_[0-9a-f]{24}$'),
    field_id VARCHAR(50) NOT NULL CHECK (field_id ~ '^[A-Za-z0-9_-]{1,50}$'),
    indicator_code TEXT NOT NULL CHECK (indicator_code ~ '^[a-z0-9_]{1,32}$'),
    scene_id TEXT NOT NULL CHECK (length(btrim(scene_id)) BETWEEN 1 AND 256),
    acquired_at TIMESTAMPTZ NOT NULL,
    mean NUMERIC NOT NULL,
    valid_pixel_ratio NUMERIC CHECK (valid_pixel_ratio IS NULL OR valid_pixel_ratio BETWEEN 0 AND 1),
    coverage_ratio NUMERIC CHECK (coverage_ratio IS NULL OR coverage_ratio BETWEEN 0 AND 1),
    cloud_pct NUMERIC CHECK (cloud_pct IS NULL OR cloud_pct BETWEEN 0 AND 100),
    quality_gate_passed BOOLEAN NOT NULL,
    geometry_revision INTEGER CHECK (geometry_revision IS NULL OR geometry_revision >= 0),
    algorithm_version TEXT,
    qa_mask_version TEXT,
    product_identity_key TEXT,
    revision_key TEXT NOT NULL CHECK (revision_key ~ '^[0-9a-f]{64}$'),
    acquisition_day_id TEXT NOT NULL CHECK (acquisition_day_id ~ '^ast_[0-9a-f]{24}$'),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    source_service TEXT NOT NULL DEFAULT 'raster-service' CHECK (source_service = 'raster-service'),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT canonical_observations_pk PRIMARY KEY (tenant_id, observation_id, revision_key)
);
CREATE INDEX IF NOT EXISTS canonical_observations_field_idx
    ON canonical_observations (tenant_id, field_id, indicator_code, acquired_at DESC);
CREATE INDEX IF NOT EXISTS canonical_observations_day_id_idx
    ON canonical_observations (tenant_id, field_id, acquisition_day_id);

ALTER TABLE canonical_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_observations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS canonical_observations_tenant ON canonical_observations;
CREATE POLICY canonical_observations_tenant ON canonical_observations
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

CREATE OR REPLACE FUNCTION canonical_observation_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    RAISE EXCEPTION 'canonical_observation_immutable' USING ERRCODE = '55000';
END; $$;
DROP TRIGGER IF EXISTS canonical_observations_immutable ON canonical_observations;
CREATE TRIGGER canonical_observations_immutable BEFORE UPDATE OR DELETE ON canonical_observations
    FOR EACH ROW EXECUTE FUNCTION canonical_observation_immutable();
DROP TRIGGER IF EXISTS canonical_observations_no_truncate ON canonical_observations;
CREATE TRIGGER canonical_observations_no_truncate BEFORE TRUNCATE ON canonical_observations
    FOR EACH STATEMENT EXECUTE FUNCTION canonical_observation_immutable();

-- The bootstrap scripts grant DML on every table to the runtime role after the migrations, so the
-- triggers are the fence; the REVOKE states the intent where no later GRANT undoes it.
REVOKE UPDATE, DELETE, TRUNCATE ON canonical_observations FROM PUBLIC;
DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['sahool_app', 'sahool_jobs'] LOOP
        IF to_regrole(r) IS NOT NULL THEN
            EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON canonical_observations FROM %I', r);
        END IF;
    END LOOP;
END $$;

-- ② the delivery outbox (raster-service).
CREATE TABLE IF NOT EXISTS raster_observation_outbox (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    indicator_code TEXT NOT NULL,
    product_identity_key TEXT NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'delivered', 'conflict', 'rejected')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_status_code INTEGER,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    -- An operator's explicit re-queue of a conflict / rejected entry (never automatic): each
    -- appends {at, by, reason, from_status, last_error, attempts}.
    requeue_history JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(requeue_history) = 'array'),
    CONSTRAINT raster_observation_outbox_once UNIQUE (tenant_id, product_identity_key, payload_sha256)
);
CREATE INDEX IF NOT EXISTS raster_observation_outbox_pending_idx
    ON raster_observation_outbox (next_attempt_at) WHERE status = 'pending';

ALTER TABLE raster_observation_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE raster_observation_outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS raster_observation_outbox_tenant ON raster_observation_outbox;
CREATE POLICY raster_observation_outbox_tenant ON raster_observation_outbox
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

COMMENT ON TABLE canonical_observations IS
    'Append-only canonical satellite-indicator observations, one per published raster asset (v286, owner indicators-service).';
COMMENT ON TABLE raster_observation_outbox IS
    'Durable delivery marker of published raster observations, drained by indicators-service over raster-service HTTP (v286, owner raster-service).';
COMMIT;
