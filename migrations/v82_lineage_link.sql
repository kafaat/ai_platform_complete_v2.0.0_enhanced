-- migrations/v82_lineage_link.sql
--
-- توحيد نَسَب التنفيذ (Unified Execution Lineage، PR #396) بنمط الإغلاق المرن:
-- يوجد نظاما قرار متوازيان بمعرّفات مختلفة — `dec_*` (قرارات المحصول، decision_record
-- v78) و`disp_*` (dispatch_decisions v66) + execution_ledger (v68). بدل إعادة تسمية أيّ
-- معرّف قائم (يكسر التاريخ والمراجع)، يُضاف **فوقها** معرّف عالميّ `lin_*` يربط كلّ
-- مراجعها في سلسلة واحدة قابلة للتتبّع — القديم يستمر، الجديد يعمل.
--
-- هذا الجدول جسر الربط: صفّ لكلّ (lineage_id ↔ مرجع)، فيُجمَع decision/dispatch/command/
-- execution/outcome تحت معرّف واحد. يُستهلَك خلف علم FEATURE_UNIFIED_LINEAGE (إغلاق مرن).
--
--   • lineage_id TEXT (بادئة lin_) — المعرّف العالميّ الموحّد للسلسلة.
--   • ref_type CHECK ضمن المجموعة المغلقة (decision|dispatch|command|execution|outcome).
--   • UNIQUE(tenant_id, ref_type, ref_id) ⇒ كلّ مرجع يُربَط مرّةً (ON CONFLICT DO NOTHING).
--   • فهرس (tenant_id, lineage_id) لجلب كامل السلسلة بكفاءة.
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE TABLE IF NOT EXISTS lineage_link (
    lineage_id  TEXT         NOT NULL,                -- المعرّف العالميّ الموحّد (بادئة lin_)
    tenant_id   UUID         NOT NULL,                -- عزل المستأجِر (RLS أدناه)
    ref_type    TEXT         NOT NULL                 -- نوع المرجع المربوط (مجموعة مغلقة)
        CHECK (ref_type IN ('decision', 'dispatch', 'command', 'execution', 'outcome')),
    ref_id      TEXT         NOT NULL,                -- معرّف المرجع نفسه (dec_/disp_/…)
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, ref_type, ref_id)             -- كلّ مرجع يُربَط مرّةً (upsert آمن)
);

-- جلب كامل السلسلة (كلّ روابط lineage_id لمستأجِر) بكفاءة.
CREATE INDEX IF NOT EXISTS idx_lineage_link_chain
    ON lineage_link (tenant_id, lineage_id);

COMMENT ON TABLE  lineage_link IS
    'جسر نَسَب التنفيذ الموحّد: يربط معرّفاً عالميّاً lin_ بمراجع decision/dispatch/command/execution/outcome. tenant-isolated عبر RLS. v82.';
COMMENT ON COLUMN lineage_link.lineage_id IS 'المعرّف العالميّ الموحّد للسلسلة (بادئة lin_).';
COMMENT ON COLUMN lineage_link.ref_type   IS 'نوع المرجع: decision|dispatch|command|execution|outcome (مجموعة مغلقة).';
COMMENT ON COLUMN lineage_link.ref_id     IS 'معرّف المرجع القائم (dec_/disp_/command_id/…) — يُربَط لا يُعاد تسميته.';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE lineage_link ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineage_link FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON lineage_link;
CREATE POLICY tenant_isolation ON lineage_link
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
