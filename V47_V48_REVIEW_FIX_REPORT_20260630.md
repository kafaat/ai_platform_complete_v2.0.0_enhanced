# مراجعة وتحسين حزمة v47/v48 — شريط سنتين + MET.no Wind Fallback

## ملخص المراجعة
تمت مراجعة الحزمة المرفقة `rc.16_27d7439` مباشرة من الكود، مع التحقق من:

- شريط الصور التاريخية سنتين في `MapHub`.
- زر backfill لمدة 24 شهراً.
- إصلاح `selected` قبل الاستخدام وعدم وجود TS2448.
- موصل MET Norway لاتجاه الرياح.
- إزالة القيمة الوهمية `315°` من الواجهة.
- تشغيل الاختبارات والبناء.

## الإصلاحات/التحسينات المضافة أثناء المراجعة

### 1) تعميم fallback MET.no على الطقس الحالي أيضاً
كان fallback الاحتياطي لاتجاه الرياح موجوداً في `fetch_weather_tile_data` للبلاطات. أُضيف نفس المنطق إلى `fetch_current` حتى تكون استجابة `/api/v1/weather/current` قادرة أيضاً على ملء `wind_direction_deg` من MET.no عند غيابها من Open-Meteo.

### 2) إضافة `wind_direction_source` للطقس الحالي
أضيف الحقل إلى نموذج `CurrentWeather` وإلى استجابة router:

```json
"wind_direction_source": "open-meteo" | "met.no" | null
```

### 3) إصلاح حالة اتجاه 0°
اتجاه الرياح `0°` قيمة صحيحة، لكن استخدام `or` قد يعاملها كـ falsy. تم تحسين اختيار اتجاه الرياح في البلاطات باستخدام null-coalescing صريح حتى لا يتم استبدال `0°` خطأً.

### 4) ضبط مصدر اتجاه الرياح في البلاطات
`wind_direction_source` صار `open-meteo` فقط إذا كان اتجاه Open-Meteo موجوداً فعلاً، وإلا `null` إلى أن ينجح fallback MET.no.

## ملفات معدلة

- `services/sahool-platform/api/connectors/openmeteo.py`
- `services/sahool-platform/api/routers/weather.py`
- `services/sahool-platform/tests/test_metno_wind_fallback.py`

## التحقق المنفذ

### Backend

```bash
PYTHONPATH=services/sahool-platform python3 -m pytest -q services/sahool-platform/tests/test_metno_wind_fallback.py
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

النتيجة:

- 6 tests passed
- Backend compile guard passed

### Frontend

```bash
cd frontend
npm test -- src/sections/MapHubTwoYearBackfill.static.test.ts src/sections/MapHubTwoYearTimeline.static.test.ts
npm run typecheck
npm run build
```

النتيجة:

- 2 test files passed
- 6 frontend tests passed
- TypeScript typecheck passed
- Vite production build passed

## ملاحظات دقيقة

- لم يتم إجراء live network call إلى MET.no من هذه البيئة.
- لا تزال الواجهة لا ترسم أسهم الاتجاه إلا عندما تكون قيمة اتجاه حقيقية موجودة.
- شريط سنتين يعتمد على `/available-dates`، أما ملء المشاهد الناقصة فيتم عبر زر backfill لمدة 24 شهر.
