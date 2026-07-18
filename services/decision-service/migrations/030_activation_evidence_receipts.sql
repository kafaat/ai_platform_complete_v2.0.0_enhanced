-- Producer-issued, signed evidence receipts consumed by activation gates.
CREATE TABLE IF NOT EXISTS activation_evidence_receipts (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  gate_name text NOT NULL,
  producer text NOT NULL,
  check_name text NOT NULL,
  environment_id text NOT NULL,
  observed_at timestamptz NOT NULL,
  valid_until timestamptz NOT NULL,
  result text NOT NULL,
  provenance text NOT NULL,
  build_sha text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  signature char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_activation_evidence_result CHECK (result IN ('pass','fail')),
  CONSTRAINT ck_activation_evidence_window CHECK (valid_until > observed_at),
  CONSTRAINT ck_activation_evidence_max_window CHECK (valid_until <= observed_at + interval '24 hours'),
  CONSTRAINT ck_activation_evidence_provenance CHECK (provenance ~ '^[a-z0-9][a-z0-9._:/-]{0,254}$'),
  CONSTRAINT ck_activation_evidence_build_sha CHECK (build_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
  CONSTRAINT ck_activation_evidence_signature CHECK (signature ~ '^[0-9a-f]{64}$')
);
-- Deduplicates an identical canonical provenance for one gate/producer/check/environment/build. A
-- genuinely new producer observation MUST carry a new canonical provenance and is intentionally a
-- new receipt; activation evaluates only the explicit UUID references supplied (no latest-wins query).
CREATE UNIQUE INDEX IF NOT EXISTS uq_activation_evidence_semantic
  ON activation_evidence_receipts(gate_name, producer, check_name, environment_id, provenance, build_sha);
CREATE INDEX IF NOT EXISTS idx_activation_evidence_lookup
  ON activation_evidence_receipts(gate_name, environment_id, valid_until DESC);
CREATE OR REPLACE FUNCTION activation_evidence_receipts_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'activation_evidence_receipts is append-only'; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_activation_evidence_receipts_immutable ON activation_evidence_receipts;
CREATE TRIGGER trg_activation_evidence_receipts_immutable
  BEFORE UPDATE OR DELETE ON activation_evidence_receipts
  FOR EACH ROW EXECUTE FUNCTION activation_evidence_receipts_immutable();

-- Revocation kill-switch: INSERT-only, one revocation per receipt (UNIQUE), never mutated.
-- This restores a revoke path without reintroducing an UPDATE-able column on the receipts
-- table, preserving the pure append-only trust root. A receipt is resolvable iff no
-- revocation row references its evidence_id (checked inside the single resolve query — no TOCTOU).
CREATE TABLE IF NOT EXISTS activation_evidence_revocations (
  revocation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id uuid NOT NULL UNIQUE REFERENCES activation_evidence_receipts(evidence_id),
  revoked_by text NOT NULL,
  reason text NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_activation_evidence_revocations_evidence
  ON activation_evidence_revocations(evidence_id);
CREATE OR REPLACE FUNCTION activation_evidence_revocations_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'activation_evidence_revocations is append-only'; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_activation_evidence_revocations_immutable ON activation_evidence_revocations;
CREATE TRIGGER trg_activation_evidence_revocations_immutable
  BEFORE UPDATE OR DELETE ON activation_evidence_revocations
  FOR EACH ROW EXECUTE FUNCTION activation_evidence_revocations_immutable();
