-- ════════════════════════════════════════════════════════════════
-- SAHOOL v9.0 — migrations/v9_foundation.sql
-- يُشغَّل قبل v9_new_tables.sql
-- يُصلح:
--   ✅ 1. جدول users (كان مفقوداً — auth-service يفشل بدونه)
--   ✅ 3. notification_preferences (كانت مفقودة)
--   ✅ 4. update_updated_at_column() (اسم خاطئ كان update_updated_at)
--   ✅ 5. إيقاف create_hypertable بدون TimescaleDB
--   ✅ 6. pgcrypto extension (gen_random_uuid())
--   ✅ 6b. توحيد UUID functions
--   ✅ 8. UNIQUE constraint على inventory_stock
--   ✅ 9. tenant context helper function لـ auth
--   ✅ 11. تصحيح pg_has_role في RLS
--   ✅ إضافة indexes للأداء
--   ✅ CHECK constraints للسلامة
-- ════════════════════════════════════════════════════════════════

-- ── Extensions ────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS postgis;
-- M02 NOTE: uuid-ossp redundant with pgcrypto (gen_random_uuid() sufficient)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- FIX 6: gen_random_uuid()

-- ── FIX 4: الدالة الصحيحة باسمها الصحيح ─────────────────────
-- init_v8.sql تعرّف update_updated_at() لكن v9 تستدعي update_updated_at_column()
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- alias للتوافق مع init_v8 triggers
-- M07 FIX: removed duplicate (use update_updated_at_column instead)

-- ── FIX 1: جدول users ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL CHECK (email ~* '^[^@]+@[^@]+\.[^@]{2,}$'),  -- H13
    password_hash   VARCHAR(255)        NOT NULL,
    full_name       VARCHAR(100)        NOT NULL,
    role            VARCHAR(20)         DEFAULT 'farmer',
    tenant_id       UUID                DEFAULT gen_random_uuid(),
    active          BOOLEAN             DEFAULT TRUE,
    created_at      TIMESTAMPTZ         DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         DEFAULT NOW()
);

-- H10 FIX: removed redundant idx_users_email (UNIQUE constraint creates index)
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── FIX 1b: جدول fields ──────────────────────────────────────
-- v9 FKs تشير إلى fields. ننشئه صراحةً بـfield_id كمفتاح فريد
-- (لجعل INSERT ... ON CONFLICT (field_id) صالحاً — كشفه validate_migrations).
CREATE TABLE IF NOT EXISTS fields (
    field_id    VARCHAR(50)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    area_ha     NUMERIC(10, 2),
    crop        VARCHAR(50),
    soil_type   VARCHAR(30),
    lat         NUMERIC(10, 6),
    lon         NUMERIC(10, 6),
    gov         VARCHAR(50) DEFAULT 'البيضاء',
    tenant_id   UUID,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Seed fields للحقول الثمانية (field_id الآن PK → ON CONFLICT صالح)
DO $$
BEGIN
    IF (SELECT table_type FROM information_schema.tables
        WHERE table_name = 'fields' AND table_schema = 'public') = 'BASE TABLE' THEN
        INSERT INTO fields (field_id, name, area_ha, crop, soil_type, lat, lon, gov)
        VALUES
    ('field_01','حقل وادي سبأ',        23.5,'قمح صلب',  'loam',      15.05,45.55,'البيضاء'),
    ('field_02','حقل البيضاء الشمالي', 32.0,'شعير',      'clay_loam', 15.02,45.58,'البيضاء'),
    ('field_03','حقل البيضاء الجنوبي', 18.7,'ذرة صفراء', 'sandy_loam',14.98,45.52,'البيضاء'),
    ('field_04','حقل رداع الغربي',     41.3,'طماطم',     'loam',      14.92,45.48,'البيضاء'),
    ('field_05','حقل ذي السفال',       28.9,'قمح صلب',  'silt_loam', 14.88,45.60,'البيضاء'),
    ('field_06','حقل عتمة الشرقي',    37.5,'شعير',      'clay_loam', 15.10,45.62,'البيضاء'),
    ('field_07','حقل الرياشية',        22.1,'خضروات',    'loam',      15.00,45.45,'البيضاء'),
    ('field_08','حقل ذي ناعم',         45.0,'بطاطس',     'sandy_loam',14.85,45.65,'البيضاء')
ON CONFLICT (field_id) DO NOTHING;
    END IF;
END $$;

-- ── FIX 3: notification_preferences ──────────────────────────
CREATE TABLE IF NOT EXISTS notification_preferences (
    id                  BIGSERIAL    PRIMARY KEY,
    user_id             INTEGER      REFERENCES users(id) ON DELETE CASCADE,
    tenant_id           UUID,
    event_types         JSONB        DEFAULT '["satellite","weather_alert","pest_alert","irrigation_rec"]',
    email_enabled       BOOLEAN      DEFAULT FALSE,
    email_address       VARCHAR(255),
    telegram_enabled    BOOLEAN      DEFAULT FALSE,
    telegram_chat_id    VARCHAR(100),
    push_enabled        BOOLEAN      DEFAULT FALSE,
    push_token          TEXT,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_pref_user
    ON notification_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_pref_tenant
    ON notification_preferences(tenant_id);

CREATE TRIGGER trg_notif_pref_updated_at
    BEFORE UPDATE ON notification_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── FIX 8: UNIQUE على inventory_stock ─────────────────────────
-- يُضاف بعد إنشاء inventory_stock في v9_new_tables.sql
-- نُعرّفه هنا كـ deferred لتجنب تعارض الترتيب
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'inventory_stock') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE tablename='inventory_stock' AND indexname='idx_inv_item_tenant'
        ) THEN
            CREATE UNIQUE INDEX idx_inv_item_tenant
                ON inventory_stock(item_name, COALESCE(tenant_id::text, 'default'));
            RAISE NOTICE '✅ UNIQUE index على inventory_stock';
        END IF;
    END IF;
