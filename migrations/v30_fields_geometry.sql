-- v30: حقل الهندسة (GeoJSON) لجدول fields
-- الفجوة: شاشة الخرائط ترسم/تعرض الحقول، لكن جدول fields لم يكن يخزّن هندسة
-- المضلّع المرسوم. POST /api/v1/fields يكتب هذا العمود، وGET /api/v1/fields
-- يقرأه لرسم الحقل على الخريطة (بدل بيانات وهميّة). idempotent.
--
-- ملاحظة: farm_id (مع FK إلى farms) وفهرسه idx_fields_farm مضافان مسبقاً في
-- v19_farms.sql — لا نكرّرهما هنا تفادياً للّبس في ترتيب الهجرات.

ALTER TABLE fields ADD COLUMN IF NOT EXISTS geometry JSONB;

-- فهرس على المستأجر: GET /api/v1/fields يُرشّح WHERE tenant_id = $1.
CREATE INDEX IF NOT EXISTS idx_fields_tenant ON fields(tenant_id);
