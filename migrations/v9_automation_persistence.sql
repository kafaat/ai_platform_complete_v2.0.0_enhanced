-- SAHOOL v9 — migrations/v9_automation_persistence.sql
-- تخزين دائم لأتمتة الطقس والصور (بدل الذاكرة التي تُفقد عند إعادة التشغيل).
--
-- الفائدة: عند إقلاع المنصّة تُحمّل الإحداثيّات/الحقول المسجّلة، وآخر صورة
-- معروفة لكلّ حقل — فلا يُعاد سحب/معالجة ما عُولج، ولا تُفقد التسجيلات.

-- ── إحداثيّات الطقس المُؤتمت ──────────────────────────────────
CREATE TABLE IF NOT EXISTS weather_automation_locations (
    location_key    VARCHAR(40)  PRIMARY KEY,   -- "lat3,lon3" مقرّب
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    field_id        VARCHAR(64),
    registered_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- آخر طقس مسحوب (cache دائم خفيف)
CREATE TABLE IF NOT EXISTS weather_automation_cache (
    location_key    VARCHAR(40)  PRIMARY KEY
                    REFERENCES weather_automation_locations(location_key) ON DELETE CASCADE,
    data_json       JSONB        NOT NULL,
    fetched_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- ── حقول متابَعة لصور Sentinel ───────────────────────────────
CREATE TABLE IF NOT EXISTS imagery_automation_fields (
    field_id            VARCHAR(64)  PRIMARY KEY,
    tenant_id           UUID,
    bbox_west           DOUBLE PRECISION NOT NULL,
    bbox_south          DOUBLE PRECISION NOT NULL,
    bbox_east           DOUBLE PRECISION NOT NULL,
    bbox_north          DOUBLE PRECISION NOT NULL,
    last_image_id       VARCHAR(128),
    last_image_date     DATE,
    last_checked_at     TIMESTAMPTZ,
    last_indicator_job  VARCHAR(64),
    new_images_found    INTEGER      DEFAULT 0,
    check_errors        INTEGER      DEFAULT 0,
    registered_at       TIMESTAMPTZ  DEFAULT NOW()
);
-- A10: للجداول الموجودة مسبقاً (idempotent) — أضِف tenant_id إن غاب
ALTER TABLE imagery_automation_fields ADD COLUMN IF NOT EXISTS tenant_id UUID;
-- FIX: last_image_date كان VARCHAR(40) — حوّله إلى DATE بأمان (للجداول القائمة).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'imagery_automation_fields'
          AND column_name = 'last_image_date'
          AND data_type <> 'date'
    ) THEN
        ALTER TABLE imagery_automation_fields
            ALTER COLUMN last_image_date TYPE DATE
            USING NULLIF(last_image_date::TEXT, '')::DATE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_imagery_auto_tenant ON imagery_automation_fields (tenant_id);

CREATE INDEX IF NOT EXISTS idx_weather_loc_field
    ON weather_automation_locations(field_id);
CREATE INDEX IF NOT EXISTS idx_imagery_last_checked
    ON imagery_automation_fields(last_checked_at);
