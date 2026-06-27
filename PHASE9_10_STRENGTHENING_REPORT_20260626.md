# SAHOOL Phase 9–10 Runtime Strengthening Report — 2026-06-26

## الهدف
تقوية Phase 9 و Phase 10 بعد Runtime Activation Patch بتحويلهما من تفعيل API/persistence أولي إلى Runtime أكثر صلابة وقابلية للتتبع، مع منع رجوع فجوات RLS/outbox/feature-store.

## ما تم تنفيذه

### Phase 9 — Autonomous Farm OS
- إضافة `runtime_event_outbox` كمخزن أحداث موحد لخطط التنفيذ ودورات الاستقلالية.
- ربط `/v1/phase9/autonomy/plan` بإصدار حدث `phase9.execution_plan.created`.
- ربط `/v1/phase9/autonomy/cycle` بإصدار حدث `phase9.autonomy_cycle.completed`.
- إضافة `persist_phase9_feature_batch()` لتخزين مخرجات `feature_store_batch` في جدول `field_feature_store_candidate`.
- تقوية ربط RLS عبر `set_config('app.tenant_id', ...)` قبل الكتابة في الجلسة.
- الحفاظ على fail-soft عند غياب `db_pool` حتى تبقى اختبارات العقود المحلية خفيفة.

### Phase 10 — Continuous Learning AI
- إضافة `online_feature_values` كـ online feature table مبدئي بجانب manifests/training datasets.
- جعل `/v1/phase10/learning/dataset` يحتفظ بالـ records داخل dataset payload حتى يستطيع adapter تخزين online rows.
- إضافة `persist_phase10_learning_outputs()` لتخزين:
  - `model_lifecycle_decisions`
  - `online_learning_updates`
  - `scenario_runs`
- تحويل `/v1/phase10/learning/cycle` إلى async endpoint مع persistence adapter.
- تقوية RLS context قبل الكتابات متعددة المستأجرين.

### Migration
أضيف ملف:

```text
migrations/v106_phase9_10_runtime_strengthening.sql
```

ويحتوي على:
- `runtime_event_outbox`
- `online_feature_values`
- indexes للـ pending events والـ online feature lookup
- `ENABLE ROW LEVEL SECURITY`
- `FORCE ROW LEVEL SECURITY`
- policies مع `WITH CHECK`

وتم تسجيله في:

```text
migrations/MANIFEST.txt
```

### Tests
أضيف اختبار regression:

```text
tests/runtime/test_phase9_10_runtime_strengthening.py
tests_v9/test_phase9_10_runtime_strengthening.py
```

> النسخة داخل `tests/runtime` قابلة للتشغيل دون تحميل `tests_v9/conftest.py` الذي يحتاج `python-jose`.

## التحقق المنفذ

```text
20 passed
```

الأمر المستخدم:

```bash
PYTHONPATH=services/sahool-platform:. pytest -q \
  tests/runtime/test_phase9_10_runtime_strengthening.py \
  shared/test_autonomous_farm_os_phase9.py \
  shared/test_continuous_learning_phase10.py \
  services/sahool-platform/tests/test_phase9_autonomous_farm_os_api.py \
  services/sahool-platform/tests/test_phase10_continuous_learning_api.py
```

## ما بقي بعد هذه التقوية
- تشغيل migration فعلياً ضد PostgreSQL/PostGIS للتحقق من RLS والسياسات داخل DB حقيقي.
- إضافة publisher worker يقرأ `runtime_event_outbox` وينشر إلى NATS JetStream.
- ربط `actuator_command_outbox` بـ IoT Gateway/MQTT/Modbus/Pivot/Pump adapters.
- بناء offline feature store فعلي/Object storage وربطه بـ `training_datasets.object_uri`.
- إضافة model artifact store/serving runtime خارج contracts الحالية.
