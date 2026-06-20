-- migrations/v85_nl_gis_audit.sql
--
-- سجلّ تدقيق استعلامات NL-GIS (Natural Language GIS Audit) — جدول append-only يُدوّن
-- كلّ استعلام لُغة-طبيعيّة وصل إلى نقطة /api/v1/nl-gis/query (read-only، #9): النصّ
-- الخام، النيّة المُصنَّفة، الخانات المُستخلَصة، المصدر المُستدعى، وحالة النتيجة
-- (ok/needs_data/unsupported). يُغلق فجوة «من سأل ماذا بِلُغته، وكيف فُسِّر، وماذا أُعيد».
--
--   • append-only: لا UPDATE ولا DELETE (لا عمود updated_at) — نزاهة التدقيق.
--   • result_status TEXT CHECK ⇒ مجموعة مغلقة (لا حالة مُلفّقة).
--   • intent TEXT: النيّة المُصنَّفة (unsupported مسموح — نُدوّن الرفض أيضاً للحَوكمة).
--   • slots JSONB: الخانات المُستخلَصة من النصّ فقط (لا قيم مُختلقة).
--   • api_called TEXT: اسم المصدر القرائيّ المُستدعى (NULL إن رُفِض قبل أيّ استدعاء).
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting.
--   • read_only BOOLEAN NOT NULL DEFAULT TRUE ⇒ أثر صريح أنّ النقطة قراءة فقط دائماً.
--   • فهرس (tenant_id, created_at DESC) ⇒ جلب سجلّ المستأجِر بالأحدث أوّلاً.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS nl_gis_audit (
    audit_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID         NOT NULL,                 -- عزل المستأجِر (RLS أدناه)
    query_text    TEXT         NOT NULL,                 -- النصّ الخام كما كتبه المستخدم
    intent        TEXT         NOT NULL,                 -- النيّة المُصنَّفة (قد تكون unsupported)
    slots         JSONB,                                 -- الخانات المُستخلَصة من النصّ (لا تلفيق)
    api_called    TEXT,                                  -- المصدر القرائيّ المُستدعى (NULL إن رُفِض)
    result_status TEXT         NOT NULL                  -- حالة النتيجة (مجموعة مغلقة)
                  CHECK (result_status IN ('ok', 'needs_data', 'unsupported', 'denied', 'error')),
    result_count  INTEGER,                               -- عدد العناصر المُعادة (NULL إن لا ينطبق)
    read_only     BOOLEAN      NOT NULL DEFAULT TRUE,    -- أثر صريح: قراءة فقط دائماً
    actor         VARCHAR(80),                           -- من أصدر الاستعلام
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()    -- زمن القيد (append-only: لا updated_at)
);

-- جلب سجلّ المستأجِر بالأحدث أوّلاً.
CREATE INDEX IF NOT EXISTS idx_nl_gis_audit_tenant
    ON nl_gis_audit (tenant_id, created_at DESC);

COMMENT ON TABLE  nl_gis_audit IS
    'سجلّ تدقيق NL-GIS append-only (لا UPDATE/DELETE): النصّ/النيّة/الخانات/المصدر/الحالة. read-only دائماً. tenant-isolated عبر RLS. v85.';
COMMENT ON COLUMN nl_gis_audit.slots IS 'الخانات المُستخلَصة من النصّ فقط (لا قيم مُختلقة).';
COMMENT ON COLUMN nl_gis_audit.api_called IS 'اسم المصدر القرائيّ المُستدعى — NULL إن رُفِض الطلب قبل أيّ استدعاء.';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE nl_gis_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE nl_gis_audit FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON nl_gis_audit;
CREATE POLICY tenant_isolation ON nl_gis_audit
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
