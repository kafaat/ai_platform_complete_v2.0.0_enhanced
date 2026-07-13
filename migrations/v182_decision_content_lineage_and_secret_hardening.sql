-- v182: immutable SHA-256 content lineage for the recommendation lifecycle (renumbered from the
-- P0-fix bundle's v181; the platform's v181 is the irrigation closed-loop migration).
-- Separates record identity from content identity and backfills existing rows.
-- RECONCILED: recommendation_outcomes is intentionally EXCLUDED here — its content_digest is
-- already governed by v167 (the decision chain propagates the collision-free digest from
-- decision_record). Governing it twice (app-propagated vs DB-computed append-only) would clash.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS content_digest TEXT;
ALTER TABLE recommendation_reviews ADD COLUMN IF NOT EXISTS source_content_digest TEXT;
ALTER TABLE recommendation_reviews ADD COLUMN IF NOT EXISTS content_digest TEXT;
ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS source_content_digest TEXT;
ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS content_digest TEXT;
ALTER TABLE recommendation_feedback ADD COLUMN IF NOT EXISTS source_content_digest TEXT;
ALTER TABLE recommendation_feedback ADD COLUMN IF NOT EXISTS content_digest TEXT;

CREATE OR REPLACE FUNCTION sahool_sha256_jsonb(payload JSONB) RETURNS TEXT
LANGUAGE SQL IMMUTABLE STRICT AS $$
    SELECT encode(digest(convert_to(payload::TEXT, 'UTF8'), 'sha256'), 'hex')
$$;

UPDATE recommendations r SET content_digest = sahool_sha256_jsonb(
    jsonb_build_object('rec_id',r.rec_id,'tenant_id',r.tenant_id,'farm_id',r.farm_id,
      'field_id',r.field_id,'crop',r.crop,'delivered',r.delivered,'reason_ar',r.reason_ar,
      'recommendation',r.recommendation,'cross_reference',r.cross_reference,
      'provenance',r.provenance,'issued_at',r.issued_at)
) WHERE content_digest IS NULL;

UPDATE recommendation_reviews rr SET source_content_digest = r.content_digest
FROM recommendations r
WHERE rr.source_content_digest IS NULL AND r.rec_id = rr.recommendation_id
  AND r.tenant_id::TEXT = rr.tenant_id;
UPDATE recommendation_reviews rr SET content_digest = sahool_sha256_jsonb(
    jsonb_build_object('id',rr.id,'tenant_id',rr.tenant_id,'field_id',rr.field_id,
      'recommendation_id',rr.recommendation_id,'source_content_digest',rr.source_content_digest,
      'state',rr.state,'risk_level',rr.risk_level,'created_at',rr.created_at,'published_at',rr.published_at)
) WHERE content_digest IS NULL;

UPDATE review_decisions rd SET source_content_digest = rr.content_digest
FROM recommendation_reviews rr
WHERE rd.source_content_digest IS NULL AND rr.id = rd.review_id;
UPDATE review_decisions rd SET content_digest = sahool_sha256_jsonb(
    jsonb_build_object('id',rd.id,'review_id',rd.review_id,'source_content_digest',rd.source_content_digest,
      'reviewer_id',rd.reviewer_id,'action',rd.action,'reason',rd.reason,
      'modifications',rd.modifications,'created_at',rd.created_at)
) WHERE content_digest IS NULL;

UPDATE recommendation_feedback rf SET source_content_digest = r.content_digest
FROM recommendations r
WHERE rf.source_content_digest IS NULL AND r.rec_id = rf.recommendation_id
  AND r.tenant_id::TEXT = rf.tenant_id;
UPDATE recommendation_feedback rf SET content_digest = sahool_sha256_jsonb(to_jsonb(rf) - 'content_digest')
WHERE content_digest IS NULL;


