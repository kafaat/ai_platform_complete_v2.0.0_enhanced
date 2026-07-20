-- v199: SCOUT-INGEST-01 B1.3 — إسقاط المقبولة إلى نموذج قراءة مملوك لـscout-ingest.
--
-- **القرار (أ) المعتمد:** scout-ingest يملك جدول إسقاطه الخاصّ ``external_field_observations``
-- (لا يكتب ``scouting_pins`` المملوك للمنصّة — single-writer محترَم مرّتين). توحيد العرض مع
-- FieldView = دَين موثَّق مؤجَّل (B1.3b)، محفّزه في المواصفة. راجع docs/specs/SCOUT-INGEST-01_B1.3_projection_spec.md.
--
-- **القاعدة الحاكمة:** لا دخول للنموذج قبل التحقّق السباعي — يُسقَط ``trust_status='accepted'`` **فقط**
-- (quarantined/untrusted لا يُلمَسان). دالّة claim تُصفّي بنيويّاً على accepted.
--
-- **تفاعل least-grant ↔ scan عابر-المستأجرين (نظير فخّ FORCE↔DEFINER في B1.2b):** العامل يمسح accepted
-- عبر المستأجرين ويحدّث projection_status، لكن ``sahool_ingest`` **بلا UPDATE** على external_submissions
-- (الحارس المُعتمَد). المخرج: دالّتا claim/complete = SECURITY DEFINER يملكهما ``sahool_ingest_resolver``
-- (BYPASSRLS، تُضبط الملكيّة في bootstrap) — فيبقى sahool_ingest عند SELECT+INSERT فقط.
--
-- **immutability الأدلّة الخامّة مصونة بنيويّاً:** projection_status سمة معالجة لا دليلاً خامّاً؛ تُضاف
-- كأعمدة، ويمنع trigger BEFORE UPDATE تغيير أيّ عمود دليل خامّ (يُسمح فقط بأعمدة projection_*) — فيبقى
-- الخامّ غير قابل للمحو (DELETE) ولا للتحوير (UPDATE) معاً.

-- ── ١) أعمدة بكرة الإسقاط على جدول الإدخال (سمة معالجة، لا دليل خامّ) ──
ALTER TABLE external_submissions
    ADD COLUMN IF NOT EXISTS projection_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (projection_status IN ('pending','running','projected','dead_letter','retry')),
    ADD COLUMN IF NOT EXISTS projection_attempts INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS projection_leased_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS projection_error TEXT;

CREATE INDEX IF NOT EXISTS ix_external_submissions_projectable
    ON external_submissions (received_at, id)
    WHERE trust_status = 'accepted' AND projection_status = 'pending';

-- الخامّ غير قابل للتحوير: يُسمح فقط بتغيّر أعمدة projection_* (بكرة المعالجة).
CREATE OR REPLACE FUNCTION external_submissions_raw_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.submission_id IS DISTINCT FROM OLD.submission_id
     OR NEW.provider IS DISTINCT FROM OLD.provider
     OR NEW.server IS DISTINCT FROM OLD.server
     OR NEW.form_id IS DISTINCT FROM OLD.form_id
     OR NEW.instance_id IS DISTINCT FROM OLD.instance_id
     OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at
     OR NEW.received_at IS DISTINCT FROM OLD.received_at
     OR NEW.raw_ref IS DISTINCT FROM OLD.raw_ref
     OR NEW.raw_payload IS DISTINCT FROM OLD.raw_payload
     OR NEW.mapping_version IS DISTINCT FROM OLD.mapping_version
     OR NEW.normalized_payload IS DISTINCT FROM OLD.normalized_payload
     OR NEW.trust_status IS DISTINCT FROM OLD.trust_status
     OR NEW.quarantine_reasons IS DISTINCT FROM OLD.quarantine_reasons THEN
    RAISE EXCEPTION 'external_submissions raw evidence is immutable: only projection_* columns may change';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_external_submissions_raw_immutable ON external_submissions;
