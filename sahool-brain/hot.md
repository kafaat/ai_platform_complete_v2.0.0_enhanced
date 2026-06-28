# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-06-28 · رأس `main`: `305eeeb`.
> **الحالة:** بعد إصلاح RLS-معاملة (#504): **إصلاح عرض تراكب المؤشّر داخل الحقول (#506)** +
> **تدقيق خارجيّ مُتحقَّق منه نقديّاً (#507)** + **تفكيك تدريجيّ واسع للملفّات الضخمة (#508→#524)**
> + **قفل تبعيّات قابل لإعادة الإنتاج مع استهلاك Docker (#520/#521)**.
> الجاهزيّة الكوديّة/الساكنة/CI = **GO**؛ الاعتماد الإنتاجيّ الكامل = **NO-GO معلّق** حتى تُنفّذ Ops
> أدلّة البيئة الحيّة (smoke/env_doctor/soak) — موثَّق في `FINAL_PRODUCTION_READINESS_REPORT.md`.
>
> **دورة 2026-06-28 (أ) — إصلاح التراكب + التدقيق:** #506 (`4e87e0e`) السبب الجذريّ لاختفاء تراكب
> المؤشّر = غياب `SAHOOL_AGENT_TOKEN` في حاوية المنصّة (فحصته 3 وكلاء استكشاف متوازية) + راوتر تمرير
> `field_imagery_backfill` يحقن التوكن والهندسة · #507 (`7b17133`) تحقّق نقديّ من تقرير تدقيق خارجيّ
> ثمّ تطبيق المؤكَّد فقط (محاذاة MANIFEST/.env-test + بداية أداة قفل التبعيّات).
>
> **دورة 2026-06-28 (ب) — التفكيك التدريجيّ:** raster-service/main.py (#508 نماذج · #509 شبكة أمان CI
> لاختبارات الراستر · #510 مساعِدات نقيّة) · fields.py (#511 نماذج · #515 منطق نقيّ) · api.ts
> (#512 عملاء · #513 صور · #514 mocks · #519 vegetation/weather/soil · #524 fields/account) ·
> useApi.ts (#516 طقس/تربة · #522 معايرة) · auth (#517 نماذج · #523 mailer). **سلوك محفوظ بالكامل**
> (إعادة تصدير/barrel)؛ كلّ تفكيك يبقي الحُرّاس النصّيّة خضراء (تُحدَّث لتقرأ الموضع الجديد لا تُضعَّف).
>
> **دورة 2026-06-28 (ج) — قفل التبعيّات:** #520 (`61dba5c`) أقفال `*.lock` مُلتزَمة (حلّ عابر +
> تجزئات) + بوّابة CI «Dependency Lock Drift» + إصلاح علّة انجراف زائف في `lock.sh` · #521 (`9f8a1e1`)
> صور Docker (auth/platform/guardrails) تُثبّت من الأقفال بـ`--require-hashes` + محاذاة `PY_TARGET=3.11`
> (مطابقة لصور py3.11). **مؤجَّل بصدق:** تحقّق ببناء صور فعليّ (تحقَّق عبر venv 3.11 فقط).
>
> **ما تبقّى تشغيليّ بحت (مالك Ops/SRE، لا كود):** smoke ضدّ stack حقيقيّ · env_doctor/runtime_doctor
> على staging · soak ٢٤س→٧أ→١٤أ · توقيعات الاعتماد · **تأكيد حيّ لإصلاح #506/#504 تحت `sahool_app`**.

## إنجازات هذه الجلسة (2026-06-28)

- **إصلاح تراكب المؤشّر (#506 `4e87e0e`):** السبب الجذريّ لمشكلة عرض الصور الجوّيّة/الخريطة/المؤشّر داخل
  الحقول = حاوية `sahool-platform` تفتقر `SAHOOL_AGENT_TOKEN` فيفشل تمرير الصور للراستر؛ أُضيف للمتغيّرات
  (`docker-compose.v9.yml`) + راوتر تمرير `field_imagery_backfill` (يحقن `X-Agent-Token` + هندسة الحقل).
- **تدقيق خارجيّ مُتحقَّق منه (#507 `7e6fa25`):** فحص نقديّ لكلّ ادّعاء مقابل الكود؛ طُبِّق المؤكَّد فقط
  (محاذاة انجراف MANIFEST/.env-test + بداية `scripts/deps/lock.sh`)، ورُفِض غير المؤكَّد بصدق.
- **تفكيك تدريجيّ (#508→#524):** 14 PR سلوك-محفوظ تفكّك raster-service/main.py · fields.py · api.ts
  (3688→~3081 سطراً) · useApi.ts (1793→1660) · auth/main.py (1654→1519) — مع شبكة أمان CI جديدة
  لاختبارات الراستر (#509) كانت غائبة قبل أيّ تفكيك عميق.
- **قفل التبعيّات (#520/#521):** أقفال مُجزّأة + بوّابة انجراف CI + استهلاك Docker بـ`--require-hashes`.
- **النمط التشغيليّ:** 4 وكلاء متوازيين في عُزلة worktree للدفعة الأخيرة (#521/#522/#523/#524)؛ دمج
  متسلسل مرتَّب مع إعادة توليف لحلّ تعارض حزمة الإصدار المتقلّبة.

## إنجازات جلسة 2026-06-27 (محفوظ)

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
