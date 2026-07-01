-- v125: قدرات وكيل الذكاء لكلّ مستأجِر (V55 — Agricultural Agent Harness)
--
-- يوسّع حوكمة V52/v124: يضيف عمود ``allowed_capabilities`` إلى ``tenant_ai_policies``
-- ليحكم أيّ أدوات (get_field_state / create_scouting_task / send_recommendation …)
-- يجوز للنموذج استخدامها. كلّ أداة تُعلن قدرة مطلوبة (shared/ai/tool_registry) —
-- فبلا القدرة لا تُستدعى. الافتراضيّ متحفّظ (قراءة فقط، fail-closed).
--
-- يُعدّل جدول v124 (يرث RLS+FORCE منه) — ADD COLUMN IF NOT EXISTS، idempotent + لا-عمليّ
-- على مخطّط طبّقه سابقاً.

ALTER TABLE tenant_ai_policies
    ADD COLUMN IF NOT EXISTS allowed_capabilities text[] NOT NULL
        DEFAULT '{can_read_field_data,can_read_historical_imagery}';

COMMENT ON COLUMN tenant_ai_policies.allowed_capabilities IS
    'قدرات الوكيل الممنوحة للمستأجِر (V55–V61): can_read_field_data · can_read_historical_imagery · can_use_external_llm · can_create_tasks · can_manage_field_boundaries · can_manage_productivity_zones · can_manage_soil_sampling · can_generate_prescriptions · can_send_recommendations · can_trigger_backfill · can_export_enterprise_data. الافتراضيّ قراءة فقط (fail-closed).';
