# SAHOOL Phase 9 — Autonomous Farm OS Runtime

## الهدف
تحويل دورة القرار من `recommend → approve` إلى دورة مغلقة آمنة:

```text
observe → analyze → recommend → approve/safety-gate → dispatch → verify → learn
```

## ما تم تنفيذه

- `shared/autonomous_farm_os_phase9.py`
  - safety gates fail-closed.
  - closed-loop execution plan.
  - actuator command outbox contracts with idempotency keys.
  - execution verification.
  - feature store candidate records.
  - model registry/champion promotion.
  - deterministic experiment assignment.
  - full Phase 9 autonomy cycle runner.

- `services/sahool-platform/api/phase9_autonomous_farm_os.py`
  - `/v1/phase9/autonomy/plan`
  - `/v1/phase9/autonomy/verify`
  - `/v1/phase9/autonomy/cycle`
  - `/v1/phase9/autonomy/models/register`
  - `/v1/phase9/autonomy/experiments/assign`

- `migrations/v118_phase9_autonomous_farm_os.sql`
  - autonomous execution plans.
  - actuator command outbox.
  - verification events.
  - feature store candidates.
  - model registry versions.
  - experiment assignments.

## حدود التنفيذ الحالية

هذا تنفيذ Runtime Contracts وDB schema وAPI، وليس تحكماً مباشراً بمعدات حقيقية. الربط التالي يجب أن يكون عبر:

- MQTT adapter.
- Modbus adapter.
- ISOBUS/ISO11783 adapter.
- LoRaWAN adapter.
- NATS outbox worker.

## سياسة الأمان

- Shadow mode لا يرسل أوامر.
- Human approval يتطلب `operator_approved`.
- Full autonomy ممنوع إلا عند `full_autonomy_enabled=true` للسياسة.
- أي telemetry offline أو manual override يمنع التنفيذ.
- كل command يحمل idempotency key لمنع التكرار.
