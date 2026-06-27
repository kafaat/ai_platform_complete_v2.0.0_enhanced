# Historical Imagery Backfill — Switchable Options

تمت إضافة دعم سحب الصور الجوية/الأقمار التاريخية كخيارات قابلة للتبديل بدلاً من فترة ثابتة مكلفة.

## الخيارات

| Preset | الفترة | الاستخدام |
|---|---:|---|
| `auto_12_months` | 12 شهر | التشغيل التلقائي عند إنشاء حقل جديد |
| `extended_3_years` | 36 شهر | مقارنة المواسم وتحليل الضعف المتكرر |
| `research_5_years` | 60 شهر | المؤسسات/البحث/النمذجة التنبؤية |
| `custom` | 1–120 شهر أو `from_date/to_date` | اختيار يدوي مضبوط |

## API جديد

### سياسة الخيارات

```http
GET /v1/imagery/backfill/policy
```

يرجع الخيارات المسموحة للواجهة ولوحات الإدارة.

### تشغيل backfill لحقل

```http
POST /v1/fields/{field_id}/imagery/backfill
```

مثال:

```json
{
  "preset": "extended_3_years",
  "indices": ["ndvi", "ndmi", "savi", "evi"],
  "max_cloud_pct": 30,
  "limit_per_month": 1,
  "dry_run": true,
  "clip_polygon_geojson": {"type":"Polygon", "coordinates": []}
}
```

## السلوك

- يحسب `bbox` من حدود الحقل الحالية.
- يبحث شهرياً عن Sentinel-2 ضمن الفترة المختارة.
- يختار أقل المشاهد غيوماً حسب `limit_per_month`.
- ينشئ خطة أو jobs لكل `(scene × index)`.
- `dry_run=true` يعطي تقدير عدد المشاهد والمهام قبل التشغيل.
- يمنع مؤشرات الدرون/RGB-only مثل `vari` في backfill Sentinel-2.

## ملفات معدلة

- `services/raster-service/main.py`
- `services/raster-service/test_historical_backfill.py`
- `frontend/src/services/api.ts`
- `frontend/src/services/api.test.ts`

## الاختبارات

Backend targeted:

```text
12 passed
```

وتشمل:

- policy presets.
- custom date range dry-run.
- رفض backfill بدون geometry.
- رفض مؤشر غير مناسب.
- اختبارات البلاطات والـtenant query السابقة.

ملاحظة: اختبارات الواجهة لم تُشغّل لأن `node_modules`/`vitest` غير مثبتة في بيئة التنفيذ الحالية، لكن تمت إضافة اختبارات API ثابتة للواجهة.
