-- ════════════════════════════════════════════════════════════
-- SAHOOL v36 — التنبيهات الزراعيّة (Agronomic alerts) لكلّ مستأجِر
-- ════════════════════════════════════════════════════════════
-- تنبيهات مُصنَّفة (رطوبة منخفضة/أمطار غزيرة/خطر مرض/إجهاد حراريّ/خطر صقيع)
-- بدرجة خطورة (info/warning/critical) وحالة (active/acknowledged/resolved)،
-- مربوطة بحقل اختياريّ ومعزولة لكلّ مستأجِر (RLS). نمط activities (v35).

CREATE TABLE IF NOT EXISTS alerts (
    alert_id    VARCHAR(50)  PRIMARY KEY,
    tenant_id   UUID         NOT NULL,
    field_id    VARCHAR(50)  REFERENCES fields(field_id) ON DELETE CASCADE,  -- حقل اختياريّ
    alert_type  VARCHAR(20)  NOT NULL
        CHECK (alert_type IN ('low_moisture', 'heavy_rain', 'disease_risk',
                              'heat_stress', 'frost_risk', 'vegetation_stress', 'other')),
    severity    VARCHAR(10)  NOT NULL
        CHECK (severity IN ('info', 'warning', 'critical')),
    title_ar    VARCHAR(200),                                -- عنوان مختصر
    message_ar  TEXT,                                        -- نصّ التنبيه
    status      VARCHAR(20)  NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'acknowledged', 'resolved')),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_field  ON alerts(field_id);
CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts(tenant_id, status, severity);

DROP TRIGGER IF EXISTS trg_alerts_updated_at ON alerts;
CREATE OR REPLACE TRIGGER trg_alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

SELECT _sahool_apply_tenant_rls('alerts');

-- ── vegetation_stress ─────────────────────────────────────────────
-- محرّك التنبيهات (alert_rules.py) يُصدر vegetation_stress منذ Stage D، والـCHECK أعلاه
-- لا يعرفه: كلّ إدراج يُرفَض فتُلغى دفعة الحقل كلّها. CREATE TABLE IF NOT EXISTS لا يُغيّر
-- جدولاً قائماً، والبيان يُعاد تطبيقه كلّ نشر (GATE-01 يُجمّده، فلا ملفّ جديد) — لذا يُوسَّع
-- القيد هنا، مرّةً، ثمّ يتخطّى: إن احتوى القيد القائم كلّ قيمة مطلوبة فلا شيء. NOT VALID لأنّ
-- القيم الجديدة مجموعةٌ فوقيّة للقديمة، فالصفوف القائمة صالحة بالبناء (ولا VALIDATE أعمى).
DO $v36_types$
DECLARE
    wanted text[] := ARRAY['disease_risk', 'frost_risk', 'heat_stress', 'heavy_rain',
                           'low_moisture', 'other', 'vegetation_stress'];
    con    record;
    have   text;
BEGIN
    SELECT c.conname, pg_get_constraintdef(c.oid) AS def INTO con
      FROM pg_constraint c
     WHERE c.conrelid = 'public.alerts'::regclass AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%alert_type%';
    IF FOUND THEN
        have := con.def;
        IF NOT EXISTS (
            SELECT 1 FROM unnest(wanted) AS w(v) WHERE have NOT LIKE '%''' || w.v || '''%'
        ) THEN
            RETURN;
        END IF;
        EXECUTE format('ALTER TABLE alerts DROP CONSTRAINT %I', con.conname);
    END IF;
    EXECUTE format(
        'ALTER TABLE alerts ADD CONSTRAINT alerts_alert_type_check CHECK (alert_type IN (%s)) NOT VALID',
        (SELECT string_agg(quote_literal(v), ', ' ORDER BY v) FROM unnest(wanted) AS w(v)));
END $v36_types$;

COMMENT ON TABLE alerts IS 'التنبيهات الزراعيّة المُصنَّفة لكلّ مستأجِر (رطوبة/أمطار/مرض/حرارة/صقيع). نمط activities. v36.';
