-- Durable timer and hand-off ledger. Does not execute equipment or verify outcomes.
BEGIN;
CREATE TABLE IF NOT EXISTS raster_follow_up_requests (
    tenant_id uuid NOT NULL,
    request_id text NOT NULL,
    field_id text NOT NULL,
    request_hash text NOT NULL CHECK (length(request_hash) = 64),
    request_payload jsonb NOT NULL,
    due_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    next_attempt_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','claimed','waiting_for_scene','retry_wait',
                         'dispatched','failed','expired','cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_token uuid,
    lease_until timestamptz,
    result_payload jsonb,
    reason_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, request_id),
    CHECK (expires_at > due_at),
    CHECK ((status = 'claimed' AND lease_token IS NOT NULL AND lease_until IS NOT NULL)
        OR (status <> 'claimed' AND lease_token IS NULL AND lease_until IS NULL)),
    CHECK (status <> 'dispatched' OR result_payload IS NOT NULL)
);
REVOKE ALL ON raster_follow_up_requests FROM PUBLIC;
ALTER TABLE raster_follow_up_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE raster_follow_up_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON raster_follow_up_requests;
CREATE POLICY tenant_isolation ON raster_follow_up_requests
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
CREATE INDEX IF NOT EXISTS idx_raster_follow_up_due
    ON raster_follow_up_requests (tenant_id, next_attempt_at, lease_until)
    WHERE status IN ('pending','claimed','waiting_for_scene','retry_wait');
COMMIT;
