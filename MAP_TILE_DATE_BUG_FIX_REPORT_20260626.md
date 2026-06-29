# SAHOOL Map Tile Date Bug Fix — 2026-06-26

## التشخيص
الصورة أظهرت شرائط رأسية في الخلفية، وهي على الأرجح من خريطة الأساس Esri World Imagery، وليست من طبقة المؤشر نفسها لأن الشرائط تمتد خارج حدود الحقل.

وجدت فجوة مؤكدة في الواجهة: `HubMap.tsx` و `HubMapGL.tsx` كانا يبنيان رابط بلاطات المؤشر دائماً باستخدام `date=latest`، حتى عند اختيار تاريخ محدد من مشاهد CDSE. هذا يسبب عدم تطابق بين التاريخ المعروض في الواجهة والبلاطات التي يجلبها المتصفح، وقد يخلط الكاش أو المشاهد.

## الإصلاحات
- أضيف `fetchFieldImageryAvailableDates(fieldId)` في `frontend/src/services/api.ts`.
- أضيفت حالة `selectedImageryDate` و `availableImageryDates` في `frontend/src/sections/MapHub.tsx`.
- أضيف منتقي تاريخ المشهد `data-testid="imagery-date-switcher"` بجانب طبقات المؤشر.
- عُدّل `HubMap.tsx` و `HubMapGL.tsx` بحيث يستقبلان `imageryDate` ويمررانه إلى رابط البلاطات بدلاً من تثبيت `latest`.
- عُدّلت خرائط المقارنة `CompareMap` لتستخدم التاريخ المختار نفسه.
- أضيف اختبار regression ثابت: `frontend/src/components/maphub/ImageryDateWiring.static.test.ts`.

## الأثر
- عند اختيار تاريخ CDSE محدد، ستطلب الواجهة الآن:
  `/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png?index=...&date=YYYY-MM-DD`
  بدلاً من:
  `date=latest` دائماً.
- هذا يمنع عدم تطابق التاريخ بين لوحة الصور وطبقة المؤشر.
- لا يزيل شرائط Esri من خريطة الأساس نفسها؛ لذلك إذا بقيت الشرائط بعد تعطيل طبقة المؤشر فهي من الـ basemap ويجب اختيار خريطة أساس بديلة أو مزود imagery آخر.

## التحقق
- فحص static grep للمسارات المعدلة.
- لم يتم تشغيل `npm run typecheck` لأن `frontend/node_modules` غير موجودة داخل بيئة الفحص.
