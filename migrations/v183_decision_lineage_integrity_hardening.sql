-- v183: close integrity and tenant-isolation gaps left by v182 content-lineage (renumbered from
-- the P0-fix bundle's v182). RECONCILED: recommendation_outcomes is EXCLUDED — governed by v167.
-- The database, not the client, owns all lifecycle digests. Governed rows are append-only.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- review_decisions previously inherited tenant context only through application joins.
ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS tenant_id TEXT;
UPDATE review_decisions rd
SET tenant_id = rr.tenant_id
FROM recommendation_reviews rr
WHERE rd.review_id = rr.id AND rd.tenant_id IS NULL;

DO $$
DECLARE missing_count BIGINT;
BEGIN
  SELECT COUNT(*) INTO missing_count FROM review_decisions WHERE tenant_id IS NULL;
  IF missing_count > 0 THEN
    RAISE EXCEPTION 'v182 cannot govern % orphan review_decisions without tenant_id', missing_count;
  END IF;
END $$;
ALTER TABLE review_decisions ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_review_decisions_tenant_review
  ON review_decisions(tenant_id, review_id);

ALTER TABLE review_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_decisions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON review_decisions;
CREATE POLICY tenant_isolation ON review_decisions
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), ''));

-- Canonical digest payload functions. Explicit fields avoid unstable to_jsonb(row) hashes.
CREATE OR REPLACE FUNCTION sahool_recommendation_digest(r recommendations) RETURNS TEXT
LANGUAGE SQL IMMUTABLE STRICT AS $$
 SELECT sahool_sha256_jsonb(jsonb_build_object(
   'rec_id',r.rec_id,'tenant_id',r.tenant_id,'farm_id',r.farm_id,'field_id',r.field_id,
   'crop',r.crop,'delivered',r.delivered,'reason_ar',r.reason_ar,
   'recommendation',r.recommendation,'cross_reference',r.cross_reference,
   'provenance',r.provenance,'issued_at',r.issued_at))
$$;
CREATE OR REPLACE FUNCTION sahool_review_digest(r recommendation_reviews) RETURNS TEXT
LANGUAGE SQL IMMUTABLE STRICT AS $$
 SELECT sahool_sha256_jsonb(jsonb_build_object(
   'id',r.id,'tenant_id',r.tenant_id,'field_id',r.field_id,
   'recommendation_id',r.recommendation_id,'source_content_digest',r.source_content_digest,
   'state',r.state,'risk_level',r.risk_level,'created_at',r.created_at,'published_at',r.published_at))
$$;
CREATE OR REPLACE FUNCTION sahool_review_decision_digest(r review_decisions) RETURNS TEXT
LANGUAGE SQL IMMUTABLE STRICT AS $$
 SELECT sahool_sha256_jsonb(jsonb_build_object(
   'id',r.id,'tenant_id',r.tenant_id,'review_id',r.review_id,
   'source_content_digest',r.source_content_digest,'reviewer_id',r.reviewer_id,
   'action',r.action,'reason',r.reason,'modifications',r.modifications,'created_at',r.created_at))
$$;
CREATE OR REPLACE FUNCTION sahool_feedback_digest(r recommendation_feedback) RETURNS TEXT
LANGUAGE SQL IMMUTABLE STRICT AS $$
 SELECT sahool_sha256_jsonb(jsonb_build_object(
   'id',r.id,'tenant_id',r.tenant_id,'field_id',r.field_id,
   'recommendation_id',r.recommendation_id,'source_content_digest',r.source_content_digest,
   'accepted',r.accepted,'actual_yield',r.actual_yield,'predicted_yield',r.predicted_yield,
   'actual_cost',r.actual_cost,'standard_cost',r.standard_cost,
   'actual_water',r.actual_water,'standard_water',r.standard_water,'created_at',r.created_at))
$$;

-- Database-owned digests: overwrite client values and derive exact parent content identity.
CREATE OR REPLACE FUNCTION sahool_prepare_recommendation_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$ BEGIN
  NEW.content_digest := sahool_recommendation_digest(NEW);
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION sahool_prepare_review_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$ BEGIN
  SELECT content_digest INTO NEW.source_content_digest
  FROM recommendations
  WHERE rec_id=NEW.recommendation_id AND tenant_id::text=NEW.tenant_id
  ORDER BY created_at DESC LIMIT 1;
  IF NEW.source_content_digest IS NULL THEN RAISE EXCEPTION 'governed recommendation content_digest not found'; END IF;
  NEW.content_digest := sahool_review_digest(NEW);
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION sahool_prepare_review_decision_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$ BEGIN
  SELECT tenant_id, content_digest INTO NEW.tenant_id, NEW.source_content_digest
  FROM recommendation_reviews WHERE id=NEW.review_id;
  IF NEW.source_content_digest IS NULL OR NEW.tenant_id IS NULL THEN
    RAISE EXCEPTION 'governed review lineage not found';
  END IF;
  NEW.content_digest := sahool_review_decision_digest(NEW);
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION sahool_prepare_feedback_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$ BEGIN
  SELECT content_digest INTO NEW.source_content_digest
  FROM recommendations
  WHERE rec_id=NEW.recommendation_id AND tenant_id::text=NEW.tenant_id
  ORDER BY created_at DESC LIMIT 1;
  IF NEW.source_content_digest IS NULL THEN RAISE EXCEPTION 'governed recommendation content_digest not found'; END IF;
  NEW.content_digest := sahool_feedback_digest(NEW);
  RETURN NEW;
