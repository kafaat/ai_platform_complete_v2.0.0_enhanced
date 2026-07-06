# Raster Main Decomposition — Phase 20

Date: 2026-07-06

## الهدف

بعد إنهاء اعتماد الراوترات والعمال الأساسية على `main.py` في المراحل السابقة، هذه المرحلة توسّع الحماية إلى كامل ملفات الإنتاج داخل `services/raster-service`.

القاعدة الجديدة:

- يُسمح لـ `main.py` أن يبقى واجهة تشغيل FastAPI وواجهة توافق للاختبارات.
- لا يُسمح لأي ملف إنتاجي آخر داخل `raster-service` أن يستورد `main` أو يستخدم `main.*`.
- الاختبارات يمكنها الاستمرار في استيراد `main` للتحقق من التطبيق والواجهات التوافقية.

## الملفات المعدّلة

### 1. `services/raster-service/test_router_no_main_import_static.py`

أضيف اختبار جديد:

```python
 test_raster_production_modules_do_not_import_or_use_main_module
```

يفحص كل ملفات الإنتاج تحت `services/raster-service/**/*.py` مع استثناء:

- `main.py`
- ملفات `test_*.py`
- `__pycache__`

ويمنع:

- `import main`
- `from main import ...`
- `main.*`

### 2. `scripts/ci/raster_main_decomposition_gate.py`

تم توسيع الحارس من فحص الراوترات والعمال المحددين فقط إلى فحص كل ملفات الإنتاج داخل `services/raster-service`.

الحارس الآن يضمن أن تفكيك `main.py` لا يتراجع في أي ملف runtime جديد لاحقاً.

### 3. `services/raster-service/router_registry.py`

تحديث تعليق معماري قديم كان يقول إن الراوترات تستورد من `main`. التعليق صار يعكس الوضع الحالي:

- الراوترات تستورد الوحدات المفككة مباشرة.
- `main.py` مسؤول عن ربط FastAPI فقط.

### 4. `services/raster-service/main.py`

تحديث تعليق stale حول تسجيل الراوترات، بدون تغيير سلوكي.

## نتيجة الفحص البنيوي

```text
production raster files scanned: 66
production files importing/using main.py: 0
main.py lines: 608
```

## التحقق المنفذ

```bash
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
PYTHONPATH=services/raster-service python3 -m pytest -q services/raster-service
```

النتيجة:

```text
158 passed
```

الحراس:

```text
raster-main-decomposition contract: OK (main.py lines=608, modules=22)
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

YAML:

```text
YAML SKIP missing: .github/workflows/ci.yml
YAML OK: docker-compose.v9.yml
YAML OK: docker-compose.fixed.yml
YAML OK: docker-compose.v9.gpu.yml
```

## ملاحظة

ملف `.github/workflows/ci.yml` غير موجود في هذه النسخة المرحلية، لذلك لم يتم التحقق منه. هذا لا يؤثر على اختبارات raster-service أو الحراس المحلية الموجودة.

## الحالة بعد phase20

- `main.py` ما زال 608 أسطر.
- كل الراوترات لا تعتمد على `main`.
- العمال الأساسية لا تعتمد على `main`.
- كل ملفات الإنتاج داخل `raster-service` لا تعتمد على `main`.
- `main.py` أصبح فعلياً application/bootstrap facade مع compatibility re-exports للاختبارات والانتقال المرحلي.
