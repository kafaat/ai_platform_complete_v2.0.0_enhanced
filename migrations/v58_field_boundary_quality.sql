-- SAHOOL v58 — migrations/v58_field_boundary_quality.sql
-- #15 — خدمة حدود الحقل (Field Boundary Service): نموذج البيانات.
--
-- الهدف: توسعة مخطّط حدود الحقل (field_boundaries المُعرّف في init_v8) لتخزين
-- مصدر/جودة استخلاص الحدّ (provenance/quality)، وإضافة «شبكة حدود الحقل»
-- (Field Boundary Graph) للعلاقات المكانيّة بين الحقول المتجاورة.
--
-- يطبّقه CI Integration Tests على PostGIS حقيقيّ عبر تمرير كامل MANIFEST.
-- idempotent بالكامل (ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS /
-- حُرّاس DO على القيود) — آمن إعادة التطبيق كلّ إقلاع.

-- ══════════════════════════════════════════════════════════════════
-- PART 1: أعمدة المصدر/الجودة على field_boundaries (provenance/quality)
-- ══════════════════════════════════════════════════════════════════

ALTER TABLE field_boundaries
    ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(4, 3),   -- 0..1، nullable
    ADD COLUMN IF NOT EXISTS source_type      VARCHAR(30),
    ADD COLUMN IF NOT EXISTS model_version    VARCHAR(40),
    ADD COLUMN IF NOT EXISTS review_status    VARCHAR(20) DEFAULT 'unreviewed';

COMMENT ON COLUMN field_boundaries.confidence_score IS 'درجة ثقة استخلاص الحدّ.';
COMMENT ON COLUMN field_boundaries.source_type      IS 'مصدر الحدّ (manual|geojson|kml|gps_trace|auto_delineation).';
COMMENT ON COLUMN field_boundaries.model_version    IS 'إصدار محرّك الاستخلاص (لتتبّع التراجع).';
COMMENT ON COLUMN field_boundaries.review_status    IS 'حالة المراجعة البشريّة (HIL).';

-- قيد CHECK على حالة المراجعة (مُضاف بحارس DO لأنّ ADD CONSTRAINT ليس له
-- IF NOT EXISTS — فنتحقّق من غيابه أوّلاً حفاظاً على الـidempotency).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'field_boundaries_review_status_chk'
          AND conrelid = 'field_boundaries'::regclass
    ) THEN
        ALTER TABLE field_boundaries
            ADD CONSTRAINT field_boundaries_review_status_chk
            CHECK (review_status IN ('unreviewed','approved','rejected','needs_edit'));
    END IF;
END $$;

-- ══════════════════════════════════════════════════════════════════
-- PART 2: شبكة حدود الحقل (Field Boundary Graph)
-- ══════════════════════════════════════════════════════════════════
-- جدول العلاقات المكانيّة بين الحقول: كلّ صفّ يمثّل علاقة جوار (الحدود
-- المشتركة / الحافّة المشتركة) بين حقلٍ وجاره. هذه الشبكة تُمكّن التحليلات
-- الإقليميّة عبر الحقول: انتشار الآفات والأمراض من حقلٍ لجاره، والريّ الجماعيّ
-- عبر قناة/منطقة ريّ مشتركة، وتجميع الحقول المتلاصقة في وحدات معالجة إقليميّة.
-- (هذا هو «Field Boundary Graph» المطلوب من المستخدم.)

CREATE TABLE IF NOT EXISTS field_boundary_graph (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           UUID         NOT NULL,         -- عزل المستأجر (تغطّيه RLS الديناميكيّة #56/#191)
    field_id            VARCHAR(50)  NOT NULL,         -- الحقل المصدر للعلاقة
    neighbor_field_id   VARCHAR(50)  NOT NULL,         -- الحقل الجار
    relation_type       VARCHAR(20)  NOT NULL DEFAULT 'adjacent'
        CHECK (relation_type IN ('adjacent','shares_canal','shares_road','same_irrigation_zone')),
    shared_edge_length_m NUMERIC(10, 2),              -- طول الحافّة المشتركة (متر)
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (tenant_id, field_id, neighbor_field_id, relation_type)
);

COMMENT ON TABLE  field_boundary_graph IS 'شبكة العلاقات المكانيّة بين الحقول (الجيران / الحواف المشتركة) — تُمكّن التحليلات الإقليميّة كانتشار الآفات والريّ الجماعيّ. هذا هو Field Boundary Graph.';
COMMENT ON COLUMN field_boundary_graph.field_id             IS 'الحقل المصدر للعلاقة.';
COMMENT ON COLUMN field_boundary_graph.neighbor_field_id    IS 'الحقل الجار في العلاقة.';
COMMENT ON COLUMN field_boundary_graph.relation_type        IS 'نوع العلاقة المكانيّة (adjacent|shares_canal|shares_road|same_irrigation_zone).';
COMMENT ON COLUMN field_boundary_graph.shared_edge_length_m IS 'طول الحافّة المشتركة بالمتر (للجوار المباشر).';

-- فهارس tenant-aware لاجتياز الشبكة بسرعة في كلا الاتّجاهين.
CREATE INDEX IF NOT EXISTS idx_fbg_tenant_field    ON field_boundary_graph(tenant_id, field_id);
CREATE INDEX IF NOT EXISTS idx_fbg_tenant_neighbor ON field_boundary_graph(tenant_id, neighbor_field_id);

-- ══════════════════════════════════════════════════════════════════
-- PART 3: عزل المستأجرين (RLS) — تطبيق صريح للأمان
-- ══════════════════════════════════════════════════════════════════
-- الجدول يحوي tenant_id فتغطّيه التغطية الديناميكيّة (v56). نطبّقه هنا صراحةً
-- أيضاً (مرآةً لبقيّة الجداول self-applied) لإغلاق نافذة الانكشاف قبل بلوغ v56،
-- محروساً بوجود الدالّة المساعدة (المعرّفة في v9_rls_tenant_isolation.sql).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = '_sahool_apply_tenant_rls') THEN
        PERFORM _sahool_apply_tenant_rls('field_boundary_graph');
        RAISE NOTICE 'v58: RLS مُفعّل على field_boundary_graph';
    ELSE
        RAISE NOTICE 'v58: تخطّي تطبيق RLS الصريح — الدالّة المساعدة غير موجودة بعد (ستغطّيه v56)';
    END IF;
END $$;
