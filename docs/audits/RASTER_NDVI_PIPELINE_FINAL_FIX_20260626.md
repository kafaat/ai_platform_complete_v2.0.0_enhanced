# Raster/NDVI pipeline final fix — 2026-06-26

## المشكلة المرصودة
الخريطة تعرض حدود الحقل وصورة الأساس، لكن طبقة NDVI لا تظهر بعد اختيار المؤشر.

## ما تم تأكيده وإصلاحه

1. `services/raster-service/db_persist.py`
   - تم تغيير `set_config('app.current_tenant', ..., true)` إلى `false` في دوال:
     - `insert_raster_asset`
     - `fetch_latest_asset`
     - `list_asset_dates`
   - السبب: مع asyncpg/autocommit، `true` محلي للمعاملة وقد يختفي قبل استعلام RLS التالي.

2. `frontend/src/components/maphub/HubMap.tsx`
   - إضافة `tenantId` و `imageryTs` للـ props.
   - إضافة `tid` و `v` إلى رابط البلاطات.
   - تضمين `tenantId/imageryTs` في مفتاح `TileLayer` لإجبار Leaflet على جلب البلاطات الجديدة.

3. `frontend/src/components/maphub/HubMapGL.tsx`
   - إضافة `tenantId` و `imageryTs` للـ props.
   - إضافة `tid` و `v` إلى رابط البلاطات.
   - إضافة `tenantId` و `imageryTs` إلى dependencies الخاصة بطبقة المؤشر.

4. `frontend/src/sections/MapHub.tsx`
   - إضافة `imageryTs` state.
   - عند اختيار حقل + مؤشر يتم استدعاء `refreshFieldImagery(fieldId)` ثم تحديث `imageryTs` بعد مهلة قصيرة لكسر كاش البلاطات.
   - تمرير `tenantId` و `imageryTs` إلى `HubMap`, `HubMapGL`, و `CompareMap`.
   - إصلاح تكرار JSX غير صحيح في `ColormapLegend`.

5. `frontend/src/services/api.ts`
   - تحديث `fieldIndicatorTileUrl` ليدعم `tenantId` و `imageryTs` اختيارياً.

## التحقق
- `python3 -m py_compile services/raster-service/main.py services/raster-service/db_persist.py`: ناجح.
- `python3 verify_review_fixes.py`: 23/23 ناجح.
- Static guards لوجود `tid/v/imageryTs` وغياب `set_config(..., true)`: ناجحة.

## ملاحظات تشغيلية
إذا لم تظهر طبقة NDVI بعد هذا الإصلاح، فافتح Network في المتصفح وتحقق من:
- طلبات `/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png?...` تظهر فعلاً.
- الرابط يحتوي `tid=` و `v=`.
- حالة البلاطات ليست 404/500.
- خدمة `/api/v1/fields/{field_id}/imagery/refresh` تنجح وتنتج COG فعلياً.
