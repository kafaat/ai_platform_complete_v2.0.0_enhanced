-- ═══════════════════════════════════════════════════════════════════
-- SAHOOL v8.0 — PostgreSQL + PostGIS + TimescaleDB Schema
-- التحسينات عن v7.5:
--   ✅ جدول field_indicators (33 مؤشر × كل حقل × زمن)
--   ✅ جدول wofost_seasons (مواسم WOFOST + GDD + LAI + إنتاجية)
--   ✅ جدول crop_stages (مراحل نمو المحصول)
--   ✅ جدول drone_missions (مهام الطائرات)
--   ✅ جدول soil_readings (قراءات IoT التربة)
--   ✅ TimescaleDB hypertables على الجداول الزمنية
--   ✅ فهارس مركبة (composite indexes) للاستعلامات السريعة
--   ✅ RLS محسّن على كل الجداول الجديدة
--   ✅ دوال مساعدة: get_field_health(), ndvi_trend()
-- ═══════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- TimescaleDB (اختياري — يُفعَّل إذا توفّر)
-- CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ══════════════════════════════════════════════════════════════════
-- PART 1: الجداول الأساسية (v7.5 محسّنة)
-- ══════════════════════════════════════════════════════════════════

-- ── Field Boundaries ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS field_boundaries (
    id          SERIAL PRIMARY KEY,
    field_id    VARCHAR(50)  NOT NULL UNIQUE,  -- FIX: قيد فريد لازم لأنّ FKs تشير إلى field_boundaries(field_id)
    field_name  VARCHAR(100) NOT NULL,
    geom        GEOMETRY(POLYGON, 4326),
    area_ha     NUMERIC(10, 2),
    crop        VARCHAR(50),
    soil_type   VARCHAR(30),
    gov         VARCHAR(50) DEFAULT 'البيضاء',
    lat         NUMERIC(10, 6),
    lon         NUMERIC(10, 6),
    tenant_id   UUID,
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (field_id, tenant_id)
);
CREATE INDEX IF NOT EXISTS idx_field_geom       ON field_boundaries USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_field_tenant     ON field_boundaries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_field_active     ON field_boundaries(active) WHERE active = TRUE;

-- ── NDVI Timeseries ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ndvi_timeseries (
    id               SERIAL PRIMARY KEY,
    field_id         VARCHAR(50)  NOT NULL,
    acquisition_date DATE         NOT NULL,
    ndvi_mean        NUMERIC(6, 4) NOT NULL,
    ndvi_min         NUMERIC(6, 4),
    ndvi_max         NUMERIC(6, 4),
    ndvi_std         NUMERIC(6, 4),
    evi              NUMERIC(6, 4),
    savi             NUMERIC(6, 4),
    gndvi            NUMERIC(6, 4),
    ndwi             NUMERIC(6, 4),
    lai              NUMERIC(6, 3),
    cloud_pct        NUMERIC(5, 2),
    satellite        VARCHAR(20)  DEFAULT 'Sentinel-2A',
    source           VARCHAR(50)  DEFAULT 'SAHOOL-v8.0',
    tenant_id        UUID,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (field_id, acquisition_date, satellite)
);
CREATE INDEX IF NOT EXISTS idx_ndvi_field_date  ON ndvi_timeseries(field_id, acquisition_date DESC);
CREATE INDEX IF NOT EXISTS idx_ndvi_tenant      ON ndvi_timeseries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ndvi_recent      ON ndvi_timeseries(acquisition_date DESC);
-- TimescaleDB hypertable (uncomment if TimescaleDB installed)
-- SELECT create_hypertable('ndvi_timeseries', 'acquisition_date', if_not_exists => TRUE);

