-- ════════════════════════════════════════════════════════════
-- SAHOOL v24 — سجلّ أجهزة IoT + صحّة + ابتلاع telemetry
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ٤): actuator-service يُرسل أوامر MQTT
-- ويستمع لـtelemetry، لكن لا سجلّ أجهزة (iot_devices كان مخطّطاً في
-- v9_automation ولم يُنشأ قطّ)، لا صحّة، لا تخزين للقراءات. هنا:
--   • iot_devices       — السجلّ (هويّة + نوع + حقل + آخر ظهور = صحّة)
--   • device_telemetry  — القراءات المُبتلَعة (هابط مستمرّ، مفهرس زمنيّاً)
-- العزل: RLS لكلّ مستأجر.

-- ── iot_devices: السجلّ + الصحّة ──────────────────────────────
CREATE TABLE IF NOT EXISTS iot_devices (
    device_id        VARCHAR(64)  PRIMARY KEY,            -- معرّف الجهاز (يطابق topic MQTT)
    tenant_id        UUID         NOT NULL,
    name             VARCHAR(120) NOT NULL,
    type             VARCHAR(30)  NOT NULL
        CHECK (type IN ('soil_moisture', 'weather_station', 'water_meter',
                        'camera', 'actuator', 'other')),
    field_id         VARCHAR(50)  REFERENCES fields(field_id) ON DELETE SET NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'unknown'
        CHECK (status IN ('online', 'offline', 'unknown')),
    last_seen_at     TIMESTAMPTZ,                          -- آخر telemetry/heartbeat = صحّة
    firmware_version VARCHAR(40),
    metadata         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_iot_devices_tenant ON iot_devices(tenant_id, type);
CREATE INDEX IF NOT EXISTS idx_iot_devices_field  ON iot_devices(field_id);

DROP TRIGGER IF EXISTS trg_iot_devices_updated_at ON iot_devices;
CREATE TRIGGER trg_iot_devices_updated_at
    BEFORE UPDATE ON iot_devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── device_telemetry: القراءات المُبتلَعة ────────────────────
CREATE TABLE IF NOT EXISTS device_telemetry (
    telemetry_id  BIGSERIAL    PRIMARY KEY,
    tenant_id     UUID         NOT NULL,
    device_id     VARCHAR(64)  NOT NULL REFERENCES iot_devices(device_id) ON DELETE CASCADE,
    sensor_type   VARCHAR(40)  NOT NULL,                   -- soil_moisture / air_temp / ...
    value         NUMERIC(16, 4) NOT NULL,
    unit          VARCHAR(20),
    recorded_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),     -- زمن القياس على الجهاز
    received_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()      -- زمن الوصول للقاعدة
);
CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
    ON device_telemetry(device_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_tenant ON device_telemetry(tenant_id);

-- عزل المستأجرين (self-applied بعد force_all)
SELECT _sahool_apply_tenant_rls('iot_devices');
SELECT _sahool_apply_tenant_rls('device_telemetry');

COMMENT ON TABLE iot_devices      IS 'سجلّ أجهزة IoT (هويّة + نوع + صحّة عبر last_seen_at). v24.';
COMMENT ON TABLE device_telemetry IS 'قراءات الأجهزة المُبتلَعة (هابط زمنيّ). v24.';
