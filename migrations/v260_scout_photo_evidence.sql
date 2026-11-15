-- v260: scout photo evidence — the observation photo's single source of truth.
-- ════════════════════════════════════════════════════════════════════════
-- Owner decision (2026-11-13): a scouting photo is an immutable evidence row owned by
-- scout-ingest, bound by tenant + field + pin to an existing saved observation. scouting_pins
-- carries no photo link (v257 had a photo_document_id draft; it was removed before merge).
-- SHA-256 certifies the received bytes only; no inference or agronomic approval is implied
-- (verification_state = bytes_verified, review_state = unreviewed are the only values).
--
-- Requires v94 (scouting_pins) and v246 (scouting_pins_tenant_field_pin_uq, the unique index on
-- (tenant_id, field_id, pin_id) that the FK below references). Numbered v260 because v256-v259
-- are taken on other stacked branches; placed before v240/v206 so v206 hardens it last.
--
-- Idempotent on a re-applied MANIFEST: CREATE … IF NOT EXISTS, DROP POLICY/TRIGGER IF EXISTS,
-- CREATE OR REPLACE FUNCTION. Grants to sahool_ingest (SELECT, INSERT; no UPDATE/DELETE) are in
-- migrations/bootstrap_postgres.sh and migrations/apply_in_compose.sh, like v197-v202.
BEGIN;
CREATE TABLE IF NOT EXISTS scout_photo_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    pin_id TEXT NOT NULL,
    object_ref TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    mime_type TEXT NOT NULL CHECK (mime_type IN ('image/jpeg', 'image/png', 'image/webp')),
    size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 8388608),
    image_width INTEGER NOT NULL CHECK (image_width > 0),
    image_height INTEGER NOT NULL CHECK (image_height > 0),
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    verification_state TEXT NOT NULL DEFAULT 'bytes_verified'
        CHECK (verification_state = 'bytes_verified'),
    review_state TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (review_state = 'unreviewed'),
    CONSTRAINT scout_photo_evidence_pin_fk FOREIGN KEY (tenant_id, field_id, pin_id)
        REFERENCES scouting_pins (tenant_id, field_id, pin_id),
    CONSTRAINT scout_photo_evidence_one_per_pin UNIQUE (tenant_id, field_id, pin_id),
    -- The service accepts only the server-derived key (shared/security/scout_photo.py:
    -- scouting-photos/v1/<tenant>/<pin>/<sha256>); the CHECK keeps a row from naming a
    -- file:// or http(s):// object at all.
    CONSTRAINT scout_photo_evidence_object_ref_ck CHECK (object_ref LIKE 's3://%')
);
CREATE INDEX IF NOT EXISTS scout_photo_evidence_field_idx
    ON scout_photo_evidence (tenant_id, field_id, uploaded_at DESC);

ALTER TABLE scout_photo_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_photo_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_photo_evidence_tenant ON scout_photo_evidence;
CREATE POLICY scout_photo_evidence_tenant ON scout_photo_evidence
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

-- Application writes are INSERT-only. Without a trigger the "immutable" contract would be
-- descriptive, and a future UPDATE could silently rewrite the original receipt. Legal
-- retention/erasure needs a separate, audited, privileged purge procedure (not this service).
CREATE OR REPLACE FUNCTION reject_scout_photo_evidence_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'scout_photo_evidence_immutable' USING ERRCODE = '55000';
END;
$$;
DROP TRIGGER IF EXISTS scout_photo_evidence_immutable_guard ON scout_photo_evidence;
CREATE TRIGGER scout_photo_evidence_immutable_guard
    BEFORE UPDATE OR DELETE ON scout_photo_evidence
    FOR EACH ROW EXECUTE FUNCTION reject_scout_photo_evidence_mutation();

COMMENT ON TABLE scout_photo_evidence IS
    'Immutable, per-tenant scouting photo record (v260, owner scout-ingest); one per pin. Byte verification is not an agricultural diagnosis.';
COMMIT;
