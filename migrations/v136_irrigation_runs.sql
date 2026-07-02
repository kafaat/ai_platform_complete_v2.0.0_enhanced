-- v136: irrigation_runs — دفتر أحداث الريّ الفيزيائيّ المنفصلة (بداية/نهاية تشغيل صمّام)
-- ════════════════════════════════════════════════════════════════════════
-- المشكلة (سطر v29.5-op-2): يملك SAHOOL جداول «نيّة» فقط — irrigation_schedules /
-- irrigation_valves (v25) + دفتر مياه **يوميّ** مُجمَّع water_ledger (v98). لا يوجد
-- سجلّ لحدث تشغيل فيزيائيّ منفصل (متى فُتح صمّام، متى أُغلق، كم حجم الماء لهذا التشغيل).
-- هذا الجدول يُدِيم «حدث تشغيل» لكلّ دورة فتح→إغلاق فيجعل التشغيل الفعليّ مرئيّاً/قابلاً
-- للتدقيق — وهو الركيزة الرصديّة لِإقرار جهاز فيزيائيّ (ACK) مستقبلاً.
--
-- صدق منهجيّ صارم (نمط v98_water_ledger): هذا **تخزين/رصد** لأحداث تُشتقّ من عمليّة
-- الصمّام (open/close) — لا اختراع أرقام. الحجم (volume_l/volume_mm) يُملأ فقط إن حملته
-- الحمولة، وإلّا NULL (لا تلفيق). started_at افتراضه NOW() (لحظة الفتح)، stopped_at يبقى
-- NULL حتّى الإغلاق.
--
-- النموذج: صفّ لكلّ تشغيل. status دورة حياة ('running' عند الفتح → 'completed' عند الإغلاق؛
-- 'aborted'/'failed' لمسارات مستقبليّة). المفاتيح field_id/valve_id نصّيّة (نمط v98/v95).
--
-- العزل: RLS على tenant_id (تفعيل صريح + FORCE + سياسة tenant_isolation على
-- current_setting('app.current_tenant')، fail-closed: سياق فارغ ⇒ صفر صفوف) — نفس نمط
-- v98_water_ledger حرفيّاً. idempotent بالكامل (IF NOT EXISTS + DROP POLICY IF EXISTS).

BEGIN;

CREATE TABLE IF NOT EXISTS irrigation_runs (
    id             UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,  -- معرّف التشغيل
    tenant_id      UUID         NOT NULL,                                         -- عزل المستأجِر (RLS أدناه)
    field_id       TEXT,                                                          -- الحقل (نمط v98: نصّ) — NULL إن غاب
    valve_id       TEXT,                                                          -- الصمّام المُشغَّل (نصّ) — NULL إن غاب
    schedule_id    TEXT,                                                          -- الجدول المُطلِق إن وُجد — NULL يدويّ
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),                           -- لحظة الفتح
    stopped_at     TIMESTAMPTZ,                                                   -- لحظة الإغلاق — NULL أثناء الجريان
    volume_l       NUMERIC,                                                       -- حجم الماء (لتر) — NULL إن لم تحمله الحمولة
    volume_mm      NUMERIC,                                                       -- حجم الماء (مم) — NULL إن لم تحمله الحمولة
    trigger_source TEXT,                                                          -- مصدر الإطلاق (valve_api/schedule/...)
    status         TEXT         NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'aborted', 'failed')),         -- دورة حياة التشغيل
    created_at     TIMESTAMPTZ  DEFAULT NOW()
);

-- فهرس القراءة الرئيس: تشغيلات حقلٍ بترتيب زمنيّ (تدقيق/عرض تاريخ الريّ).
CREATE INDEX IF NOT EXISTS idx_irrigation_runs_field_started
    ON irrigation_runs (field_id, started_at);

-- فهرس جزئيّ للمسار الساخن: إيجاد التشغيل الجاري لصمّام عند الإغلاق (WHERE status='running').
CREATE INDEX IF NOT EXISTS idx_irrigation_runs_running
    ON irrigation_runs (valve_id, started_at)
    WHERE status = 'running';

COMMENT ON TABLE  irrigation_runs IS
    'دفتر أحداث الريّ الفيزيائيّ المنفصلة (بداية/نهاية تشغيل صمّام) — صفّ لكلّ دورة فتح→إغلاق: بداية/نهاية/حجم/مصدر/حالة. رصد لأحداث تُشتقّ من عمليّة الصمّام، لا اختراع أرقام (الحجم NULL إن لم تحمله الحمولة). ركيزة رصديّة لِإقرار جهاز فيزيائيّ (ACK) مستقبلاً. معزول بالمستأجِر (RLS). v136.';
COMMENT ON COLUMN irrigation_runs.status IS
    'running=جارٍ (بعد الفتح) · completed=اكتمل (بعد الإغلاق) · aborted/failed=مسارات مستقبليّة.';
COMMENT ON COLUMN irrigation_runs.volume_l IS 'حجم الماء (لتر) إن حملته الحمولة، وإلّا NULL (لا تلفيق).';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
-- FORCE يُخضِع حتّى مالك الجدول للسياسة (دفاع عمق). السياسة مُنطّقة بالمستأجِر عبر
-- current_setting('app.current_tenant') (fail-closed: سياق فارغ ⇒ صفر صفوف).
ALTER TABLE irrigation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_runs FORCE ROW LEVEL SECURITY;  -- يُخضِع المالك أيضاً

DROP POLICY IF EXISTS tenant_isolation ON irrigation_runs;  -- idempotency
CREATE POLICY tenant_isolation ON irrigation_runs
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        -- عزل الكتابة (دفاع عمق): بلا سياق (هجرات/نظام) تُسمح، وإلّا المطابقة فقط.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMIT;
