# SAHOOL — Weather/Wind Tile Overlay Activation Report — 2026-06-29

## الهدف
تفعيل طبقة عرض الطقس واتجاه الرياح فوق الخريطة عند فتح الحقل من شاشة «حقولي»، مع الحفاظ على مسار CDSE/NDVI الحالي وعدم تغيير نمط MapHub.

## التغييرات المنفذة

### 1) فتح الحقل من «حقولي» مع الطقس مفعل
تم تحديث `frontend/src/sections/MyFieldsPage.tsx` بحيث ينتقل الصف المختار إلى:

```text
/fields/map-center?field_id=<FIELD_ID>&index=ndvi&source=my-fields&weather=1
```

ويُمرر في route state:

```ts
{ fieldId, openCdse: true, indicator: 'ndvi', from: 'my-fields', showWeather: true }
```

### 2) MapHub يفعّل طبقة الطقس/الرياح تلقائياً
تم تحديث `frontend/src/sections/MapHub.tsx` لقراءة:

- `weather=1`
- `weather=true`
- `source=my-fields`
- `routeState.showWeather === true`

ثم تنفيذ:

```ts
setShowWeather(true)
```

مع استمرار تفعيل CDSE/NDVI للحقل نفسه.

### 3) طبقة الطقس تعمل كطبقة بلاطة/راستر فوق الخريطة
تم تحسين `WeatherRasterOverlay` في:

`frontend/src/components/maphub/OverlayMarkers.tsx`

بحيث:

- تغطي نافذة الخريطة بالكامل كـ SVG raster overlay.
- تعرض تلويناً حرارياً شفافاً حسب الحرارة/الرطوبة.
- تعرض خطوط اتجاه الرياح متحركة.
- تتحدث حدودها عند `moveend`, `zoomend`, `resize` حتى تبقى فوق كامل الخريطة بعد التحريك أو التكبير.
- لا تخترع بيانات: عند غياب اتجاه الرياح تُعرض خطوط محايدة بشفافية أقل.

### 4) تحسين نصوص الواجهة
تم تعديل زر الطبقة من «طقس» إلى «طقس/رياح»، وتم تحديث نص فتح الحقل إلى «الخريطة وCDSE والطقس/الرياح».

## السلوك النهائي
1. المستخدم يفتح `/fields`.
2. يضغط على أي حقل في جدول/قائمة «حقولي».
3. ينتقل إلى MapHub مع:
   - الحقل المختار مثبت.
   - مؤشر NDVI/CDSE مفعل.
   - طبقة الطقس واتجاه الرياح مفعّلة فوق الخريطة.
4. تظهر شارة الطقس فوق مركز الحقل، وفوق الخريطة تظهر طبقة راستر/بلاطة شفافة للطقس والرياح.

## التحقق
تم تنفيذ فحص Python backend:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

النتيجة: نجح بدون أخطاء Syntax.

لم يتم تشغيل فحص TypeScript/Flutter في هذه البيئة لأن `node_modules` و Dart/Flutter CLI غير متوفرين داخل الحاوية.
