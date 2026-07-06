# Raster main.py decomposition — Phase 19: worker main-free runtime

## الهدف
بعد المرحلة 18 أصبحت كل راوترات `services/raster-service/routers/*.py` مستقلة عن `main.py`.
هذه المرحلة نقلت نفس معيار الفصل إلى عامل backfill حتى لا يحمّل تطبيق FastAPI لمجرّد تشغيل عامل خلفي.

## التغييرات

### 1) `services/raster-service/backfill_scan_worker.py`
أزيل الاعتماد المباشر على:

```python
import main
main.*
```

واستُبدل باستيرادات مباشرة من الوحدات المفككة:

```text
raster_api_models
raster_backfill_scene_processing
raster_date_geo
raster_processing_runtime
raster_runtime_state
raster_security_context
raster_settings
scene_policy
stac_search
```

كما أضيفت تهيئة مستقلة لـ STAC داخل العامل عبر `ResilientStacClient` و `stac_search.configure(...)`، بحيث لا يحتاج العامل إلى استيراد `main.py` لتفعيل البحث.

### 2) حارس static جديد داخل الاختبار
تم توسيع:

```text
services/raster-service/test_router_no_main_import_static.py
```

ليتحقق من أن العمال الخلفيين الأساسيين لا يستوردون `main.py`:

```text
backfill_scan_worker.py
cache_invalidation_worker.py
```

### 3) حارس CI
تم توسيع:

```text
scripts/ci/raster_main_decomposition_gate.py
```

ليمنع رجوع أي من الراوترات أو العمال الخلفيين إلى:

```text
import main
from main import ...
main.*
```

## الحالة بعد المرحلة

```text
routers importing main: 0
core workers importing main: 0
main.py lines: 608
raster-service tests: 157 passed
```

## التحقق المنفذ

```bash
PYTHONPATH=services/raster-service python3 -m pytest -q services/raster-service
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
python3 scripts/ci/raster_main_decomposition_gate.py
python3 scripts/ci/minio_s3_contract_gate.py
python3 scripts/ci/compose_env_contract_gate.py
python3 scripts/ci/backfill_ui_sync_gate.py
python3 scripts/ci/runtime_readiness_contract_gate.py
python3 scripts/ci/mobile_contract_gate.py
python3 scripts/ci/public_weather_route_governance_gate.py
python3 scripts/ci/service_port_gate.py
python3 scripts/ci/nginx_compose_dns_gate.py
python3 scripts/ci/v9_gpu_contract_gate.py
python3 scripts/ci/runtime_contract_gate.py
```

## النتائج

```text
157 passed
raster-main-decomposition contract: OK (main.py lines=608, modules=22)
MinIO/S3 contract: OK
compose-env contract: OK
backfill-ui-sync contract: OK
runtime-readiness contract: OK
mobile contract: OK
public-weather-route-governance contract: OK
service-port-gate: PASS
nginx-compose-dns-gate: PASS
v9-gpu-contract-gate: PASS
runtime-contract-gate: PASS
```

## ملاحظة
ملف `.github/workflows/ci.yml` غير موجود داخل هذه النسخة المرحلية؛ لذلك تم فحص ملفات compose YAML الموجودة فقط.
