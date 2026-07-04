# RASTER_FIELD_ID_AND_MASK_PERSISTENCE_FIX_20260704

## السبب الجذري من السجلّ

السجلّ أظهر أن CDSE/Sentinel Hub processing نجح فعلياً:

- `HTTP/1.1 200 OK`
- `job ... completed → layer ...`
- `5 نجح، 0 فشل`

لكن persistence كان يتخطّى الكتابة:

```text
raster_assets persist skipped: missing/invalid field_id='fld_b1c8ff30d02c'
```

السبب: `raster-service` كان يتحقق من `field_id` كـ UUID فقط، بينما عقد SAHOOL الحقيقي يستخدم معرفات نصية للحقول مثل `fld_demo_001` و `fld_b1c8ff30d02c`. جدول `raster_assets.field_id` في `migrations/v14_imagery_storage.sql` هو `VARCHAR(50)` وليس UUID، و`v18_entity_ids_text.sql` يثبت أن معرفات الحقول نصية.

## الإصلاحات

### 1. قبول field_id النصي في raster_assets persistence

تعديل:

- `services/raster-service/main.py`
- `services/raster-service/db_persist.py`

أضيفت دوال تحقق مخصصة لحقل `field_id` النصي:

- تقبل: `fld_b1c8ff30d02c`, `fld_demo_001`, و UUIDs القديمة.
- ترفض: القيم الفارغة، المسافات فقط، slash/path-like IDs، والقيم الأطول من `VARCHAR(50)`.
- بقي `tenant_id` مقيداً بـ UUID كما هو، لأن `tenant_id` فعلاً UUID في الجدول.

### 2. إصلاح قناع COG الداخلي في البلاطات والمصغرات

أثناء تشغيل كامل اختبارات raster-service ظهر خلل أعمق: `test_tiles.py` كان يفشل بسبب أن `rasterio.warp.reproject` قد يتجاهل mask band عندما يكون هناك `src_nodata` أيضاً، فتظهر بكسلات finite مثل `0.0` خارج القناع كأنها صالحة.

تعديل:

- `services/raster-service/tile_render.py`

أضيفت إعادة إسقاط صريحة لقناع Dataset mask ثم تطبيقه على مصفوفة القيمة بعد warp:

- `render_tile_png(...)`
- `render_cog_thumbnail_png(...)`

هذا يمنع ظهور شرائط داكنة فوق الحقل، ويضمن أن نصف القناع في thumbnail يصبح شفافاً.

### 3. اختبار regression جديد

أضيف:

- `services/raster-service/test_raster_assets_text_field_id.py`

يثبت أن:

- `fld_b1c8ff30d02c` مقبول.
- `fld_demo_001` مقبول.
- UUID قديم ما زال مقبولاً.
- القيم غير الآمنة أو الطويلة مرفوضة.
- `main.py` و `db_persist.py` يستخدمان عقد field_id النصي نفسه.

## التحقق المنفذ

```bash
cd services/raster-service
python -m pytest -q
```

النتيجة:

```text
106 passed
```

Frontend/build/gates:

```bash
cd frontend
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npm run typecheck
npm run build:docker
```

النتيجة:

```text
npm audit: 0 vulnerabilities
typecheck: passed
build:docker: passed
```

Coverage gates:

```bash
python3 scripts/ci/service_feature_ui_contract_gate.py
python3 scripts/ci/endpoint_ui_coverage_gate.py
python -m pytest -q tests_v9/test_coverage_gates_ci_wiring.py tests_v9/test_endpoint_ui_coverage_gate.py
```

النتيجة:

```text
service-feature-ui-contract-gate: PASS (26/26)
endpoint-ui-coverage-gate: PASS — 102 endpoint
coverage gate tests: 4 passed
```

## الأثر المتوقع على السجلّ بعد الإصلاح

بدلاً من:

```text
raster_assets persist skipped: missing/invalid field_id='fld_b1c8ff30d02c'
```

يجب أن يحاول النظام الإدراج في `raster_assets`. إذا كانت قاعدة البيانات/الجدول/RLS غير متاحة سيظهر سبب DB صريح، وليس رفضاً خاطئاً للـ `field_id`.

## المتبقي

لم يتم تشغيل Docker Compose كامل أو اختبار حي ضد Postgres فعلي. الاختبار التالي الموصى به:

1. شغّل مسار `/api/v1/fields/{field_id}/imagery/backfill` لحقل `fld_...`.
2. تأكد أن صفاً جديداً يظهر في `raster_assets`.
3. أعد تشغيل `raster-service`.
4. تأكد أن timeline/tilejson يعيد الترطيب من `raster_assets`.