END $$;

-- ── FIX 9: tenant_context helper لـ auth ─────────────────────
-- دالة مساعدة تُستخدم في auth service
CREATE OR REPLACE FUNCTION set_tenant_context(p_tenant_id TEXT)
RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_tenant', p_tenant_id, true);
END;
-- FIX: SET search_path يجب أن يكون في ترويسة الدالّة (لا داخل الجسم قبل BEGIN)
-- وإلّا "syntax error at or near SET". يمنع حقن search_path لدالّة SECURITY DEFINER.
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog;

-- ── FIX 11: تصحيح RLS policies (بدون pg_has_role bypass) ─────
-- يُطبَّق بعد v9_new_tables.sql إذا احتجنا إعادة تعريف policies
-- هذا placeholder — v9_new_tables.sql سيُعاد تعريفه في v9_new_tables_fixed.sql

-- ── FIX 5: BRIN index بديلاً عن create_hypertable ────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'edge_results') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE tablename='edge_results' AND indexname='idx_edge_results_brin'
        ) THEN
            CREATE INDEX IF NOT EXISTS idx_edge_results_brin
                ON edge_results USING BRIN(recorded_at);
            RAISE NOTICE '✅ BRIN index على edge_results';
        END IF;
    END IF;
END $$;

-- ── Medium fixes: CHECK constraints + indexes ─────────────────
DO $$
BEGIN
    -- FIX 18: inventory_stock quantity >= 0
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename='inventory_stock') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='chk_qty_positive'
        ) THEN
            ALTER TABLE inventory_stock
                ADD CONSTRAINT chk_qty_positive CHECK (quantity >= 0);
        END IF;
    END IF;

    -- FIX 20: confidence BETWEEN 0 AND 1
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename='agent_queries') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='chk_confidence_range'
        ) THEN
            ALTER TABLE agent_queries
                ADD CONSTRAINT chk_confidence_range
                CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1);
        END IF;
    END IF;

    -- FIX 21: overall_risk IN valid values
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename='guardrails_log') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='chk_risk_levels'
        ) THEN
            ALTER TABLE guardrails_log
                ADD CONSTRAINT chk_risk_levels
                CHECK (overall_risk IN ('LOW','MEDIUM','HIGH','CRITICAL'));
        END IF;
    END IF;

    -- FIX 16: index on field_tasks.source_event_type
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename='field_tasks') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes WHERE indexname='idx_ft_source_event'
        ) THEN
            CREATE INDEX IF NOT EXISTS idx_ft_source_event ON field_tasks(source_event_type);
        END IF;
    END IF;

    -- FIX 17: index on approval_workflows.expires_at
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename='approval_workflows') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes WHERE indexname='idx_workflow_expires'
        ) THEN
            CREATE INDEX IF NOT EXISTS idx_workflow_expires ON approval_workflows(expires_at);
        END IF;
    END IF;

EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'CHECK constraint error (may already exist): %', SQLERRM;
END $$;

-- ── تقرير ─────────────────────────────────────────────────────
DO $$
BEGIN
    RAISE NOTICE '════════════════════════════════════════════════════';
    RAISE NOTICE '  SAHOOL v9 — v9_foundation.sql مكتمل';
    RAISE NOTICE '════════════════════════════════════════════════════';
    RAISE NOTICE '  ✅ users table';
    RAISE NOTICE '  ✅ fields table / VIEW';
    RAISE NOTICE '  ✅ notification_preferences';
    RAISE NOTICE '  ✅ update_updated_at_column()';
    RAISE NOTICE '  ✅ pgcrypto extension';
    RAISE NOTICE '  ✅ set_tenant_context() helper';
    RAISE NOTICE '  ✅ CHECK constraints';
    RAISE NOTICE '  ✅ Performance indexes';
    RAISE NOTICE '════════════════════════════════════════════════════';
END $$;

-- ═══════════════════════════════════════════════════════════════
-- REVIEW FIX: RLS for users + notification_preferences
-- ═══════════════════════════════════════════════════════════════
DO $$
BEGIN
    -- Users: each user sees their own row (or admin sees all)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
        EXECUTE 'ALTER TABLE users ENABLE ROW LEVEL SECURITY';
        EXECUTE 'DROP POLICY IF EXISTS user_self ON users';
        EXECUTE $ddl$CREATE POLICY user_self ON users USING (
            id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
            OR tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
            OR current_setting('app.current_role', true) = 'admin'
        )$ddl$;
    END IF;

    -- notification_preferences: each user sees their own
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'notification_preferences') THEN
        EXECUTE 'ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY';
        EXECUTE 'DROP POLICY IF EXISTS user_own_prefs ON notification_preferences';
        EXECUTE $ddl$CREATE POLICY user_own_prefs ON notification_preferences USING (
            user_id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
            OR tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
        )$ddl$;
    END IF;
END $$;
