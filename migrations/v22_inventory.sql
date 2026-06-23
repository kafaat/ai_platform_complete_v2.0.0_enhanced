-- ════════════════════════════════════════════════════════════
-- SAHOOL v22 — إدارة المخزون (Inventory): عناصر + دفعات
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ١٠ — غائبة 100%): أسمدة/مبيدات/بذور/
-- قطع غيار مع تتبّع الكمّيّات والدفعات وتواريخ الانتهاء. كان يُشار إليها في
-- تعليقات v9 (inventory_stock/procurement) لكن لم يُنشأ أيّ جدول قطّ.
--
-- النموذج: عنصر (كتالوج) ← دفعات (lots بكمّيّة + انتهاء + مورّد). المخزون
-- الكلّيّ لعنصر = مجموع كمّيّات دفعاته. العزل: RLS لكلّ مستأجر.

-- ── inventory_items: كتالوج ما يُخزَّن ────────────────────────
CREATE TABLE IF NOT EXISTS inventory_items (
    item_id        VARCHAR(50)  PRIMARY KEY,
    tenant_id      UUID         NOT NULL,
    category       VARCHAR(20)  NOT NULL
        CHECK (category IN ('fertilizer', 'pesticide', 'seed', 'spare_part', 'other')),
    name           VARCHAR(120) NOT NULL,
    unit           VARCHAR(20)  NOT NULL DEFAULT 'unit',   -- kg / L / bag / unit
    reorder_level  NUMERIC(14, 3) CHECK (reorder_level IS NULL OR reorder_level >= 0),  -- حدّ إعادة الطلب

    notes          TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_items_tenant ON inventory_items(tenant_id, category);

DROP TRIGGER IF EXISTS trg_inv_items_updated_at ON inventory_items;
CREATE OR REPLACE TRIGGER trg_inv_items_updated_at
    BEFORE UPDATE ON inventory_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── inventory_batches: الدفعات (كمّيّة + انتهاء + مورّد) ──────
CREATE TABLE IF NOT EXISTS inventory_batches (
    batch_id     VARCHAR(50)   PRIMARY KEY,
    tenant_id    UUID          NOT NULL,
    item_id      VARCHAR(50)   NOT NULL REFERENCES inventory_items(item_id) ON DELETE CASCADE,
    quantity     NUMERIC(14, 3) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    unit         VARCHAR(20),
    batch_code   VARCHAR(80),                             -- رقم الدفعة من المورّد
    expiry_date  DATE,                                    -- تتبّع الانتهاء (تنبيه قبل النفاد)
    received_at  DATE          NOT NULL DEFAULT CURRENT_DATE,
    supplier     VARCHAR(120),
    notes        TEXT,
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_batches_item ON inventory_batches(item_id);
CREATE INDEX IF NOT EXISTS idx_inv_batches_expiry
    ON inventory_batches(tenant_id, expiry_date) WHERE expiry_date IS NOT NULL;

DROP TRIGGER IF EXISTS trg_inv_batches_updated_at ON inventory_batches;
CREATE OR REPLACE TRIGGER trg_inv_batches_updated_at
    BEFORE UPDATE ON inventory_batches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- عزل المستأجرين (self-applied بعد force_all، كنمط v15/v16/v19)
SELECT _sahool_apply_tenant_rls('inventory_items');
SELECT _sahool_apply_tenant_rls('inventory_batches');

COMMENT ON TABLE inventory_items   IS 'كتالوج المخزون (أسمدة/مبيدات/بذور/قطع غيار). v22.';
COMMENT ON TABLE inventory_batches IS 'دفعات المخزون (كمّيّة + انتهاء + مورّد). v22.';
