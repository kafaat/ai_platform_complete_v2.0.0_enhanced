-- 026_content_digest_lineage.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- Decision-service SoR schema companion to platform migration v167.
--
-- The decision chain propagated lineage only via the 16-hex candidate_lineage_id;
-- the collision-free full digest (sha256, 64-hex) stayed buried in decision_value
-- JSONB — not queryable/indexable across the chain tables. persistence.py now
-- promotes it to a first-class column: persist_decision_record extracts it from
-- decision_value and writes the head row; dispatch/outcome/recommendation read it
-- server-side from decision_record and propagate. This migration adds the matching
-- column to the decision-service-owned schema (created in 001_decision_sor.sql) so
-- those writes have a column to land in.
--
-- Additive, NULL-able, idempotent (ADD COLUMN / INDEX IF NOT EXISTS): existing rows
-- untouched, backward-compatible.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE decision_record        ADD COLUMN IF NOT EXISTS content_digest text;
ALTER TABLE dispatch_decisions     ADD COLUMN IF NOT EXISTS content_digest text;
ALTER TABLE outcome_record         ADD COLUMN IF NOT EXISTS content_digest text;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS content_digest text;

-- Tenant-scoped tracing indexes (consistent with RLS / tenant-bound access).
CREATE INDEX IF NOT EXISTS idx_decision_record_content_digest
    ON decision_record (tenant_id, content_digest);
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_content_digest
    ON dispatch_decisions (tenant_id, content_digest);
CREATE INDEX IF NOT EXISTS idx_outcome_record_content_digest
    ON outcome_record (tenant_id, content_digest);
CREATE INDEX IF NOT EXISTS idx_recommendation_outcomes_content_digest
    ON recommendation_outcomes (tenant_id, content_digest);

COMMENT ON COLUMN decision_record.content_digest IS
    'Full sha256 (64-hex) over canonical-JSON of all decision facts — collision-free lineage propagated across the chain (v167/026). NULL for legacy rows or sources without a digest.';
