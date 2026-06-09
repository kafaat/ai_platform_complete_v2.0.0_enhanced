# raster-service — سدّ الفجوة المعماريّة (الصور الجوّية + الراستر)

## الفجوة المكتشفة
تطبيق الجوال (`imagery.ts` + `raster.ts`) يستدعي خدمة على port 8001
متوقّعاً "raster-service"، لكنّها **لم تكن موجودة** — ميزة الصور والمؤشّرات
كانت ستتعطّل عند التشغيل الفعلي.

## الحلّ: خدمة raster-service كاملة (port 8001)
أُنشئت `services/raster-service/` تنفّذ **عقد الجوال كاملاً** (10 مسارات):

### بحث الصور (Element84 Earth Search — Sentinel-2 مجّاني بلا مفتاح)
- GET /imagery/search/recent — آخر صور لمنطقة
- GET /imagery/search/season — صور الموسم الزراعي
- POST /imagery/search — بحث متقدّم
يستخرج 12 نطاق Sentinel-2 + فلترة سحب + ترتيب زمني تنازلي.

### معالجة الراستر
- POST /upload/raster + /upload/drone — رفع
- POST /process — معالجة مؤشّر (غير متزامن → job)
- GET /jobs/{id} + /jobs/{id}/result — استعلام المهمّة
- GET /info/{layer_id} — معلومات الطبقة
- GET /tiles/{layer_id}/{z}/{x}/{y}.png — بلاطات MapLibre

### المؤشّرات العشرة (تطابق أنواع الجوال)
NDVI, EVI, SAVI, NDWI, NDMI, GNDVI, FAPAR + VARI, GLI, TGI (RGB للدرون)
بصيغها الرياضيّة الموثّقة.

## التحقّق
- ✓ كلّ مسارات الجوال الـ10 منفّذة ومطابقة
- ✓ كلّ حقول الاستجابة متطابقة (STACImageryItem/ProcessingResult/JobInfo/IndicatorStats)
- ✓ معالجة أخطاء: 502 (Earth Search)، 404، 409 (job غير مكتمل)
- ✓ مُضاف لـdocker-compose (port 8001 + volume + healthcheck)

## مبدأ الصدق المطبّق
- **البحث عن الصور يعمل بالكامل** (httpx + Element84، بلا مكتبات ثقيلة)
- **معالجة البكسلات الفعليّة** (NDVI...) تعمل عند توفّر rasterio في بيئة
  التشغيل؛ بدونها تُرجع بنية صحيحة (لا تنهار) مع ملاحظة واضحة — لم أدّعِ
  حساباً فعليّاً حيث لا تتوفّر المكتبة
- البلاطة الاحتياطيّة شفّافة (PNG صحيح) للعرض السليم

## المصادر الموثّقة
- Element84 Earth Search v1 (Sentinel-2 L2A، AWS Open Data، إعادة زيارة ٥ أيّام)
- صيغ المؤشّرات قياسيّة (NDVI: Rouse 1974، SAVI: Huete 1988، EVI: Liu&Huete 1995)

## الأثر
ميزة الصور الجوّية والمؤشّرات في الجوال صارت **قابلة للتشغيل فعليّاً** —
الفجوة بين الواجهة والخادم سُدّت. النظام الآن متّسق من الجوال → port 8001 →
Element84، ومن الرفع → المعالجة → البلاطات → MapLibre.
