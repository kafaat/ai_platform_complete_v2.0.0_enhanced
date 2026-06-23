-- ════════════════════════════════════════════════════════════
-- SAHOOL v25 — الري التشغيلي: صمامات + جداول ري مُستمرّة
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ٣): حساب الري (water_balance/FAO-56)
-- موجود لكنّه إرشاديّ فقط — لا تُحفظ جداول ريّ، ولا نمذجة للصمامات/التحكّم.
-- (المضخّات تُنمذَج في equipment كـtype='pump' منذ v23). هنا:
--   • irrigation_valves    — سجلّ الصمامات (نوع + حالة + تدفّق + ربط بجهاز IoT)
--   • irrigation_schedules — جداول الريّ المُستمرّة (وقت + مدّة + أيّام + هدف)
-- العزل: RLS لكلّ مستأجر. التشغيل الفيزيائي يمرّ عبر actuator/automation +
-- موافقة بشريّة (HIL)؛ هذه الطبقة تحفظ النيّة والحالة لا تُشغّل العتاد مباشرةً.

-- ── irrigation_valves: سجلّ الصمامات ──────────────────────────
CREATE TABLE IF NOT EXISTS irrigation_valves (
    valve_id      VARCHAR(50)  PRIMARY KEY,
    tenant_id     UUID         NOT NULL,
    name          VARCHAR(120) NOT NULL,
    field_id      VARCHAR(50)  REFERENCES fields(field_id) ON DELETE SET NULL,
    device_id     VARCHAR(64)  REFERENCES iot_devices(device_id) ON DELETE SET NULL,  -- مُشغّل IoT
    valve_type    VARCHAR(20)  NOT NULL DEFAULT 'solenoid'
        CHECK (valve_type IN ('solenoid', 'manual', 'drip_header', 'gate')),
    status        VARCHAR(20)  NOT NULL DEFAULT 'unknown'
        CHECK (status IN ('open', 'closed', 'unknown')),
    flow_rate_lpm NUMERIC(12, 2) CHECK (flow_rate_lpm IS NULL OR flow_rate_lpm >= 0),  -- لتر/دقيقة
    last_changed_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_valves_tenant ON irrigation_valves(tenant_id);
CREATE INDEX IF NOT EXISTS idx_valves_field  ON irrigation_valves(field_id);

DROP TRIGGER IF EXISTS trg_valves_updated_at ON irrigation_valves;
CREATE OR REPLACE TRIGGER trg_valves_updated_at
    BEFORE UPDATE ON irrigation_valves
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── irrigation_schedules: جداول الريّ المُستمرّة ──────────────
CREATE TABLE IF NOT EXISTS irrigation_schedules (
    schedule_id     VARCHAR(50)  PRIMARY KEY,
    tenant_id       UUID         NOT NULL,
    field_id        VARCHAR(50)  REFERENCES fields(field_id) ON DELETE CASCADE,
    valve_id        VARCHAR(50)  REFERENCES irrigation_valves(valve_id) ON DELETE SET NULL,
    name            VARCHAR(120) NOT NULL,
    start_time      TIME         NOT NULL,                  -- وقت البدء اليومي
    duration_min    INTEGER      NOT NULL CHECK (duration_min > 0 AND duration_min <= 1440),
    days_of_week    INTEGER[],                              -- 0=الإثنين..6=الأحد؛ NULL=يوميّاً
    water_target_mm NUMERIC(10, 2) CHECK (water_target_mm IS NULL OR water_target_mm >= 0),
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    last_run_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sched_field  ON irrigation_schedules(field_id);
CREATE INDEX IF NOT EXISTS idx_sched_tenant ON irrigation_schedules(tenant_id) WHERE enabled = TRUE;

DROP TRIGGER IF EXISTS trg_sched_updated_at ON irrigation_schedules;
CREATE OR REPLACE TRIGGER trg_sched_updated_at
    BEFORE UPDATE ON irrigation_schedules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- عزل المستأجرين (self-applied بعد force_all)
SELECT _sahool_apply_tenant_rls('irrigation_valves');
SELECT _sahool_apply_tenant_rls('irrigation_schedules');

COMMENT ON TABLE irrigation_valves    IS 'سجلّ صمامات الري (نوع/حالة/تدفّق + ربط بجهاز IoT). v25.';
COMMENT ON TABLE irrigation_schedules IS 'جداول الريّ المُستمرّة (وقت/مدّة/أيّام/هدف). v25.';
