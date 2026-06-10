-- v15: durable store for synced offline-first operations
-- ════════════════════════════════════════════════════════════════════════
-- النواة sahool_core.offline_first نقيّة (لا I/O بالتصميم): تُدير queue في
-- الذاكرة فقط. حين يعود الاتّصال، endpoint ‎/api/v1/sync‎ يُفرّغ الـqueue ويكتب
-- كلّ عمليّة هنا بمتانة. المفتاح op_id (معرّف العميل) ⇒ إعادة الـsync idempotent.
-- العزل: RLS على tenant_id عبر الدالّة المشتركة _sahool_apply_tenant_rls.
CREATE TABLE IF NOT EXISTS offline_synced_operations (
    op_id       UUID PRIMARY KEY,                       -- معرّف العميل (idempotency)
    tenant_id   UUID NOT NULL,
    user_id     TEXT NOT NULL,
    kind        TEXT NOT NULL,                          -- OperationKind value
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL,                   -- حين أُنشئت offline
    synced_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()      -- حين كُتبت للقاعدة
);

CREATE INDEX IF NOT EXISTS idx_offline_synced_ops_tenant
    ON offline_synced_operations (tenant_id, synced_at DESC);

-- RLS: ENABLE + FORCE + سياسة العزل (tenant_id = current_setting('app.current_tenant')).
-- الدالّة مُعرّفة في v9_rls_tenant_isolation.sql (تُطبَّق قبل هذا الملف).
SELECT _sahool_apply_tenant_rls('offline_synced_operations');
