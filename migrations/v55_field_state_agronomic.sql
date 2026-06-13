-- migrations/v55_field_state_agronomic.sql
-- Stage E (توحيد النواة): تخزين الحقائق الزراعيّة الغنيّة في إسقاط field_state.
--
-- recompute_field_state يدمج compose_field_state (النواة: crop_vigor/salinity_class
-- + تحكيم + provenance). هذا العمود يحفظها في الإسقاط نفسه، فتكون متاحة لمن يقرأ
-- الجدول مباشرةً (لا عبر recompute فقط) — تحقيقاً لهدف «دمج النواة في الإسقاط».
--
-- صدق: NULL = لا إشارات كافية لتأليف الحالة الزراعيّة (لا تلفيق). idempotent.

ALTER TABLE field_state ADD COLUMN IF NOT EXISTS agronomic JSONB;
