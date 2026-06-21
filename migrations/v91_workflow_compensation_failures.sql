-- ════════════════════════════════════════════════════════════
-- SAHOOL v91 — workflow_state: عمود compensation_failures (صدق Saga)
-- ════════════════════════════════════════════════════════════
-- تقوية محرّك السير/Saga (Stage A P1): فشل خطوة تعويض (compensate) كان يُبتلَع
-- صامتاً في _compensate (except: continue) ⇒ تراجع جزئيّ غير متّسق دون أثر.
-- الآن المحرّك يُسجّله عند ERROR ويحفظه في الحالة (fail-loud)؛ هذا العمود يُديم
-- ذلك السجلّ ليصمد عبر إعادة التشغيل ويظهر في الرصد (workflow_trace) للتحقيق.
--
-- كلّ عنصر JSONB: {"step_id": "...", "error": "..."} لخطوة تعذّر تراجعها.
-- يُضاف كذلك compensation_failed إلى مجموعة قيم status (تراجع جزئيّ نهائيّ يحتاج
-- تدخّلاً يدويّاً — لا COMPENSATED زائفة). RLS (FORCE) على workflow_state قائمة
-- من v16 (عزل المستأجِر) — لا تتغيّر هنا، والعمود يخضع لها كبقيّة الأعمدة.
-- idempotent بالكامل (IF NOT EXISTS).

ALTER TABLE workflow_state
    ADD COLUMN IF NOT EXISTS compensation_failures JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN workflow_state.compensation_failures IS
    'فشل تعويض Saga (fail-loud): [{step_id, error}] لخطوات تعذّر تراجعها — نظام غير متّسق يحتاج تحقيقاً يدويّاً.';
