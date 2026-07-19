-- v198: SCOUT-INGEST-01 B1.2b — per-source ingest credential registry (control-plane).
--
-- يربط (provider,server,form) → tenant ويحمل **hash** توكن كلّ مصدر (لا التوكن نفسه أبداً).
-- ``resolve_ingest_source(token_hash)`` = SECURITY DEFINER: يحلّ توكناً → مستأجِراً **قبل** ضبط
-- ``app.current_tenant`` (غرضه)، ويعيد **الصفّ المطابق المُفعَّل فقط** — لا تعداد لكلّ التعيينات.
--
-- **تفاعل حرِج (FORCE ↔ DEFINER):** ``FORCE ROW LEVEL SECURITY`` يسري على مالك الجدول أيضاً؛ والدالّة
-- تعمل بصلاحية مالكها. فلو كان مالكها خاضعاً لـFORCE ⇒ سياق فارغ ⇒ صفر صفوف ⇒ كلّ توكن 403 (سطح ميت).
-- لذا يُنقَل مالك الدالّة في bootstrap إلى دور تحكّم مخصّص ``sahool_ingest_resolver`` (NOSUPERUSER
-- BYPASSRLS، SELECT على هذا الجدول فقط). راجع docs/specs/SCOUT-INGEST-01_B1.2b_ingress_odk_spec.md §1.1.

CREATE TABLE IF NOT EXISTS external_ingest_sources (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    provider           TEXT NOT NULL,
    server             TEXT NOT NULL,
    form_id            TEXT NOT NULL,
    token_hash         TEXT NOT NULL,                 -- sha256(scout_ingest_token) — لا التوكن
    mapping_version    TEXT NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, server, form_id)
);
CREATE INDEX IF NOT EXISTS ix_external_ingest_sources_token ON external_ingest_sources (token_hash);

-- كتابة إداريّة مقيَّدة بالمستأجِر (المالك يسجّل مصدره فقط): RLS FORCE + WITH CHECK (مسافة واحدة).
ALTER TABLE external_ingest_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_ingest_sources FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
  EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON external_ingest_sources';
  EXECUTE
    'CREATE POLICY tenant_isolation ON external_ingest_sources '
    'USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) '
    'WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))';
END $$;

-- resolver آمن: يعيد الصفّ المُفعَّل المطابق فقط (لا تعداد). المالك يُضبط في bootstrap (§1.1).
CREATE OR REPLACE FUNCTION resolve_ingest_source(p_token_hash TEXT)
RETURNS TABLE(tenant_id UUID, provider TEXT, server TEXT, form_id TEXT, mapping_version TEXT)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT s.tenant_id, s.provider, s.server, s.form_id, s.mapping_version
    FROM external_ingest_sources s
   WHERE s.token_hash = p_token_hash AND s.enabled = true
   LIMIT 1;
$$;
-- افتراضيّاً تُمنح EXECUTE لـPUBLIC — نُلغيها؛ bootstrap يمنحها لـsahool_app صراحةً (لا 500).
REVOKE ALL ON FUNCTION resolve_ingest_source(TEXT) FROM PUBLIC;

COMMENT ON TABLE external_ingest_sources IS
  'SCOUT-INGEST-01 per-source ingest credentials (control-plane). token_hash only; resolver is SECURITY DEFINER owned by sahool_ingest_resolver (set in bootstrap). v198.';
