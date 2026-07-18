-- Gate-Trust-1 (P0) — the STORED PRODUCER-ISSUED EVIDENCE RECEIPT store: the activation gate's
-- root of trust. Replaces caller-supplied evidence (spoofable) with server-stored receipts that a
-- trusted producer issued over an authenticated ingest path. complete_evaluation admits check
-- results ONLY by resolving receipt IDs here, server-side — the caller submits references, never
-- results (raw caller evidence is forbidden).
--
-- Shared by every activation gate (keyed by gate_name), so it lives once here, not per-gate.
--
-- Append-only with a ONE-WAY revoke: a receipt is immutable content; the only permitted mutation is
-- revoked false->true (with revoked_at). Receipts are reusable until valid_until unless revoked, so
-- freshness is a property of the receipt, not of a single evaluation attempt.

CREATE TABLE IF NOT EXISTS activation_evidence_receipts (
  receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  gate_name text NOT NULL,
  environment_id text NOT NULL,
  producer text NOT NULL,
  check_name text NOT NULL,
  result text NOT NULL,
  observed_at timestamptz NOT NULL,
  valid_until timestamptz NOT NULL,
  provenance text NULL,
  build_sha char(64) NULL,
  -- Server-computed canonical fingerprint of the receipt content (identity + dedup anchor).
  content_hash char(64) NOT NULL,
  -- Defense-in-depth authentication (mandatory for external producers in production); the receipt
  -- store is the trust root, the signature is proof-of-origin, not the sole source of truth.
  key_id text NULL,
  signature text NULL,
  revoked boolean NOT NULL DEFAULT false,
  revoked_at timestamptz NULL,
  revoked_reason text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_receipt_result CHECK (result IN ('pass','fail')),
  CONSTRAINT ck_receipt_gate CHECK (length(btrim(gate_name)) BETWEEN 1 AND 128),
  CONSTRAINT ck_receipt_env CHECK (length(btrim(environment_id)) BETWEEN 1 AND 128),
  CONSTRAINT ck_receipt_producer CHECK (length(btrim(producer)) BETWEEN 1 AND 128),
  CONSTRAINT ck_receipt_check CHECK (length(btrim(check_name)) BETWEEN 1 AND 128),
  CONSTRAINT ck_receipt_content_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_receipt_build_sha CHECK (build_sha IS NULL OR build_sha ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_receipt_revoked_at CHECK (revoked = (revoked_at IS NOT NULL))
);

-- Idempotent ingest: the same canonical content IS the same receipt (a producer re-POSTing an
-- identical result is a no-op that returns the existing receipt, not a duplicate).
CREATE UNIQUE INDEX IF NOT EXISTS uq_activation_receipt_content
  ON activation_evidence_receipts (gate_name, environment_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_activation_receipt_lookup
  ON activation_evidence_receipts (gate_name, environment_id, check_name);

CREATE OR REPLACE FUNCTION activation_evidence_receipts_guard()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'activation_evidence_receipts is append-only (no delete)';
  END IF;
  -- The receipt content is immutable; every identity/content column is frozen after insert.
  IF NEW.receipt_id <> OLD.receipt_id
     OR NEW.gate_name <> OLD.gate_name
     OR NEW.environment_id <> OLD.environment_id
     OR NEW.producer <> OLD.producer
     OR NEW.check_name <> OLD.check_name
     OR NEW.result <> OLD.result
     OR NEW.observed_at <> OLD.observed_at
     OR NEW.valid_until <> OLD.valid_until
     OR NEW.content_hash <> OLD.content_hash
     OR NEW.build_sha IS DISTINCT FROM OLD.build_sha
     OR NEW.provenance IS DISTINCT FROM OLD.provenance
     OR NEW.signature IS DISTINCT FROM OLD.signature
     OR NEW.key_id IS DISTINCT FROM OLD.key_id THEN
    RAISE EXCEPTION 'activation_evidence_receipts content is immutable';
  END IF;
  -- The only permitted mutation is a ONE-WAY revoke.
  IF OLD.revoked AND NOT NEW.revoked THEN
    RAISE EXCEPTION 'activation_evidence_receipts revoke is one-way';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_activation_evidence_receipts_guard ON activation_evidence_receipts;
CREATE TRIGGER trg_activation_evidence_receipts_guard
  BEFORE UPDATE OR DELETE ON activation_evidence_receipts
  FOR EACH ROW EXECUTE FUNCTION activation_evidence_receipts_guard();