CREATE TRIGGER trg_external_submissions_raw_immutable
  BEFORE UPDATE ON external_submissions
  FOR EACH ROW EXECUTE FUNCTION external_submissions_raw_immutable();

-- ── ٢) نموذج القراءة المملوك لـscout-ingest ──
CREATE TABLE IF NOT EXISTS external_field_observations (
    observation_id        TEXT PRIMARY KEY,             -- مشتقّ حتميّاً من الإدخال ⇒ إسقاط idempotent
    tenant_id             UUID NOT NULL,
    field_id              TEXT NOT NULL,
    source_submission_key TEXT NOT NULL,                -- external_submissions.idempotency_key (نَسَب)
    observed_property     TEXT,                         -- من normalized_payload (لا اختلاق: مفقود ⇒ NULL)
    value                 JSONB,
    severity              TEXT,
    lat                   DOUBLE PRECISION,
    lng                   DOUBLE PRECISION,
    observed_at           TIMESTAMPTZ,
    projected_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_external_field_observations_tenant_field
    ON external_field_observations (tenant_id, field_id, projected_at DESC);

ALTER TABLE external_field_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_field_observations FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
  EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON external_field_observations';
  EXECUTE
    'CREATE POLICY tenant_isolation ON external_field_observations '
    'USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) '
    'WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))';
END $$;

-- ── ٣) claim/complete = SECURITY DEFINER (المالك sahool_ingest_resolver في bootstrap) ──
-- claim: يمسح accepted+pending عابراً للمستأجرين (DEFINER يتجاوز RLS)، يعلّم running، SKIP LOCKED.
CREATE OR REPLACE FUNCTION claim_submissions_for_projection(p_limit INT DEFAULT 50, p_lease_seconds INT DEFAULT 120)
RETURNS TABLE(
    submission_ref BIGINT, tenant_id UUID, submission_id TEXT, idempotency_key TEXT,
    normalized_payload JSONB, submitted_at TIMESTAMPTZ, attempts INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
  RETURN QUERY
  WITH candidate AS (
      SELECT e.id
      FROM external_submissions e
      WHERE e.trust_status = 'accepted'
        AND (e.projection_status = 'pending'
             OR (e.projection_status = 'retry')
             OR (e.projection_status = 'running'
                 AND e.projection_leased_at < now() - make_interval(secs => GREATEST(1, p_lease_seconds))))
      ORDER BY e.received_at, e.id
      FOR UPDATE SKIP LOCKED
      LIMIT GREATEST(1, p_limit)
  )
  UPDATE external_submissions e
  SET projection_status = 'running',
      projection_attempts = e.projection_attempts + 1,
      projection_leased_at = now()
  FROM candidate c
  WHERE e.id = c.id
  RETURNING e.id, e.tenant_id, e.submission_id, e.idempotency_key,
            e.normalized_payload, e.submitted_at, e.projection_attempts;
END $$;

-- complete: حالة نهائيّة (projected/dead_letter) أو retry — لا يُغيّر أيّ عمود خامّ (يمرّ عبر trigger).
CREATE OR REPLACE FUNCTION complete_submission_projection(p_ref BIGINT, p_status TEXT, p_error TEXT DEFAULT NULL)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
  IF p_status NOT IN ('projected','dead_letter','retry') THEN
    RAISE EXCEPTION 'invalid projection terminal status: %', p_status;
  END IF;
  UPDATE external_submissions
  SET projection_status = p_status,
      projection_leased_at = NULL,
      projection_error = LEFT(p_error, 4000)
  WHERE id = p_ref;
END $$;

REVOKE ALL ON FUNCTION claim_submissions_for_projection(INT, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION complete_submission_projection(BIGINT, TEXT, TEXT) FROM PUBLIC;

COMMENT ON TABLE external_field_observations IS
  'SCOUT-INGEST-01 B1.3 — scout-ingest-owned read model of accepted external submissions (tenant-RLS). Owner writes only via the projection worker; unification with FieldView scouting_pins deferred to B1.3b. v199.';
