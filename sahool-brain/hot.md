# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-06-24 · حزمة العمل المحليّة: `4942b69_sahool_brain_forensic_verified`.
> الحالة الحالية: **Farm Operations Ledger + Budget/Costing + Closed Loop Economic Projections** مضافة خلف أعلام OFF افتراضياً، وتمت إضافة/تشغيل تتبّع جنائي لعقل سهول: نواة الحقل، تحكيم الملوحة، D2 water-stress، محرك التوصية، provenance، وRBAC delivery. طبقة التنفيذ الفيزيائي ما زالت `implemented-gated-fail-safe`، وERP إسقاط اختياري لا كتابة فعلية.

## إنجازات الجلسات الأخيرة المؤكّدة

- **Actuator Safety Hardening** — `ACTUATOR_MODE` الافتراضي = `simulation`؛ لا real إلا بتعيين صريح، وكل مسارات dispatch/automation/manual محروسة بأعلام OFF افتراضياً.
- **Field/Raster Flow** — إصلاحات رسم الحقل والمحوري geodesic، حفظ pivot parameters، timeline بعد restart، tile date/indicator selection، legend في tilejson، واختبار raster bleed.
- **ADR-0001 ERP Provider** — `ERP_PROVIDER=odoo|erpnext|none` عبر `ERPProvider`، وOdoo لم يعد إلزامياً.
- **Farm Operations Ledger** — سجلات رقابية للأعمال اليومية والمياه والطاقة والمعدات والعمالة والمواد خلف `FEATURE_FARM_OPERATIONS_LEDGER`.
- **Budget/Costing/Variance/Profitability** — موازنة الموسم، بنود الموازنة، الإيرادات، التكاليف غير المباشرة، الانحرافات، الربحية، وتوصيات تكلفة تحفظية.
- **Closed Loop Economic Projections** — autowrite preview، inventory projection-only، ERP projection-only، economic snapshot اختياري، بلا كتابة Inventory/ERP/CanonicalFieldState افتراضياً.
- **Inspector Cleanup** — تحذير NATS المعروف `sahool.weather.field.overlay.completed` صار **declared future subject** داخل المفتّش، ونقاط public reference لم تعد WARN لأنها لا تمس قاعدة/مستأجر.
- **Sahool Brain Forensic Tests** — اختبار جديد `tests_v9/test_sahool_brain_forensic.py` يغطي: Salinity>Vigor arbitration، بوابة D2b (AWF+confidence+NDMI/MSI)، حجب تناقضات الري، عقود blocked/limited للتوصيات، وdelivery pipeline مع provenance/RBAC. أُصلح تمرير `issue_type` داخل `full_delivery_pipeline` إلى `enrich_with_context`.

## حالة التحقق الأخيرة

```text
PYTHONPATH=services/sahool-platform pytest -q \
  tests_v9/test_sahool_brain_forensic.py \
  services/sahool-platform/tests/test_agronomic_state_engine.py \
  services/sahool-platform/tests/test_recommendation_engine.py \
  services/sahool-platform/tests/test_decision_engine.py \
  services/sahool-platform/tests/test_recommendation_bridge.py \
  tests_v9/test_canonical_water_stress.py
→ 95 passed

PYTHONPATH=services/sahool-platform python import sweep core+api
→ 480 OK / 0 FAIL

python -m compileall -q services/sahool-platform/core/recommendation_bridge.py tests_v9/test_sahool_brain_forensic.py
→ passed

python tools/sahool_inspector.py
→ PASS كامل: RLS/router/NATS/authz/migrations بلا WARN/FAIL
```

## أعلى الأعمال المتبقية

| الأولوية | البند | الحالة |
|---|---|---|
| ✅ | تشغيل فحوص حيّة Docker: DB/حقول/مزارع | **مؤكَّد 2026-06-25** — POST/GET /api/v1/fields 201/200 OK |
| P1 | Daily Farm Log UI + Mobile Offline Forms | غير منفّذ |
| P1 | Inventory/ERP writes الحقيقية | مؤجلة؛ حالياً projection-only |
| P2 | معايرة Cost Intelligence على بيانات مواسم فعلية | يحتاج بيانات |
| P2 | SAM2/MAP-QA | implemented-gated-but-env-unverified |

## إصلاحات جلسة 2026-06-25

- **`planting_date` column**: `migrations/v103_fields_planting_date.sql` — غياب العمود كان يُسبّب 503 عند إنشاء أيّ حقل.
- **tenant_query_audit Windows fix**: `scripts/tenant_query_audit.py:130` — path separator normalization؛ اختبار CI `test_no_unclassified_raw_tenant_queries` أصبح ✅.
- **Unit tests**: **1866 passed, 0 failed** (coverage 48.41%).
- **ReplayMapPage.test.tsx** — 6/6 ✅: إصلاح timezone bug (span date-only strings = UTC-safe).
- **sahool-migrate seed idempotency**: `migrations/init_v8.sql:478` — `ON CONFLICT (field_id, tenant_id)` → `ON CONFLICT (field_id)` يُصلح فشل إعادة الإقلاع على DB موجودة (NULL≠NULL في UNIQUE المركّب).
