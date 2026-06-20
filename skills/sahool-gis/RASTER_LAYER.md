# RASTER_LAYER — طبقات الراستر (NDVI / NDRE / LAI / الإجهاد المائي)

طبقات المؤشّرات الطيفيّة فوق الحقل. **مصدران مختلفان بصدق مختلف** — ميّزهما دائماً.

## API
- `POST /api/v1/fields/{field_id}/ndvi-analysis` (`ndvi_analysis.py:34`) — يحلّل
  **سلسلة NDVI يوفّرها العميل** (تطبيق الجوّال / تاريخ Sentinel): اتجاه + شذوذ +
  صحّة الغطاء. **لا قراءة قاعدة** — `field_id` للسياق فقط. صلاحيّة `FIELD_VIEW`.
- `GET /api/v1/fields/{field_id}/water-stress-spectral?ndmi=&msi=`
  (`fields.py:2416`) — إجهاد مائيّ من مؤشّرات الرطوبة، جسر للقرار.
- `GET /api/v1/indices/coverage-report` (`indices.py:21`) — تقرير حوكمة شفّاف: أيّ
  مؤشّر مربوط بالقرار وأيّها عرض/سياق.
- **خدمات منفصلة (عملاء `vegetationApi` / `rasterApi`):**
  - `vegetationApi` (`:8090`): `GET /v1/analyze`, `GET /v1/timeseries/{field_id}`,
    `GET /v1/ndvi/current/{field_id}` — **تقدير تركيبيّ موسوم `real_data=False`**
    (نطاقات تركيبيّة، لا بكسل). `_current_ndvi_payload` يصرّح بذلك.
  - `rasterApi` (`:8099`): `GET /info/{layer_id}`, `GET /tiles/{layer_id}/{z}/{x}/{y}.png`
    — **بكسل حقيقيّ**؛ البلاطة شفّافة 1×1 إن لم تُنتَج بعد (لا تلوين مفبرك).

## المدخلات (شكل)
- `ndvi-analysis` (`NdviAnalysisRequest`): `{ "series": [ {"date":"2026-05-01","ndvi":0.62}, … ] }`.
- `water-stress-spectral`: query `ndmi`, `msi` (`float|null`).
- بلاطات الراستر: `layer_id` + `z/x/y` (تُضاف كـ`TileLayer` في Leaflet).

## المخرجات (شكل، من الموجِّه)
- `ndvi-analysis` → ناتج `analyze_ndvi_series` (`core/ndvi_analysis.py`):
```jsonc
{ "trend":"insufficient|rising|falling|stable", "health_class":"unknown|healthy|moderate|stressed",
  "anomaly": { "has_anomaly": false, "reason_ar":"", "points":[] }, "note_ar":"…" }
```
> سلسلة فارغة ⇒ `422`. سلسلة قصيرة ⇒ `trend:"insufficient"` + `health_class:"unknown"` + `note_ar`.
- `water-stress-spectral` → `{ "field_id":"…","indices_source":"query_params", …fuse_water_stress(ndmi,msi) }`؛
  لا مؤشّر ⇒ حالة `unknown`.
- `rasterApi GET /info/{layer_id}` → كائن الطبقة المعالَجة (`404` إن غابت).

## empty/loading/error
- **on_demand:** طبقات الأقمار `available=false, status:"on_demand"` في الـworkspace
  — لا تُخزَّن، تُجلب عند الطلب. اعرض زرّ «جلب» لا لوناً افتراضيّاً.
- **empty:** بلاطة شفّافة من raster = لا بيانات بعد ⇒ لا overlay مرئيّ (صحيح).
- **error:** `422` (سلسلة فارغة/مدخل)، `404` (طبقة/حقل)، `503` (قاعدة).

## tenant/RLS
- `water-stress-spectral` يتحقّق أنّ الحقل للمستأجِر (`_assert_field_in_tenant` ⇒
  `404` وإلّا). `ndvi-analysis` بتوكن `FIELD_VIEW` (بلا DB). خدمتا veg/raster
  تشتقّان المستأجِر من التوكن (لا من الـquery — منع تسرّب عابر المستأجرين).

## قاعدة عدم الاختلاق
- **لا تلوّن بكسلاً لم يُرجِعه raster.** البلاطة الشفّافة تعني «لا بيانات» — اتركها.
- **وسِم المصدر صراحةً في الواجهة:** «تقدير تركيبيّ» (vegetation, `real_data=false`)
  مقابل «قياس بكسليّ» (raster). لا تدمجهما كأنّهما نفس الموثوقيّة.
- `health_class:"unknown"`/`trend:"insufficient"` يُعرَض كما هو، لا قيمة مُخمَّنة.

## ربط field_id الحقيقيّ
- كلّ النقاط `field-scoped`. سلسلة `ndvi-analysis` تخصّ الحقل المختار؛ بلاطات
  raster مرتبطة بـ`layer_id` المُنتَج لذلك الحقل/التاريخ.

## مثال نداء
```ts
// تحليل سلسلة NDVI (العميل يوفّر السلسلة):
const a = await kongApi.post(`/api/v1/fields/${fieldId}/ndvi-analysis`,
  { series: readings /* [{date,ndvi}] */ }).then(r => r.data);
// طبقة بلاطات حقيقيّة فوق Leaflet:
// <TileLayer url={`${RASTER_URL}/tiles/${layerId}/{z}/{x}/{y}.png`} />
```
