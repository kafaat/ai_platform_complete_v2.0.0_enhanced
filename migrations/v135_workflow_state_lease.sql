-- ════════════════════════════════════════════════════════════
-- SAHOOL v135 — workflow_state: عقد كاتب-واحد (single-writer lease)
-- ════════════════════════════════════════════════════════════
-- الفجوة: workflow قابل للاستئناف بلا حارس كاتب-واحد ⇒ عاملان يستأنفان نفس
-- workflow_id ينفّذان الخطوات معاً (تنفيذ مزدوج لأثر جانبيّ). نُحاكي مثبّت
-- الـoutbox (FOR UPDATE SKIP LOCKED — services/sahool-platform/api/event_bus.py)
-- على مخزن الـworkflow: عمودا عقد (lease) يسمحان لعامل واحد فقط بالمطالبة.
--
-- lease_owner:      معرّف العامل المالك للعقد الحيّ (worker id — uuid افتراضاً).
-- lease_expires_at: انتهاء العقد. عقد حيّ (lease_expires_at > NOW()) بيد مالك
--                   مختلف ⇒ يُرفض التشغيل. عقد منتهٍ ⇒ قابل لإعادة المطالبة.
-- يُمسَح/يُجدَّد العقد عند الحفظ/الإكمال. مسار الاستئناف بلا تغيير (المكتمل لا يُعاد).
--
-- فهرس جزئيّ لإعادة المطالبة بالعقود المنتهية بكفاءة (running + منتهٍ). RLS (FORCE)
-- على workflow_state قائمة من v16 (عزل المستأجِر) — لا تتغيّر، والعمودان يخضعان لها.
-- إضافيّ idempotent بالكامل (IF NOT EXISTS). بعد v132.

ALTER TABLE workflow_state
    ADD COLUMN IF NOT EXISTS lease_owner      TEXT;
ALTER TABLE workflow_state
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

COMMENT ON COLUMN workflow_state.lease_owner IS
    'مالك عقد الكاتب-الواحد (worker id): العامل المخوّل بتنفيذ خطوات هذا الـworkflow.';
COMMENT ON COLUMN workflow_state.lease_expires_at IS
    'انتهاء عقد الكاتب-الواحد: عقد حيّ (>NOW()) بيد مالك مختلف يُرفض؛ منتهٍ قابل لإعادة المطالبة.';

-- فهرس جزئيّ لإعادة المطالبة بالعقود المنتهية (workflows جارية بعقد قائم).
CREATE INDEX IF NOT EXISTS idx_workflow_lease_reclaim
    ON workflow_state(status, lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;
