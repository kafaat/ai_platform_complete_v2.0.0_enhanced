# WEATHER_ENGINE_V28_METEOBLUE_SOIL_TEMP_DEPTH_REPORT_20260629

## الهدف
تنفيذ طبقة مستوحاة من رابط Meteoblue المرفق:

`soilTemperature~hourly~auto~10-40 cm down~windAnimationOverlay,temperatureObsOverlay`

بدون استخدام tiles خارجية من Meteoblue. Open-Meteo يبقى مصدر البيانات، وSAHOOL يرسم البلاطات والرياح والـlegend داخلياً.

## Backend

### Connector
تم تحديث:

`services/sahool-platform/api/connectors/openmeteo.py`

- إضافة طلب `soil_temperature_54cm` من Open-Meteo.
- إضافة الحقل المشتق:
  - `soil_temperature_10_40cm_c`
- آلية الاشتقاق:
  - الاعتماد الأساسي على `soil_temperature_18cm`.
  - تقدير 40cm بالاستيفاء بين 18cm و54cm عند توفر 54cm.
  - مزج 18cm و40cm لإخراج طبقة 10-40cm down.

### Router
تم تحديث:

`services/sahool-platform/api/routers/weather.py`

- إضافة layer جديد:
  - `soil_temperature_10_40cm`
- تحديث manifest:
  - depth: `10-40 cm down`
  - derived: true
  - provider_native: false
- دعم layer داخل:
  - `/api/v1/weather/tile-data/{z}/{x}/{y}`
  - spatial interpolation grid
  - cache/rate/metrics الحالية

## Frontend
تم تحديث:

`frontend/src/components/maphub/weather/weatherLayerDefinitions.ts`

- إضافة طبقة:
  - `soil_temperature_10_40cm`
- إضافة preset:
  - `تربة 10-40 سم`
- دعم القراءة من sample:
  - `soil_temperature_10_40cm_c`
  - fallback إلى `soil_temperature_18cm_c` ثم `soil_temperature_6cm_c`

## Tests
أضيف:

`services/sahool-platform/tests/test_weather_engine_v28_soil_temperature_depth.py`

ويغطي:
- إعلان الطبقة داخل manifest.
- صحة الاشتقاق المحلي للقيمة.
- دعم endpoint `tile-data` للطبقة الجديدة.

## التحقق المنفذ

### Backend

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

نجح.

```bash
PYTHONPATH=services/sahool-platform python3 -m pytest -q <weather tests v10-v28>
```

النتيجة: `46 passed`.

### Frontend

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts
```

النتيجة:
- TypeScript passed
- Vite build passed
- WeatherEngine.static.test.ts: `6 passed`

## ملاحظة صدق
هذه ليست نسخة tiles من Meteoblue ولا تستخدم أصول Meteoblue. هي طبقة SAHOOL داخلية تحاكي الوظيفة المطلوبة: Soil temperature hourly, auto model, 10-40 cm down, مع wind animation overlay.
