-- SAHOOL v9.1 — migrations/v9_new_tables.sql (FIXED)
-- FIX: Removed pg_has_role bypass from RLS policies

CREATE TABLE IF NOT EXISTS field_tasks (
    task_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id             VARCHAR(50)  NOT NULL REFERENCES field_boundaries(field_id) ON DELETE CASCADE,  -- C2 FIX: FK to TABLE not VIEW
    tenant_id            UUID,
    task_type            VARCHAR(50)  NOT NULL,
    priority             SMALLINT     DEFAULT 3,
    status               VARCHAR(20)  DEFAULT 'pending',
    recommended_date     DATE,
    completed_at         TIMESTAMPTZ,
    assigned_to          VARCHAR(200),
    estimated_duration_min INTEGER    DEFAULT 60,
    estimated_cost_usd   NUMERIC(10,2),
    actual_cost_usd      NUMERIC(10,2),
    notes                TEXT,
    photo_url            TEXT,
    source_event_type    VARCHAR(100),
    source_agent         VARCHAR(50),
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ft_field_status   ON field_tasks(field_id, status);
CREATE INDEX IF NOT EXISTS idx_ft_tenant_date    ON field_tasks(tenant_id, recommended_date);
CREATE INDEX IF NOT EXISTS idx_ft_active         ON field_tasks(status) WHERE status IN ('pending','in_progress');

CREATE TABLE IF NOT EXISTS guardrails_log (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       UUID,
    user_id         INTEGER,
    action_type     VARCHAR(50)  NOT NULL,
    overall_risk    VARCHAR(20)  NOT NULL CHECK (UPPER(overall_risk) IN ('LOW','MEDIUM','HIGH','CRITICAL')),  -- H01 FIX: case-insensitive
    allowed         BOOLEAN      NOT NULL,
    tier_checks     JSONB        DEFAULT '[]',
    action_data     JSONB        DEFAULT '{}',
    diff            JSONB,
    arabic_explanation TEXT,
    processing_ms   INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guard_tenant_risk  ON guardrails_log(tenant_id, overall_risk);
CREATE INDEX IF NOT EXISTS idx_guard_recent       ON guardrails_log(created_at DESC) WHERE NOT allowed;

CREATE TABLE IF NOT EXISTS approval_workflows (
    workflow_id     VARCHAR(30)  PRIMARY KEY,
    tenant_id       UUID,
    user_id         INTEGER,
    status          VARCHAR(20)  DEFAULT 'pending',
    risk_level      VARCHAR(20)  NOT NULL,
    action_type     VARCHAR(50)  NOT NULL,
    action_data     JSONB        DEFAULT '{}',
    farm_context    JSONB        DEFAULT '{}',
    required_roles  TEXT[],
    approvals       JSONB        DEFAULT '[]',
    rejections      JSONB        DEFAULT '[]',
    escalation_count SMALLINT   DEFAULT 0,
    expires_at      TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_tenant    ON approval_workflows(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_workflow_pending   ON approval_workflows(status, expires_at) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS edge_results (
    id              BIGSERIAL PRIMARY KEY,
    field_id        VARCHAR(50)  NOT NULL REFERENCES field_boundaries(field_id) ON DELETE CASCADE,  -- C2 FIX: FK to TABLE not VIEW
    tenant_id       UUID,
    result_type     VARCHAR(50)  NOT NULL,
    device          VARCHAR(50),
    offline_mode    BOOLEAN      DEFAULT false,
    synced          BOOLEAN      DEFAULT false,
    result_data     JSONB        NOT NULL,
    alert_ar        TEXT,
    confidence      NUMERIC(5,4),
    inference_ms    INTEGER,
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_edge_field_type  ON edge_results(field_id, result_type);
CREATE INDEX IF NOT EXISTS idx_edge_unsynced    ON edge_results(synced, recorded_at) WHERE NOT synced;
CREATE INDEX IF NOT EXISTS idx_edge_results_time_brin ON edge_results USING BRIN(recorded_at);

CREATE TABLE IF NOT EXISTS agent_queries (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       UUID,
    user_id         INTEGER,
    field_id        VARCHAR(50),
    query_text      TEXT         NOT NULL,
    domain          VARCHAR(50),
    sub_intent      VARCHAR(50),
    confidence      NUMERIC(5,4),
    response_ar     TEXT,
    actions_triggered TEXT[],
    processing_ms   INTEGER,
    sources         TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aq_tenant_date   ON agent_queries(tenant_id, created_at DESC);

-- FIX: RLS without pg_has_role bypass
DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['field_tasks','inventory_stock','guardrails_log','approval_workflows','edge_results','agent_queries']
    LOOP
        -- FIX: تخطَّ الجداول غير الموجودة (inventory_stock يُنشأ في مجموعة أوسع) بدل الفشل.
        CONTINUE WHEN to_regclass(tbl) IS NULL;
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', tbl);
        EXECUTE format(
            $ddl$CREATE POLICY tenant_isolation ON %I USING (
                tenant_id::TEXT = current_setting('app.current_tenant', true)
                -- Removed: empty tenant bypass (C14 security fix)
                -- System services must use explicit tenant_id or service account
            )$ddl$, tbl
        );
    END LOOP;
END $$;

DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['field_tasks','inventory_stock']
    LOOP
        -- FIX: EXCEPTION يجب أن يكون داخل بلوك BEGIN...END فرعيّ (لا مباشرةً في
        -- LOOP) وإلّا "syntax error at or near EXCEPTION". + تخطّي الجداول الغائبة.
        CONTINUE WHEN to_regclass(tbl) IS NULL;
        BEGIN
            EXECUTE format(
                'CREATE TRIGGER trg_%s_updated_at
                 BEFORE UPDATE ON %I
                 FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()',
                replace(tbl, '-', '_'), tbl
            );
        EXCEPTION WHEN duplicate_object OR undefined_table OR undefined_column THEN NULL;  -- C6 FIX
        END;
    END LOOP;
END $$;

DO $$
BEGIN
    RAISE NOTICE '════════════════════════════════════════════════════';
    RAISE NOTICE '  SAHOOL v9.1 — v9_new_tables.sql مكتمل';
    RAISE NOTICE '════════════════════════════════════════════════════';
END $$;

-- H09 FIX: Missing performance indexes
-- FIX: market_*/workflow_instances تُنشأ في مجموعات لاحقة/أوسع — احرس كلّ
-- فهرس بوجود جدوله بدل الفشل بـ"relation does not exist" وكسر التمهيد.
CREATE INDEX IF NOT EXISTS idx_guardrails_tenant_date
    ON guardrails_log(tenant_id, created_at DESC);
DO $$
BEGIN
    IF to_regclass('market_sales_listings') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_market_listings_crop_status
            ON market_sales_listings(crop_type, status);
        CREATE INDEX IF NOT EXISTS idx_market_listings_tenant_status
            ON market_sales_listings(tenant_id, status);
    END IF;
    IF to_regclass('market_price_history') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_market_price_history_crop_date
            ON market_price_history(crop_type, recorded_at DESC);
    END IF;
    IF to_regclass('workflow_instances') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_workflow_instances_tenant_status
            ON workflow_instances(tenant_id, status) WHERE status != 'completed';
    END IF;
END $$;
