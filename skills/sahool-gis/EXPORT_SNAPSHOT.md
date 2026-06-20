# EXPORT_SNAPSHOT — تصدير لقطة الخريطة وتقرير الحقل

تصدير ما يراه المستخدم: **لقطة الخريطة** (client-side canvas) + **تقرير PDF**
لخطّة المشي الميدانيّة.

## API
- **لقطة الخريطة:** client-side فقط (لا API). التقاط canvas الخريطة الحاليّة
  (`leaflet-image`/`html2canvas` على حاوية `MapContainer`) ⇒ PNG تنزيل.
- **تقرير PDF:** `POST /api/v1/fields/{field_id}/walk-plan/pdf` (`fields.py:2383`)
  — يحوّل وصفة الحقل إلى خطّة مشي ثمّ يُرجِعها **PDF عربيّ** للطباعة. توكن
  (`get_current_user`).
- (نظير JSON) `POST /api/v1/fields/{field_id}/walk-plan` (`fields.py:2373`) — نفس
  الخطّة كـJSON (`_build_walk_plan(...).to_dict()`).

## المدخلات (شكل)
- `walk-plan/pdf` (`WalkPlanRequest`): وصفة الحقل (نفس جسم `walk-plan`). 
- لقطة الخريطة: لا مدخل API — عنصر DOM للخريطة.

## المخرجات (شكل، من الموجِّه)
- `walk-plan/pdf` (`fields.py:2395`): **استجابة ثنائيّة** —
  `media_type="application/pdf"`،
  `Content-Disposition: attachment; filename="walk_plan_{field_id}.pdf"`.
  > في الواجهة: اطلبها كـ`responseType:'blob'` ثمّ نزّلها.
- لقطة الخريطة: `Blob`/`dataURL` PNG من canvas (client-side).

## empty/loading/error
- **error:** `walk-plan/pdf` يرفع `503` إن تعذّر توليد الـPDF (`walk_plan_to_pdf_bytes`
  ترمي `RuntimeError`) — اعرض «تعذّر إنشاء التقرير» لا ملفّاً فارغاً.
- **loading:** أظهر مؤشّر أثناء التوليد/الالتقاط؛ عطّل الزرّ.
- لقطة فارغة (الخريطة لم تُحمَّل بعد) ⇒ لا تصدّر canvas فارغاً.

## tenant/RLS
- `walk-plan/pdf` بتوكن (`get_current_user`)؛ `field_id` في المسار. اللقطة
  client-side تعرض فقط ما حمّلته طبقات مُصادَقة (لا تسرّب بيانات مستأجِر آخر).

## قاعدة عدم الاختلاق
- اللقطة تصوّر **ما هو معروض فعلاً** (طبقات `available` فقط) — لا تُضِف طبقات وهميّة
  قبل التصدير. التقرير يبني على الوصفة المُمرَّرة؛ لا تستوفِ حقولاً ناقصة بقيم
  مُخترَعة. إن تعذّر الـPDF أعلِن الفشل (`503`) لا تُصدِّر بديلاً.

## ربط field_id الحقيقيّ
- التقرير `field-scoped` بـ`field_id` (يظهر في اسم الملفّ). اللقطة تخصّ الحقل/المزرعة
  المعروضة حاليّاً على الخريطة.

## مثال نداء
```ts
// تقرير PDF لخطّة المشي:
const pdf = await kongApi.post(`/api/v1/fields/${fieldId}/walk-plan/pdf`, walkPlanReq,
  { responseType: 'blob' }).then(r => r.data);
const url = URL.createObjectURL(pdf); /* … <a download=`walk_plan_${fieldId}.pdf`> */
// لقطة الخريطة (client-side): التقط حاوية MapContainer إلى PNG ثمّ نزّلها.
```
