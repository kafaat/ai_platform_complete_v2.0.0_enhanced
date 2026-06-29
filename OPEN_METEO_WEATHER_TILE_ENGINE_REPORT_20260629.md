# SAHOOL — Open-Meteo Weather Tile Engine Implementation

## الهدف
تحويل طبقة الطقس/الرياح من تمثيل بصري محلي ثابت إلى بنية إنتاجية أفضل:

- Open-Meteo مصدر البيانات فقط.
- SAHOOL يرسم البلاطات داخل Leaflet.
- SAHOOL يرسم أنيميشن الرياح.
- SAHOOL يعرض الـ legend.
- SAHOOL يوفّر layer controls لتبديل طبقات الطقس الزراعية.

## Backend

### الملفات المعدّلة

- `services/sahool-platform/api/connectors/openmeteo.py`
- `services/sahool-platform/api/routers/weather.py`

### Endpoint جديد

```http
GET /api/v1/weather/tile-data/{z}/{x}/{y}?layer=temperature
```

### الطبقات المدعومة

- `temperature`
- `wind`
- `precipitation`
- `et0`
- `vpd`
- `soil_temperature`
- `soil_moisture`
- `pressure`
- `clouds`

### السلوك

- يحسب مركز بلاطة WebMercator من `z/x/y`.
- يجلب عينة Open-Meteo من مركز البلاطة.
- يستخدم `current` للمتغيرات السريعة مثل الحرارة والرياح والضغط والسحب.
- يستخدم `hourly` لأول ساعة متاحة للمتغيرات الزراعية مثل ET0 و VPD ورطوبة/حرارة التربة.
- يعيد JSON فقط، لا صورة جاهزة.
- الواجهة ترسم الـ SVG GridLayer داخل SAHOOL.
- يوجد cache داخلي TTL = 10 دقائق لتقليل طلبات Open-Meteo أثناء التحريك/التكبير.

## Frontend

### الملف المعدّل

- `frontend/src/components/maphub/OverlayMarkers.tsx`

### ما تم تنفيذه

- `Leaflet GridLayer` فعلي يرسم كل بلاطة كـ SVG.
- كل بلاطة تطلب بياناتها من:

```http
/api/v1/weather/tile-data/{z}/{x}/{y}?layer=<layer>
```

- عند فشل طلب البلاطة، يتم fallback إلى بيانات الحقل الحالية حتى لا تختفي الطبقة.
- Layer controls داخل الخريطة لتبديل الطبقات الزراعية.
- Legend ديناميكي يتغير حسب الطبقة.
- أنيميشن الرياح يبقى مفعل فوق كل الطبقات.
- اتجاه الرياح يعتمد على `wind_direction_10m_deg` من Open-Meteo عند توفره.
- سرعة الخطوط وكثافتها تتأثر بـ `wind_speed_10m_kmh`.

## التحقق

تم تشغيل:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

ونجح بدون أخطاء Python Syntax.

## ملاحظة

لم يتم تشغيل build للواجهة لأن `frontend/node_modules` غير موجود في بيئة الفحص. التغيير مكتوب كـ TSX/React/Leaflet ويحتاج تشغيل `npm install` ثم `npm run build` داخل بيئة المشروع للتحقق النهائي من TypeScript.
