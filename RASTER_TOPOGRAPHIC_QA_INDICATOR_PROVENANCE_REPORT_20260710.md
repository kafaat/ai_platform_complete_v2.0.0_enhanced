# Raster Topographic QA Indicator Provenance — 2026-07-10

## الهدف

استكمال طبقة Raw Raster QA بحيث لا تعتمد جودة المؤشرات على cloud/nodata فقط، بل تحمل أيضاً عقداً صادقاً لمخاطر التضاريس مثل ظلال التضاريس والانحدار عندما تتوفر مدخلات DEM ومحاذاة مكانية صحيحة.

## ما تم تنفيذه

### 1. وحدة جديدة

- `services/raster-service/raster_topographic_qa.py`

تضيف:

- `build_topographic_qa(...)`
- schema: `sahool.raster_topographic_qa/1`
- أعلام صريحة:
  - `dem_configured`
  - `dem_aligned`
  - `hillshade_available`
  - `sun_geometry_available`
  - `terrain_shadow_risk_pct`
  - `slope_risk_pct`
  - `topographic_qa_applied`
  - `fabricated_topographic_mask: false`

السلوك صادق: لا يتم تخمين terrain shadow أو slope risk إذا لم تكن DEM ومحاذاة grid/sun geometry متاحة.

### 2. توسيع `compute_quality_score`

تم تحديث `services/raster-service/raw_data_processing.py` لدعم:

- `terrain_shadow_risk_pct`
- `slope_risk_pct`
- `topographic_qa_applied`
- penalties محافظة:
  - `terrain_shadow_penalty`
  - `slope_risk_penalty`
- warnings:
  - `terrain_shadow_risk_unavailable`
  - `high_terrain_shadow_risk`
  - `high_slope_risk`

### 3. ربطها بمسار المؤشرات

تم تحديث `services/raster-service/raster_pixel_processing.py` لكي يضيف إلى `stats` و`meta`:

- `topographic_qa`
- `quality_flags.topographic_qa_applied`
- `quality_flags.terrain_shadow_risk_applied`
- `quality_flags.slope_risk_applied`
- `quality_flags.topographic_qa_sources`

في الوضع الحالي إذا كان `FIELD_DEM_PATH` غير مضبوط أو غير محاذى إلى grid المؤشر، تُسجل الطبقة `available=false` ولا يتم اختلاق masks.

### 4. حارس CI جديد

- `scripts/ci/raster_topographic_qa_guard.py`
- `tests_v9/test_raster_topographic_qa_guard.py`
- أُضيف إلى `scripts/ci/runtime_real_smoke.sh`

يفشل إذا اختفت عقود topographic QA أو إذا لم تعد موجودة في مسار المؤشرات.

### 5. اختبارات

- `services/raster-service/test_raster_topographic_qa.py`

تتحقق من أن الطبقة:

- لا تختلق QA بدون DEM.
- تصبح `available=true` فقط عند توفر DEM aligned + risk percentages حقيقية.

## التحقق

```text
raster_topographic_qa_guard_ok
raster_pixel_qa_indicator_guard_ok
9 passed
```

كما نجحت الحراس الأساسية بعد التحديث:

```text
raw_data_processing_contract_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
test_dependency_inventory_check_ok
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
report_index_check_ok
```

## ما لم يتم ادعاؤه

لم يتم بعد تطبيق terrain-shadow mask حقيقي على البكسلات داخل المؤشر، لأن ذلك يحتاج:

- DEM co-registration إلى grid الراستر.
- sun azimuth/elevation من metadata أو provider.
- اختبار ميداني على DEM/scene حقيقي.

الحالي يغلق فجوة provenance والـquality contract، ويمنع اختلاق topographic QA.

## الحكم

أصبحت مؤشرات الرستر تحمل الآن QA متعدد المصادر:

- nodata/valid pixels
- cloud
- cloud shadow
- snow/ice
- saturation
- topographic QA provenance

لكن terrain-shadow masking الفعلي ما زال مرحلة لاحقة مشروطة بربط DEM ومحاذاته زمنياً/مكانياً.
