# v53 — MapHub TrueColor Default Regression Fix

## السبب
الحزمة `sahool_rc16_5ac1f19_v52_ai_governance_complete.zip` كانت تحتوي حوكمة AI، لكن فحص MapHub كشف بقايا انحدار:

- عند الدخول من «حقولي» كان `activeIndicator` قد يصبح `null`، وهذا يعني خريطة أساس عامة وليس بلاطة حقل TrueColor من raster-service.
- `showWeather` كان يستعيد قيمة workspace المحفوظة، فيمكن أن يعود الطقس كطبقة ظاهرة افتراضياً.
- `layerRegistry` لم يكن يسجل `truecolor` كطبقة raster رسمية.

## الإصلاح
- أضيفت طبقة `truecolor` إلى `frontend/src/lib/layerRegistry.ts` كمصدر raster `source: 'truecolor'`.
- أضيف `RAW_IMAGERY_INDEX_ID = 'truecolor'` داخل `MapHub.tsx`.
- صار فتح الحقل من «حقولي» يمرر `indicator=truecolor` و `showWeather: false`.
- صار `showWeather` يبدأ فقط من `requestedWeatherOpen` ولا يستعيد قيمة workspace.
- تم منع ظهور `MapIndicatorLegend` فوق `truecolor` لأنه صورة خام وليست scale رقمياً.
- تمت حماية backfill ليشمل `truecolor` مع `ndvi/ndmi`.

## التحقق
- `npm test -- src/sections/MapHubSatelliteDefault.static.test.ts src/sections/MapHubTwoYearBackfill.static.test.ts src/sections/MapHubTwoYearTimeline.static.test.ts`
- `npm run typecheck`
- `npm run build`

النتائج: 9 اختبارات واجهة ناجحة، TypeScript typecheck ناجح، و Vite build ناجح.

## القرار المحمي
MapHub default = صورة الحقل الخام TrueColor من raster-service داخل حدود الحقل.
NDVI/NDMI/Weather = overlays تفسيرية اختيارية.
