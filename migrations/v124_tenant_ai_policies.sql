-- v124: سياسة حوكمة الذكاء الاصطناعيّ الدائمة للمستأجِر (V52)
--
-- يُغلِق خطر V51: ``TenantPolicyStore`` كان في الذاكرة (يُفقَد عند إعادة التشغيل، بلا
-- تدقيق). الآن تصبح سياسة الذكاء للمستأجِر **دائمة + قابلة للتدقيق** في جدول معزول
-- بـRLS على نمط ``app.current_tenant`` (المعيار القانونيّ للمنصّة).
--
-- idempotent + لا-عمليّ على مخطّط طبّقه سابقاً (CREATE … IF NOT EXISTS + حارس pg_policies).

CREATE TABLE IF NOT EXISTS tenant_ai_policies (
    tenant_id                   uuid PRIMARY KEY,
    ai_generation_allowed       boolean     NOT NULL DEFAULT true,
    allowed_providers           text[]      NOT NULL DEFAULT '{}',
    allowed_models              text[]      NOT NULL DEFAULT '{}',
    external_data_sharing_level  text       NOT NULL DEFAULT 'local_only'
        CHECK (external_data_sharing_level IN ('local_only', 'redacted_external', 'full_external')),
    redaction_profile           text        NOT NULL DEFAULT 'default',
    updated_by                  text,
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE tenant_ai_policies IS
    'حوكمة الذكاء للمستأجِر (V52): سماح التوليد، قوائم المزوّدات/النماذج المسموحة، مستوى مشاركة البيانات الخارجيّ، ملفّ التنقيح.';

-- عزل المستأجرين (RLS) — نفس عقد v9_rls_tenant_isolation: قراءة فشل-مغلق + كتابة معزولة.
ALTER TABLE tenant_ai_policies ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'tenant_ai_policies'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $ddl$
            CREATE POLICY tenant_isolation ON tenant_ai_policies
            USING (
                tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
            )
            WITH CHECK (
                NULLIF(current_setting('app.current_tenant', true), '') IS NULL
                OR tenant_id::text = current_setting('app.current_tenant', true)
            )
        $ddl$;
    END IF;
END$$;
