-- 035_decision_version_binding.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- IRRIGATION-APPROVAL-NOT-BOUND-TO-DECISION-VERSION-01.
--
-- WX-10.7 approved a candidate by its 16-hex candidate_lineage_id only. Nothing tied the
-- approval to the exact content the reviewer saw, and decision_value had no DB-level
-- immutability: the only guarantee was that the code path never wrote it. A plan therefore
-- carried no proof of WHICH version was approved, and a manual execution had nothing to
-- re-check at the moment of action.
--
-- This migration adds:
--   * decision_record.decision_value_digest — server-computed sha256 over canonical JSON of
--     decision_value (persistence.py computes it; the client never supplies it);
--   * a BEFORE UPDATE trigger that forbids changing the evidence and identity columns, so the
--     digest stays true for the life of the row (review_state transitions remain allowed);
--   * decision_reviews.approved_decision_value_digest — the version the reviewer approved;
--   * decision_execution_plans.decision_value_digest — the version a plan was derived from.
--
-- Additive, NULL-able, idempotent. Legacy rows keep NULL digests; a NULL digest can never be
-- approved under the new review contract (fail-closed: resubmit the candidate).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE decision_record          ADD COLUMN IF NOT EXISTS decision_value_digest text;
ALTER TABLE decision_reviews         ADD COLUMN IF NOT EXISTS approved_decision_value_digest text;
ALTER TABLE decision_execution_plans ADD COLUMN IF NOT EXISTS decision_value_digest text;

CREATE OR REPLACE FUNCTION decision_record_evidence_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.decision_value IS DISTINCT FROM OLD.decision_value
     OR NEW.decision_value_digest IS DISTINCT FROM OLD.decision_value_digest
     OR NEW.content_digest IS DISTINCT FROM OLD.content_digest
     OR NEW.candidate_lineage_id IS DISTINCT FROM OLD.candidate_lineage_id
     OR NEW.decision_type IS DISTINCT FROM OLD.decision_type
     OR NEW.field_id IS DISTINCT FROM OLD.field_id
     OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.stage IS DISTINCT FROM OLD.stage THEN
    RAISE EXCEPTION 'decision_record evidence is immutable (decision_id=%)', OLD.decision_id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_decision_record_evidence_immutable ON decision_record;
CREATE TRIGGER trg_decision_record_evidence_immutable
  BEFORE UPDATE ON decision_record
  FOR EACH ROW EXECUTE FUNCTION decision_record_evidence_immutable();

COMMENT ON COLUMN decision_record.decision_value_digest IS
    'Server-computed sha256 (64-hex) over canonical JSON of decision_value. Immutable by trigger; approval binds to it (035).';
COMMENT ON COLUMN decision_reviews.approved_decision_value_digest IS
    'decision_value_digest the reviewer approved (035). NULL for pre-035 reviews.';
COMMENT ON COLUMN decision_execution_plans.decision_value_digest IS
    'decision_value_digest of the approved decision this plan was derived from (035).';
