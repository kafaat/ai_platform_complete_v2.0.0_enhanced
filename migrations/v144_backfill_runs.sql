-- migrations/v144_backfill_runs.sql
--
-- v144: تشغيل backfill الصور التاريخيّة كوظيفة لاتزامنيّة (تدقيق الأقمار v5/v6).
--
-- المشكلة (بمراجعة الكود + السجلّ الحيّ):
--   • نقطة /imagery/backfill تمسح STAC شهريّاً **داخل مسار الطلب** (حتّى 60 مكالمة
--     لـ5 سنوات) قبل الردّ ⇒ latency المصدر يصير latency الـAPI، وقد يتجاوز مهلة
--     proxy المنصّة (60s) فيظهر 502 رغم أنّ الخدمة تمسح (v5-F1/F2 · v6-F1/F2).
--   • لا مفتاح idempotency: كلّ نقرة تُنشئ مهامّ UUID جديدة وتُعيد معالجة نفس
--     (مستأجِر/حقل/مشهد/مؤشّر) ⇒ تكرار + ضغط STAC/معالجة (v5-F4 · v6-F4).
--
-- الحلّ: جدولا حالة يمكّنان عاملاً يمسح خارج مسار الطلب:
--   • backfill_runs: تشغيلة فحص (planned→searching→queued→processing→completed/failed)
--     تحمل عدّادات الفحص للتشخيص/الاستئناف.
--   • backfill_run_items: صفّ لكلّ (مشهد×مؤشّر) بمفتاح idempotency فريد يمنع التكرار.
-- كلاهما معزول بالمستأجِر (RLS FORCE، نمط v140 الحرفيّ). idempotent + آمن لإعادة التشغيل.

BEGIN;

CREATE TABLE IF NOT EXISTS backfill_runs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    preset TEXT,
    from_date DATE,
    to_date DATE,
    months INTEGER,
    indices JSONB NOT NULL DEFAULT '[]'::jsonb,
    max_cloud_pct NUMERIC(5, 2) DEFAULT 30,
    geometry_revision INTEGER,
    clip_polygon_geojson JSONB,
    apply_cloud_mask BOOLEAN NOT NULL DEFAULT TRUE,
    limit_per_month INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'searching', 'queued', 'processing', 'completed', 'failed')),
    months_scanned INTEGER NOT NULL DEFAULT 0,
    scenes_selected INTEGER NOT NULL DEFAULT 0,
    jobs_scheduled INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- طابور المطالبة: العامل يلتقط أقدم planned بـFOR UPDATE SKIP LOCKED.
CREATE INDEX IF NOT EXISTS idx_backfill_runs_planned
    ON backfill_runs (created_at)
    WHERE status = 'planned';
CREATE INDEX IF NOT EXISTS idx_backfill_runs_tenant_field
    ON backfill_runs (tenant_id, field_id, created_at DESC);

CREATE TABLE IF NOT EXISTS backfill_run_items (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES backfill_runs (id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    scene_id TEXT,
    index_name TEXT NOT NULL,
    acquisition_date DATE,
    provider TEXT,
    -- مفتاح idempotency: (مستأجِر/حقل/مراجعة هندسة/مزوّد/مشهد/مؤشّر) — إعادة النقر لا
    -- تُكرّر عنصراً، والمعالجة تُنجَز مرّة لكلّ مفتاح. v5-F4/v6-F4.
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'persisted', 'skipped', 'failed')),
    job_id TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_backfill_run_items_run
    ON backfill_run_items (run_id, status);

-- RLS (نمط v140 الحرفيّ: FORCE + current_setting — الفاحص الساكن يطلبه صراحةً).
ALTER TABLE backfill_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE backfill_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON backfill_runs;
CREATE POLICY tenant_isolation ON backfill_runs
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

ALTER TABLE backfill_run_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE backfill_run_items FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON backfill_run_items;
CREATE POLICY tenant_isolation ON backfill_run_items
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMIT;
