# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-06-27 · رأس `main`: `e09ce27` (#497).
> **الحالة:** اكتمل **تكامل لقطة الأرشيف بالكامل** (٤ مراحل / ٥ طلبات دمج حسب المجال) فوق إصلاحات
> تأسيسيّة (CLAUDE.md · Phase 22 RLS · تفكيك main.py). كلّ بوّابات CI خضراء. لم يُضعَّف أيّ حارس —
> أُصلحت أخطاء الأرشيف الحقيقيّة (تأمين phase9-12، استعادة ci.yml، توافقيّة compat_gateway…).

## إنجازات هذه الجلسة (2026-06-27)

- **CLAUDE.md (#486):** دليل مساهمة شامل للوكلاء (بنية + سير عمل + اتّفاقات + بوّابات CI الـ١١).
- **Phase 22 — RLS WITH CHECK + توحيد الجلسة (#487، v122):** backfill مدفوع بالكتالوج +
  `sahool_effective_tenant_id()`؛ بوّابة `validate_rls_write_policies` في Security Scan.
- **تفكيك main.py (#491):** تسجيل تلقائيّ للراوترات (`pkgutil.iter_modules`) بدل ~١٤٢ تضميناً يدويّاً.
- **تكامل الأرشيف (#488-#497):** بيانات المزرعة v100-105 · runtime 9-12 v106-113 · GIS سحابيّ v114-121،
  ثمّ الدفعة ٤ مقسَّمة: scripts/security · raster · frontend · mobile · الربط النهائيّ.
- **تأمين phase9-12 (#497):** ٦٤ نقطة POST بلا مصادقة ⇒ حارس توكن خدمة على مستوى الراوتر عبر
  `api/service_token_auth.py` (تفادي دورة الاستيراد) + تعليم حارس auth-coverage اكتشاف تبعيّات الراوتر.

## ملخّص الجلسات السابقة (محفوظ)

- **Actuator Safety Hardening** — `ACTUATOR_MODE` الافتراضيّ = `simulation`؛ كلّ مسارات dispatch/automation/manual محروسة بأعلام OFF.
- **Field/Raster Flow** — رسم الحقل/المحوري geodesic، pivot params، timeline بعد restart، tile date/indicator، legend، raster bleed.
- **ADR-0001 ERP Provider** — `ERP_PROVIDER=odoo|erpnext|none`؛ Odoo لم يعد إلزاميّاً.
- **Farm Operations Ledger + Budget/Costing + Closed Loop** — سجلات رقابيّة خلف أعلام OFF؛ ERP/Inventory إسقاط لا كتابة.
- **Sahool Brain Forensic Tests** — `tests_v9/test_sahool_brain_forensic.py`.

## أعلى الأعمال المتبقية

| الأولوية | البند | الحالة |
|---|---|---|
| P1 | تفعيل phase9-12 حيّاً (يحتاج `SAHOOL_AGENT_TOKEN` + خدمات runtime) | منفَّذ-محروس، env-unverified |
| P1 | Daily Farm Log UI + Mobile Offline Forms | غير منفّذ |
| P1 | Inventory/ERP writes الحقيقيّة | مؤجّلة؛ projection-only |
| P2 | معايرة Cost Intelligence على بيانات مواسم فعليّة | يحتاج بيانات |
| P2 | SAM2/MAP-QA · سير production-gates: runtime-stack-e2e-chaos (workflow_dispatch) | implemented-gated-but-env-unverified |
| P2 | بنود راستر مؤجّلة: `map_runtime_chain`/`security_visual` أُسقطتا (تعارض راستر #484) | deferred by design |

## حالة التحقّق الأخيرة (2026-06-27)

```text
CI على PR #497 (رأس 7f803a1 → دُمج e09ce27):
  ci.yml — ١١ وظيفة: خضراء (Unit/Platform/Security/Integration/E2E/Flutter/Lint/Compose/Inspector/Structural).
  sahool-production-gates.yml — ٨ وظائف: خضراء؛ runtime-stack-e2e-chaos: متخطّاة (workflow_dispatch).
محليّاً: Platform Unit Tests 2873 passed (أخطاء التجميع المحلّيّة من تبعيّات تُثبَّت في CI)؛
  guards: router-decomp · endpoint-auth-coverage · mutating-authn · compose-security · raster-auth — كلّها خضراء؛
  ruff check/format نظيف؛ بصمة الإصدار ٢٤٨٤ بلا تسرّب ملفّات غير مُتعقَّبة.
```
