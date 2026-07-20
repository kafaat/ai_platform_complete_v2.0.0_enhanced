-- SAHOOL v9.1 — migrations/v9_odoo_bridge.sql (FIXED)
-- FIX: RLS without pg_has_role bypass, UNIQUE on workflow_transitions


-- ── workflow_states (FIXED: was referenced but missing) ──────
CREATE TABLE IF NOT EXISTS workflow_states (
    state_id    SERIAL       PRIMARY KEY,
    workflow_name VARCHAR(100) NOT NULL,
    state_name  VARCHAR(100) NOT NULL,
    is_initial  BOOLEAN      DEFAULT FALSE,
    is_final    BOOLEAN      DEFAULT FALSE,
    description TEXT,
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE(workflow_name, state_name)
);

CREATE TABLE IF NOT EXISTS workflow_transitions (
    transition_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_name   VARCHAR(50) NOT NULL,
    -- FIX: from/to_state أسماء حالات نصيّة (الـINSERT يضع 'proc_draft'...) لا
    -- state_id عدديّ — كان INTEGER(50) صياغة غير صالحة + تعارض نوع مع البيانات.
    from_state  VARCHAR(50) NOT NULL,
    to_state    VARCHAR(50) NOT NULL,
    required_role   VARCHAR(50),
    condition_json  JSONB DEFAULT '{}',
    notify_users    BOOLEAN DEFAULT true,
    auto_trigger    BOOLEAN DEFAULT false,
    active          BOOLEAN DEFAULT true,
    sort_order      INTEGER DEFAULT 0,
    UNIQUE(workflow_name, from_state, to_state)
);

-- FIX: ON CONFLICT now has unique target
INSERT INTO workflow_transitions (workflow_name, from_state, to_state, required_role, condition_json, notify_users, sort_order) VALUES
('procurement', 'proc_draft', 'proc_pending', NULL, '{}', true, 1),
('procurement', 'proc_pending', 'proc_manager_approved', 'manager', '{"max_amount":5000}', true, 2),
('procurement', 'proc_pending', 'proc_finance_approved', 'finance', '{"min_amount":5000}', true, 3),
('procurement', 'proc_manager_approved', 'proc_ordered', NULL, '{}', true, 4),
('procurement', 'proc_finance_approved', 'proc_ordered', NULL, '{}', true, 5),
('procurement', 'proc_ordered', 'proc_received', NULL, '{}', true, 6),
('procurement', 'proc_pending', 'proc_rejected', 'manager', '{}', true, 99),
('procurement', 'proc_manager_approved', 'proc_rejected', 'finance', '{}', true, 99)
ON CONFLICT (workflow_name, from_state, to_state) DO NOTHING;

-- ── ERP bridge sync tables ────────────────────────────────────────────────────
-- تُنشأ هنا (بواسطة sahool_user) كي لا يحتاج sahool_app إلى امتياز CREATE.
-- erp_runtime._run_migrations() كانت تُنشئها لكنّ sahool_app يفتقر إلى CREATE
-- على schema public (ERR-BRIDGE-001: ينهار lifespan ⇒ healthcheck لا يستجيب).
CREATE TABLE IF NOT EXISTS odoo_sync_state (
    entity       TEXT        NOT NULL,
    direction    TEXT        NOT NULL,
    last_sync_at TIMESTAMPTZ,
    PRIMARY KEY (entity, direction)
);

CREATE TABLE IF NOT EXISTS odoo_sync_log (
    id           BIGSERIAL    PRIMARY KEY,
    direction    TEXT         NOT NULL,
    entity       TEXT         NOT NULL,
    odoo_id      INTEGER,
    sahool_id    TEXT,
    status       TEXT         NOT NULL,
    details      TEXT         DEFAULT '',
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'odoo_sync_state','odoo_sync_log','inventory_locations',
        'field_cost_ledger','crop_batches','crop_batch_events',
        'workflow_states','workflow_transitions','workflow_instances','workflow_logs'
    ]
    LOOP
        -- FIX: طبّق عزل المستأجر فقط على جدول موجود **ولديه عمود tenant_id**.
        -- بعض الجداول المُدرجة تُنشأ في مجموعة أوسع (odoo_sync_*/inventory_*)،
        -- وبعضها (workflow_states/transitions) بلا tenant_id — تخطّيها يمنع
        -- "relation does not exist" و"column tenant_id does not exist".
        CONTINUE WHEN to_regclass(tbl) IS NULL;
        CONTINUE WHEN NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'tenant_id'
        );
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

-- FIX: فهارس odoo على جداول قد لا تُنشأ في هذه المجموعة — احرسها بوجود الجدول.
DO $$
BEGIN
    IF to_regclass('market_products') IS NOT NULL THEN
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_products_odoo_product_id ON market_products(odoo_product_id);
    END IF;
    IF to_regclass('market_suppliers') IS NOT NULL THEN
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_suppliers_odoo_partner_id ON market_suppliers(odoo_partner_id);
    END IF;
    IF to_regclass('inventory_locations') IS NOT NULL THEN
        CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_locations_odoo_warehouse_id ON inventory_locations(odoo_warehouse_id);
    END IF;
END $$;
