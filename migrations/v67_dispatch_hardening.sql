-- SAHOOL v67 — migrations/v67_dispatch_hardening.sql
-- تصليب موزِّع القرار: مفتاح لاتكرار + توسيع دورة حياة التنفيذ (المرحلة A، الشريحة 2).
--
-- الفجوة (تشغيليّة): جدول dispatch_decisions (v66) يسجّل القرار ويعمل طابوراً، لكن:
--   1. لا حارس لاتكرار: نداء execute مكرّر لنفس التوصية يُدرِج صفّين «queued» ⇒ خطر
--      إطلاق مزدوج (ريّ/رشّ مرّتين). نضيف idempotency_key + فهرساً فريداً جزئيّاً على
--      الحالات الحيّة (queued/dispatched) لكلّ مستأجِر — يمنع التكرار قاعديّاً.
--   2. exec_status ثلاثيّ ساكن (not_executed/queued/executed) لا يكفي للحلقة: المستهلِك
--      (الشريحة 3) يحتاج «dispatched» (أُخطِر البشر)، والسجلّ (الشريحة 4) يحتاج «failed».
--      نوسّع CHECK ليشمل dispatched/failed مع إبقاء دورة الحياة محروسة في core/.
--
-- idempotent بالكامل (ADD COLUMN/INDEX IF NOT EXISTS + DROP/ADD CONSTRAINT محروس) —
-- آمن إعادة التطبيق. يعدّل dispatch_decisions (v66) دون كسر الأعمدة/الـRLS القائمة.

-- ── 1. مفتاح اللاتكرار (idempotency) ─────────────────────────────────
ALTER TABLE dispatch_decisions
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(120);

COMMENT ON COLUMN dispatch_decisions.idempotency_key IS
    'مفتاح لاتكرار حتميّ من (recommendation_id|action_type|field_id) — يمنع الإطلاق المزدوج. v67.';

-- فهرس فريد جزئيّ: لا قراران حيّان (queued/dispatched) بنفس المفتاح لنفس المستأجِر.
-- جزئيّ عمداً: بعد executed/failed يُسمح بقرار جديد لنفس التوصية (دورة لاحقة مشروعة).
CREATE UNIQUE INDEX IF NOT EXISTS uq_dispatch_idempotency_live
    ON dispatch_decisions (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND exec_status IN ('queued', 'dispatched');

-- ── 2. توسيع دورة حياة exec_status ───────────────────────────────────
-- القيد المُضمَّن في v66 اسمه التلقائيّ dispatch_decisions_exec_status_check؛ نُسقطه
-- محروساً ونعيد بناءه بالقيم الموسَّعة. الانتقالات المسموحة محروسة في core/dispatch_lifecycle.
ALTER TABLE dispatch_decisions
    DROP CONSTRAINT IF EXISTS dispatch_decisions_exec_status_check;
ALTER TABLE dispatch_decisions
    ADD CONSTRAINT dispatch_decisions_exec_status_check
    CHECK (exec_status IN ('not_executed', 'queued', 'dispatched', 'executed', 'failed'));

COMMENT ON COLUMN dispatch_decisions.exec_status IS
    'دورة حياة التنفيذ: not_executed | queued | dispatched | executed | failed (محروسة في core/dispatch_lifecycle). v67.';

-- فهرس جزئيّ للقرارات المُسلَّمة قيد المتابعة (يستعلمها السجلّ لتسجيل النتيجة).
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_dispatched
    ON dispatch_decisions (exec_status) WHERE exec_status = 'dispatched';
