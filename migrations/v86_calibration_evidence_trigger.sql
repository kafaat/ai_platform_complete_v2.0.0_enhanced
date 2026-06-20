-- v86: trigger تحديث calibration_evidence التراكمي عند INSERT في outcome_record.
-- الفجوة: الفرع يحسب evidence ديناميكيّاً من outcome_record عند كلّ طلب (صحيح
-- وظيفيّاً)، لكنّه يُعيد الحساب من كلّ الصفوف في كلّ مرّة. هذا الـtrigger
-- يُدام التجميع المُسبَق (sample_count/success_rate/evidence_level) في جدول
-- calibration_evidence — فيجعل GET /evidence قراءة O(1) لا O(n).
--
-- idempotent: لا يلمس أعمدة outcome_record أو calibration_override الموجودة.
-- يُنشئ calibration_evidence إن لم يوجد (لا يعيد تعريفه).
--
-- ── مراجعة الدمج (تصحيحان عن نسخة المرفق، حفاظاً على الصدق والصحّة) ──
--   ١) فهرس فريد بتعبير COALESCE بدل قيد UNIQUE داخل الجدول: PostgreSQL لا يسمح
--      بتعبير داخل قيد UNIQUE على مستوى الجدول (يلزم UNIQUE INDEX) — وإلّا فشل التطبيق؛
--      و ON CONFLICT يستنتج هذا الفهرس التعبيريّ.
--   ٢) النجاح من عمود outcome_record.success القانونيّ (BOOLEAN) أوّلاً، مع رجوع
--      احتياطيّ إلى metrics->>'success_flag' — كي لا يُنقَص عدّ النجاح (الحقل القانونيّ
--      في v79 هو success، لا metrics). success=NULL ⇒ لا يُحتسب نجاحاً (لا تلفيق).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS calibration_evidence (
    evidence_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID         NOT NULL,
    region              VARCHAR(40)  NOT NULL,
    crop_type           TEXT,
    param_key           TEXT         NOT NULL DEFAULT 'general',
    sample_count        INT          NOT NULL DEFAULT 0,
    success_count       INT          NOT NULL DEFAULT 0,
    success_rate        NUMERIC(5,4),
    evidence_level      TEXT         NOT NULL DEFAULT 'none'
                            CHECK (evidence_level IN
                                ('none','expert_opinion','field_preliminary','field_verified')),
    thresholds_estimated BOOLEAN     NOT NULL DEFAULT TRUE,
    last_outcome_at     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
-- مفتاح فريد تعبيريّ (يُعامِل crop_type الغائب كـ'*') — فهرس فريد لا قيد جدول.
CREATE UNIQUE INDEX IF NOT EXISTS ux_calibration_evidence
    ON calibration_evidence (tenant_id, region, COALESCE(crop_type, '*'), param_key);
CREATE INDEX IF NOT EXISTS idx_calibration_evidence_lookup
    ON calibration_evidence (tenant_id, region, param_key);

ALTER TABLE calibration_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE calibration_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ce_tenant ON calibration_evidence;
CREATE POLICY ce_tenant ON calibration_evidence
    USING  (tenant_id = current_setting('app.current_tenant',true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant',true)::uuid);

-- دالّة التحديث التراكمي
CREATE OR REPLACE FUNCTION fn_update_calibration_evidence()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_region VARCHAR(40);
    v_success BOOLEAN;
BEGIN
    v_region  := COALESCE(NEW.region, 'unknown');
    -- النجاح من العمود القانونيّ success أوّلاً، ثمّ metrics احتياطاً (NULL ⇒ لا نجاح).
    v_success := COALESCE(
        NEW.success,
        (NEW.metrics IS NOT NULL AND (NEW.metrics->>'success_flag') = 'true'),
        FALSE
    );

    INSERT INTO calibration_evidence
        (tenant_id, region, param_key,
         sample_count, success_count, success_rate,
         evidence_level, thresholds_estimated,
         last_outcome_at, updated_at)
    VALUES (
        NEW.tenant_id, v_region, 'general',
        1,
        CASE WHEN v_success THEN 1 ELSE 0 END,
        NULL,
        'expert_opinion', TRUE,
        NOW(), NOW()
    )
    ON CONFLICT (tenant_id, region, COALESCE(crop_type, '*'), param_key)
    DO UPDATE SET
        sample_count  = calibration_evidence.sample_count + 1,
        success_count = calibration_evidence.success_count +
                        CASE WHEN v_success THEN 1 ELSE 0 END,
        success_rate  = CASE
            WHEN (calibration_evidence.sample_count + 1) >= 5
            THEN ROUND(
                (calibration_evidence.success_count +
                 CASE WHEN v_success THEN 1 ELSE 0 END)::NUMERIC
                / (calibration_evidence.sample_count + 1), 4)
            ELSE NULL END,
        evidence_level = CASE
            WHEN (calibration_evidence.sample_count + 1) >= 30 THEN 'field_verified'
            WHEN (calibration_evidence.sample_count + 1) >= 5  THEN 'field_preliminary'
            ELSE 'expert_opinion' END,
        last_outcome_at = NOW(),
        updated_at      = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_calibration_evidence ON outcome_record;
CREATE TRIGGER trg_calibration_evidence
    AFTER INSERT ON outcome_record
    FOR EACH ROW EXECUTE FUNCTION fn_update_calibration_evidence();

COMMENT ON TABLE calibration_evidence IS
    'تجميع مُسبَق للدليل التراكمي من outcome_record (يُحدَّث بـtrigger).
     يُغني عن حساب evidence ديناميكيّاً من كلّ الصفوف عند كلّ طلب (O(1) بدل O(n)).
     متوافق مع evidence_from_persisted_outcomes في calibration.py — كلاهما يصلان
     نفس النتيجة؛ الـtrigger أسرع للـendpoints المتكرّرة. v86.';
