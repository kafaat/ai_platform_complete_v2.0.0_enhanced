-- ═══════════════════════════════════════════════════════════════════
-- v9_lifecycle_occurred_at.sql — وقت حدوث الانتقال (Temporal Invariant)
-- ═══════════════════════════════════════════════════════════════════
-- المراجعة 10: المقارنة الزمنيّة يجب أن تكون ضدّ occurred_at السابق (وقت
-- الحقيقة) لا transitioned_at (وقت الإدراج NOW()). نضيف occurred_at + seq
-- (tiebreaker للطوابع المتساوية).

ALTER TABLE field_lifecycle_transitions
    ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ;
-- للصفوف القديمة: occurred_at = transitioned_at كأفضل تقدير
UPDATE field_lifecycle_transitions
    SET occurred_at = transitioned_at WHERE occurred_at IS NULL;
-- seq: tiebreaker تسلسلي للطوابع المتساوية (مراجعة 10)
ALTER TABLE field_lifecycle_transitions
    ADD COLUMN IF NOT EXISTS seq BIGSERIAL;

-- جدول الرفض الزمني (audit — لا نرمي المتأخّر، نخزّنه للتسوية)
CREATE TABLE IF NOT EXISTS lifecycle_temporal_rejections (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     UUID,
    lifecycle_id  UUID NOT NULL,
    to_stage      VARCHAR(40),
    occurred_at   TIMESTAMPTZ,
    last_occurred_at TIMESTAMPTZ,
    reason        TEXT,
    rejected_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_temporal_rej_lifecycle
    ON lifecycle_temporal_rejections (lifecycle_id);

CREATE INDEX IF NOT EXISTS idx_lifecycle_trans_occurred
    ON field_lifecycle_transitions (lifecycle_id, occurred_at DESC, seq DESC);
