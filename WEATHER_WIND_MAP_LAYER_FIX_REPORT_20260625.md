# Weather/Wind Map Layer Verification & Fix — 2026-06-25

## النتيجة قبل التعديل
- الويب كان يعرض شارة طقس صغيرة فوق الحقل المختار فقط (`WeatherOverlay`).
- لم يكن هناك تراكب بصري كامل فوق الخريطة شبيه Windy لحرارة/رطوبة/اتجاه الرياح.
- الموبايل (`OfflineFieldMap`) كان يعرض: طبقة أساس، حدود الحقول، الرسم/الدائرة، ولا يحتوي طبقة طقس/رياح مرئية.

## ما تم تنفيذه
### Web / Leaflet
- إضافة `WeatherRasterOverlay` في:
  - `frontend/src/components/maphub/OverlayMarkers.tsx`
- ربطه داخل الخريطة:
  - `frontend/src/components/maphub/HubMap.tsx`
- الطبقة الآن تُرسم كـ `L.svgOverlay` فوق الخريطة:
  - تظليل حراري/رطوبي.
  - خطوط رياح متحركة فوق الخريطة.
  - تستخدم بيانات الحقل المختار.

### Web / MapLibre GL
- إضافة تراكب بصري فوق محرك MapLibre داخل:
  - `frontend/src/components/maphub/HubMapGL.tsx`
- يظهر عند تفعيل زر الطقس `showWeather`.

### Weather data binding
- توسيع الطقس الحالي لاستقبال اتجاه الرياح:
  - `wind_direction_deg`
  - `wind_dir_deg`
- تمرير:
  - `windSpeedKmh`
  - `windDirectionDeg`
- الملفات:
  - `frontend/src/hooks/useApi.ts`
  - `frontend/src/sections/MapHub.tsx`

### Mobile Flutter
- إضافة خصائص اختيارية إلى `OfflineFieldMap`:
  - `showWeatherOverlay`
  - `weatherTempC`
  - `weatherHumidityPct`
  - `windSpeedKmh`
  - `windDirectionDeg`
  - `weatherOverlayOpacity`
- إضافة `CustomPainter` يرسم:
  - تظليل طقسي فوق الخريطة.
  - خطوط اتجاه الرياح فوق الخريطة.
- الملف:
  - `mobile/sahool_app/lib/widgets/offline_field_map.dart`

## ملاحظات أمانة
- الطبقة تعتمد على بيانات الطقس الحالية المتاحة من API.
- إن لم يرجع API اتجاه الرياح، تظهر خطوط اتجاه افتراضية منخفضة الشفافية بدل الادعاء باتجاه دقيق.
- هذه طبقة تراكب داخل التطبيق، وليست تكاملاً مع Windy.com ولا تعتمد على صور خارجية.
