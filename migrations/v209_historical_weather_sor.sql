-- v209 / S3: canonical, point-in-time historical weather Source of Truth.
-- Append-only observations; corrections create a new row that supersedes an older row.

BEGIN;

CREATE TABLE IF NOT EXISTS historical_weather_daily (
    record_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT,
    observed_on DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    quality TEXT NOT NULL CHECK (quality IN ('validated','provisional','suspect')),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    content_hash CHAR(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    supersedes_record_id TEXT,
    ingested_by TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT historical_weather_source_idempotency
      UNIQUE (tenant_id, source, source_record_id),
    CONSTRAINT historical_weather_tenant_record_unique
      UNIQUE (tenant_id, record_id),
    CONSTRAINT historical_weather_supersedes_fk
      FOREIGN KEY (tenant_id, supersedes_record_id)
      REFERENCES historical_weather_daily(tenant_id, record_id)
);

CREATE INDEX IF NOT EXISTS idx_historical_weather_field_day
  ON historical_weather_daily(tenant_id, field_id, observed_on DESC, available_at DESC);
CREATE INDEX IF NOT EXISTS idx_historical_weather_season_day
  ON historical_weather_daily(tenant_id, season_id, observed_on DESC)
  WHERE season_id IS NOT NULL;

ALTER TABLE historical_weather_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE historical_weather_daily FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS historical_weather_tenant_isolation ON historical_weather_daily;
CREATE POLICY historical_weather_tenant_isolation ON historical_weather_daily
  USING (
    tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
  )
  WITH CHECK (
    tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
  );

CREATE OR REPLACE FUNCTION prevent_historical_weather_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'historical weather truth is append-only; insert a superseding record';
END;
$$;
DROP TRIGGER IF EXISTS historical_weather_append_only ON historical_weather_daily;
CREATE TRIGGER historical_weather_append_only
BEFORE UPDATE OR DELETE ON historical_weather_daily
FOR EACH ROW EXECUTE FUNCTION prevent_historical_weather_mutation();

COMMENT ON TABLE historical_weather_daily IS
  'S3 canonical historical weather truth: immutable daily facts with PIT available_at, provenance and explicit corrections.';

COMMIT;
