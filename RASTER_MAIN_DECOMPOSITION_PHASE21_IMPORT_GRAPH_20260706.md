# Raster Main Decomposition — Phase 21

Date: 2026-07-06

## الهدف

بعد أن أصبحت كل الراوترات والعمال الأساسية لا تعتمد على `main.py`، أُضيفت في هذه المرحلة شبكة أمان أوسع لفحص import graph داخل `services/raster-service` بالكامل.

القواعد الجديدة:

- `main.py` يبقى application/bootstrap facade فقط.
- لا يُسمح لأي ملف إنتاجي داخل `services/raster-service`، باستثناء `main.py` نفسه، أن يستورد `main` أو يستخدم `main.*`.
- لا توجد cycles بين وحدات الإنتاج المحلية.
- وحدات core/runtime/helper لا تستورد وحدات `routers.*`؛ اتجاه الاعتماد يجب أن يبقى: router → runtime/helper، وليس العكس.

## الملفات المضافة

### `scripts/ci/raster_import_graph_gate.py`

حارس AST مستقل لا يستورد التطبيق ولا يحتاج GDAL/rasterio. يفحص:

- ملفات الإنتاج تحت `services/raster-service/**/*.py`.
- منع `import main` / `from main import ...` / `main.*` خارج `main.py`.
- local import graph cycles.
- منع اعتماد core modules على HTTP routers.

### `services/raster-service/test_raster_import_graph_static.py`

اختبار ثابت يحمّل الحارس ويفحص نفس القواعد ضمن suite الخاصة بـ `raster-service`.

## النتيجة البنيوية

```text
production modules scanned: 67
local import edges: 159
main.py runtime dependents outside main.py: 0
local import cycles: 0
core -> router imports: 0
main.py lines: 608
```

## التحقق المنفذ

```bash
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
PYTHONPATH=services/raster-service python3 -m pytest -q services/raster-service
```

النتيجة:

```text
159 passed
```

الحراس:

```text
raster-main-decomposition contract: OK (main.py lines=608, modules=22)
raster-import-graph gate: OK (modules=67, local_edges=159)
MinIO/S3 contract: OK
compose-env contract: OK
backfill-ui-sync contract: OK
runtime-readiness contract: OK
mobile contract gate: OK
public-weather-route-governance contract: OK
service-port-gate: PASS
nginx-compose-dns-gate: PASS
v9-gpu-contract-gate: PASS
runtime-contract-gate: PASS
```

ملاحظات:

- `mobile_contract_gate` ما زال يعطي نفس التحذيرات غير القاتلة: `pubspec.lock` و `android/` و `ios/` غير موجودة.
- ملف `.github/workflows/ci.yml` غير موجود في هذه النسخة المرحلية؛ تم فحص ملفات compose YAML الموجودة ونجحت.

## الحالة بعد phase21

- `main.py` لم يعد مركز اعتماد runtime.
- الراوترات لا تعتمد على `main.py`.
- العمال الأساسية لا تعتمد على `main.py`.
- كل ملفات الإنتاج داخل `raster-service` خالية من import/use لـ `main.py`.
- import graph المحلي acyclic ومحكوم بحارس CI جديد.
