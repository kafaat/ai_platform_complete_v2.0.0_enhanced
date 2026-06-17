-- SAHOOL v68 — migrations/v68_execution_ledger.sql
-- سجلّ التنفيذ append-only: يربط القرار المُسلَّم بنتيجته المُقاسة (المرحلة A، الشريحة 4).
--
-- الفجوة (تدقيق المعماريّة): الحلقة كانت مفتوحة عند آخر خطوة — توصية←قرار←أمر، ثمّ
-- صمت. لا أثر لِـ«ماذا حدث فعلاً» بعد التسليم. هذا الجدول يُغلِق الحلقة ويقيسها: لكلّ
-- قرار مُسلَّم (dispatched) قيدٌ بنتيجته (executed/failed) + بصمة تدقيق (content_hash)
-- تكشف التلاعب. مرجع متبادَل مع dispatch_decisions (decision_id) وdفتر farm_ledger
-- الماليّ (التكلفة) — فيكتمل الأثر: توصية ← قرار ← أمر ← نتيجة مُقاسة.
--
-- append-only: لا UPDATE/DELETE في مسار التطبيق (محاسبة/تدقيق) — كما custody_chain (v65).
-- عزل المستأجرين إلزاميّ عبر _sahool_apply_tenant_rls (v9). idempotent بالكامل.

CREATE TABLE IF NOT EXISTS execution_ledger (
    ledger_id       VARCHAR(40)  PRIMARY KEY,
    tenant_id       UUID         NOT NULL,            -- عزل المستأجر (RLS أدناه)
    decision_id     VARCHAR(40)  NOT NULL,            -- القرار المصدر (dispatch_decisions)
    action_type     VARCHAR(60)  NOT NULL,            -- نوع الإجراء المُنفَّذ
    field_id        VARCHAR(50),                      -- الحقل (اختياريّ)
    channel         VARCHAR(24),                      -- قناة التسليم (sms/whatsapp/mobile_task)
    -- النتيجة النهائيّة: نُفِّذ أو فشل (تطابق دورة حياة exec_status في core/dispatch_lifecycle).
    outcome         VARCHAR(16)  NOT NULL
        CHECK (outcome IN ('executed', 'failed')),
    note_ar         TEXT,                             -- ملاحظة بشريّة (سبب الفشل/تفاصيل التنفيذ)
    detail          JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- تفاصيل مهيكلة (كمّيّة فعليّة…)
    content_hash    VARCHAR(64)  NOT NULL,            -- SHA-256 لسلامة القيد (كشف التلاعب)
    recorded_by     VARCHAR(80),                      -- من سجّل النتيجة (مستخدم/نظام)
    recorded_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- فهرس tenant_id لكفاءة مسح RLS (كلّ استعلام يُرشّح بـtenant_id).
CREATE INDEX IF NOT EXISTS idx_execution_ledger_tenant   ON execution_ledger (tenant_id);
-- فهرس decision_id لربط النتيجة بقرارها (الاستعلام المتبادَل الأكثر شيوعاً).
CREATE INDEX IF NOT EXISTS idx_execution_ledger_decision ON execution_ledger (decision_id);
-- فهرس field_id لتاريخ تنفيذ حقل بعينه.
CREATE INDEX IF NOT EXISTS idx_execution_ledger_field    ON execution_ledger (field_id);

COMMENT ON TABLE  execution_ledger IS
    'سجلّ تنفيذ append-only: نتيجة كلّ قرار مُسلَّم (executed/failed) + content_hash للتدقيق. tenant-isolated عبر RLS. v68.';
COMMENT ON COLUMN execution_ledger.outcome      IS 'النتيجة النهائيّة: executed | failed.';
COMMENT ON COLUMN execution_ledger.content_hash IS 'SHA-256 لمحتوى القيد (decision|outcome|at|detail) — يكشف التلاعب اللاحق.';

-- عزل المستأجرين (RLS) — تطبيق صريح إلزاميّ، محروس بوجود الدالّة المساعدة (v9):
-- ENABLE + FORCE + سياسة tenant_isolation (يُنشأ بعد v9_rls_force_all، فالـFORCE صريح هنا).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = '_sahool_apply_tenant_rls') THEN
        PERFORM _sahool_apply_tenant_rls('execution_ledger');
        RAISE NOTICE 'v68: RLS مُفعّل على execution_ledger';
    ELSE
        RAISE NOTICE 'v68: تخطّي تطبيق RLS الصريح — الدالّة المساعدة غير موجودة بعد (ستغطّيه v56)';
    END IF;
END $$;
