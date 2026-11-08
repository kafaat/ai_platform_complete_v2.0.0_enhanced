-- v239_detection_provenance.sql — نسبُ كشف الآفات/الأمراض لكلّ كشفٍ مُخزَّن.
--
-- العطل: نتيجةُ الكشف من الحافّة تُكتَب في edge_results.result_data (JSONB حرّ) بلا سجلٍّ
-- دائم يقول أيُّ مصنوعة نموذج (الاسم · الإصدار · sha256) وأيُّ صورة (بصمة المحتوى) وأيُّ
-- عتبة وحالةُ المعايرة أنتجتها — فتنبيهٌ لا يُتتبَّع ولا يُدقَّق.
--
-- القاعدة: صفٌّ لكلّ كشف (edge_result_id, detection_index) يُكتَب في معاملة الكتابة نفسها
-- (services/sahool-platform/api/routers/edge.py ← api/edge_models.py).
--   * attested           ⇒ بصمتا المصنوعة والمدخل + العتبة + النموذج والإصدار إلزاميّة.
--   * unattested_legacy  ⇒ نتيجةٌ بلا كتلة نسب (جهاز أقدم): بلا بصمات، والغيابُ مُعلَن.
--   * calibrated = (calibration_ref IS NOT NULL): لا «معايَر» بلا سجلّ معايرة.
--   * المستأجر نفسه: مفتاحٌ أجنبيّ مركّب (edge_result_id, tenant_id) ⇒ لا نسبَ لنتيجة مستأجرٍ آخر.
--   * لا تعديل بعد الكتابة (trigger): سجلُّ تدقيق؛ الحذف يتبع النتيجة (ON DELETE CASCADE).
--
-- RLS + FORCE بالشكل الصارم نفسه لـv236 (NULLIF ⇒ لا سياق = لا صفوف ولا كتابة).
-- ذرّيّ وقابل لإعادة التشغيل. يُدرَج قبل v206 كي يبقى v206 آخر مدخل.
BEGIN;
SET LOCAL lock_timeout = '15s';

-- هدفُ المفتاح المركّب: id فريدٌ أصلاً، فالفهرسُ لا يرفض صفّاً قائماً.
CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_results_id_tenant
    ON edge_results (id, tenant_id);

CREATE TABLE IF NOT EXISTS detection_provenance (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    edge_result_id bigint NOT NULL,
    detection_index integer NOT NULL CHECK (detection_index >= 0),
    label text CHECK (label IS NULL OR length(label) BETWEEN 1 AND 200),
    score double precision NOT NULL CHECK (score >= 0 AND score <= 1),
    threshold double precision CHECK (threshold IS NULL OR (threshold >= 0 AND threshold <= 1)),
    model_id text CHECK (model_id IS NULL OR length(model_id) BETWEEN 1 AND 200),
    model_version text CHECK (model_version IS NULL OR length(model_version) BETWEEN 1 AND 200),
    artifact_sha256 text CHECK (artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'),
    input_sha256 text CHECK (input_sha256 IS NULL OR input_sha256 ~ '^[0-9a-f]{64}$'),
    attestation text NOT NULL CHECK (attestation IN ('attested', 'unattested_legacy')),
    calibrated boolean NOT NULL DEFAULT false,
    calibration_ref text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_detection_provenance_detection UNIQUE (edge_result_id, detection_index),
    CONSTRAINT fk_detection_provenance_result FOREIGN KEY (edge_result_id, tenant_id)
        REFERENCES edge_results (id, tenant_id) ON DELETE CASCADE,
    CONSTRAINT ck_detection_provenance_attested CHECK (
        attestation <> 'attested'
        OR (model_id IS NOT NULL AND model_version IS NOT NULL AND artifact_sha256 IS NOT NULL
            AND input_sha256 IS NOT NULL AND threshold IS NOT NULL)),
    CONSTRAINT ck_detection_provenance_legacy CHECK (
        attestation <> 'unattested_legacy'
        OR (artifact_sha256 IS NULL AND input_sha256 IS NULL)),
    CONSTRAINT ck_detection_provenance_calibration CHECK (
        calibrated = (calibration_ref IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_detection_provenance_tenant_artifact
    ON detection_provenance (tenant_id, artifact_sha256, created_at DESC);

CREATE OR REPLACE FUNCTION detection_provenance_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'detection_provenance is append-only (UPDATE refused)'
        USING ERRCODE = 'insufficient_privilege';
END $$;

DROP TRIGGER IF EXISTS trg_detection_provenance_immutable ON detection_provenance;
CREATE TRIGGER trg_detection_provenance_immutable
    BEFORE UPDATE ON detection_provenance
    FOR EACH ROW EXECUTE FUNCTION detection_provenance_immutable();

REVOKE ALL ON detection_provenance FROM PUBLIC;
ALTER TABLE detection_provenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE detection_provenance FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON detection_provenance;
CREATE POLICY tenant_isolation ON detection_provenance
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

-- تأكيد كتالوج: الجدول يدخل v206 مُقفَلاً، لا يعتمد على تمريرة لاحقة.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class
                   WHERE oid = 'public.detection_provenance'::regclass
                     AND relrowsecurity AND relforcerowsecurity) THEN
        RAISE EXCEPTION 'v239: detection_provenance without RLS+FORCE';
    END IF;
END $$;
COMMIT;
