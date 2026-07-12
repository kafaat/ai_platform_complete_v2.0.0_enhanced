# Water Deficit Governed Bridge — Completion Report

Date: 2026-07-12

## Implemented

- Added `api/water_decision_bridge.py` as the single governed bridge from canonical `water_ledger` deficit to Decision-Service.
- Default-off gates:
  - `WATER_DEFICIT_DECISION_BRIDGE_ENABLED=false`
  - `WATER_DEFICIT_AUTO_EXECUTION_ENABLED=false`
- Deterministic decision, lineage, review, plan, authorization, request, and command idempotency keys.
- Threshold gate (`WATER_DEFICIT_DECISION_THRESHOLD_MM`, default 10 mm).
- Fail-closed when Decision-Service is not authoritative/persisted.
- Human-review path by default; optional explicit policy auto-approval path.
- Auto-execution requires an explicit target ID and valid target type.
- Full governed chain supported:
  `water_ledger -> candidate -> review -> execution plan -> authorization -> execution request -> actuator consumer`.
- Canonical `events` timeline write using a tenant/field/day dedup key.
- Added `decision.water_deficit` as an operation category in the unified timeline.
- Added compose configuration for all bridge controls.

## Verification

- Water bridge / ledger / timeline focused tests: `17 passed`.
- Actuator safety / dedup / dispatch tests: `30 passed, 1 skipped`.
- Python compilation passed for all modified Python modules.

## Operational activation order

1. Enable Decision-Service SoR on real PostgreSQL.
2. Enable `WATER_LEDGER_AUTO_ENABLED=true`.
3. Enable `WATER_DEFICIT_DECISION_BRIDGE_ENABLED=true` with auto execution still false.
4. Verify candidates and timeline events.
5. Configure a staging target and enable `WATER_DEFICIT_AUTO_EXECUTION_ENABLED=true` in simulation only.
6. Enable the Actuator consumer and verify claim/receipt/outcome lifecycle.

## Remaining external certification

Real PostgreSQL/container E2E and physical-device staging are environment certifications, not missing code. They were not executable in this isolated environment.

---

## ملحق التكامل (أُضيف عند الإنزال — منهجيّة «التكامل على الشكل المُنزَل»)

- **علّة مُسلَّمة أُصلحت عند الدمج:** كتابة حدث الخطّ الزمنيّ كانت تُلقي `entity_id` بـ`$2::uuid`
  بينما `events.entity_id` **نصّيّ منذ ترحيل v18** (معرّفات الحقول `fld_…` ليست UUIDs) —
  مع تفعيل الجسر كان الإدراج سيفشل لكلّ حقل. أُصلح إلى `::text` (يطابق الكاتب القانونيّ
  `event_bus.emit_event`). فهرس dedup الجزئيّ (`WHERE dedup_key IS NOT NULL`) تحقّقتُ من
  مطابقته لبند `ON CONFLICT` المُسلَّم، و`source='scheduler'` ضمن قيود CHECK.
- **قاعدة الحزمة بائتة (على لقطة 3b20e07+مراجعة):** أربعة ملفّات فيها نسخ أقدم من قمّتي
  (إصلاح mypy في logging_config، تسجيل allowlist في اختبار العقود، إصلاح ruff في actuator
  main.py، سجلّ العقل والمانيفستات) — أُخذت **دلتاها الحقيقيّة فقط** ولم تُسترجَع البائتة.
- **تسجيلات الحُرّاس** (تمنعها الحزمة عادة ولا تعرفها): الوحدة الجديدة في baseline نموّ
  المنصّة بتبرير، واستعلام `events` في العامل ضمن allowlist تدقيق الاستئجار (GUC مضبوط
  لكلّ حقل + tenant_id صريح + dedup_key).
- **الاتّساق مع القيود المُعلَنة مُتحقَّق منه:** default-off مزدوج، حتميّة المفاتيح على
  (tenant, field, ledger_date, policy_version)، fail-closed عند غير-الآمِر، المراجعة
  البشريّة افتراضاً، والتنفيذ الآليّ يتطلّب هدفاً صريحاً. **حدّ معروف:** تحت
  `DECISION_REQUIRE_AGRONOMIC_CONTEXT` الصارم سيُرفض مرشّح الجسر (بلا سياق زراعيّ
  مركَّب) — رفض مقصود fail-closed؛ ربط الجسر بالـcomposer زيادة لاحقة إن فُعّل الوضع الصارم.
- التحقّق عند الدمج: جسر 4/4 + بطاريّة المنصّة 3714 + تدقيق الاستئجار + unit 2912 + ruff
  + compose/env gates. برهان PG/E2E الحيّ يبقى شهادة بيئة كما أقرّ التقرير.