END $$;

-- Recompute historical hashes from parent to child after tenant backfill.
UPDATE recommendations r SET content_digest=sahool_recommendation_digest(r);
UPDATE recommendation_reviews rr
SET source_content_digest=r.content_digest
FROM recommendations r
WHERE r.rec_id=rr.recommendation_id AND r.tenant_id::text=rr.tenant_id;
UPDATE recommendation_reviews r SET content_digest=sahool_review_digest(r)
  WHERE source_content_digest IS NOT NULL;
UPDATE review_decisions rd
SET tenant_id=rr.tenant_id, source_content_digest=rr.content_digest
FROM recommendation_reviews rr WHERE rr.id=rd.review_id;
UPDATE review_decisions r SET content_digest=sahool_review_decision_digest(r)
  WHERE source_content_digest IS NOT NULL;
UPDATE recommendation_feedback rf
SET source_content_digest=r.content_digest
FROM recommendations r
WHERE r.rec_id=rf.recommendation_id AND r.tenant_id::text=rf.tenant_id;
UPDATE recommendation_feedback r SET content_digest=sahool_feedback_digest(r)
  WHERE source_content_digest IS NOT NULL;

DO $$
DECLARE orphans BIGINT;
BEGIN
 SELECT
   (SELECT COUNT(*) FROM recommendation_reviews WHERE content_digest IS NULL OR source_content_digest IS NULL)+
   (SELECT COUNT(*) FROM review_decisions WHERE content_digest IS NULL OR source_content_digest IS NULL)+
   (SELECT COUNT(*) FROM recommendation_feedback WHERE content_digest IS NULL OR source_content_digest IS NULL)
 INTO orphans;
 IF orphans > 0 THEN
   RAISE EXCEPTION 'v182 found % orphan lifecycle rows; reconcile before promotion', orphans;
 END IF;
END $$;

ALTER TABLE recommendation_reviews ALTER COLUMN source_content_digest SET NOT NULL;
ALTER TABLE recommendation_reviews ALTER COLUMN content_digest SET NOT NULL;
ALTER TABLE review_decisions ALTER COLUMN source_content_digest SET NOT NULL;
ALTER TABLE review_decisions ALTER COLUMN content_digest SET NOT NULL;
ALTER TABLE recommendation_feedback ALTER COLUMN source_content_digest SET NOT NULL;
ALTER TABLE recommendation_feedback ALTER COLUMN content_digest SET NOT NULL;

-- NOTE: the four *_digest_shape / content_digest_sha256 constraints stay NOT VALID here (added
-- in v182). Per repo policy (docs/runbooks/validate_not_valid_constraints.md) the blocking
-- `VALIDATE CONSTRAINT` step is operator-run under monitoring, NOT executed inside a migration.
-- NOT VALID still enforces every NEW insert/update; only the one-time backfill scan is deferred.

-- Append-only governance: material content and lineage cannot be rewritten in place.
CREATE OR REPLACE FUNCTION sahool_reject_governed_row_mutation() RETURNS TRIGGER
LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION '% is append-only; create a new governed row instead', TG_TABLE_NAME;
END $$;
DROP TRIGGER IF EXISTS recommendations_digest_immutable ON recommendations;
CREATE TRIGGER recommendations_digest_immutable BEFORE UPDATE OR DELETE ON recommendations
FOR EACH ROW EXECUTE FUNCTION sahool_reject_governed_row_mutation();
DROP TRIGGER IF EXISTS recommendation_reviews_digest_immutable ON recommendation_reviews;
CREATE TRIGGER recommendation_reviews_digest_immutable BEFORE UPDATE OR DELETE ON recommendation_reviews
FOR EACH ROW EXECUTE FUNCTION sahool_reject_governed_row_mutation();
DROP TRIGGER IF EXISTS review_decisions_digest_immutable ON review_decisions;
CREATE TRIGGER review_decisions_digest_immutable BEFORE UPDATE OR DELETE ON review_decisions
FOR EACH ROW EXECUTE FUNCTION sahool_reject_governed_row_mutation();
DROP TRIGGER IF EXISTS recommendation_feedback_digest_immutable ON recommendation_feedback;
CREATE TRIGGER recommendation_feedback_digest_immutable BEFORE UPDATE OR DELETE ON recommendation_feedback
FOR EACH ROW EXECUTE FUNCTION sahool_reject_governed_row_mutation();

COMMIT;
