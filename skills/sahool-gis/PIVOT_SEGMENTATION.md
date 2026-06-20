# PIVOT_SEGMENTATION — تقطيع المحوريّ ومناطق الإدارة

اقتراح **مناطق إدارة** (zones) من قيم NDVI + عمليّات هندسيّة (buffer/union/split/
validate) لتقطيع/تعديل الحدّ — كلّها **معاينة dry-run** لا كتابة صامتة.

## API
- `POST /api/v1/fields/{field_id}/zones` (`fields.py:2402`) — يقترح مناطق إدارة من
  قيم NDVI عبر k-means (`delineate_zones`). توكن (`get_current_user`).
- **نواة GIS (خلف `FEATURE_GIS_KERNEL`، `gis_kernel.py`):** صلاحيّة
  `RECOMMENDATION_VIEW`. مُطفأة افتراضاً ⇒ **`404`** (إغلاق مرن).
  - `POST /api/v1/gis/buffer` — `ST_Buffer(geom, distance_m)` على هندسة مُمرَّرة أو
    `field_id`.
  - `POST /api/v1/gis/union` — `ST_Union` لهندستين/حقلين (دمج).
  - `POST /api/v1/gis/split` — `ST_Split(geom, blade)` ⇒ أجزاء (تقطيع المحوريّ مثلاً).
  - `POST /api/v1/gis/validate` — `ST_IsValid` + `ST_MakeValid`.

## المدخلات (شكل)
- `zones` (`ZoningRequest`): `{ "cells":[{"cell_id":"…","value":0.62,"confidence":0.8}], "n_zones":3 }`.
- `buffer` (`BufferRequest`): `{ "geometry":<GeoJSON>|null, "field_id":"…"|null, "distance_m": 5.0 }`
  — **أحدهما تماماً** (geometry أو field_id، لا كلاهما ولا لا شيء ⇒ `422`).
- `union` (`UnionRequest`): `{ geometry_a|field_id_a, geometry_b|field_id_b }`.
- `split` (`SplitRequest`): `{ geometry|field_id, "blade":<GeoJSON LineString> }`.
- `validate` (`ValidateRequest`): `{ geometry|field_id }`.

## المخرجات (شكل، من الموجِّه)
- `zones` → `delineate_zones(...).to_dict()` (مناطق + إحصاءات). `422` على مدخل غير صالح.
- `buffer` (`gis_kernel.py:146`): `{ "operation":"buffer","dry_run":true,"distance_m":5.0,"result":<GeoJSON> }`.
- `union`: `{ "operation":"union","dry_run":true,"result":<GeoJSON> }`.
- `split` (`gis_kernel.py:238`): `{ "operation":"split","dry_run":true,"part_count":2,"result":<GeometryCollection> }`.
- `validate` (`gis_kernel.py:284`): `{ "operation":"validate","dry_run":true,"is_valid":bool,"reason":str|null,"repaired":<GeoJSON> }`.

## empty/loading/error
- **feature off:** نواة GIS مُطفأة ⇒ `404` «نواة GIS غير مُفعَّلة (اضبط
  FEATURE_GIS_KERNEL)». اعرض أنّ الميزة غير متاحة، لا تُحاكِها.
- **empty/error:** `422` (مدخل/distance فاسد، حقل بلا هندسة)، `503` (قاعدة/PostGIS).

## tenant/RLS
- كلّها عبر `tenant_connection` (RLS) — جلب هندسة `field_id` محصور بالمستأجِر. حقل
  لمستأجِر آخر أو بلا geom ⇒ `422`. عمليّات GIS **dry-run: لا تكتب `fields.geom`**.

## قاعدة عدم الاختلاق
- **dry-run فقط:** اعرض النتيجة المقترحة للمراجعة — لا تطبّقها كحدّ نهائيّ تلقائيّاً
  (لا كتابة هندسة صامتة). المناطق المقترحة تحمل ثقتها؛ لا تُخفِ الخلايا منخفضة الثقة.

## ربط field_id الحقيقيّ
- يمكن تمرير `field_id` بدل GeoJSON خام في كلّ عمليّات النواة ⇒ تعمل على هندسة
  الحقل الحقيقيّة (`fields.geom`، RLS). `zones` مرتبطة بـ`field_id` المسار.

## مثال نداء
```ts
// تقطيع المحوريّ بشفرة خطّيّة (يتطلّب FEATURE_GIS_KERNEL):
const split = await kongApi.post('/api/v1/gis/split',
  { field_id: fieldId, blade: bladeLineString }).then(r => r.data);
// مناطق إدارة من NDVI:
const zones = await kongApi.post(`/api/v1/fields/${fieldId}/zones`,
  { cells, n_zones: 3 }).then(r => r.data);
```