-- Existing orphan rows remain visible but cannot be promoted as governed lineage.
ALTER TABLE recommendations ALTER COLUMN content_digest SET NOT NULL;
ALTER TABLE recommendations DROP CONSTRAINT IF EXISTS recommendations_content_digest_sha256;
ALTER TABLE recommendations ADD CONSTRAINT recommendations_content_digest_sha256
    CHECK (content_digest ~ '^[0-9a-f]{64}$') NOT VALID;
ALTER TABLE recommendation_reviews DROP CONSTRAINT IF EXISTS recommendation_reviews_digest_shape;
ALTER TABLE recommendation_reviews ADD CONSTRAINT recommendation_reviews_digest_shape
    CHECK (content_digest ~ '^[0-9a-f]{64}$' AND source_content_digest ~ '^[0-9a-f]{64}$') NOT VALID;
ALTER TABLE review_decisions DROP CONSTRAINT IF EXISTS review_decisions_digest_shape;
ALTER TABLE review_decisions ADD CONSTRAINT review_decisions_digest_shape
    CHECK (content_digest ~ '^[0-9a-f]{64}$' AND source_content_digest ~ '^[0-9a-f]{64}$') NOT VALID;
ALTER TABLE recommendation_feedback DROP CONSTRAINT IF EXISTS recommendation_feedback_digest_shape;
ALTER TABLE recommendation_feedback ADD CONSTRAINT recommendation_feedback_digest_shape
    CHECK (content_digest ~ '^[0-9a-f]{64}$' AND source_content_digest ~ '^[0-9a-f]{64}$') NOT VALID;

CREATE UNIQUE INDEX IF NOT EXISTS uq_recommendations_tenant_content_digest
    ON recommendations (tenant_id, content_digest);
CREATE UNIQUE INDEX IF NOT EXISTS uq_recommendation_reviews_content_digest
    ON recommendation_reviews (tenant_id, content_digest) WHERE content_digest IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_decisions_content_digest
    ON review_decisions (content_digest) WHERE content_digest IS NOT NULL;


CREATE OR REPLACE FUNCTION sahool_prepare_recommendation_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.content_digest := COALESCE(NEW.content_digest, sahool_sha256_jsonb(
        jsonb_build_object('rec_id',NEW.rec_id,'tenant_id',NEW.tenant_id,'farm_id',NEW.farm_id,
          'field_id',NEW.field_id,'crop',NEW.crop,'delivered',NEW.delivered,'reason_ar',NEW.reason_ar,
          'recommendation',NEW.recommendation,'cross_reference',NEW.cross_reference,
          'provenance',NEW.provenance,'issued_at',NEW.issued_at)));
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION sahool_prepare_review_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.source_content_digest IS NULL THEN
        SELECT content_digest INTO NEW.source_content_digest FROM recommendations
        WHERE rec_id = NEW.recommendation_id AND tenant_id::TEXT = NEW.tenant_id
        ORDER BY created_at DESC LIMIT 1;
    END IF;
    IF NEW.source_content_digest IS NULL THEN
        RAISE EXCEPTION 'governed recommendation content_digest not found';
    END IF;
    NEW.content_digest := COALESCE(NEW.content_digest, sahool_sha256_jsonb(
        jsonb_build_object('id',NEW.id,'tenant_id',NEW.tenant_id,'field_id',NEW.field_id,
          'recommendation_id',NEW.recommendation_id,'source_content_digest',NEW.source_content_digest,
          'state',NEW.state,'risk_level',NEW.risk_level,'created_at',NEW.created_at,'published_at',NEW.published_at)));
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION sahool_prepare_review_decision_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.source_content_digest IS NULL THEN
        SELECT content_digest INTO NEW.source_content_digest FROM recommendation_reviews WHERE id = NEW.review_id;
    END IF;
    IF NEW.source_content_digest IS NULL THEN
        RAISE EXCEPTION 'governed review content_digest not found';
    END IF;
    NEW.content_digest := COALESCE(NEW.content_digest, sahool_sha256_jsonb(
        jsonb_build_object('id',NEW.id,'review_id',NEW.review_id,
          'source_content_digest',NEW.source_content_digest,'reviewer_id',NEW.reviewer_id,
          'action',NEW.action,'reason',NEW.reason,'modifications',NEW.modifications,'created_at',NEW.created_at)));
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION sahool_prepare_feedback_digest() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.source_content_digest IS NULL THEN
        SELECT content_digest INTO NEW.source_content_digest FROM recommendations
        WHERE rec_id = NEW.recommendation_id AND tenant_id::TEXT = NEW.tenant_id
        ORDER BY created_at DESC LIMIT 1;
    END IF;
    IF NEW.source_content_digest IS NULL THEN
        RAISE EXCEPTION 'governed recommendation content_digest not found';
    END IF;
    NEW.content_digest := COALESCE(NEW.content_digest, sahool_sha256_jsonb(to_jsonb(NEW) - 'content_digest'));
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS recommendations_digest_prepare ON recommendations;
CREATE TRIGGER recommendations_digest_prepare BEFORE INSERT ON recommendations
FOR EACH ROW EXECUTE FUNCTION sahool_prepare_recommendation_digest();
DROP TRIGGER IF EXISTS recommendation_reviews_digest_prepare ON recommendation_reviews;
CREATE TRIGGER recommendation_reviews_digest_prepare BEFORE INSERT ON recommendation_reviews
FOR EACH ROW EXECUTE FUNCTION sahool_prepare_review_digest();
DROP TRIGGER IF EXISTS review_decisions_digest_prepare ON review_decisions;
CREATE TRIGGER review_decisions_digest_prepare BEFORE INSERT ON review_decisions
FOR EACH ROW EXECUTE FUNCTION sahool_prepare_review_decision_digest();
DROP TRIGGER IF EXISTS recommendation_feedback_digest_prepare ON recommendation_feedback;
CREATE TRIGGER recommendation_feedback_digest_prepare BEFORE INSERT ON recommendation_feedback
FOR EACH ROW EXECUTE FUNCTION sahool_prepare_feedback_digest();