-- ── Processing Jobs ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS processing_jobs (
    id          SERIAL PRIMARY KEY,
    job_id      UUID         DEFAULT uuid_generate_v4(),
    field_id    VARCHAR(50)  NOT NULL,
    job_type    VARCHAR(50)  NOT NULL, -- 'ndvi_compute', 'wofost_simulate', 'cog_convert'
    status      VARCHAR(20)  DEFAULT 'pending', -- pending/running/completed/failed/cancelled
    progress    NUMERIC(5, 2) DEFAULT 0,
    priority    SMALLINT     DEFAULT 5, -- 1=high, 10=low
    parameters  JSONB,
    result      JSONB,
    error_msg   TEXT,
    tenant_id   UUID,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_field       ON processing_jobs(field_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status      ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant      ON processing_jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_jobs_pending     ON processing_jobs(status, priority) WHERE status = 'pending';

-- ══════════════════════════════════════════════════════════════════
-- PART 2: الجداول الجديدة v8.0
-- ══════════════════════════════════════════════════════════════════

-- ── Field Indicators (33 مؤشر × كل حقل × زمن) ────────────────────
CREATE TABLE IF NOT EXISTS field_indicators (
    id              BIGSERIAL PRIMARY KEY,
    field_id        VARCHAR(50)  NOT NULL,
    indicator_id    VARCHAR(50)  NOT NULL,  -- ndvi, evi, soil_ph, wue, ...
    category        VARCHAR(30)  NOT NULL,  -- vegetation/water/soil/weather/health/productivity/physiology
    value           NUMERIC(12, 4) NOT NULL,
    unit            VARCHAR(20),
    status          VARCHAR(20),            -- excellent/good/fair/poor/critical
    source          VARCHAR(30),            -- sentinel2/iot/wofost/model/lab
    confidence      NUMERIC(4, 3),          -- 0.0–1.0
    raw_data        JSONB,
    tenant_id       UUID,
    recorded_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fi_field_ind     ON field_indicators(field_id, indicator_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_fi_tenant        ON field_indicators(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fi_category      ON field_indicators(category);
CREATE INDEX IF NOT EXISTS idx_fi_recent        ON field_indicators(recorded_at DESC);
-- TimescaleDB:
-- SELECT create_hypertable('field_indicators', 'recorded_at', if_not_exists => TRUE);

-- ── WOFOST Seasons (محاكاة مواسم WOFOST) ──────────────────────────
CREATE TABLE IF NOT EXISTS wofost_seasons (
    id                  SERIAL PRIMARY KEY,
    season_id           UUID         DEFAULT uuid_generate_v4(),
    field_id            VARCHAR(50)  NOT NULL,
    crop                VARCHAR(50)  NOT NULL,
    season_year         SMALLINT     NOT NULL,
    sowing_date         DATE,
    harvest_date        DATE,
    days_grown          SMALLINT,
    -- WOFOST outputs
    gdd_accumulated     NUMERIC(8, 2),    -- درجات نمو متراكمة
    gdd_total_needed    NUMERIC(8, 2),    -- إجمالي GDD المطلوب للنضج
    progress_pct        NUMERIC(5, 2),    -- نسبة اكتمال الموسم
    lai_max             NUMERIC(6, 3),    -- أقصى LAI خلال الموسم
    biomass_kg_ha       NUMERIC(10, 2),   -- الكتلة الحيوية kg/ha
    yield_t_ha          NUMERIC(8, 3),    -- الإنتاجية المتوقعة t/ha
    harvest_index       NUMERIC(4, 3),    -- مؤشر الحصاد (HI)
    rue                 NUMERIC(4, 2),    -- كفاءة استخدام الإشعاع
    water_use_mm        NUMERIC(8, 2),    -- استهلاك المياه mm
    nitrogen_uptake     NUMERIC(8, 2),    -- امتصاص النيتروجين kg/ha
    -- مدخلات النموذج
    soil_nitrogen       NUMERIC(6, 2),
    avg_tmax            NUMERIC(5, 2),
    avg_tmin            NUMERIC(5, 2),
    avg_et0             NUMERIC(5, 2),
    avg_radiation       NUMERIC(5, 2),
    engine_version      VARCHAR(20) DEFAULT 'WOFOST-RUE-v8',
    notes               TEXT,
    tenant_id           UUID,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wofost_field     ON wofost_seasons(field_id, season_year DESC);
CREATE INDEX IF NOT EXISTS idx_wofost_tenant    ON wofost_seasons(tenant_id);
CREATE INDEX IF NOT EXISTS idx_wofost_yield     ON wofost_seasons(yield_t_ha);

-- ── Crop Stages (مراحل نمو المحصول) ──────────────────────────────
CREATE TABLE IF NOT EXISTS crop_stages (
    id              SERIAL PRIMARY KEY,
    field_id        VARCHAR(50)  NOT NULL,
    season_id       UUID,
    stage_name      VARCHAR(50)  NOT NULL, -- germination/vegetative/flowering/grain_filling/maturity
    stage_name_ar   VARCHAR(50),
    stage_number    SMALLINT,
    gdd_start       NUMERIC(8, 2),
    gdd_end         NUMERIC(8, 2),
    date_start      DATE,
    date_end        DATE,
    progress_pct    NUMERIC(5, 2) DEFAULT 0,
    is_current      BOOLEAN DEFAULT FALSE,
    ndvi_expected   NUMERIC(5, 4),
    ndvi_actual     NUMERIC(5, 4),
    deviation_pct   NUMERIC(6, 2),
    recommendations JSONB,              -- توصيات لهذه المرحلة
    tenant_id       UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stages_field     ON crop_stages(field_id, is_current);
CREATE INDEX IF NOT EXISTS idx_stages_current   ON crop_stages(is_current) WHERE is_current = TRUE;

-- ── Drone Missions (مهام أسطول الطائرات) ─────────────────────────
CREATE TABLE IF NOT EXISTS drone_missions (
    id              SERIAL PRIMARY KEY,
    mission_id      UUID         DEFAULT uuid_generate_v4(),
    drone_id        VARCHAR(20)  NOT NULL, -- dr-001, dr-002, ...
    drone_model     VARCHAR(50),
    field_id        VARCHAR(50),
    mission_type    VARCHAR(30) NOT NULL,  -- spray/survey/monitor/inspect
    status          VARCHAR(20) DEFAULT 'planned', -- planned/active/completed/cancelled/emergency
    -- مسار الطيران
    area_covered_ha NUMERIC(8, 2),
    altitude_m      NUMERIC(6, 1),
    speed_ms        NUMERIC(5, 2),
    -- بيانات الرش
    spray_volume_l  NUMERIC(8, 2),
    chemical_used   VARCHAR(100),
    -- بيانات الطائرة
    battery_start   SMALLINT,
    battery_end     SMALLINT,
    signal_strength SMALLINT,
    flight_time_min NUMERIC(6, 1),
    -- GIS
    flight_path     GEOMETRY(LINESTRING, 4326),
    coverage_geom   GEOMETRY(POLYGON, 4326),
    -- زمن
    planned_at      TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    notes           TEXT,
    tenant_id       UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_drone_field      ON drone_missions(field_id);
CREATE INDEX IF NOT EXISTS idx_drone_status     ON drone_missions(status);
CREATE INDEX IF NOT EXISTS idx_drone_path       ON drone_missions USING GIST(flight_path);
CREATE INDEX IF NOT EXISTS idx_drone_tenant     ON drone_missions(tenant_id);

-- ── Soil Readings IoT (قراءات التربة من المستشعرات) ───────────────
CREATE TABLE IF NOT EXISTS soil_readings (
    id              BIGSERIAL PRIMARY KEY,
    field_id        VARCHAR(50)  NOT NULL,
    sensor_id       VARCHAR(50),
    depth_cm        SMALLINT DEFAULT 30,
    -- قياسات
    moisture_pct    NUMERIC(6, 2),
    temperature_c   NUMERIC(5, 2),
    ph              NUMERIC(4, 2),
    ec_ds_m         NUMERIC(6, 3),
    nitrogen_mg_kg  NUMERIC(8, 2),
    phosphorus_mg_kg NUMERIC(8, 2),
    potassium_mg_kg  NUMERIC(8, 2),
    organic_matter_pct NUMERIC(5, 2),
    -- metadata
    source          VARCHAR(30) DEFAULT 'iot_sensor',
    quality         VARCHAR(20) DEFAULT 'good', -- good/suspect/invalid
    tenant_id       UUID,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_soil_field_time  ON soil_readings(field_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_soil_tenant      ON soil_readings(tenant_id);
-- TimescaleDB:
-- SELECT create_hypertable('soil_readings', 'recorded_at', if_not_exists => TRUE);

-- ── Weather Observations (بيانات الطقس) ──────────────────────────
CREATE TABLE IF NOT EXISTS weather_observations (
    id              BIGSERIAL PRIMARY KEY,
    station_id      VARCHAR(50),
    field_id        VARCHAR(50),
    obs_date        DATE         NOT NULL,
    tmax_c          NUMERIC(5, 2),
    tmin_c          NUMERIC(5, 2),
    tmean_c         NUMERIC(5, 2),
    humidity_pct    NUMERIC(5, 2),
    rainfall_mm     NUMERIC(7, 2),
    wind_speed_kmh  NUMERIC(6, 2),
    solar_rad_mj    NUMERIC(7, 3),
    et0_mm          NUMERIC(6, 3),  -- Hargreaves ET0
    gdd             NUMERIC(6, 2),  -- Growing Degree Days (Tbase=10)
    source          VARCHAR(30) DEFAULT 'station',
    tenant_id       UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (station_id, obs_date)
);
CREATE INDEX IF NOT EXISTS idx_weather_date     ON weather_observations(obs_date DESC);
CREATE INDEX IF NOT EXISTS idx_weather_field    ON weather_observations(field_id, obs_date DESC);

-- ══════════════════════════════════════════════════════════════════
-- PART 3: ROW LEVEL SECURITY (RLS)
-- ══════════════════════════════════════════════════════════════════

ALTER TABLE field_boundaries    ENABLE ROW LEVEL SECURITY;
ALTER TABLE ndvi_timeseries     ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_jobs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_indicators    ENABLE ROW LEVEL SECURITY;
ALTER TABLE wofost_seasons      ENABLE ROW LEVEL SECURITY;
ALTER TABLE crop_stages         ENABLE ROW LEVEL SECURITY;
ALTER TABLE drone_missions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_readings       ENABLE ROW LEVEL SECURITY;
ALTER TABLE weather_observations ENABLE ROW LEVEL SECURITY;

-- سياسة موحّدة لكل الجداول: المستأجر يرى بياناته فقط
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'field_boundaries','ndvi_timeseries','processing_jobs',
        'field_indicators','wofost_seasons','crop_stages',
        'drone_missions','soil_readings'
    ] LOOP
        EXECUTE format($ddl$
            DROP POLICY IF EXISTS tenant_isolation ON %I;
            CREATE POLICY tenant_isolation ON %I
            USING (
                tenant_id IS NULL
                OR tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID
            )$ddl$, tbl, tbl);
    END LOOP;
END
$$;

-- ══════════════════════════════════════════════════════════════════
-- PART 4: updated_at TRIGGERS
-- ══════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'field_boundaries','ndvi_timeseries','processing_jobs',
        'wofost_seasons','drone_missions'
    ] LOOP
        EXECUTE format('
            DROP TRIGGER IF EXISTS trg_updated_at ON %I;
            CREATE TRIGGER trg_updated_at
            BEFORE UPDATE ON %I
            FOR EACH ROW EXECUTE FUNCTION update_updated_at()', tbl, tbl);
    END LOOP;
END
$$;

-- ══════════════════════════════════════════════════════════════════
-- PART 5: دوال مساعدة (Helper Functions)
-- ══════════════════════════════════════════════════════════════════

-- دالة: حالة صحة الحقل (مجمّعة)
CREATE OR REPLACE FUNCTION get_field_health(p_field_id VARCHAR)
RETURNS TABLE(
    field_id        VARCHAR,
    ndvi_latest     NUMERIC,
    ndvi_trend      VARCHAR,
    soil_ph_latest  NUMERIC,
    moisture_latest NUMERIC,
    health_score    NUMERIC,
    health_label    VARCHAR
) LANGUAGE plpgsql AS $$
DECLARE
    v_ndvi      NUMERIC; v_ndvi_prev NUMERIC;
    v_ph        NUMERIC; v_moisture  NUMERIC;
    v_score     NUMERIC; v_label     VARCHAR;
BEGIN
    -- آخر NDVI
    SELECT ndvi_mean INTO v_ndvi
    FROM ndvi_timeseries
    WHERE field_id = p_field_id
    ORDER BY acquisition_date DESC LIMIT 1;

    -- NDVI قبل أسبوع
    SELECT ndvi_mean INTO v_ndvi_prev
    FROM ndvi_timeseries
    WHERE field_id = p_field_id
      AND acquisition_date <= CURRENT_DATE - 7
    ORDER BY acquisition_date DESC LIMIT 1;

    -- آخر قراءة تربة
    SELECT ph, moisture_pct INTO v_ph, v_moisture
    FROM soil_readings
    WHERE field_id = p_field_id
    ORDER BY recorded_at DESC LIMIT 1;

    -- حساب الصحة
    v_score := COALESCE(v_ndvi, 0.5) * 60
             + CASE WHEN COALESCE(v_ph, 7) BETWEEN 6 AND 7.5 THEN 20 ELSE 5 END
             + CASE WHEN COALESCE(v_moisture, 35) BETWEEN 25 AND 60 THEN 20 ELSE 5 END;

    v_label := CASE
        WHEN v_score >= 80 THEN 'ممتاز'
        WHEN v_score >= 60 THEN 'جيد'
        WHEN v_score >= 40 THEN 'مقبول'
        ELSE 'يحتاج تدخل'
    END;

    RETURN QUERY SELECT
        p_field_id,
        COALESCE(v_ndvi, 0),
        CASE WHEN v_ndvi > COALESCE(v_ndvi_prev, v_ndvi) THEN 'improving'
             WHEN v_ndvi < COALESCE(v_ndvi_prev, v_ndvi) THEN 'declining'
             ELSE 'stable' END,
        COALESCE(v_ph, 0),
        COALESCE(v_moisture, 0),
        ROUND(v_score, 1),
        v_label;
END;
$$;

-- دالة: اتجاه NDVI (آخر N يوم)
CREATE OR REPLACE FUNCTION ndvi_trend(p_field_id VARCHAR, p_days INT DEFAULT 30)
RETURNS TABLE(
    obs_date    DATE,
    ndvi        NUMERIC,
    evi         NUMERIC,
    lai         NUMERIC,
    ma7         NUMERIC  -- المتوسط المتحرك 7 أيام
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        n.acquisition_date,
        n.ndvi_mean,
        n.evi,
        n.lai,
        AVG(n.ndvi_mean) OVER (
            ORDER BY n.acquisition_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS ma7
    FROM ndvi_timeseries n
    WHERE n.field_id = p_field_id
      AND n.acquisition_date >= CURRENT_DATE - p_days
    ORDER BY n.acquisition_date;
END;
$$;

-- دالة: ملخص المؤشر لكل الحقول
CREATE OR REPLACE FUNCTION indicator_summary(p_indicator_id VARCHAR)
RETURNS TABLE(
    field_id    VARCHAR,
    latest_val  NUMERIC,
    avg_7d      NUMERIC,
    trend       VARCHAR,
    status      VARCHAR,
    recorded_at TIMESTAMPTZ
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        fi.field_id,
        fi.value,
        AVG(fi.value) OVER (
            PARTITION BY fi.field_id
            ORDER BY fi.recorded_at
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ),
        fi.status AS trend,
        fi.status,
        fi.recorded_at
    FROM field_indicators fi
    WHERE fi.indicator_id = p_indicator_id
      AND fi.recorded_at = (
          SELECT MAX(recorded_at)
          FROM field_indicators fi2
          WHERE fi2.field_id = fi.field_id
            AND fi2.indicator_id = p_indicator_id
      )
    ORDER BY fi.field_id;
END;
$$;

-- ══════════════════════════════════════════════════════════════════
-- PART 6: بيانات تجريبية (Seed Data) — 8 حقول يمنية
-- ══════════════════════════════════════════════════════════════════

INSERT INTO field_boundaries (field_id, field_name, area_ha, crop, soil_type, gov, lat, lon)
VALUES
    ('field_01','حقل وادي سبأ',       23.5,'قمح صلب',    'loam',       'البيضاء',15.05,45.55),
    ('field_02','حقل البيضاء الشمالي',32.0,'شعير',        'clay_loam',  'البيضاء',15.02,45.58),
    ('field_03','حقل البيضاء الجنوبي',18.7,'ذرة صفراء',   'sandy_loam', 'البيضاء',14.98,45.52),
    ('field_04','حقل رداع الغربي',    41.3,'طماطم',       'loam',       'البيضاء',14.92,45.48),
    ('field_05','حقل ذي السفال',      28.9,'قمح صلب',    'silt_loam',  'البيضاء',14.88,45.60),
    ('field_06','حقل عتمة الشرقي',   37.5,'شعير',        'clay_loam',  'البيضاء',15.10,45.62),
    ('field_07','حقل الرياشية',       22.1,'خضروات',      'loam',       'البيضاء',15.00,45.45),
    ('field_08','حقل ذي ناعم',        45.0,'بطاطس',       'sandy_loam', 'البيضاء',14.85,45.65)
ON CONFLICT (field_id, tenant_id) DO NOTHING;

-- بيانات NDVI تجريبية (30 يوم)
INSERT INTO ndvi_timeseries (field_id, acquisition_date, ndvi_mean, ndvi_min, ndvi_max, evi, savi, gndvi, cloud_pct, satellite)
SELECT
    f.field_id,
    CURRENT_DATE - (d || ' days')::INTERVAL,
    ROUND((0.45 + RANDOM() * 0.35)::NUMERIC, 4),
    ROUND((0.30 + RANDOM() * 0.20)::NUMERIC, 4),
    ROUND((0.65 + RANDOM() * 0.25)::NUMERIC, 4),
    ROUND((0.35 + RANDOM() * 0.30)::NUMERIC, 4),
    ROUND((0.28 + RANDOM() * 0.25)::NUMERIC, 4),
    ROUND((0.42 + RANDOM() * 0.30)::NUMERIC, 4),
    ROUND((RANDOM() * 15)::NUMERIC, 1),
    CASE WHEN RANDOM() > 0.5 THEN 'Sentinel-2A' ELSE 'Sentinel-2B' END
FROM field_boundaries f, generate_series(0, 29) d
ON CONFLICT (field_id, acquisition_date, satellite) DO NOTHING;

-- موسم WOFOST تجريبي
INSERT INTO wofost_seasons (field_id, crop, season_year, sowing_date, days_grown, gdd_accumulated, gdd_total_needed, progress_pct, lai_max, biomass_kg_ha, yield_t_ha, harvest_index, engine_version)
VALUES
    ('field_01','قمح صلب',   2026, '2025-11-15', 80, 960,  1800, 53.3, 4.2, 4200, 2.8, 0.45, 'WOFOST-RUE-v8'),
    ('field_02','شعير',       2026, '2025-11-20', 75, 825,  1500, 55.0, 3.8, 3800, 2.5, 0.45, 'WOFOST-RUE-v8'),
    ('field_03','ذرة صفراء',  2026, '2025-12-01', 70, 980,  2200, 44.5, 5.1, 5500, 3.9, 0.50, 'WOFOST-RUE-v8'),
    ('field_04','طماطم',      2026, '2025-12-10', 65, 780,  1500, 52.0, 3.2, 3200, 4.2, 0.55, 'WOFOST-RUE-v8'),
    ('field_05','قمح صلب',   2026, '2025-11-10', 85, 1020, 1800, 56.7, 4.5, 4600, 3.1, 0.45, 'WOFOST-RUE-v8'),
    ('field_06','شعير',       2026, '2025-11-25', 72, 792,  1500, 52.8, 3.6, 3600, 2.4, 0.45, 'WOFOST-RUE-v8'),
    ('field_07','خضروات',     2026, '2025-12-15', 60, 660,  1000, 66.0, 2.8, 2800, 5.5, 0.60, 'WOFOST-RUE-v8'),
    ('field_08','بطاطس',      2026, '2025-12-05', 68, 680,  1200, 56.7, 3.0, 3000, 6.8, 0.75, 'WOFOST-RUE-v8')
ON CONFLICT DO NOTHING;

-- مراحل النمو الحالية
INSERT INTO crop_stages (field_id, stage_name, stage_name_ar, stage_number, progress_pct, is_current, ndvi_expected)
VALUES
    ('field_01','grain_filling','ملء الحبوب', 4, 65.0, TRUE, 0.72),
    ('field_02','vegetative',   'نمو خضري',  2, 80.0, TRUE, 0.65),
    ('field_03','flowering',    'تزهير',      3, 45.0, TRUE, 0.70),
    ('field_04','fruiting',     'ثمرة',       4, 55.0, TRUE, 0.68),
    ('field_05','grain_filling','ملء الحبوب', 4, 70.0, TRUE, 0.74),
    ('field_06','vegetative',   'نمو خضري',  2, 75.0, TRUE, 0.63),
    ('field_07','harvest',      'حصاد',       5, 90.0, TRUE, 0.55),
    ('field_08','tuber_init',   'تكوين الدرنات',3,60.0,TRUE, 0.61)
ON CONFLICT DO NOTHING;

-- ══════════════════════════════════════════════════════════════════
-- PART 7: Views مفيدة
-- ══════════════════════════════════════════════════════════════════

-- عرض: آخر مؤشرات NDVI لكل الحقول
CREATE OR REPLACE VIEW v_latest_ndvi AS
SELECT DISTINCT ON (field_id)
    field_id,
    acquisition_date,
    ndvi_mean,
    evi,
    savi,
    gndvi,
    lai,
    satellite,
    CASE
        WHEN ndvi_mean >= 0.70 THEN 'excellent'
        WHEN ndvi_mean >= 0.50 THEN 'good'
        WHEN ndvi_mean >= 0.30 THEN 'fair'
        WHEN ndvi_mean >= 0.10 THEN 'poor'
        ELSE 'critical'
    END AS ndvi_status,
    CASE
        WHEN ndvi_mean >= 0.70 THEN 'ممتاز'
        WHEN ndvi_mean >= 0.50 THEN 'جيد'
        WHEN ndvi_mean >= 0.30 THEN 'مقبول'
        WHEN ndvi_mean >= 0.10 THEN 'منخفض'
        ELSE 'حرج'
    END AS ndvi_status_ar
FROM ndvi_timeseries
ORDER BY field_id, acquisition_date DESC;

-- عرض: ملخص الحقل الشامل
CREATE OR REPLACE VIEW v_field_summary AS
SELECT
    fb.field_id,
    fb.field_name,
    fb.area_ha,
    fb.crop,
    fb.soil_type,
    fb.gov,
    fb.lat,
    fb.lon,
    ln.ndvi_mean AS ndvi_latest,
    ln.ndvi_status,
    ln.ndvi_status_ar,
    ln.acquisition_date AS ndvi_date,
    ws.yield_t_ha AS wofost_yield,
    ws.progress_pct AS season_progress,
    ws.gdd_accumulated,
    cs.stage_name_ar AS current_stage_ar
FROM field_boundaries fb
LEFT JOIN v_latest_ndvi ln ON ln.field_id = fb.field_id
LEFT JOIN wofost_seasons ws ON ws.field_id = fb.field_id AND ws.season_year = EXTRACT(YEAR FROM CURRENT_DATE)
LEFT JOIN crop_stages cs ON cs.field_id = fb.field_id AND cs.is_current = TRUE;

-- عرض: إحصاءات المزرعة الكاملة
CREATE OR REPLACE VIEW v_farm_stats AS
SELECT
    COUNT(DISTINCT field_id)                    AS total_fields,
    SUM(area_ha)                                AS total_area_ha,
    AVG(area_ha)                                AS avg_field_area_ha,
    (SELECT AVG(ndvi_mean) FROM v_latest_ndvi)  AS avg_ndvi_farm,
    (SELECT AVG(yield_t_ha) FROM wofost_seasons WHERE season_year = EXTRACT(YEAR FROM CURRENT_DATE)) AS avg_yield_t_ha,
    NOW()                                        AS computed_at
FROM field_boundaries
WHERE active = TRUE;

-- رسالة نهائية
DO $$ BEGIN
    RAISE NOTICE '✅ SAHOOL v8.0 schema installed successfully';
    RAISE NOTICE '   Tables: %, Indexes: %, Functions: 3, Views: 3',
        (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'),
        (SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public');
END $$;
