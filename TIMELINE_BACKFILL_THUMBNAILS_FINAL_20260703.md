# TIMELINE_BACKFILL_THUMBNAILS_FINAL_20260703

## الهدف
إغلاق نقطتين في MapHub:

1. تشغيل backfill التاريخي لمدة سنتين من الواجهة عبر sahool-platform، لا مباشرةً إلى raster-service، حتى لا يُكشف `X-Agent-Token` للمتصفح.
2. عرض thumbnails فعلية داخل Timeline سنتين، وليس بطاقات نصية فقط.

## التعديلات المنفذة

### Backend — sahool-platform

تمت إضافة مسار منصة آمن:

```text
POST /api/v1/fields/{field_id}/imagery/backfill
```

في:

```text
services/sahool-platform/api/routers/fields.py
```

السلوك:

- يتحقق من ملكية الحقل داخل tenant.
- يستعمل حدود الحقل canonical كـ `clip_polygon_geojson` عند غيابها من الطلب.
- يحقن server-side:
  - `X-Agent-Token`
  - `X-Tenant-Id`
- يمرر الطلب إلى:

```text
raster-service /v1/fields/{field_id}/imagery/backfill
```

- يسجل event:

```text
FIELD_IMAGERY_BACKFILL_REQUESTED
```

### Frontend API

تم تعديل:

```text
frontend/src/services/api.ts
```

من:

```text
rasterApi.post('/v1/fields/${fieldId}/imagery/backfill', payload)
```

إلى:

```text
kongApi.post('/api/v1/fields/${fieldId}/imagery/backfill', payload)
```

### MapHub Timeline Thumbnails

تم تعديل:

```text
frontend/src/sections/MapHub.tsx
```

Timeline سنتين أصبح يعرض صورة فعلية لكل مشهد عبر:

```text
fieldCdseThumbnailUrl(...)
```

مع:

- تاريخ المشهد.
- المؤشر النشط.
- tenant id.
- حدود الحقل للقص.
- lazy loading.
- fallback صامت عند فشل تحميل thumbnail، بدون كسر Timeline.

### Tests / Static guards

تم تحديث:

```text
frontend/src/services/api.test.ts
frontend/src/sections/MapHubTwoYearBackfill.static.test.ts
```

للتأكد من:

- backfill يمر عبر platform proxy.
- Timeline يستخدم `fieldCdseThumbnailUrl`.
- لا يتم إرسال `truecolor` كـ IndicatorKind للـ backfill.

## التحقق المنفذ

```text
python -m py_compile services/sahool-platform/api/routers/fields.py
```

نجح بدون أخطاء syntax.

لم يتم تشغيل اختبارات frontend داخل هذه البيئة لأن `frontend/node_modules` غير موجود.
