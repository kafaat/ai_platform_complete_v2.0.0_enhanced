-- AC-1 (Agronomic Context Master Plan, Phase A): canonical immutable context contracts.
-- Note on numbering: the master plan calls this "migration 016"; in this repository the next free
-- slot is 018 (016=runtime work claims, 017=runtime schedules). Content follows the plan.
--
-- Three immutable contracts every governed decision must eventually reference:
--   AgronomicContextSnapshot        — point-in-time composed state (crop/soil/irrigation/weather/…)
--   FieldHistoricalContextSnapshot  — bounded, provenance-carrying historical projection
--   FeatureManifest (+entries)      — the ACTUAL values used, each with source/time/quality
-- Structured domain groups live in validated jsonb (the composer validates shape and hashes the
-- canonical content); identity/lineage/PIT columns are first-class for indexing and enforcement.
CREATE TABLE IF NOT EXISTS decision_agronomic_context_snapshots (
 snapshot_id text PRIMARY KEY, tenant_id uuid NOT NULL,
 field_id text NOT NULL, season_id text,
 as_of_time timestamptz NOT NULL, schema_version text NOT NULL, composer_version text NOT NULL,
 context jsonb NOT NULL, content_hash text NOT NULL,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, idempotency_key), UNIQUE(tenant_id, content_hash),
 CHECK (content_hash ~ '^[a-f0-9]{64}$')
);
CREATE INDEX IF NOT EXISTS idx_agro_ctx_field_time
  ON decision_agronomic_context_snapshots (tenant_id, field_id, season_id, as_of_time DESC);

CREATE TABLE IF NOT EXISTS decision_field_historical_context_snapshots (
 historical_snapshot_id text PRIMARY KEY, tenant_id uuid NOT NULL,
 field_id text NOT NULL, season_id text,
 as_of_time timestamptz NOT NULL, history_from timestamptz NOT NULL, history_to timestamptz NOT NULL,
 manifest_version text NOT NULL, history jsonb NOT NULL, content_hash text NOT NULL,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, idempotency_key),
 CHECK (content_hash ~ '^[a-f0-9]{64}$'),
 CHECK (history_to <= as_of_time AND history_from < history_to)
);
CREATE INDEX IF NOT EXISTS idx_hist_ctx_field_time
  ON decision_field_historical_context_snapshots (tenant_id, field_id, season_id, as_of_time DESC);

CREATE TABLE IF NOT EXISTS decision_feature_manifests (
 feature_manifest_id text PRIMARY KEY, tenant_id uuid NOT NULL,
 field_id text NOT NULL, as_of_time timestamptz NOT NULL,
 decision_cutoff_time timestamptz NOT NULL, content_hash text NOT NULL,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, idempotency_key),
 CHECK (content_hash ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS decision_feature_manifest_entries (
 entry_id text PRIMARY KEY, tenant_id uuid NOT NULL, feature_manifest_id text NOT NULL,
 name text NOT NULL, value jsonb NOT NULL, unit text,
 source_service text NOT NULL, source_snapshot_id text,
 observed_at timestamptz NOT NULL, available_at timestamptz NOT NULL,
 quality_status text NOT NULL, formula_version text, spatial_scope text, temporal_scope text,
 UNIQUE(tenant_id, feature_manifest_id, name),
 FOREIGN KEY (feature_manifest_id) REFERENCES decision_feature_manifests(feature_manifest_id),
 CHECK (quality_status IN ('verified','accepted_with_warning','stale','missing','rejected')),
 -- point-in-time invariant lives in the row itself: nothing observed after availability.
 CHECK (observed_at <= available_at)
);

DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['decision_agronomic_context_snapshots','decision_field_historical_context_snapshots','decision_feature_manifests','decision_feature_manifest_entries'] LOOP EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_append_only ON %I',t,t); EXECUTE format('CREATE TRIGGER trg_%s_append_only BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only()',t,t); END LOOP; END $$;

-- Mandatory decision binding (plan "migration 017"): lineage columns on decision_record.
-- Existing rows become 'legacy_unbound'; NEW governed decisions must carry 'ac-1' context when
-- enforcement is enabled (DECISION_REQUIRE_AGRONOMIC_CONTEXT) — validated at the API layer and
-- re-checked in persistence against existing tenant/field-matched snapshots.
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS agronomic_context_snapshot_id text;
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS field_historical_context_snapshot_id text;
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS feature_manifest_id text;
ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS context_contract_version text NOT NULL DEFAULT 'legacy_unbound';
