-- ════════════════════════════════════════════════════════════
-- SAHOOL v35 — العمليّات الزراعيّة (Field activities) لكلّ حقل
-- ════════════════════════════════════════════════════════════
-- تسجيل العمليّات الميدانيّة لكلّ حقل (بذر/تسميد/ريّ/رشّ/تقليم/حصاد/كشف)
-- مع تفاصيل JSONB وتواريخ (مُجدوَلة/مُنفَّذة) وحالة. مربوط بالحقل (وموسم
-- اختياريّ) ومعزول لكلّ مستأجِر (RLS). نمط seasons (v32).

CREATE TABLE IF NOT EXISTS activities (
    activity_id    VARCHAR(50)  PRIMARY KEY,
    tenant_id      UUID         NOT NULL,
    field_id       VARCHAR(50)  NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    season_id      VARCHAR(50),                                 -- موسم اختياريّ
    activity_type  VARCHAR(20)  NOT NULL
        CHECK (activity_type IN ('planting', 'fertilization', 'irrigation',
                                 'spraying', 'pruning', 'harvest', 'scouting')),
    title_ar       VARCHAR(200),                                -- عنوان وصفيّ
    details        JSONB        NOT NULL DEFAULT '{}'::jsonb,    -- تفاصيل حرّة
    scheduled_for  DATE,                                        -- تاريخ مُجدوَل
    performed_on   DATE,                                        -- تاريخ التنفيذ
    status         VARCHAR(20)  NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'done', 'skipped')),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activities_field  ON activities(field_id);
CREATE INDEX IF NOT EXISTS idx_activities_tenant ON activities(tenant_id, status);

DROP TRIGGER IF EXISTS trg_activities_updated_at ON activities;
CREATE TRIGGER trg_activities_updated_at
    BEFORE UPDATE ON activities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

SELECT _sahool_apply_tenant_rls('activities');

COMMENT ON TABLE activities IS 'العمليّات الزراعيّة لكلّ حقل (بذر/تسميد/ريّ/رشّ/تقليم/حصاد/كشف). نمط seasons. v35.';
