-- v126: سجلّ تدقيق أدوات الوكيل الدائم + الموافقة البشريّة (V55 — المرحلة ٤)
--
-- كلّ استدعاء أداة يُدوَّن هنا (منفَّذاً كان أو مؤجَّلاً لموافقة أو مرفوضاً): الأداة،
-- القدرة، الخطورة، الوسائط المُنقَّحة، النتيجة، الفاعل، ومن وافق. **append-only
-- (immutable)** — تدقيق لا يُزوَّر: UPDATE/DELETE محظوران عبر trigger
-- ``sahool_block_mutation`` (v9_append_only_enforcement — يسبق هذا في المانيفست).
-- RLS+FORCE معزول بالمستأجِر (نمط v124). idempotent.

CREATE TABLE IF NOT EXISTS agent_tool_audit (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid        NOT NULL,
    tool         text        NOT NULL,
    capability   text,
    risk         text        NOT NULL,
    params       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    outcome      text        NOT NULL,
    actor        text        NOT NULL,
    approved_by  text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE agent_tool_audit IS
    'تدقيق استدعاءات أدوات الوكيل (V55): append-only، معزول بالمستأجِر. الوسائط مُنقَّحة (لا أسرار).';

ALTER TABLE agent_tool_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_tool_audit FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'agent_tool_audit'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $ddl$
            CREATE POLICY tenant_isolation ON agent_tool_audit
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

-- append-only: يمنع تزوير التاريخ (يعتمد الدالّة المُعرَّفة في v9_append_only_enforcement).
DROP TRIGGER IF EXISTS trg_append_only_agent_tool_audit ON agent_tool_audit;
CREATE TRIGGER trg_append_only_agent_tool_audit
    BEFORE UPDATE OR DELETE ON agent_tool_audit
    FOR EACH ROW EXECUTE FUNCTION sahool_block_mutation();

CREATE INDEX IF NOT EXISTS idx_agent_tool_audit_tenant
    ON agent_tool_audit (tenant_id, created_at DESC);
