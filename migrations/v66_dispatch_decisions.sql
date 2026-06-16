-- SAHOOL v66 — migrations/v66_dispatch_decisions.sql
-- سجلّ قرارات الإرسال المحروسة (guarded-dispatch decision→execution audit trail).
--
-- الفجوة (من تدقيق المعماريّة): لا سجلّ تدقيق يربط قرار التوصية بتنفيذه — كلّ
-- guarded-dispatch يُتّخذ ويُنسى. هذا الجدول يسجّل **كلّ** قرار (محظور /
-- بانتظار موافقة / جاهز) مع أسباب الحظر والتحذير والموافقات المطلوبة/المُجمَّعة،
-- ويعمل أيضاً كطابور أوامر (command queue) يستهلكه الـactuator لاحقاً
-- (exec_status='queued') — فيُغلِق الحلقة من القرار إلى التنفيذ.
--
-- عزل المستأجرين إلزاميّ: يُطبَّق RLS صراحةً عبر _sahool_apply_tenant_rls
-- (المعرّفة في v9_rls_tenant_isolation.sql) كي يخضع الجدول لـ
-- current_setting('app.current_tenant', true).
--
-- idempotent بالكامل (CREATE TABLE/INDEX IF NOT EXISTS + حارس DO على RLS) —
-- آمن إعادة التطبيق كلّ إقلاع. يطبّقه CI Integration Tests عبر MANIFEST كامل.

CREATE TABLE IF NOT EXISTS dispatch_decisions (
    decision_id         VARCHAR(40)  PRIMARY KEY,
    tenant_id           UUID         NOT NULL,           -- عزل المستأجر (RLS أدناه)
    recommendation_id   VARCHAR(80)  NOT NULL,           -- التوصية المصدر للقرار
    action_type         VARCHAR(60)  NOT NULL,           -- نوع الإجراء المُقترح
    field_id            VARCHAR(50),                     -- الحقل (اختياريّ)
    -- حالة القرار: محظور / بانتظار موافقة / جاهز للتنفيذ.
    state               VARCHAR(24)  NOT NULL
        CHECK (state IN ('blocked', 'pending_approval', 'ready')),
    risk_level          VARCHAR(16)  NOT NULL,           -- مستوى المخاطرة المُقدّر
    required_approvals  INT          NOT NULL DEFAULT 0, -- عدد الموافقات المطلوبة
    approvals_collected INT          NOT NULL DEFAULT 0, -- عدد الموافقات المُجمَّعة
    halt_breaches       JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- خروقات حاجزة (تمنع التنفيذ)
    warn_breaches       JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- خروقات تحذيريّة (لا تمنع)
    reason_ar           TEXT,                            -- سبب القرار بالعربيّة (شرح بشريّ)
    command             JSONB,                           -- حمولة أمر الـactuator عند READY، وإلا NULL
    -- حالة التنفيذ: لم يُنفّذ / في الطابور / نُفّذ — يحرّكها الـactuator.
    exec_status         VARCHAR(16)  NOT NULL DEFAULT 'not_executed'
        CHECK (exec_status IN ('not_executed', 'queued', 'executed')),
    created_by          VARCHAR(80),                     -- من اتّخذ القرار (مستخدم/نظام)
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- فهرس tenant_id لكفاءة مسح RLS (كلّ استعلام يُرشّح بـtenant_id).
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_tenant ON dispatch_decisions (tenant_id);
-- فهرس field_id للبحث عن قرارات حقل بعينه.
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_field  ON dispatch_decisions (field_id);
-- فهرس جزئيّ لطابور الأوامر — يستهلكه الـactuator (المنتظِرون فقط).
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_queued
    ON dispatch_decisions (exec_status) WHERE exec_status = 'queued';

COMMENT ON TABLE  dispatch_decisions IS
    'سجلّ تدقيق قرارات الإرسال المحروسة (decision→execution) + طابور أوامر الـactuator. tenant-isolated عبر RLS. v66.';
COMMENT ON COLUMN dispatch_decisions.state         IS 'حالة القرار: blocked | pending_approval | ready.';
COMMENT ON COLUMN dispatch_decisions.command       IS 'حمولة أمر الـactuator عند READY، وإلا NULL.';
COMMENT ON COLUMN dispatch_decisions.exec_status   IS 'حالة التنفيذ: not_executed | queued | executed (يحرّكها الـactuator).';

-- عزل المستأجرين (RLS) — تطبيق صريح إلزاميّ، محروس بوجود الدالّة المساعدة
-- (المعرّفة في v9_rls_tenant_isolation.sql): ENABLE + FORCE + سياسة tenant_isolation.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = '_sahool_apply_tenant_rls') THEN
        PERFORM _sahool_apply_tenant_rls('dispatch_decisions');
        RAISE NOTICE 'v66: RLS مُفعّل على dispatch_decisions';
    ELSE
        RAISE NOTICE 'v66: تخطّي تطبيق RLS الصريح — الدالّة المساعدة غير موجودة بعد (ستغطّيه v56)';
    END IF;
END $$;
