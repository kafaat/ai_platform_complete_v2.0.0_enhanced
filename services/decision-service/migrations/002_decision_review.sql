-- WX-10.7 — Reviewer/Policy decision on a pending_approval candidate.
-- Additive + idempotent. Applied by the custom runner (migration_runner.py --apply), NOT at
-- startup. The review transition is authoritative ONLY under a deployed SoR
-- (DECISION_SERVICE_SOR_ENABLED=true + DATABASE_URL + promoted ownership); in the current
-- interim-bridge/mirror deployment the review endpoint fails closed (503) — it never claims an
-- authoritative transition it cannot make.
--
-- State model: a DEDICATED operational `review_state` column on decision_record carries the
-- lifecycle (pending_approval -> approved | rejected). The evidence in `decision_value` (jsonb)
-- is NEVER used as an operational state source and is NEVER mutated by a review. `candidate_
-- lineage_id` is promoted to its own column (no longer read from jsonb) so the atomic transition
-- can key on it directly.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- (1) Dedicated operational columns on decision_record (nullable ⇒ backward-compatible: only
-- candidates carry a review_state / candidate_lineage_id).
ALTER TABLE decision_record
  ADD COLUMN IF NOT EXISTS review_state text,
  ADD COLUMN IF NOT EXISTS candidate_lineage_id text,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_decision_record_review_state'
  ) THEN
    ALTER TABLE decision_record
      ADD CONSTRAINT ck_decision_record_review_state
      CHECK (review_state IS NULL OR review_state IN ('pending_approval', 'approved', 'rejected'));
  END IF;
END$$;

-- Backfill existing WX-10.6 candidates (written before these columns existed): mark them
-- pending_approval and lift candidate_lineage_id out of decision_value ONCE (idempotent — only
-- rows still missing review_state).
UPDATE decision_record
   SET review_state = 'pending_approval',
       candidate_lineage_id = decision_value->>'candidate_lineage_id'
 WHERE stage = 'candidate' AND review_state IS NULL;

CREATE INDEX IF NOT EXISTS idx_decision_record_tenant_review_state
  ON decision_record (tenant_id, review_state, created_at DESC);

-- (2) Append-only review audit. One terminal review per (tenant, decision) — reopen is a future
-- increment with its own audit contract.
CREATE TABLE IF NOT EXISTS decision_reviews (
  review_id text PRIMARY KEY,
  decision_id text NOT NULL,
  tenant_id uuid NOT NULL,
  action text NOT NULL,
  previous_state text NOT NULL,
  new_state text NOT NULL,
  reason text NULL,
  reviewed_by text NOT NULL,
  reviewed_at timestamptz NOT NULL DEFAULT now(),
  candidate_lineage_id text NOT NULL,
  request_id text NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  policy_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_decision_reviews_action CHECK (action IN ('approve', 'reject')),
  CONSTRAINT ck_decision_reviews_prev CHECK (previous_state = 'pending_approval'),
  CONSTRAINT ck_decision_reviews_new CHECK (new_state IN ('approved', 'rejected')),
  CONSTRAINT ck_decision_reviews_agree CHECK (
    (action = 'approve' AND new_state = 'approved')
    OR (action = 'reject' AND new_state = 'rejected')
  ),
  CONSTRAINT ck_decision_reviews_reviewed_by CHECK (length(btrim(reviewed_by)) > 0)
);

-- Terminal single-review per tenant+decision (concurrency backstop on INSERT).
CREATE UNIQUE INDEX IF NOT EXISTS uq_decision_reviews_tenant_decision
  ON decision_reviews (tenant_id, decision_id);
-- Idempotency: one logical review per (tenant, key).
CREATE UNIQUE INDEX IF NOT EXISTS uq_decision_reviews_tenant_idem
  ON decision_reviews (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_decision_reviews_tenant_created
  ON decision_reviews (tenant_id, created_at DESC);

-- Real append-only enforcement (not descriptive): block UPDATE/DELETE at the DB layer.
CREATE OR REPLACE FUNCTION decision_reviews_append_only()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'decision_reviews is append-only (% not allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decision_reviews_append_only ON decision_reviews;
CREATE TRIGGER trg_decision_reviews_append_only
  BEFORE UPDATE OR DELETE ON decision_reviews
  FOR EACH ROW EXECUTE FUNCTION decision_reviews_append_only();
