-- ════════════════════════════════════════════════════════════
-- SAHOOL v45 — فهرس season_id على activities + توثيق العلاقة المنطقيّة
-- ════════════════════════════════════════════════════════════
-- العمليّة (activity) قد ترتبط بموسم (season) اختياريّاً عبر season_id.
-- العلاقة منطقيّة: الموسم يجب أن يخصّ نفس الحقل (field_id). لا نفرض FK صلباً
-- على القاعدة لأنّه قد يفشل على صفوف يتيمة قائمة؛ بدلاً من ذلك نضيف فهرساً
-- يدعم تحقّق التطبيق (SELECT ... FROM seasons WHERE season_id=$1 AND field_id=$2)
-- في create_activity. خطوة إضافيّة آمنة (idempotent). نمط v35.

CREATE INDEX IF NOT EXISTS idx_activities_season ON activities(season_id);

COMMENT ON COLUMN activities.season_id IS 'موسم اختياريّ مرتبط بالعمليّة — يجب (تطبيقيّاً) أن يخصّ نفس الحقل. v45.';
