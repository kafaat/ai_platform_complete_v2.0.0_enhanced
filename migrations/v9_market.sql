-- SAHOOL v9.1 — migrations/v9_market.sql (FIXED)
-- FIX: RLS without pg_has_role bypass, GENERATED column not in INSERT

CREATE TABLE IF NOT EXISTS market_sales_listings (
    listing_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    batch_id        UUID,
    crop_type       VARCHAR(50) NOT NULL,
    variety         VARCHAR(100),
    quantity_kg     NUMERIC(12,2) NOT NULL,
    price_per_kg_usd NUMERIC(10,4) NOT NULL,
    total_value_usd NUMERIC(18,4) GENERATED ALWAYS AS (quantity_kg * price_per_kg_usd) STORED,  -- C7 FIX: was NUMERIC(12,2)
    currency        VARCHAR(3) DEFAULT 'USD',
    quality_grade   VARCHAR(20) DEFAULT 'A',
    moisture_pct    NUMERIC(5,2),
    protein_pct     NUMERIC(5,2),
    certifications  TEXT[],
    lab_report_url  TEXT,
    photos_urls     TEXT[],
    available_from  DATE DEFAULT CURRENT_DATE,
    available_until DATE,
    pickup_location VARCHAR(200),
    pickup_geo      GEOGRAPHY(POINT,4326),
    status          VARCHAR(20) DEFAULT 'active',
    buyer_id        UUID,
    sold_at         TIMESTAMPTZ,
    sold_price_usd  NUMERIC(10,4),
    featured        BOOLEAN DEFAULT false,
    view_count      INTEGER DEFAULT 0,
    inquiry_count   INTEGER DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- FIX: RLS without pg_has_role
DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'market_suppliers','market_products','market_price_history',
        'market_procurement_orders','market_procurement_items',
        'market_sales_listings','market_analytics_snapshots'
    ]
    LOOP
        -- FIX: تخطَّ الجداول غير الموجودة (بعضها يُنشأ في مجموعة أوسع/خدمات
        -- منفصلة) بدل الفشل بـ"relation does not exist" وكسر التمهيد.
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

-- H23 FIX: missing indexes on market_sales_listings
CREATE INDEX IF NOT EXISTS idx_market_sales_crop_status
    ON market_sales_listings(crop_type, status);
CREATE INDEX IF NOT EXISTS idx_market_sales_tenant_created
    ON market_sales_listings(tenant_id, created_at DESC);
