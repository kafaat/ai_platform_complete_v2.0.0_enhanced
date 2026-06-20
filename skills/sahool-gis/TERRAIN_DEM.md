# TERRAIN_DEM — التضاريس (DEM / انحدار / اتّجاه)

طبقة تفسير تضاريسيّ للحقل: ارتفاع/منحدر/اتّجاه ⇒ دلالة زراعيّة (انجراف/صقيع/تعرّض
شمسيّ/صرف). **طبقة عرض/استرشاد فقط** (`display_only`).

## API
- `GET /api/v1/fields/{field_id}/terrain` (`fields.py:462`) — يقرأ أعمدة التضاريس
  المخزّنة (`elevation_m`, `slope_pct`, `aspect`) ويُرجِع `enrich_terrain`. صلاحيّة
  `FIELD_VIEW`.

## المدخلات (شكل)
- لا جسم. `field_id` في المسار. توكن.

## المخرجات (شكل، من الموجِّه)
ناتج `enrich_terrain(...)` + إضافات (`fields.py:491`):
```jsonc
{ /* …تفسير enrich_terrain: تدريج/انجراف/صقيع/تعرّض شمسيّ/صرف… */
  "field_id": "…",
  "dem_auto_fill": {
    "available": false,
    "note_ar": "التعبئة التلقائيّة من DEM مؤجَّلة (تحتاج مزوّد SRTM/Copernicus حيّاً)…"
  } }
```
> القيم الغائبة (`elevation_m`/`slope_pct`/`aspect = null`) ⇒ التفسير يُعلِنها
> ناقصة بصدق؛ لا يخترع منحدراً.

## empty/loading/error
- **empty:** أعمدة التضاريس فارغة ⇒ التفسير ناقص + `dem_auto_fill.available=false`.
  اعرض «أدخِل القيم عبر `PATCH /api/v1/fields/{field_id}`» — لا منحدر/اتّجاه مُخمَّن.
- **error:** `404` (الحقل ليس للمستأجِر)، `503` (قاعدة).

## tenant/RLS
- عبر `tenant_connection` (RLS) بتوكن `FIELD_VIEW`. `404` إن لم يكن الحقل للمستأجِر.

## قاعدة عدم الاختلاق
- **التعبئة التلقائيّة من DEM (SRTM/Copernicus) مؤجَّلة** (لا مزوّد حيّ مضبوط):
  `dem_auto_fill.available=false` دائماً حاليّاً. لا تعرض hillshade/منحدر «تلقائيّ»
  كأنّه محسوب من DEM — التفسير يعمل فقط على القيم **المخزّنة يدويّاً**.
- (للبكسل التضاريسيّ الحقيقيّ لاحقاً: `rasterApi GET /imagery/dem` و
  `POST /terrain/slope` موجودان في raster-service لكن خارج هذا المسار.)

## ربط field_id الحقيقيّ
- `field-scoped`. القيم تُملأ عبر `PATCH /api/v1/fields/{field_id}`
  (`elevation_m`/`slope_pct`/`aspect`) ثمّ تُفسَّر فوراً.

## مثال نداء
```ts
const terrain = await kongApi.get(`/api/v1/fields/${fieldId}/terrain`).then(r => r.data);
if (!terrain.dem_auto_fill.available) {
  // اعرض دعوة إدخال يدويّ — لا تصوّر تضاريس مفبركة
}
```
