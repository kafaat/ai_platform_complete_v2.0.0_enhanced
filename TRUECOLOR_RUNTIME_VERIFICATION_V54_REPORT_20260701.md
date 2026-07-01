# SAHOOL v54 — TrueColor Runtime Verification

## الهدف
تثبيت أن افتراضي MapHub (`truecolor`) ليس مجرد اختيار واجهة، بل يطلب فعلياً بلاطات Sentinel-2 من `raster-service` داخل حدود الحقل.

## التغييرات

- `frontend/src/sections/MapHub.tsx`
  - إضافة تحقق Runtime عبر:
    - `GET /v1/fields/{field_id}/cdse-tilejson?index=truecolor`
  - عرض حالة جاهزية خاصة بـ TrueColor:
    - جاهز: البلاطات متاحة من raster-service.
    - غير جاهز/خطأ: رسالة صادقة مع زر تجهيز صورة TrueColor.
  - استمرار منع الطقس كافتراضي.
  - استمرار منع scale legend الرقمي فوق TrueColor.

- `frontend/src/sections/MapHubTrueColorRuntime.v54.static.test.ts`
  - حارس ثابت يمنع الانحدار إلى basemap أو NDVI أو null.
  - يتحقق أن TrueColor يمر عبر `/cdse-tiles/` مع `poly` و `bbox`.

## القرار المحمي

```text
MapHub default = truecolor raw Sentinel-2 imagery from raster-service
Weather = explicit overlay only
NDVI/NDMI = optional analytical overlays
Scale legend = numerical indices only, not TrueColor
```

## ملاحظة
لم يتم إجراء اتصال live فعلي مع CDSE/raster-service من بيئة التنفيذ هنا. التحقق يثبت مسار الكود والعقد والـ build/typecheck. الاختبار الحي التالي يجب أن يشغّل docker compose ويقرأ بلاطة فعلية لحقل حقيقي.
