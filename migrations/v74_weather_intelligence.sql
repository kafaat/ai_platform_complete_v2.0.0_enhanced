-- migrations/v74_weather_intelligence.sql
--
-- طبقة ذكاء الطقس (Weather Intelligence Layer) — مُكيَّفة لمخطّط SAHOOL الفعليّ وأمنه:
--   • field_id نصّ (TEXT) لا UUID — يطابق fields.field_id VARCHAR(50) (راجع v18).
--   • RLS+FORCE بسياسة current_setting (يطابق حُرّاس test_rls_*); الكتابة عبر sahool_app
--     (NOBYPASSRLS) لا superuser. المهامّ العابرة (worker) تستعمل sahool_jobs (BYPASSRLS).
--   • PK (tenant_id, field_id, time) — لأنّ field_id ليس عالميّاً عبر المستأجرين.
--   • قيود CHECK على الدرجات [0,1]/[0,100] + confidence_score [0,1].
-- idempotent (IF NOT EXISTS + DROP POLICY IF EXISTS).
--
-- weather_grid/weather_forecasts: **عالميّة بلا tenant** (بيانات تنبّؤ مشترَكة، غير
-- سرّيّة). إن أُضيفت لاحقاً بيانات خاصّة بمستأجِر ⇒ يجب إضافة tenant_id + RLS.

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── جداول عالميّة (بلا RLS — تنبّؤ مشترَك، موثّق) ──
CREATE TABLE IF NOT EXISTS weather_grid (
    grid_id        TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    resolution_deg DOUBLE PRECISION NOT NULL,
    lat            DOUBLE PRECISION NOT NULL,
    lon            DOUBLE PRECISION NOT NULL,
    geom           GEOMETRY(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_forecasts (
    id                        BIGSERIAL PRIMARY KEY,
    time                      TIMESTAMPTZ NOT NULL,
    grid_id                   TEXT NOT NULL REFERENCES weather_grid(grid_id),
    forecast_reference_time   TIMESTAMPTZ NOT NULL,
    source                    TEXT NOT NULL,
    ensemble_member           INT DEFAULT 0,
    temperature_2m_c          DOUBLE PRECISION,
    humidity_percent          DOUBLE PRECISION,
    wind_speed_10m_ms         DOUBLE PRECISION,
    wind_direction_deg        DOUBLE PRECISION,
    precipitation_mm          DOUBLE PRECISION,
    precipitation_probability DOUBLE PRECISION,
    pressure_hpa              DOUBLE PRECISION,
    solar_radiation_wm2       DOUBLE PRECISION,
    et0_mm                    DOUBLE PRECISION,
    delta_t_c                 DOUBLE PRECISION,
    UNIQUE(time, grid_id, forecast_reference_time, ensemble_member)
);
CREATE INDEX IF NOT EXISTS idx_wf_grid_time ON weather_forecasts(grid_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_wf_time ON weather_forecasts(time DESC);

-- ── جداول بمستأجِرين (RLS) — field_id TEXT (لا UUID) ──
CREATE TABLE IF NOT EXISTS field_weather_overlay (
    field_id                  TEXT NOT NULL,
    tenant_id                 UUID NOT NULL,
    time                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    temperature_min_c         DOUBLE PRECISION,
    temperature_max_c         DOUBLE PRECISION,
    temperature_avg_c         DOUBLE PRECISION,
    humidity_avg_percent      DOUBLE PRECISION,
    wind_speed_avg_ms         DOUBLE PRECISION,
    wind_gust_max_ms          DOUBLE PRECISION,
    precipitation_sum_mm      DOUBLE PRECISION,
    precipitation_probability DOUBLE PRECISION,
    et0_sum_mm                DOUBLE PRECISION,
    delta_t_avg_c             DOUBLE PRECISION,
    spray_suitability_score   DOUBLE PRECISION CHECK (spray_suitability_score BETWEEN 0 AND 1),
    disease_risk_score        DOUBLE PRECISION CHECK (disease_risk_score BETWEEN 0 AND 1),
    heat_stress_hours         INT,
    frost_risk_hours          INT,
    trafficability_score      DOUBLE PRECISION CHECK (trafficability_score BETWEEN 0 AND 100),
    grid_cells_count          INT,
    spatial_coverage          DOUBLE PRECISION,
    -- field_id ليس عالميّاً عبر المستأجرين ⇒ يُضمَّن tenant_id في المفتاح.
    PRIMARY KEY (tenant_id, field_id, time)
);
CREATE INDEX IF NOT EXISTS idx_fwo_tenant_time ON field_weather_overlay(tenant_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_fwo_field_time ON field_weather_overlay(field_id, time DESC);

CREATE TABLE IF NOT EXISTS weather_signals (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    field_id         TEXT NOT NULL,
    signal_type      TEXT NOT NULL,
    confidence_score DOUBLE PRECISION CHECK (confidence_score BETWEEN 0 AND 1),
    time             TIMESTAMPTZ NOT NULL,
    valid_until      TIMESTAMPTZ,
    payload          JSONB,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ws_field_time ON weather_signals(field_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_ws_tenant ON weather_signals(tenant_id);

CREATE TABLE IF NOT EXISTS weather_alerts (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL,
    alert_type             TEXT NOT NULL,
    severity               TEXT NOT NULL,
    field_ids              TEXT[] NOT NULL,
    message                TEXT NOT NULL,
    message_ar             TEXT,
    recommended_action     TEXT,
    recommended_action_ar  TEXT,
    trigger_conditions     JSONB,
    triggered_at           TIMESTAMPTZ DEFAULT NOW(),
    expires_at             TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_wa_tenant ON weather_alerts(tenant_id);

-- ── RLS+FORCE + سياسات tenant_isolation (current_setting — تطابق الحُرّاس) ──
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['field_weather_overlay', 'weather_signals', 'weather_alerts']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format(
            $ddl$CREATE POLICY tenant_isolation ON %I USING (
              tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
            ) WITH CHECK (
              NULLIF(current_setting('app.current_tenant', true), '') IS NULL
              OR tenant_id::TEXT = current_setting('app.current_tenant', true)
            )$ddl$, t
        );
    END LOOP;
END $$;

COMMIT;