CREATE OR REPLACE FUNCTION sahool_reject_digest_mutation() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.content_digest IS DISTINCT FROM NEW.content_digest THEN
        RAISE EXCEPTION 'content_digest is immutable';
    END IF;
    IF to_jsonb(OLD) ? 'source_content_digest'
       AND OLD.source_content_digest IS DISTINCT FROM NEW.source_content_digest THEN
        RAISE EXCEPTION 'source_content_digest is immutable';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS recommendations_digest_immutable ON recommendations;
CREATE TRIGGER recommendations_digest_immutable BEFORE UPDATE ON recommendations
FOR EACH ROW EXECUTE FUNCTION sahool_reject_digest_mutation();
DROP TRIGGER IF EXISTS recommendation_reviews_digest_immutable ON recommendation_reviews;
CREATE TRIGGER recommendation_reviews_digest_immutable BEFORE UPDATE ON recommendation_reviews
FOR EACH ROW EXECUTE FUNCTION sahool_reject_digest_mutation();
DROP TRIGGER IF EXISTS review_decisions_digest_immutable ON review_decisions;
CREATE TRIGGER review_decisions_digest_immutable BEFORE UPDATE ON review_decisions
FOR EACH ROW EXECUTE FUNCTION sahool_reject_digest_mutation();
DROP TRIGGER IF EXISTS recommendation_feedback_digest_immutable ON recommendation_feedback;
CREATE TRIGGER recommendation_feedback_digest_immutable BEFORE UPDATE ON recommendation_feedback
FOR EACH ROW EXECUTE FUNCTION sahool_reject_digest_mutation();

COMMENT ON COLUMN recommendations.content_digest IS 'Immutable SHA-256 identity of the recommendation content.';
COMMENT ON COLUMN recommendation_reviews.source_content_digest IS 'Exact recommendation content reviewed.';
COMMENT ON COLUMN review_decisions.source_content_digest IS 'Exact review content decided upon.';
COMMIT;
