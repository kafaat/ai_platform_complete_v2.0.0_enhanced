-- migrations/v148_field_evidence_snapshots.sql
--
-- v148: استمرار رسم أدلّة الحقل (Evidence Graph Persistence) — سجلّ لقطات عبر الزمن.
--
-- المشكلة: ``evidence_graph`` يُبنى في استجابة ``field-intelligence/analyze`` ويُعرَض في
--   الواجهة، لكنّه **عابر** — لا تاريخ. لا يمكن تتبّع «لماذا صدرت توصية»، ولا مقارنة الأدلّة
--   عبر الزمن، ولا تقارير audit، ولا تعلّم لاحق من تطوّر الأدلّة/القرارات.
--
-- الحلّ (المرحلة 1، بلا Graph DB): جدول لقطات JSONB قابل للترقية. كاتب داخليّ fail-soft
--   عند نجاح analyze (لا يكسر التحليل إن فشلت الكتابة). قراءة latest/timeline معزولة
--   بالمستأجِر. لا أسرار/توكنات تُخزَّن (يُنقّيها الكاتب قبل الإدراج).
-- معزول بالمستأجِر (RLS FORCE، نمط v140/v144 الحرفيّ). idempotent + آمن لإعادة التشغيل.

BEGIN;

CREATE TABLE IF NOT EXISTS field_evidence_snapshots (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    analysis_id TEXT,  -- correlation_id للتحليل (ربط عبر الخدمات).
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recommendation_hash TEXT,  -- بصمة مدخلات القرار (ثابتة لنفس المدخلات — كشف التغيّر).
    confidence_score NUMERIC(4, 3),
    evidence_graph JSONB NOT NULL,  -- عُقَد/حوافّ (بلا أسرار — يُنقّيها الكاتب).
    evidence_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    knowledge_gaps JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- استعلام latest/timeline: أحدث لقطات حقل لمستأجِر بترتيب زمنيّ تنازليّ.
CREATE INDEX IF NOT EXISTS idx_field_evidence_snapshots_tenant_field_time
    ON field_evidence_snapshots (tenant_id, field_id, generated_at DESC);
-- بحث داخل الرسم (لاحقاً: أدلّة/فجوات معيّنة عبر الزمن).
CREATE INDEX IF NOT EXISTS idx_field_evidence_snapshots_graph_gin
    ON field_evidence_snapshots USING GIN (evidence_graph);

-- RLS (نمط v140/v144 الحرفيّ: FORCE + current_setting — الفاحص الساكن يطلبه صراحةً).
ALTER TABLE field_evidence_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_evidence_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_evidence_snapshots;
CREATE POLICY tenant_isolation ON field_evidence_snapshots
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMIT;
