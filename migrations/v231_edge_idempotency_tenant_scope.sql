-- ═══════════════════════════════════════════════════════════════════
-- v231_edge_idempotency_tenant_scope.sql — ديدوب مزامنة الحافة لكلّ مستأجِر
-- ═══════════════════════════════════════════════════════════════════
-- عطلان مقيسان (مراجعة Copilot على #997):
--   ١. v9_edge_idempotency جعل التفرّد **عالميّاً** على idempotency_key بينما البحث عن
--      الصفّ القائم في api/routers/edge.py مقيّد بالمستأجِر. فمفتاحٌ يملكه المستأجِر A
--      يجعل إدراج المستأجِر B يصطدم بـON CONFLICT، ثمّ لا يجد B صفّاً في نطاقه فيُرفَع
--      409 edge_idempotency_conflict على حدثٍ صالح.
--   ٢. العمود VARCHAR(32) بينما عقد الـAPI (EdgeSyncRequest) يقبل حتّى 128 حرفاً؛ مفتاحٌ
--      بطول 33–128 يجتاز التحقّق ثمّ يسقط عند حدّ القاعدة (500 لا 422).
-- العلاج: توسيع العمود إلى عرض العقد، وإحلال فهرس فريد جزئيّ على (tenant_id,
-- idempotency_key) محلّ الفهرس العالميّ. الراوتر يستهدف الزوج نفسه. idempotent.
-- ALTER فقط، بلا RLS جديد. يُدرَج قبل v206 كي يبقى v206 آخِر مدخل.

ALTER TABLE edge_results ALTER COLUMN idempotency_key TYPE VARCHAR(128);

DROP INDEX IF EXISTS uq_edge_idempotency;

CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_idempotency_tenant
    ON edge_results (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
