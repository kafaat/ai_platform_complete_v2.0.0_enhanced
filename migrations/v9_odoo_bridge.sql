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
    from_state  INTEGER  (50) NOT NULL REFERENCES workflow_states(state_id) ON DELETE CASCADE,
    to_state    INTEGER  (50) NOT NULL REFERENCES workflow_states(state_id) ON DELETE CASCADE,
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

DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'odoo_sync_state','odoo_sync_log','inventory_locations',
        'field_cost_ledger','crop_batches','crop_batch_events',
        'workflow_states','workflow_transitions','workflow_instances','workflow_logs'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', tbl);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (
                tenant_id::TEXT = current_setting(''app.current_tenant'', true)
                -- Removed: empty tenant bypass (C14 security fix)
                -- System services must use explicit tenant_id or service account
            )', tbl
        );
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_products_odoo_product_id ON market_products(odoo_product_id);  -- HIGH-ODOO-02 FIX

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_suppliers_odoo_partner_id ON market_suppliers(odoo_partner_id);  -- HIGH-ODOO-02 FIX

CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_locations_odoo_warehouse_id ON inventory_locations(odoo_warehouse_id);  -- HIGH-ODOO-02 FIX
