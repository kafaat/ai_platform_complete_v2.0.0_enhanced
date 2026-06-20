# MAP_VIEWER — عارض الخريطة (react-leaflet 2D)

عارض الخريطة الأساس على البنية الحاليّة: يرسم **كلّ حقول المستأجِر** فوق صور أقمار،
مضلّعاً لكلّ حقل بهندسة وعلامة نقطيّة لما بلا هندسة. المرجع الحيّ:
`frontend/src/sections/FarmMapOverview.tsx`.

## API
- `GET /api/v1/fields` — قائمة حقول المستأجِر (`fields.py:349`، `list_fields`).
  في الواجهة عبر `listFields()` / `useSelectedField()` (تستعمل `kongApi`).
- لا حاجة لخدمة بلاطات: الأساس صور Esri مباشرة
  (`https://server.arcgisonline.com/.../World_Imagery/...`).

## المدخلات (شكل)
- لا جسم. توكن عبر `kongApi` interceptor. التصفية بالمستأجِر تلقائيّة (RLS +
  `WHERE tenant_id = $1`).

## المخرجات (شكل، من الموجِّه)
`list[FieldSummary]` (`api/field_models.py:23`). الحقول المهمّة للخريطة:
```jsonc
{
  "field_id": "fld_…", "farm_id": "", "name_ar": "حقل وادي سبأ",
  "crop": "قمح صلب", "area_ha": 23.5, "quality_grade": "READY",
  "health_summary_ar": "—", "soil_type": "loam", "manager": null,
  "lat": 15.0, "lon": 44.0,            // قد تكون null
  "geometry": { "type": "Polygon", "coordinates": [[[lon,lat],…]] } // أو null
}
```
> `geometry` GeoJSON (lon,lat). Leaflet يتطلّب (lat,lng) ⇒ استعمل `geomToPolygon`
> من `lib/geo` للقلب. `geometry=null` ⇒ ارسم `CircleMarker` على `[lat,lon]`.

## empty/loading/error
- **loading:** `<LoadingState message="جارٍ تحميل خريطة المزرعة…" />`.
- **empty:** المصفوفة فارغة ⇒ `<EmptyState title="لا حقول مُسجّلة بعد" … />` —
  **لا تخترع حقولاً**.
- **error:** `503`/شبكة ⇒ `<ErrorState onRetry={refetch} />`. لا بيانات بديلة.

## tenant/RLS
- قراءة محميّة بتوكن (`get_current_user`) + ترشيح صريح بـ`tenant_id` + RLS. لا حقل
  من مستأجِر آخر يصل أبداً.

## قاعدة عدم الاختلاق
- ارسم فقط ما رجع في `geometry`/`lat`/`lon`. حقل بلا هندسة وبلا مركز ⇒ **لا تعرضه
  على الخريطة** (في `FarmMapOverview` يُرجِع `null`)، ويظهر في القائمة الجانبيّة
  موسوماً «بلا حدود».

## ربط field_id الحقيقيّ
- مفتاح كلّ عنصر = `field.field_id` (في الواجهة `f.id`). النقر يضبط الحقل النشط
  المشترك عبر `useSelectedField().setFieldId(f.id)` فيتبع المستخدم عبر الشاشات.

## متى 2D يكفي ومتى يلزم 3D لاحقاً
- **Leaflet 2D يكفي** لـ: حدود الحقل، overlay الريّ/المعدّات، طبقات NDVI كـraster
  overlay، الـpopup، التقطيع — أي كلّ مهارات هذه الحزمة.
- **3D لاحقاً (مؤجَّل)** يلزم فقط عند: تصوّر التضاريس مجسّماً (DEM hillshade مجسّم)
  أو مسارات طيران/طائرات مسيّرة بارتفاع. حتى ذلك، التضاريس تُعرَض كتفسير رقميّ
  (انظر TERRAIN_DEM) لا مجسّم. لا تُدخِل مكتبة 3D دون حاجة مؤكَّدة.

## مثال نداء
```ts
import { listFields } from '../services/api';
const fields = await listFields();           // FieldSummary[]
// الرسم: <Polygon positions={geomToPolygon(f.geometry)} … /> أو <CircleMarker … />
```
