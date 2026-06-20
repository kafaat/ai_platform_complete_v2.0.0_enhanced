# NDVI_TIMELINE — الخطّ الزمنيّ التاريخيّ للحقل

شريط/خطّ زمنيّ من **أحداث مسجّلة فقط** (لا تاريخ مخترَع على الخادم).

## API
- `GET /api/v1/fields/{field_id}/unified-timeline?limit=&newest_first=&category=`
  (`fields.py:2280`) — يدمج أحداث الحقل عبر **كلّ أنواع الكيانات** (دورة حياة،
  أنشطة، تنبيهات، توصيات) سواء كان `field_id` هو `entity_id` أو داخل
  `payload->>'field_id'`. يمرّ بـ`assemble_timeline` (تصنيف+فرز+إحصاءات).
- `GET /api/v1/fields/{field_id}/history?limit=` (`fields.py:2227`) — أحداث الحقل
  (`entity_type='field'`) فقط + `issue_tags` (farm memory).
- `POST /api/v1/fields/{field_id}/timeline` (`fields.py:2207`) — يبني خطّاً من
  أحداث **مُمرَّرة في الجسم** (لا قاعدة) — للمعاينة/الأوفلاين.

> تحقّق: `unified-timeline` و`history` **GET**؛ `timeline` **POST** (أحداث من
> العميل). للسلسلة الرقميّة NDVI نفسها (قيم/تواريخ) استعمل
> `vegetationApi GET /v1/timeseries/{field_id}` (تقدير تركيبيّ موسوم).

## المدخلات (شكل)
- `unified-timeline`/`history`: query فقط (`limit` يُقصّ [1..1000]).
- `timeline` (`TimelineRequest`): `{ "events":[…], "newest_first":true, "category_filter":[…] }`.

## المخرجات (شكل، من الموجِّه)
- `history` (`fields.py:2277`):
```json
{ "field_id":"…", "events":[ {"event_id":"…","event_type":"irrigation.logged",
  "occurred_at":"2026-05-01T…","issue_tags":["…"]} ], "total_events": 12 }
```
- `unified-timeline` / `timeline` → ناتج `assemble_timeline(...).to_dict()`:
  بطاقات مُصنّفة + مرتّبة + إحصاءات فئات (`tl.to_dict()`).
- القاعدة غير مفعّلة ⇒ `{ "events":[], "total_events":0, "note_ar":"… لا تاريخ حيّ" }`.

## empty/loading/error
- **empty:** `events:[]` (لا أحداث، أو DB متعذّرة) ⇒ اعرض «لا تاريخ مسجّل» + سبب
  من `note_ar`/`error`. **لا تملأ نقاطاً وهميّة**.
- **loading/error:** `history`/`unified` **لا ترفع 500** عند فشل DB — تُرجِع خطّاً
  فارغاً + `error`. اعرض الرسالة بصدق.

## tenant/RLS
- `unified`/`history` عبر `tenant_connection` (RLS) بتوكن (`get_current_user`).
  كلّ مستأجر أحداثه فقط. `timeline` بلا DB (أحداث من العميل) لكن بتوكن.

## قاعدة عدم الاختلاق
- التاريخ من **أحداث مسجّلة فقط**. عند تعطّل القاعدة لا يُخترَع تاريخ — يُعلَن السبب
  (`note_ar`/`error`) وتُعرَض قائمة فارغة. لا تستوفِ الفجوات الزمنيّة بتقدير.

## ربط field_id الحقيقيّ
- `field-scoped` بـ`field_id`. `unified-timeline` يلتقط الأحداث المرتبطة بالحقل
  حتى لو خُزِّن `field_id` داخل `payload` (لا يقتصر على `entity_id`).

## مثال نداء
```ts
const tl = await kongApi
  .get(`/api/v1/fields/${fieldId}/unified-timeline`, { params: { limit: 200 } })
  .then(r => r.data);   // { events|cards, stats, … } من assemble_timeline
```
