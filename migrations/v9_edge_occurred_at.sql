-- ═══════════════════════════════════════════════════════════════════
-- v9_edge_occurred_at.sql — وقت حدوث القياس على الجهاز (Temporal Authority)
-- ═══════════════════════════════════════════════════════════════════
-- المراجعة 9: المزامنة المتأخّرة يجب أن تحمل وقت حدوث القياس على الجهاز
-- (occurred_at) لا وقت وصوله للسحابة (recorded_at) — وإلّا تنهار السببيّة
-- (حدث قديم يبدو جديداً). occurred_at = المرجع الزمني الحاسم للترتيب.

ALTER TABLE edge_results ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ;
-- للصفوف القديمة بلا occurred_at: استخدم recorded_at كأفضل تقدير متاح
UPDATE edge_results SET occurred_at = recorded_at WHERE occurred_at IS NULL;

-- فهرس للترتيب السببي (occurred_at لا recorded_at)
CREATE INDEX IF NOT EXISTS idx_edge_occurred ON edge_results (occurred_at DESC);
