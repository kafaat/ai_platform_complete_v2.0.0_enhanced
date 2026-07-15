-- RS-6 durable multi-replica anomaly store (Postgres + FORCE RLS).
-- Replaces the single-replica, service-local SQLite anomaly store so
-- vegetation-analysis can scale horizontally behind a load balancer with
-- DB-enforced tenant isolation (matching the rest of the platform's SoR model).
-- Selected at runtime by VEGETATION_ANOMALY_STORE=postgres; SQLite stays the
-- default until this path is certified against a live PostgreSQL in staging.

CREATE TABLE IF NOT EXISTS signal_anomalies (
    anomaly_ref  text PRIMARY KEY,
    tenant_id    uuid NOT NULL,
    field_id     text NOT NULL,
    season_id    text NOT NULL,
    status       text NOT NULL CHECK (status IN (
        'detected', 'triaged', 'verification_requested', 'confirmed',
        'rejected', 'inconclusive', 'diagnosis_proposed',
        'decision_referred', 'resolved'
    )),
    version      integer NOT NULL CHECK (version >= 1),
    task_ref     text,
    payload_json jsonb NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signal_anomalies_field
    ON signal_anomalies (tenant_id, field_id, season_id, status);

-- DB-enforced tenant isolation (FORCE RLS so even the table owner is bound).
ALTER TABLE signal_anomalies ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_anomalies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS signal_anomalies_tenant ON signal_anomalies;
CREATE POLICY signal_anomalies_tenant ON signal_anomalies
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
