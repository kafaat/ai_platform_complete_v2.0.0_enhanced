# RIV Truth and Contract Hardening Continuation — 2026-07-12

## Scope
Implemented the first execution increments from the deep source plan:

1. Remove synthetic indicator serving from Raster production routes.
2. Prevent prescriptions from unqualified/non-real indicator products.
3. Remove the direct Sentinel-Hub spectral-compute exception.
4. Reconcile indicators-service runtime identity across app, Docker, Compose, and CI.
5. Add executable production-truth guards and focused regression tests.

## Changes

### Raster truth closure
- `GET /v1/fields/{field_id}/indicator-grid` now returns HTTP 424 when no real COG-backed product can be resolved/read.
- `POST /v1/fields/{field_id}/prescription` now requires:
  - `real_data is True`
  - `source == raster-service`
  - `estimated is False`
  - `quality_gate_passed is True`
  - non-empty provenance
- Removed `synthetic_grid` from the production `indicator_grid.py` module.
- Added `scripts/ci/raster_production_truth_guard.py` using AST call inspection.

### Direct Sentinel path removal
- Replaced `sentinel_hub/vegetation_real.py` with a compatibility-only facade.
- The facade contains no evalscript, band math, or direct provider HTTP endpoint.
- Legacy `_fetch_sentinel_hub` import remains as a fail-closed shim.
- Ownership allowlist now contains only `services/raster-service`.

### Indicators contract reconciliation
- Standardized role as `contract-only` across:
  - service runtime
  - Dockerfile comments/health semantics
  - `docker-compose.v9.yml`
  - container contract guard
  - production honesty guard
- The service remains lightweight and infrastructure-free.
- Spectral compute remains rejected with HTTP 409.

### CI wiring
- Added the production truth guard to GitHub CI and runtime smoke.
- Updated stale tests to verify behavior rather than old textual markers.

## Verification

- Focused regression suite: **29 passed**
- Guards:
  - `riv_boundary_gate_ok`
  - `raster_production_truth_guard_ok`
  - `raster_validated_product_guard_ok`
  - `indicators_container_contract_guard_ok`
  - `production honesty guard passed`
- `py_compile`: passed for modified Python modules.

## Remaining execution plan

1. Clean and version the canonical indicator registry and aliases.
2. Add a root contract index and JSON Schema compatibility gate.
3. Replace remaining regex guards with AST/OpenAPI-aware checks and mutation tests.
4. Add an observation-bundle endpoint to reduce Vegetation fan-out.
5. Add durable product uniqueness/recovery in PostgreSQL.
6. Run real PostgreSQL/Redis/MinIO multi-worker staging certification.

---

## ملحق التكامل (أُضيف عند الدمج على الشجرة المُهبَطة — 2026-07-12)

قاعدة الحزمة `3b20e07`؛ دُمجت فوق دمج riv_brain_governance (ebd4494/0af1fd0). قرارات الدمج:

- **مأخوذ كما هو:** حذف `synthetic_grid` من وحدة الإنتاج + فشل `indicator-grid` المُغلَق 424
  بكود `RASTER_INDICATOR_PRODUCT_UNAVAILABLE` + اشتراطات الوصفة الحقيقيّة + façade
  `vegetation_real.py` بلا evalscript + توحيد هويّة indicators-service على contract-only
  (compose أيضاً) + حارس AST الجديد `raster_production_truth_guard.py` موصولاً بخطوة CI.
- **اختبارات قديمة حدّثتها على العقد الجديد (الحزمة غيّرت الكود دون اختباراته):**
  `test_clip_grid.py` قسم (هـ) كان يثبّت عقد المحاكاة المحذوف — صار يثبت 424؛
  `tests_v9/test_raster_validated_product_guard.py` كان يطلب توكن synthetic_grid
  في الحارس — صار يطلب توكن منع عودة المسار التركيبيّ.
- **تحقّق محلّيّ:** raster 233 ✓ · unit 2912 ✓ · منصّة 3715 ✓ · الحُرّاس الخمسة
  (production_truth/riv_boundary/honesty/container_contract/validated_product) ✓.
