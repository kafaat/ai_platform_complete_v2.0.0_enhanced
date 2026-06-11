-- ════════════════════════════════════════════════════════════
-- SAHOOL v36 — التنبيهات الزراعيّة (Agronomic alerts) لكلّ مستأجِر
-- ════════════════════════════════════════════════════════════
-- تنبيهات مُصنَّفة (رطوبة منخفضة/أمطار غزيرة/خطر مرض/إجهاد حراريّ/خطر صقيع)
-- بدرجة خطورة (info/warning/critical) وحالة (active/acknowledged/resolved)،
-- مربوطة بحقل اختياريّ ومعزولة لكلّ مستأجِر (RLS). نمط activities (v35).

CREATE TABLE IF NOT EXISTS alerts (
    alert_id    VARCHAR(50)  PRIMARY KEY,
    tenant_id   UUID         NOT NULL,
    field_id    VARCHAR(50)  REFERENCES fields(field_id) ON DELETE CASCADE,  -- حقل اختياريّ
    alert_type  VARCHAR(20)  NOT NULL
        CHECK (alert_type IN ('low_moisture', 'heavy_rain', 'disease_risk',
                              'heat_stress', 'frost_risk', 'other')),
    severity    VARCHAR(10)  NOT NULL
        CHECK (severity IN ('info', 'warning', 'critical')),
    title_ar    VARCHAR(200),                                -- عنوان مختصر
    message_ar  TEXT,                                        -- نصّ التنبيه
    status      VARCHAR(20)  NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'acknowledged', 'resolved')),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_field  ON alerts(field_id);
CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts(tenant_id, status, severity);

DROP TRIGGER IF EXISTS trg_alerts_updated_at ON alerts;
CREATE TRIGGER trg_alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

SELECT _sahool_apply_tenant_rls('alerts');

COMMENT ON TABLE alerts IS 'التنبيهات الزراعيّة المُصنَّفة لكلّ مستأجِر (رطوبة/أمطار/مرض/حرارة/صقيع). نمط activities. v36.';
