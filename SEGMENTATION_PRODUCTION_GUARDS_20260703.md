# SAHOOL Segmentation Production Guards — 2026-07-03

## الهدف
تنفيذ تحسينات إنتاجية حقيقية بعد تحسين طبقات الخرائط وSAM2 polygon post-processing:

1. نقل شفافية/metadata نتيجة SAM2 عبر `field-segmentation` إلى الواجهة.
2. تمرير `boundary_metadata` عند حفظ الحقل حتى تُسجل في outbox/geometry revision.
3. إضافة حارس حفظ هندسي يمنع الحدود الرديئة قبل إدخالها في مصدر الحقيقة.
4. تثبيت عقد الثقة: `frontend → nginx → sahool-platform → field-segmentation → sam2-inference`.

## الملفات المعدلة/المضافة

- `services/field-segmentation/main.py`
- `services/field-segmentation/test_segmentation.py`
- `services/sam2-inference/main.py`
- `services/sahool-platform/api/field_models.py`
- `services/sahool-platform/api/field_geometry_save_guard.py`
- `services/sahool-platform/api/routers/fields.py`
- `frontend/src/components/AddFieldWithMap.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/sections/FieldManagementPage.tsx`
- `frontend/src/sections/MapHub.tsx`
- `tests_v9/test_field_geometry_save_guard_20260703.py`
- `tests_v9/test_segmentation_boundary_metadata_contract_20260703.py`

## تفاصيل التنفيذ

### 1. Metadata من SAM2
`sam2-inference` صار يُرجع:

```json
{
  "geometry": {"type":"Polygon", "coordinates":[...]},
  "confidence": 0.87,
  "metadata": {
    "source": "sam2",
    "mode": "auto",
    "model": "sam2",
    "model_version": "1.0.0",
    "checkpoint": "sam2_hiera_large.pt",
    "model_cfg": "sam2_hiera_l.yaml",
    "post_processing": {
      "simplify_tolerance_m": 3,
      "dedup_tolerance_m": 0.5,
      "preserve_topology": true
    },
    "vertices_after": 123,
    "mask_area_px": 12345,
    "inference_ms": 312.4
  }
}
```

### 2. field-segmentation يمرر metadata
`field-segmentation` الآن يقرأ metadata المسموحة من upstream ويرجعها للواجهة مع `geometry/confidence/source`.

### 3. الواجهة تحفظ مصدر الحدود
`AddFieldWithMap.tsx` يحتفظ بـ`boundaryMetadata` بعد اقتراح SAM2 ويرسلها عند الحفظ:

```json
{
  "geometry": {...},
  "boundary_metadata": {
    "source": "sam2",
    "mode": "auto",
    "confidence": 0.87,
    "imagery_source": "sentinel_truecolor",
    "model_version": "sam2-hiera-large"
  }
}
```

للرسم اليدوي يرسل:

```json
{"source":"manual", "mode":"manual"}
```

### 4. حارس حفظ الحدود
تمت إضافة `field_geometry_save_guard.py` ويمنع:

- `boundary_ring_too_short`
- `boundary_too_many_vertices`
- `boundary_area_not_finite`
- `boundary_area_too_small`
- `boundary_area_too_large`
- metadata غير مسموحة مثل `x_agent_token` و`tenant_id`

يعمل في مساري:

- `POST /api/v1/fields`
- `PATCH /api/v1/fields/{field_id}` عند تغيير geometry

### 5. التخزين/التدقيق
`boundary_metadata` تُضاف إلى:

- `FIELD_CREATED` domain event payload
- `field_geometry_revision.metadata`

هذا يجعل مصدر الحدود قابلاً للتدقيق لاحقاً: manual / sam2 / hybrid، model version، ثقة النموذج، إعدادات post-processing.

## التحقق المنفذ

```text
v9-gpu-contract-gate: PASS
v9-feature-transfer-gate: PASS
service-port-gate: PASS
```

```text
services/field-segmentation/test_segmentation.py: 23 passed
focused tests_v9: 35 passed
frontend api/layerRegistry vitest: 25 passed
frontend npm run typecheck: PASS
production_validation_gate.sh: PASS
Python compile compiled=1656 failed=0
```

## ملاحظة
هذا لا يغير مسار الثقة الأمني. الواجهة لا تستدعي `field-segmentation` مباشرة؛ المسار يبقى عبر `sahool-platform` التي تتحقق JWT وتحقن `X-Agent-Token` و`X-Tenant-Id`.
