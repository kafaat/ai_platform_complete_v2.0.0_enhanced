-- MARKET-MCP-SCHEMA-01: tables required by the Market MCP runtime.
-- Forward-only repair: v9_market historically created only market_sales_listings.

CREATE TABLE IF NOT EXISTS market_suppliers (
    supplier_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    country TEXT,
    rating NUMERIC(3,2),
    contact_email TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    odoo_partner_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    supplier_id UUID REFERENCES market_suppliers(supplier_id),
    sku TEXT,
    product_name TEXT NOT NULL,
    product_name_ar TEXT,
    category TEXT NOT NULL,
    unit_price_usd NUMERIC(14,4) NOT NULL CHECK (unit_price_usd >= 0),
    stock_qty NUMERIC(16,3) NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    featured BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    odoo_product_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_price_history (
    price_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID REFERENCES market_products(product_id),
    category TEXT NOT NULL,
    market_location TEXT NOT NULL,
    price_usd NUMERIC(14,4) NOT NULL CHECK (price_usd >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    recorded_date DATE NOT NULL,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_procurement_orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) REFERENCES fields(field_id),
    status TEXT NOT NULL DEFAULT 'draft',
    total_estimated_usd NUMERIC(16,4) NOT NULL DEFAULT 0 CHECK (total_estimated_usd >= 0),
    delivery_date DATE,
    notes TEXT,
    auto_approve_threshold NUMERIC(16,4),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_procurement_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL REFERENCES market_procurement_orders(order_id) ON DELETE CASCADE,
    product_id UUID REFERENCES market_products(product_id),
    product_name TEXT NOT NULL,
    quantity NUMERIC(16,3) NOT NULL CHECK (quantity > 0),
    unit TEXT NOT NULL,
    max_unit_price_usd NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (max_unit_price_usd >= 0),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_analytics_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    snapshot_date DATE NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_market_products_tenant_category
    ON market_products(tenant_id, category) WHERE active;
CREATE INDEX IF NOT EXISTS idx_market_price_tenant_category_date
    ON market_price_history(tenant_id, category, recorded_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_orders_tenant_created
    ON market_procurement_orders(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_items_order ON market_procurement_items(order_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_products_odoo_product_id
    ON market_products(odoo_product_id) WHERE odoo_product_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_suppliers_odoo_partner_id
    ON market_suppliers(odoo_partner_id) WHERE odoo_partner_id IS NOT NULL;

-- Keep the RLS DDL literal: repository governance scans these statements and
-- must report the same protection that PostgreSQL applies at runtime.
ALTER TABLE market_suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_suppliers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON market_suppliers;
CREATE POLICY tenant_isolation ON market_suppliers
    USING (tenant_id::text = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));

ALTER TABLE market_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_products FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON market_products;
CREATE POLICY tenant_isolation ON market_products
    USING (tenant_id::text = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));

ALTER TABLE market_price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_price_history FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON market_price_history;
CREATE POLICY tenant_isolation ON market_price_history
    USING (tenant_id::text = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));

ALTER TABLE market_procurement_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_procurement_orders FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON market_procurement_orders;
CREATE POLICY tenant_isolation ON market_procurement_orders
    USING (tenant_id::text = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));

ALTER TABLE market_procurement_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_procurement_items FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON market_procurement_items;
CREATE POLICY tenant_isolation ON market_procurement_items
    USING (tenant_id::text = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));

ALTER TABLE market_analytics_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_analytics_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON market_analytics_snapshots;
CREATE POLICY tenant_isolation ON market_analytics_snapshots
    USING (tenant_id::text = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
