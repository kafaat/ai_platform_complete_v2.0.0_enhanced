-- migrations/v12_trueup_sharing.sql
--
-- v12: TrueUp calibration history + Sharing keys
--
-- المرجع: المستند ٩ (Prompt Comprehensive)
--   ٧. TrueUp Engine
--   Sharing Key & Data Transfer

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- ١. TrueUp Calibrations (audit log)
-- ════════════════════════════════════════════════════════════════
-- كل مرّة يطبّق المزارع TrueUp، يُحفَظ السجلّ.
-- يسمح بـ:
--   - rollback لو شخص غلط في القياس
--   - audit "لماذا الإنتاج تغيّر؟"
--   - حساب trends في دقّة الـcombines عبر الزمن

CREATE TABLE IF NOT EXISTS trueup_calibrations (
    calibration_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id          UUID NOT NULL,            -- harvest operation
    field_id              UUID NOT NULL,
    tenant_id             UUID NOT NULL,

    -- The math
    k_factor              NUMERIC(8, 4) NOT NULL CHECK (k_factor BETWEEN 0.7 AND 1.3),
    actual_weight_kg      NUMERIC(12, 2) NOT NULL CHECK (actual_weight_kg >= 0),
    actual_moisture_pct   NUMERIC(5, 2) NOT NULL CHECK (actual_moisture_pct BETWEEN 0 AND 100),
    measured_weight_kg    NUMERIC(12, 2) NOT NULL CHECK (measured_weight_kg > 0),

    -- Outputs
    measured_yield_kg_ha  NUMERIC(10, 2),
    adjusted_yield_kg_ha  NUMERIC(10, 2),
    error_pct             NUMERIC(5, 2),

    -- Audit
    applied_by            TEXT NOT NULL,
    command_id            UUID REFERENCES commands(command_id),
    notes_ar              TEXT,
    applied_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trueup_operation  ON trueup_calibrations(operation_id, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_trueup_field      ON trueup_calibrations(field_id, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_trueup_tenant     ON trueup_calibrations(tenant_id);

ALTER TABLE trueup_calibrations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS trueup_tenant_isolation ON trueup_calibrations;  -- idempotency (المُشغِّل يُعيد التطبيق كلّ إقلاع)
CREATE POLICY trueup_tenant_isolation ON trueup_calibrations
    USING (
        -- fail-closed: لو app.current_tenant غير مضبوط (NULL) → لا صفوف
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    );


-- ════════════════════════════════════════════════════════════════
-- ٢. Sharing Keys (advisor / dealer / ministry access)
-- ════════════════════════════════════════════════════════════════
-- المزارع يولّد key:
--   - scope: read | read_write
--   - مدّة الصلاحية
--   - حقول محدّدة (لا كل المزرعة)
-- الـadvisor يستخدم الـkey للوصول

CREATE TABLE IF NOT EXISTS sharing_keys (
    key_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash            TEXT NOT NULL UNIQUE,         -- bcrypt(key) — نخزّن hash فقط
    key_prefix          TEXT NOT NULL,                -- أوّل ٨ أحرف للـUI ("sk_abc1...")
    tenant_id           UUID NOT NULL,                -- owner's tenant
    created_by          TEXT NOT NULL,                -- user_id of owner

    -- Scope
    scope               TEXT NOT NULL CHECK (scope IN ('read', 'read_write')),
    third_party_name    TEXT,                          -- "م. أحمد المهندس الزراعي"
    third_party_type    TEXT CHECK (
        third_party_type IN ('advisor', 'dealer', 'ministry', 'researcher', 'other')
    ),

    -- What can it access
    allowed_field_ids   UUID[],                        -- NULL = كل المزرعة
    allowed_endpoints   TEXT[] DEFAULT '{}',           -- whitelist (e.g., 'fields.read', 'reports.generate')

    -- Lifecycle
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,
    last_used_at        TIMESTAMPTZ,
    use_count           INT NOT NULL DEFAULT 0,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sharing_keys_tenant
    ON sharing_keys(tenant_id, created_at DESC)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sharing_keys_prefix
    ON sharing_keys(key_prefix);

CREATE INDEX IF NOT EXISTS idx_sharing_keys_active
    ON sharing_keys(expires_at)
    WHERE revoked_at IS NULL;

ALTER TABLE sharing_keys ENABLE ROW LEVEL SECURITY;

-- المالك يرى مفاتيحه فقط
DROP POLICY IF EXISTS sharing_keys_owner ON sharing_keys;  -- idempotency (المُشغِّل يُعيد التطبيق كلّ إقلاع)
CREATE POLICY sharing_keys_owner ON sharing_keys
    USING (
        -- fail-closed: لو app.current_tenant غير مضبوط (NULL) → لا صفوف
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    );


-- ════════════════════════════════════════════════════════════════
-- ٣. Helper: is_sharing_key_valid()
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION is_sharing_key_valid(p_key_hash TEXT)
RETURNS TABLE(
    valid           BOOLEAN,
    tenant_id       UUID,
    scope           TEXT,
    allowed_fields  UUID[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (k.revoked_at IS NULL AND k.expires_at > NOW()) AS valid,
        k.tenant_id,
        k.scope,
        k.allowed_field_ids
    FROM sharing_keys k
    WHERE k.key_hash = p_key_hash
    LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;


-- ════════════════════════════════════════════════════════════════
-- ٤. Trigger: increment use_count + update last_used_at
-- ════════════════════════════════════════════════════════════════
-- (يُستخدَم من tipo function ضمن middleware عند authentication بالـkey)
CREATE OR REPLACE FUNCTION touch_sharing_key(p_key_hash TEXT) RETURNS VOID AS $$
BEGIN
    UPDATE sharing_keys
    SET use_count = use_count + 1,
        last_used_at = NOW()
    WHERE key_hash = p_key_hash;
END;
$$ LANGUAGE plpgsql;


COMMIT;

-- Verification:
-- SELECT * FROM is_sharing_key_valid('test_hash');   -- returns valid=NULL لو غير موجود
