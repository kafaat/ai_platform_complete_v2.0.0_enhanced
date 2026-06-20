# FIELD_BOUNDARY — حدود الحقل (قراءة/تهديف/تنظيف)

طبقة المتّجهات الأساس: مضلّع حدّ الحقل + جودة الحدّ (ثقة/تنظيف طوبولوجيّ).

## API
- `GET /api/v1/fields` → قائمة بهندسة كلّ حقل (`fields.py:349`).
- `GET /api/v1/fields/{field_id}` → `FieldDetail` كامل بـ`geometry`
  (`fields.py:438`, `get_field`).
- `POST /api/v1/fields/{field_id}/boundary/score` → تهديف ثقة الحدّ
  (`boundaries.py:78`). صلاحيّة `FIELD_VIEW`.
- `POST /api/v1/fields/{field_id}/boundary/clean` → تنظيف طوبولوجيّ حتميّ
  (`boundaries.py:180`). صلاحيّة `FIELD_EDIT` (كتابة على `field_boundaries.geom`).
- (مساعِد) `GET /api/v1/fields/{field_id}/boundary-graph` → جيران الحقل
  (`boundaries.py:264`).

> ملاحظة تحقّق: لا توجد نقطة `GET .../boundary` مفردة لجلب الهندسة — الهندسة تأتي
> ضمن `GET /fields/{id}` (و`GET /fields`). `score`/`clean` كلاهما **POST** لا GET.

## المدخلات (شكل)
- `score`: جسم `BoundaryScoreRequest` (`api/boundary_models.py`). `props` اختياريّة
  (`dict|null`)؛ إن لم تُرسَل تُشتقّ الخصائص البنيويّة من `geom` المخزَّنة عبر PostGIS.
- `clean`: `BoundaryCleanRequest` بـ`tolerance_m` (متر).
- لا جسم لـ`GET`.

## المخرجات (شكل، من الموجِّه)
- `GET /fields/{id}`: `FieldDetail` — يشمل `geometry` GeoJSON Polygon +
  `row_version` + أعمدة متقدّمة (`api/field_models.py:94`).
- `boundary/clean` (`boundaries.py:233`):
```json
{ "field_id":"…","vertex_count_before":42,"vertex_count_after":18,
  "is_valid_before":false,"is_valid_after":true,"tolerance_m":1.0 }
```
- `boundary/score`: نتيجة `score_boundary` الكاملة + `derived_props` (الخصائص
  المُشتقّة من PostGIS عند عدم تمرير props). `temporal_agreement` يبقى `null`
  (تهديف هندسيّ أحاديّ التاريخ).

## empty/loading/error
- **empty:** `geometry=null` ⇒ لا حدّ يُرسَم (اعرض «بلا حدود»، لا مضلّع وهميّ).
- **error:** `404` = الحقل/الحدّ ليس للمستأجِر؛ `503` = القاعدة متعذّرة؛
  `422` = حالة/مدخل غير صالح. اعرض الرسالة العربيّة من `detail`.

## tenant/RLS
- كلّها عبر `tenant_connection` (RLS). `score`/`clean` كتابة معزولة. القراءة بتوكن.
- `clean`/`review` بصلاحيّة `FIELD_EDIT`؛ `score`/القراءة بـ`FIELD_VIEW`.

## قاعدة عدم الاختلاق
- ارسم الحدّ فقط من `geometry` المُرجَع. **لا تُولّد حدّاً تقريبيّاً** عند غيابه.
- اعرض `confidence_score`/صلاحيّة الطوبولوجيا كما رجعت — لا تُحسّن الأرقام. `clean`
  **حتميّ** (نفس المدخل نفس المخرج) وشبه-عديم الأثر عند الإعادة.

## ربط field_id الحقيقيّ
- كلّ النقاط `field-scoped` بـ`field_id` من القائمة/الحقل النشط. التهديف/التنظيف
  يعملان على `field_boundaries` لنفس `field_id`.

## مثال نداء
```ts
const detail = await kongApi.get(`/api/v1/fields/${fieldId}`).then(r => r.data); // FieldDetail
// تنظيف الحدّ (FIELD_EDIT):
await kongApi.post(`/api/v1/fields/${fieldId}/boundary/clean`, { tolerance_m: 1.0 });
```
