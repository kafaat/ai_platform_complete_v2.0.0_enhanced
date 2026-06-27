# Phase 20 — Runtime Worker Side-Effect Hardening

## الهدف

إغلاق فجوة أن بعض مسارات Phase 9-12 كانت تملك جداول runtime وworkers، لكن بعض العمال كانوا يسجلون `completed`/`blocked` بمنطق مبسط بدون عقد واضح للـ side effects الخارجية.

## التغييرات

- إضافة `shared/runtime_worker_contracts.py` كعقد deterministic/fail-closed لكل worker.
- تقوية `services/sahool-platform/api/phase_runtime_workers.py` حتى لا يعتبر أي side effect مكتملاً بدون backend/ack خارجي.
- Plugin worker:
  - لا يضع `completed` عند السماح فقط.
  - يطلب `PLUGIN_EXECUTION_ENABLED=true` و`PLUGIN_EXECUTOR_URL`.
  - يضع التنفيذ في `queued` وينشر `plugin.execution.requested` عبر NATS عند توفر البنية.
  - ينشر أحداث `marketplace_plugin_runtime_events` بدلاً من تركها pending.
- Model worker:
  - يتحقق من `artifact_uri` و`artifact_hash` قبل promotion.
  - يتطلب `MODEL_SERVING_ENABLED=true` و`MODEL_SERVING_BACKEND_URL`.
  - يضع serving alias في `pending_external_ack` بدلاً من إقرار نهائي وهمي.
  - يعالج rollback عبر `MODEL_SERVING_ROLLBACK_ENABLED` وbackend URL.
- Actuator worker:
  - يقرأ `ACTUATOR_ADAPTER_CONFIG_JSON`.
  - لا يعطي `physical_effect=true` قبل ACK.
  - ينتقل إلى `waiting_ack` فقط عند وجود adapter real ومفعّل.
- Outbox worker:
  - أصبح يستخدم عقد outbox واضحاً ويفشل إلى retry/dead_letter عند غياب NATS.

## ما بقي خارج النطاق

- لا ينفذ plugin code داخل sandbox حقيقي داخل هذه الحزمة؛ يحتاج plugin runner مستقل.
- لا يشغل model server فعلي؛ يطلب backend serving خارجي أو خدمة لاحقة.
- لا يرسل Modbus/MQTT فعلياً من worker بدون adapter config وack channel.

## التحقق

- Tests added:
  - `tests/runtime/test_phase20_worker_side_effect_contracts.py`
  - `tests/runtime/test_phase20_worker_static_contracts.py`
- Release manifest updated to include:
  - `shared/runtime_worker_contracts.py`
  - `PHASE20_RUNTIME_WORKER_SIDE_EFFECTS_REPORT_20260626.md`

## نتيجة السلامة

كل worker أصبح fail-closed عند غياب backend خارجي. لا يوجد مسار جديد يعلن اكتمال تنفيذ فيزيائي أو plugin/model side-effect بدون طلب خارجي قابل للتتبع.
