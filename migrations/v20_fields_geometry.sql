-- v20: حقل الهندسة (GeoJSON) + farm_id لجدول fields
-- الفجوة: شاشة الخرائط ترسم/تعرض الحقول، لكن جدول fields لم يكن يخزّن هندسة
-- المضلّع المرسوم ولا ربطه بمزرعة. POST /api/v1/fields يكتب هذين العمودين،
-- وGET /api/v1/fields يقرأهما لرسم الحقل على الخريطة (بدل بيانات وهميّة).
-- idempotent: IF NOT EXISTS على كلّ تغيير.

ALTER TABLE fields ADD COLUMN IF NOT EXISTS geometry JSONB;
ALTER TABLE fields ADD COLUMN IF NOT EXISTS farm_id   VARCHAR(50);

-- فهرس على المستأجر: GET /api/v1/fields يُرشّح WHERE tenant_id = $1.
CREATE INDEX IF NOT EXISTS idx_fields_tenant ON fields(tenant_id);
-- فهرس على المزرعة: GET /api/v1/farms/{farm_id}/fields يُرشّح WHERE farm_id = $1.
CREATE INDEX IF NOT EXISTS idx_fields_farm   ON fields(farm_id);
