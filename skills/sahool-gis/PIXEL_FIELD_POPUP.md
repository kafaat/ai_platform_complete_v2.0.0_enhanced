# PIXEL_FIELD_POPUP — popup قيم pixel/field

نافذة منبثقة عند النقر على الحقل/البكسل تعرض حالة الغطاء النباتيّ — **بقاعدة صارمة:
لا قيمة بلا بيانات ⇒ `needs_data`**.

## API
- `POST /api/v1/fields/{field_id}/ndvi-analysis` (`ndvi_analysis.py:34`) — يحلّل
  سلسلة NDVI من العميل ويُرجِع اتجاه/شذوذ/صحّة (`analyze_ndvi_series`). صلاحيّة
  `FIELD_VIEW`. لا قاعدة — `field_id` للسياق.
- (سياق إضافيّ للـpopup) `GET /api/v1/fields/{field_id}/water-stress-spectral`
  (`fields.py:2416`) لقيمة الإجهاد المائيّ إن توفّرت مؤشّرات الرطوبة.

## المدخلات (شكل)
- `{ "series": [ {"date":"2026-05-01","ndvi":0.62}, … ] }` (`NdviAnalysisRequest`).
  سلسلة فارغة ⇒ `422` («سلسلة NDVI فارغة»).

## المخرجات (شكل، من الموجِّه)
ناتج `analyze_ndvi_series`:
```jsonc
{ "trend":"insufficient|rising|falling|stable",
  "health_class":"unknown|healthy|moderate|stressed",
  "anomaly": { "has_anomaly": false, "reason_ar":"", "points":[] },
  "note_ar": "…" }
```
- خرائط العرض العربيّة في المحرّك:
  `healthy→صحّيّ`, `moderate→متوسّط`, `stressed→مُجهَد`.

## empty/loading/error
- **needs_data (القاعدة الذهبيّة):** لا سلسلة / سلسلة قصيرة ⇒
  `trend:"insufficient"` و`health_class:"unknown"`. اعرض الـpopup بحالة **«تحتاج
  بيانات»** + `note_ar` — **لا رقم NDVI مُخمَّن ولا لون صحّة**.
- **loading:** أثناء الطلب اعرض هيكلاً، لا قيمة سابقة كأنّها حاليّة.
- **error:** `422` (سلسلة فارغة) ⇒ اعرض رسالة الجلب الصريحة؛ لا تُخفِها بقيمة صفر.

## tenant/RLS
- بتوكن `FIELD_VIEW`. لا قراءة قاعدة هنا، لكن النقطة `field-scoped` (المسار يحمل
  `field_id` للسياق والاتّساق). قيمة `water-stress-spectral` تتحقّق من ملكيّة الحقل.

## قاعدة عدم الاختلاق
- **هذه المهارة هي التجسيد المباشر للقاعدة.** كلّ حقل في الـpopup يجب أن يقابله
  مصدر فعليّ: NDVI من السلسلة، الصحّة من `health_class`، الشذوذ من `anomaly`. أيّ
  حقل بلا مصدر ⇒ شارة `needs_data` لا قيمة. لا تشتقّ لوناً من تقدير.

## ربط field_id الحقيقيّ
- الـpopup مرتبط بـ`field_id` للحقل المنقور (من الخريطة/الحقل النشط). السلسلة
  المُرسَلة تخصّ ذلك الحقل (من تطبيق الجوّال أو `vegetationApi/v1/timeseries`).

## مثال نداء
```ts
const res = await kongApi
  .post(`/api/v1/fields/${fieldId}/ndvi-analysis`, { series: readings })
  .then(r => r.data);
const label = res.health_class === 'unknown'
  ? 'تحتاج بيانات'                       // needs_data — لا تخترع
  : { healthy:'صحّيّ', moderate:'متوسّط', stressed:'مُجهَد' }[res.health_class];
```
