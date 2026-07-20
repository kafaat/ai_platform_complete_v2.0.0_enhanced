-- v197: SCOUT-INGEST-01 B1.2a — external field-submission storage (raw preserved).
--
-- عقد محايد المزوّد (ODK/Kobo/CSV/GeoJSON) يهبط خلف مظروف موحّد (B1.0) بعد التحقّق
-- السباعي (B1.1). المبدأ الحاكم: **الوصول ≠ الثقة** — الخامّ محفوظ، والحالة (untrusted/
-- accepted/quarantined) سمة على الصفّ لا كيان منفصل. لا إسقاط domain هنا (B1.3).
--
-- «نفس مفتاح، جسم مختلف» = حدث يُرى (quarantine بمفتاح مشتقّ)، لا يُبتلع بصمت —
-- يُنفَّذ في مسار الكتابة (B1.2b) عبر resolver نقيّ (shared/contracts/ingest/dedup_resolution.py).
--
-- immutability: raw evidence غير قابل للمحو — **سمة جدول (trigger) لا اعتماداً على grant**
-- (الـgrants العالميّة قد تمنح DELETE؛ الـtrigger يمنعه بنيويّاً بصرف النظر).

CREATE TABLE IF NOT EXISTS external_submissions (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    submission_id      TEXT NOT NULL,
    provider           TEXT NOT NULL,
    server             TEXT NOT NULL,
    form_id            TEXT NOT NULL,
    instance_id        TEXT NOT NULL,
    content_hash       TEXT NOT NULL,                 -- sha256 للخامّ
    idempotency_key    TEXT NOT NULL,                 -- = derive_dedup_key (B1.0) أو مفتاح مشتقّ للمتباين
    submitted_at       TIMESTAMPTZ NOT NULL,
    received_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_ref            TEXT NOT NULL,                 -- مقبض URN للنَّسَب (يقرأه إسقاط B1.3 للاستشهاد بالخامّ) — البايتات في raw_payload
    raw_payload        JSONB NOT NULL,                -- الخامّ محفوظ (الوصول ≠ الثقة)
    mapping_version    TEXT NOT NULL,                 -- mapping مُصدَّر
    normalized_payload JSONB NOT NULL,                -- محاذاة العنقود 4 (ADR-0034)
    trust_status       TEXT NOT NULL DEFAULT 'untrusted'
                       CHECK (trust_status IN ('untrusted','accepted','quarantined')),
    quarantine_reasons TEXT[] NOT NULL DEFAULT '{}',  -- check_ids الفاشلة (B1.1) أو duplicate_key_divergent_payload
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- dedup بنيويّ مقيّد بالمستأجِر (يتّسق مع RLS). الصفّ المتباين يحمل مفتاحاً مشتقّاً ⇒ لا يصطدم.
CREATE UNIQUE INDEX IF NOT EXISTS ux_external_submissions_dedup
    ON external_submissions (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS ix_external_submissions_accepted
    ON external_submissions (tenant_id, trust_status) WHERE trust_status = 'accepted';

-- عقد RLS الحرفيّ (FORCE + USING + WITH CHECK على app.current_tenant) — نمط v155/v192 المشهود.
ALTER TABLE external_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_submissions FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
  EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON external_submissions';
  EXECUTE
    'CREATE POLICY tenant_isolation ON external_submissions '
    'USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) '
    'WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))';
END $$;

-- immutability كسمة أدلة: منع الحذف بنيويّاً (لا اعتماد على غياب grant قابل للإلغاء).
CREATE OR REPLACE FUNCTION external_submissions_forbid_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'external_submissions is append-only: raw evidence is immutable (no DELETE)';
END;
$$;
DROP TRIGGER IF EXISTS trg_external_submissions_no_delete ON external_submissions;
CREATE TRIGGER trg_external_submissions_no_delete
  BEFORE DELETE ON external_submissions
  FOR EACH ROW EXECUTE FUNCTION external_submissions_forbid_delete();

COMMENT ON TABLE external_submissions IS
  'SCOUT-INGEST-01 external field submissions — raw preserved, tenant-RLS, append-only. v197.';
