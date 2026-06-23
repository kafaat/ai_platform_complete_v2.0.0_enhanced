-- v16: حالة الـworkflow متعدّد الخطوات (durable, resumable)
-- يدعم workflow_engine.py: يحفظ تقدّم الخطوات ليُستأنف من حيث توقّف عند
-- الفشل/إعادة التشغيل. RLS مُطبَّق (كلّ مستأجر workflows الخاصّة به فقط).

CREATE TABLE IF NOT EXISTS workflow_state (
    workflow_id      TEXT PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    status           TEXT NOT NULL DEFAULT 'running',  -- running|completed|failed|suspended
    completed_steps  JSONB NOT NULL DEFAULT '[]'::jsonb,  -- ترتيب الخطوات المكتملة
    step_results     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {step_id: result}
    context          JSONB NOT NULL DEFAULT '{}'::jsonb,  -- السياق المتراكم
    current_step     TEXT,
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_tenant_status
    ON workflow_state(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_workflow_updated
    ON workflow_state(updated_at DESC);

-- RLS: عزل المستأجرين (نفس نمط بقيّة الجداول)
-- تقوية: FORCE حتّى لا يتجاوز مالك الجدول العزل، ومقارنة NULLIF آمنة (cast ::uuid
-- على سياق فارغ '' كان يرمي خطأ — نطابق نصّيّاً كبقيّة الجداول).
ALTER TABLE workflow_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_state FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workflow_tenant_isolation ON workflow_state;
CREATE POLICY workflow_tenant_isolation ON workflow_state
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));

-- تحديث updated_at تلقائيّاً
CREATE OR REPLACE FUNCTION touch_workflow_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_workflow_updated ON workflow_state;
CREATE OR REPLACE TRIGGER trg_workflow_updated
    BEFORE UPDATE ON workflow_state
    FOR EACH ROW EXECUTE FUNCTION touch_workflow_updated_at();
