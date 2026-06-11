-- ════════════════════════════════════════════════════════════
-- SAHOOL v20 — جداول الأتمتة: automation_rules + device_commands_log
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ٣): services/actuator-service يقرأ
-- automation_rules ويكتب device_commands_log (Scene Linkage: قاعدة → MQTT →
-- تشغيل جهاز)، لكن الجدولين لم يُنشآ قطّ — فقط v9_automation.sql يحاول فرض RLS
-- عليهما ويتخطّاهما (CONTINUE WHEN to_regclass IS NULL). النتيجة: الأتمتة
-- معطّلة على مستوى القاعدة. هذه الأعمدة تطابق استعلامات actuator حرفيّاً.

-- ── automation_rules ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS automation_rules (
    rule_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    field_id             VARCHAR(50),                 -- سياق الحقل (اختياريّ)
    name                 VARCHAR(120),
    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    -- المُحفّز (trigger): حسّاس + عامل مقارنة + عتبة
    trigger_sensor       TEXT NOT NULL,               -- soil_moisture / air_humidity / ...
    trigger_operator     TEXT NOT NULL CHECK (trigger_operator IN ('>', '>=', '<', '<=', '==')),
    trigger_threshold    NUMERIC NOT NULL,
    trigger_duration_sec INTEGER NOT NULL DEFAULT 0,
    -- الإجراء (action): جهاز + أمر + حمولة
    action_device        TEXT NOT NULL,               -- pump-01 / valve-north / ...
    action_command       TEXT NOT NULL,               -- open / close / start / stop
    action_payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- حواجز السلامة (تطابق منطق actuator: cooldown + سقف يومي + نافذة زمنيّة)
    max_daily_runs       INTEGER NOT NULL DEFAULT 999,
    cooldown_sec         INTEGER NOT NULL DEFAULT 0,
    last_triggered       TIMESTAMPTZ,
    today_run_count      INTEGER NOT NULL DEFAULT 0,
    last_reset_date      DATE,
    time_window_start    TIME,                         -- لا تشغيل خارج النافذة (مثلاً ليلاً فقط)
    time_window_end      TIME,
    days_of_week         INTEGER[],                    -- 0=الإثنين..6=الأحد (Python weekday)؛ NULL=كلّها
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_autorules_tenant_sensor
    ON automation_rules(tenant_id, trigger_sensor) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_autorules_field ON automation_rules(field_id);

DROP TRIGGER IF EXISTS trg_autorules_updated_at ON automation_rules;
CREATE TRIGGER trg_autorules_updated_at
    BEFORE UPDATE ON automation_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── device_commands_log ───────────────────────────────────────
-- سجلّ كلّ أمر أُرسِل لجهاز (تتبّع/تدقيق: من شغّل المضخّة، متى، بأيّ قاعدة).
CREATE TABLE IF NOT EXISTS device_commands_log (
    log_id        BIGSERIAL PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    rule_id       UUID REFERENCES automation_rules(rule_id) ON DELETE SET NULL,
    device_id     TEXT NOT NULL,
    command       TEXT NOT NULL,
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT NOT NULL,                        -- sent / failed
    mqtt_topic    TEXT,
    triggered_by  TEXT,                                 -- rule / manual / system
    -- sent_at: actuator-service يختار ويُرتّب بـsent_at (GET /commands) — لا created_at.
    -- الإدراج لا يضبطه (DEFAULT NOW يملؤه = لحظة الإرسال).
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devcmd_tenant   ON device_commands_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_devcmd_device   ON device_commands_log(device_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_devcmd_rule     ON device_commands_log(rule_id);

-- عزل المستأجرين (self-applied بعد force_all، كنمط v15/v16)
SELECT _sahool_apply_tenant_rls('automation_rules');
SELECT _sahool_apply_tenant_rls('device_commands_log');

COMMENT ON TABLE automation_rules IS 'قواعد الأتمتة (Scene Linkage): حسّاس→عتبة→أمر جهاز. v20.';
COMMENT ON TABLE device_commands_log IS 'سجلّ أوامر الأجهزة (تتبّع التشغيل الميداني). v20.';
