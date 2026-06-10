-- v17: أعمدة WorkflowState الناقصة في v16 — ليحفظ PostgresWorkflowStore الحالة
-- كاملةً فيصمد الاستئناف عبر إعادة التشغيل بلا فقدان (compensated_steps لـSaga،
-- workflow_version لكشف عدم تطابق التعريف، correlation_id لخيط التتبّع).
ALTER TABLE workflow_state
    ADD COLUMN IF NOT EXISTS compensated_steps JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE workflow_state
    ADD COLUMN IF NOT EXISTS workflow_version TEXT NOT NULL DEFAULT '1';
ALTER TABLE workflow_state
    ADD COLUMN IF NOT EXISTS correlation_id TEXT;
