# ⚖️ سجلّ القرارات (Decisions Ledger)

> ثلاثة مستويات: ADRs الرسميّة + آليّة القرار الحيّة + قرارات الجلسة. كلّ قرار يحوي **سبباً** و
> **PR/SHA**.

## 1) ADRs الرسميّة

من [`../../docs/adr/`](../../docs/adr/) (فهرس: [`README.md`](../../docs/adr/README.md)):

- **ADR-0001** تجريد مزوّد ERP — [`0001-erp-provider-abstraction.md`](../../docs/adr/0001-erp-provider-abstraction.md)
- **ADR-0002** قاطع دائرة MCP — [`0002-circuit-breaker-mcp.md`](../../docs/adr/0002-circuit-breaker-mcp.md)
- **ADR-0003** سلسلة تفسير القرار — [`0003-explainability-lineage.md`](../../docs/adr/0003-explainability-lineage.md)

## 2) آليّة القرار الحيّة (في القاعدة)

- **API:** [`../../services/sahool-platform/api/routers/decision_record.py`](../../services/sahool-platform/api/routers/decision_record.py)
  — يُدِيم رأس القرار ونتيجته (`POST …/decision/record`، `POST …/outcome/record`،
  `GET …/decision/{id}/lineage`) ضمن معاملة + RLS + outbox. الصدق: لا يستبدل المنطق النقيّ؛
  `success`/`confidence` الناقصان ⇒ NULL لا تلفيق (`decision_record.py:17-19`).
- **الجداول:** `v78_decision_record.sql` (رأس القرار) + `v79_outcome_record.sql` (النتيجة) —
  انظر [`../schema/migrations.md`](../schema/migrations.md).

## 3) قرارات هذه الجلسة (#431 → #447)

SHAs من `git log --oneline origin/main`.

| PR | SHA | القرار + السبب (rationale) |
|---|---|---|
| #431 | `c7f4b4d` | تقوية سلامة الهندسة المكانيّة (v96): سجلّ مراجعات + إبطال كاش — يمنع كاشاً قديماً بعد تعديل الهندسة. |
| #432–#434 | `48b6ef6`/`e30c555`/`efe9c31` | طبقة GIS نحو FieldView + توافق React 19 (react-leaflet 5/zustand 5) + انتقال WebGL تدريجيّ — تحديث المنظومة المكانيّة بأقلّ كسر. |
| #435 | `980daf6` | إزالة volume filestore المتداخل في Odoo — كان يكسر تثبيت base بـ`PermissionError`. |
| #436 | `f011775` | مراجعة P0/P1 + إصلاحات إقلاع docker (وسيط MQTT، RLS التسجيل، healthchecks) — جعل `up` ذاتيّ التهيئة. |
| **#437** | `6714bc0` | **auth:** سياق admin على كلّ اكتساب اتّصال (`_acquire`) — العلاج الجذريّ لفشل RLS في التسجيل/الدخول (يكمّله v97). |
| #438/#439 | `aaa28b6`/`16ef19a` | تفعيل صور Sentinel الحقيقيّة تلقائيّاً عند إنشاء الحقل (بلا محاكاة) + خادم SAM2 GPU opt-in — صدق البيانات + GPU اختياريّ. |
| #440/#442 | `de40881`/`45fbbc6` | توحيد وكيل تطوير Vite مع بوّابة nginx — يُصلح `npm run dev` + رؤية تشخيصيّة (offline/معالجة الصور). |
| #441 | `d23eb6b` | سويت Playwright لبوّابة QA لـMapLibre/WebGL (9 خطوات) + وظيفة CI — تأكيد عرض الخرائط قبل الدمج. |
| #443 | `2456d2b` | دمج/انقسام الحقول **ذرّيّاً** عبر نقطتَي backend — سدّ خطر «البيانات الثلاثيّة» (حالة غير متّسقة عند الفشل الجزئيّ). |
| #444 | `9e00d0a` | تصحيح مسار سلسلة NDVI (404) في الموبايل + تقرير مراجعة عميقة. |
| #445 | `a7909e6` | مصدر المؤشّرات الصحيح + زرّ تحديث الأقمار + إدارة المزارع — تكافؤ ويب/موبايل. |
| #446 | `edfc19c` | ربط أقسام مساحة العمل (موسم/أنشطة/طقس/خطّ زمنيّ) بالخلفيّة القائمة — لا واجهات وهميّة. |
| #447 | `0023f57` | سمة داكنة رسميّة متّسقة (`AppTheme.dark`) — توحيد تجربة الموبايل. |

> ملاحظة: PRs #422–#430 (مراحل الواجهة، دبابيس الاستطلاع v94، الوصفات v95، تفعيل edge/soil) سبقت
> نطاق هذه الجلسة المركّز (#431→#447) لكنّها في نفس السلسلة — راجع `git log` للتفاصيل.

## 4) قرارات جلسة التوحيد والكنسنة (water/SSOT) (#456 → #468 + D2)

ذكاء المياه + توحيد `CanonicalFieldState` مصدراً وحيداً (Bundles A/B/D). التفاصيل الكاملة + الأسباب في
[`../log.md`](../log.md) (مداخل (ح)→(ش)) و[`strategy.md`](strategy.md). SHAs المعروفة من `git log origin/main`.

| PR | SHA | القرار + السبب (rationale) |
|---|---|---|
| #457–#465 | راجع log.md | توحيد ET0 (H4) + Dual-Kc + Kc-NDVI + etc-dual + Water Twin + Open-Meteo + عمق جذور Zr — إزالة تكرار حسابات المياه وتأسيس مدخلات FAO-56 موحّدة. |
| #464 | راجع log.md | **H5:** الملوحة اختياريّة pluggable + سياسة تفعيل تلقائيّ (`core/salinity_policy`) — مرونة بلا فرض، تُفعَّل عند تحليل مختبريّ موثوق (ECe>2/ECw>1.5، age<12شهر، confidence≥0.8). |
| #466 | راجع log.md | **Bundle D / D1:** حقن ET0/ETc الكنسيّين في `operational_truths` (إضافيّ محفوظ السلوك) — الحالة تحمل قيم المياه دون مسّ التحكيم. |
| #467 | `bc16209` | **Bundle D / D3:** قارئ كنسيّ `canonical_water` + كتلة `water` موحّدة يقرؤها المستهلكون من **مصدر واحد** — يُغلق فئة تناقضات ET0/ETc، لا يغيّر القرار. |
| #468 | `208454d` | **Bundle B:** توصيل ثقة حدّ الحقل المخزَّنة إلى الحالة القانونيّة عبر `canonical_boundary` + **تصعيد** `execution_mode→human_review` عند ثقة < 0.6 (نظير الملوحة) — يمنع تسرّب أخطاء الترسيم بصمت. |
| (D2 قرار) | — | **عتبة الإجهاد المائيّ (المستخدم 2026-06-23):** نموذج 4 مستويات؛ التصعيد للمراجعة حصراً عند `AWF≤0.2 ∧ depletion_confidence≥0.8 ∧ تأكيد طيفيّ` — «فيزياء+رصد»، نادر عالي الثقة (Dr≥RAW لا يُصعّد). [`water-stress-d2.md`](water-stress-d2.md). |
| #469 | `7c897ea` | **Bundle D / D2a:** كتلة `water_stress` كنسيّة (AWF + NORMAL/WATCH/CRITICAL) من `water_ledger`+TAW — **معلوماتيّ بلا تصعيد** (محفوظ السلوك). |
| **D2b** | فرع `claude/bundle-d2b-spectral-escalation` | **تفعيل تصعيد الإجهاد المائيّ خلف feature flag (default off):** هجرة v99 (NDMI/MSI على imagery) + خطّ الصور يحسبهما/يخزّنهما + `canonical_water_stress` يحسب `escalation_eligible` (critical ∧ conf≥0.8 ∧ تأكيد NDMI+MSI) + `field_state_projection` يطبّق `FEATURE_WATER_STRESS_ESCALATION` ⇒ `human_review` عند ON. السبب: تفعيل القرار المُقَرّ بأمان (مراقبة ميدانيّة أوّلاً، لا تغيير إنتاجيّ افتراضيّ). |

> **قرار العلم (D2b):** `FEATURE_WATER_STRESS_ESCALATION` **default OFF** (إطار «implemented-but-off-by-default»):
> الإشارة + الأهليّة معلوماتيّتان دائماً؛ `human_review` عند تفعيل العلم فقط، والكتلة تُعلن `disabled_reason`.
> اختباران يثبتان: OFF لا يُصعّد · ON يُصعّد. تفعيل العلم لمستأجرين/بيئات بعد مراقبة ميدانيّة.

## 5) إغلاقات إطار «implemented-but-off-by-default»

أوّل دفعة من إغلاق الفجوات المؤجَّلة كـ«موجودة لكن معطَّلة افتراضيّاً» (شرط: علم واضح · default off · إعلان
سبب التعطيل · اختبار off لا يكسر · اختبار opt-in يعمل). SAM2/MAP-QA تبقى `implemented-gated-but-env-unverified`.

| الإغلاق | العلم (default off) | القرار + السبب |
|---|---|---|
| **ETc-dual canonical** | `FEATURE_CANONICAL_ETC_DUAL` (#471، `b722b4c`) | الحالة الكنسيّة تحسب ETc بالنهج المزدوج `(Kcb·Ks+Ke)·ET0` عند التفعيل بدل single `Kc·ET0`. النواة: `et0_override` (يبقى ET0 مصدراً واحداً — SSOT/H4) + `soil_ece=None` (الملوحة off — H5). الإسقاط يبدّل `water.etc`+`etc_source`، ويتراجع single + `dual_inputs_unavailable` عند نقص المدخلات. OFF ⇒ لا تغيير إنتاجيّ. |
| **C5 عتبات NDVI** | `APPLY_NDVI_THRESHOLDS` (#472، `768c396`) | NDVI معلوماتيّ لا يحكم الصلاحيّة؛ الإغلاق **إعلانيّ**: `remote_sensing` يُعلن `calibration_status="insufficient_field_calibration"` (OFF/لا معايرة) صراحةً بدل الإبهام. **لا عتبات معايَرة في النظام ⇒ لا نختلقها** (صدق)؛ opt-in يقرأ مظروف بطاقة المحصول (غائب الآن). لا تغيير validity. يحوّل C5 من Open إلى Closed (gated, calibration absent). |
| **H2 ناشرو NATS** | `FEATURE_NATS_PUBLISHERS` (#473، `c9c70a7`) | اشتراكات NATS يتيمة؛ البنية موجودة (emit→outbox ذرّيّ + OutboxWorker→NATS). العلم يحرس **تشغيل الناشر فقط**: OFF (افتراضيّ) ⇒ الأحداث تبقى في outbox (`record_decision_only`، لا تُفقَد) + إعلان السجلّ؛ ON ⇒ تشغيل OutboxWorker (`publish_event`). التسجيل الذرّيّ مستقلّ عن العلم. **ON env-unverified** (يحتاج NATS حيّاً). الاشتراكات الخدميّة الـ8 تبقى يتيمة (خدماتها غير مُسلَّمة). |
| **C4/M1 push موبايل** | `FEATURE_MOBILE_PUSH` (#474، `2e08f65`) | الـpush مُنفَّذ ومحروس بقدرة FCM؛ الفجوة الفعليّة = إسقاط صامت عند تعطّل FCM. العلم (default off) + `push_decision` (send/record_only/skip) + `_record_push_fallback` يُدِيم إيصال `notification_delivery` (queued) بدل الإسقاط (`create_notification_record`). OFF ⇒ سجلّ احتياطيّ، لا فقد. **ON env-unverified** (FCM حيّ + tokens). M1 WebSocket منفَّذ أصلاً. |
| **Bundle C (مراجعة حالة)** | لا علم — توثيقيّ (فرع `claude/bundle-c-rd-status`) | **إغلاق توثيقيّ لا برمجيّ** (قرار المستخدم): لا تُختلَق أعلام لما لا وجود له. SAM2 closed (gated, env-unverified) · Field Embeddings/RAG closed (خدمات اختياريّة، لا مسار قرار بلا حراسة ⇒ لا `FEATURE_CONSERVATIVE_RAG`) · Multi-engine Ensemble open (concept-only؛ fusion.py للمؤشّرات شيء مختلف) · نماذج أساس not started · ISOXML deferred by design (#456). [`bundle-c-status.md`](bundle-c-status.md). |

> **اكتمل سحب الإطار «implemented-but-off-by-default»:** 4 إغلاقات كود (#471 ETc-dual · #472 C5 · #473 H2 ·
> #474 C4/M1، كلّها default off + إعلان سبب + اختبار off/opt-in) + إغلاق حالة واحد (Bundle C، توثيقيّ).
> SAM2/MAP-QA تبقيان `implemented-gated-but-env-unverified` (لا production-ready).

## 6) تعميق الميزة: شفافيّة الثقة + النتائج + الاستدامة

| التحسين | الموضع | القرار + السبب |
|---|---|---|
| **Field Data Readiness Index** | `api/field_readiness.py` (#476، `486de6a`) | درجة جاهزيّة بيانات الحقل المُفسَّرة — **تجميع نقيّ** للإشارات القائمة (نضارة/ثقة/معايرة-C5/تغطية) في درجة واحدة + إرشاد عمليّ، **معلوماتيّ لا يمسّ القرار**، أوزان مُعلَنة لا معايَرة. السبب: يجعل صدق المنصّة (النقص المُعلَن) مرئيّاً وقابلاً للفعل — offline/explainable-first، مُلاءمة اليمن. مكمِّل لـ`data_readiness.py` (onboarding) لا مكرِّر. |
| **Water Use Efficiency (Outcome KPI)** | `api/water_efficiency.py` + `routers/water_ledger.py` (#477، `f01c468`) | كفاءة استخدام المياه لكلّ حقل على فترة (يخدم «خفض المياه») — **تجميع نقيّ** من دفتر المياه: WUE من **التوازن المائيّ** (ETc مقابل المُورَّد) + `over_application_mm` (ذراع الخفض). نقطة قراءة فقط، **لا هجرة، لا تغيير قرار**. الصدق: **الغلّة خارج النطاق** (لا حلقة غلّة-أرضيّة)؛ `needs_data`/`needs_irrigation_data` عند النقص (لا رقم مُضلِّل). يُعيد استخدام `water_ledger` (v98). |
| **Field Sustainability Index** | `api/field_sustainability.py` + `routers/reports.py` (#478، `4d58c1c`) | درجة استدامة مُفسَّرة لكلّ حقل عبر **تربة + مياه + مغذّيات** (بلا كربون) — **تجميع نقيّ** يُعيد استخدام `salinity_class`/`water_stress_class` الكنسيّين (لا حساب) + تحليل التربة (pH/OM). نقطة قراءة فقط، **لا هجرة، لا تغيير قرار**. الصدق: **بُعد المغذّيات `needs_data` دائماً** (توازن NPK غير مقيس — P محجوب، K معطّل) فلا «NPK Index» مُلفَّق؛ بُعد غائب يُستبعَد + إعادة تسوية (لا عقاب على ما لا يُقاس)؛ **بلا كربون** صراحةً؛ أوزان/عتبات مُعلَنة (`calibrated=False`). |

## 7) كنس الفجوات القابلة للتنفيذ (متعدّد الوكلاء، فرع `claude/actionable-gaps-sweep`)

| الفجوة | الموضع | القرار + السبب |
|---|---|---|
| **H5-residual (ربط كنسيّ)** | `api/field_state_projection.py::_apply_canonical_salinity` | ربط الملوحة بالكتلة الكنسيّة `water` خلف `FEATURE_CANONICAL_SALINITY` (default OFF). السبب: الملوحة **قرار إدخال** (قرار H5)، لا تُفعَّل ضمنيّاً. OFF ⇒ كتلة تُعلِن التعطيل؛ ON+موثوق ⇒ Ks فعليّة بإعادة استخدام `salinity_decision`/`salinity_stress_ks` (لا تكرار). ECw غير مُدخَل ⇒ الغسيل `None` معلَن (لا اختلاق، نظير `de_mm=0`). يحاكي `_apply_canonical_etc_dual`. |
| **بوّابة CI ساكنة** | `.github/workflows/ci.yml` (`Platform Structure Inspector`) | تشغيل `tools/sahool_inspector.py` ساكناً (exit 1 على FAIL فقط). السبب: تحويل ضمانات RLS/router/migration (C1/C2/H6) من «fixed يحتاج تأكيداً» إلى **تأكيد ساكن مستمرّ** — بلا خدمات حيّة. WARN (NATS/authz) إرشاديّ لا حاجب. لا تعديل على الأداة. |
| **NATS/H4 = إعلان لا سلوك** | `weather-polygon-worker/src/main.py` · `mcp_servers/weather_server.py` · `wofost_real/wofost_engine.py` | **قرار صدق:** الإصلاح الصادق لهاتين **إعلان توثيقيّ** لا تغيير سلوك. NATS: المسار سقالة مقصودة (محروسة بعلم OFF) ⇒ لا مستهلك مُلفَّق (قرار H2). H4: ٣/٥ موحّدة؛ المتبقّيان محجوبان بعزل خدمات مقصود ⇒ مرجع كنسيّ بدل نقل `core→shared` المحفوف. السبب: بناء سلوك وهميّ لإسكات المفتّش/إغلاق صوريّ يخالف لا-الاختلاق ومُلاءمة اليمن. |

## 8) جسر القرار→التنفيذ (Shard 3، فرع `claude/dispatch-actuator-bridge`)

**قرار سلامة (المستخدم): محاكاة-أوّلاً.** الحلقة كانت مغلقة **عبر الإنسان** (إخطار)؛ التنفيذ الفيزيائيّ محجوز عمداً
في `actuator-service` («البشر أوّلاً، المضخّات آخراً»). بناء جسر تلقائيّ = تجاوز حدّ أمان ⇒ بُني محروساً مزدوجاً.

| المكوّن | القرار + السبب |
|---|---|
| **الموضع: `actuator-service` (لا المنصّة)** | التنفيذ الفيزيائيّ يبقى في الخدمة المُحصَّنة. داخل `main.py` لا وحدة منفصلة: `shared` بجذر الريبو ⇒ استيراد شقيق يكسر اختبار الـactuator (قرار بنيويّ مدفوع بعزل الخدمة، نظير H4). |
| **حراسة مزدوجة** | `FEATURE_DISPATCH_ACTUATOR` (default OFF ⇒ مسار الإنسان يبقى المستهلك) **+** `ACTUATOR_MODE=real` (وإلّا simulation ⇒ لا حركة فيزيائيّة). السبب: تفعيل التحكّم الفيزيائيّ الذاتيّ قرار تشغيليّ صريح بخطوتين، لا افتراضيّ. |
| **قائمة مخاطر + عزل جهاز** | `low,medium` افتراضيّاً (HIGH/CRITICAL/NULL تبقى للإنسان) + `_device_belongs_to_tenant` (fail-closed) يمنع تحكّماً عابراً للمستأجرين. الأخير **أُضيف من مراجعة عدائيّة ذاتيّة** (يُحيّد قلق RLS: لا نشر تحت سياق غير مضبوط). |
| **صدق «نُشِر≠نُفِّذ»** | `send_mqtt_command` بلا ack ⇒ `executed` = «نُشِر للوسيط» لا تأكيد فيزيائيّ — مُعلَن في الكود/السجلّ. مطالبة ذرّيّة (`FOR UPDATE SKIP LOCKED`) ⇒ لا إطلاق مزدوج. حدّ مُعلَن: لا تعافي تلقائيّ لصفّ عالق في `dispatched`. |

## 9) Actuator Safety Hardening (آمن افتراضيّاً، فرع `claude/actuator-safety-hardening`)

**قرار سلامة فيزيائيّة (المستخدم): fail-safe > حفظ السلوك التاريخيّ.** فحصُ المستخدم كشف أنّ `ACTUATOR_MODE`
يُرجّح `real` افتراضيّاً (يُستنتَج من `MQTT_BROKER_URL` الإنتاجيّ) — فالطبقة الفيزيائيّة **غير آمنة افتراضيّاً**.

| المكوّن | القرار + السبب |
|---|---|
| **الافتراضيّ ⇒ simulation (كسر واعٍ)** | `resolve_actuator_mode` عند غياب العلم يُرجِع `simulation` لا الاستنتاج. السبب: وجود وسيط MQTT **ليس موافقة تشغيل** لمضخّات/صمّامات؛ real يتطلّب opt-in صريحاً. **يعكس قرار PR #394 بوعي** — في طبقة فيزيائيّة، الفشل الآمن أهمّ من حفظ السلوك. يقبل المستخدم توقّف الأتمتة لمن لم يضبط الوضع. حُدِّث `test_actuator_mode.py` للعقد الجديد. |
| **نقطة اختناق واحدة + دفاع بالعمق** | `send_mqtt_command` نقطة النشر الفيزيائيّ الوحيدة (يحرسها `ACTUATOR_MODE`). فوقها أعلام per-path **كلّها default-OFF**: `FEATURE_AUTOMATION_RULES_ACTUATION` (رأس `evaluate_rules`) · `FEATURE_MANUAL_ACTUATOR_COMMANDS` (`/command`) · `FEATURE_DISPATCH_ACTUATOR` (الجسر). فحص أكّد: `ACTUATOR_MODE=real` **وحده لا يكفي** — كلّ مسار يفحص علمه قبل النشر. |
| **`/command` 403 صريح + `/safety-status`** | تعطيل اليدويّ ⇒ 403 `manual_actuator_commands_disabled_by_safety_policy` (لا رسالة عامّة، قرار المستخدم). `/safety-status` يُعلِن الوضع وحراسة كلّ مسار — **لا أسرار** (لا broker/tokens/tenant/secrets، قرار المستخدم). تحذير إقلاع صاخب عند real. |
| **تحقّق** | مراجعة عدائيّة: ٧ ادّعاءات تصمد، **لا ثغرة** — شامل مسار `_compensate` (محروس ترانزيتيفيّاً عبر علم `evaluate_rules` + نقطة الاختناق). أُصلِح تعليق ACTUATOR_MODE القديم المُضلِّل (صدق). الحالة: **implemented-gated-fail-safe**. |

## ADR-0002 — Farm Operations Ledger
- الحالة: مقبول/مطبّق مبدئياً خلف `FEATURE_FARM_OPERATIONS_LEDGER`.
- القرار: سجلات SAHOOL التشغيلية هي مصدر الحقيقة الرقابي؛ ERP إسقاط مالي اختياري.
- النطاق: أعمال يومية، مياه، طاقة، معدات، عمالة، مواد، تلخيص تكلفة رقابي.

## ADR-0003 — Farm Ledger Budget & Cost Intelligence
- Status: accepted / implemented behind `FEATURE_FARM_OPERATIONS_LEDGER`.
- Adds season budget lines, revenue records, indirect cost pools, variance analysis, profitability, explainable cost recommendations, and ERP financial projection without ERP writes.
- Keeps SAHOOL operational ledger as operational truth; ERP remains optional projection.

## ADR-0004 — Farm Ledger Closed Loop
أُضيفت طبقة إغلاق الحلقة التشغيلية الاقتصادية خلف أعلام off افتراضياً: autowrite preview، إسقاط مخزون projection-only، economic-state اختياري، وتوصيات كفاءة تحفظية قابلة للمراجعة. لا ERP write، لا inventory write، ولا CanonicalFieldState write افتراضياً.

## 10) تكامل لقطة الأرشيف (جلسة 2026-06-27، رأس `main`: `e09ce27`)

دمج لقطة أرشيف كاملة عبر **٤ مراحل / ٥ طلبات حسب المجال** فوق إصلاحات تأسيسيّة. المبدأ الحاكم:
دفعات إضافيّة قائمة بذاتها، الحفاظ على خضرة كلّ بوّابات CI، وإصلاح أخطاء الأرشيف الحقيقيّة لا إضعاف الحرّاس.

| المكوّن | القرار + السبب |
|---|---|
| **Phase 22 — RLS WITH CHECK + توحيد الجلسة** | `migrations/v122` (#487، `24e7923`) — backfill مدفوع بالكتالوج لكلّ سياسة كتابة tenant + `sahool_effective_tenant_id()` يوحّد `app.current_tenant`/`app.tenant_id`. السبب: سدّ مسار الكتابة (USING وحده يسمح بكتابة عابرة للمستأجر)؛ v122 يبقى الأخير في MANIFEST (يقرأ الكتالوج وقت التطبيق). |
| **تفكيك main.py ⇒ تسجيل تلقائيّ** | (#491، `2198525`) — حلقة `pkgutil.iter_modules` تستبدل ~١٤٢ تضميناً يدويّاً. السبب: منع تضخّم main.py كدَيْن تقنيّ (خيار المستخدم «أ»). `service_proxy` مُستثنى (يستورد من api.main ⇒ دورة) ويُستورَد متأخّراً. الحارس + المفتّش يتحقّقان عبر `app.routes` (وقت التشغيل) لا مطابقة نصّ. |
| **تقسيم الدفعة ٤ حسب المجال** | (#493-#497) — scripts/security · raster · frontend · mobile · الربط النهائيّ. السبب: خيار المستخدم «قسّمها لـPRs حسب المجال»؛ كلّ اختبار عابر-المجال يذهب للدفعة التي تكتمل فيها كلّ تبعيّاته (frontend+raster+platform). |
| **تأمين phase9-12 بتوكن خدمة على مستوى الراوتر** | (#497، `e09ce27`) — `dependencies=[Depends(_require_service_token)]` للرواتر الأربعة عبر وحدة مستقلّة `api/service_token_auth.py`. السبب: الأرشيف جلب ٦٤ نقطة POST بلا مصادقة (autonomy/federation/IoT/marketplace)؛ خيار المستخدم «توكن خدمة على مستوى الراوتر» (خدمة-لخدمة). وحدة مستقلّة تتفادى دورة استيراد `api.main` (اختبارات المنصّة تستورد وحدات phase مباشرةً ⇒ استيراد جزئيّ يكسر `router`). عُلِّم `test_endpoint_auth_coverage` اكتشاف تبعيّات مستوى-الراوتر (تحسين الكاشف، لا allowlist أعمى). |
| **توافقيّة compat_gateway عامّة بتبرير** | (#497) — مسابر الصحّة عامّة (مثل /healthz)؛ تمرير vegetation/raster يُفوّض المصادقة للخدمة الخلفيّة (المتصفّح يحمّل البلاطات `<img>` بلا ترويسات) ⇒ PUBLIC_ALLOWLIST لا توكن. السبب: صدق التصنيف — لا مصادقة حيث لا أصول مكشوفة، والتفويض موثَّق. |
| **استعادة الملفّات المدموجة من main عند دهس الأرشيف** | (#493/#497) — `ci.yml` (تخطّي rag-kg-mcp + بوّابة RLS) · `migrations/` · `validate_rls_write_policies` تُستعاد من main حين تَدهسها نسخ مجلّدات الأرشيف. السبب: نسخ الأرشيف تراكميّ يعيد ملفّات لإصدار أقدم؛ القاعدة: أيّ ملفّ مدموج دهسه الأرشيف يُستعاد من main. |
| **راستر #484 الأحدث يسود** | (#494/#497) — راستر الأرشيف الأقدم (3973 سطر) لا يُرجِع راستر #484 (4178)؛ أُسقط اختبارا raster-internal متعارضان (`map_runtime_chain`/`security_visual`). السبب: عدم انحدار ميزات #484 (هندسة جيوديسيّة/سلسلة زمنيّة صارمة). |
| **إخضرار سير عمل production-gates الجديد بدل تعطيله** | (#497) — pyyaml للوظائف + استبعاد `.claude/settings.local.json` من بصمة الإصدار + حصر `build_release_bundle` على ملفّات git المُتعقَّبة (إصلاح كامن في rglob) + حصر فاحص سلسلة الإمداد في الخطر الحقيقيّ (PR-target/latest). السبب: خيار المستخدم «أصلِح وظائفه»؛ إصلاحات سطحيّة حقيقيّة لا إسكات. |

## 11) تصلّب ما بعد الأرشيف + الاعتماد الإنتاجيّ (جلسة 2026-06-27 ب، رأس `main`: `95dc750`)

استجابةً لمراجعة خارجيّة للأرشيف. مبدأ: تنفيذ متوازٍ، **دمج مرتَّب**، لا دمج فرعين متداخلين في
ملفّات حسّاسة (`main.py`/MANIFEST/CI)، وإصلاح أخطاء حقيقيّة لا إضعاف حرّاس، وعدم تلفيق أدلّة.

| المكوّن | القرار + السبب |
|---|---|
| **v123 RLS وقائيّ (Track A)** | #499 (`be1bd56`) — v122 يستبدل `USING` بمسند tenant مُنشأ. التحقّق: **بلا انحدار فعليّ** (السياسة المركّبة الوحيدة `user_self` لديها WITH CHECK فيتخطّاها v122). فالقرار: خَلَف v123 **حافظ لـ`USING`** (forward-only، idempotent، fail-closed) كتصلّب وقائيّ للنمط، لا إصلاح عطل قائم. السبب: «أصلِح الأخطاء الحقيقيّة» مع صدق التشخيص (الخطورة كانت مُبالَغاً فيها). |
| **عدم تعديل v122 المُطبَّق** | استُخدم v123 forward بدل تحرير v122 (migrate.py يتتبّع بـchecksum؛ تحرير مُطبَّق سيّئ). v123 يبقى ذيل MANIFEST + مُدرَج في run_migrations.sql. |
| **docstring صادق + .claude (Track B)** | #500 (`488a7c7`) — صُحِّحت ملاحظة DB المغلوطة؛ **أُبقيَ HS256/in-process-rate-limit مؤجَّلين بصدق** (لم يُدّعَ production-grade). إزالة ملفّ محلّيّ من git. السبب: صدق التوثيق. |
| **router_registry استخراج فقط (Track C)** | #501 (`e230ecb`) — استخراج التسجيل من main.py إلى وحدة مخصّصة. **رُفض نقل router_groups الفيزيائيّ (١٤٦ ملفّاً)**: churn ضخم يكسر استيرادات/اختبارات/حارس التفكيك بلا مكسب وظيفيّ (التفكيك يعمل عبر auto-reg). السبب: أقصى تقليل دَيْن بأقلّ مخاطرة؛ تأجيل النقل الفيزيائيّ (C2-C5 لاحقاً، تنظيم specs لا نقل). |
| **رفض إعادة «Batch 1»** | الدفعات 1-4 مدموجة سلفاً (#488-#497)؛ إعادة إضافة v100-v105 سيرفضها `validate_migration_manifest` (duplicate prefix). القرار: تدقيق حضور (للقراءة) بدل دمج جديد. السبب: الأدلّة تناقض المقدّمة ⇒ تُصحَّح لا تُنفَّذ. |
| **اعتماد إنتاجيّ صادق (No-Go معلّق)** | #502 (`95dc750`) — `FINAL_PRODUCTION_READINESS_REPORT.md` + مصفوفة: **GO** للكود/CI، **NO-GO معلّق** للإنتاج حتى staging+soak. السبب: smoke/env_doctor/soak تتطلّب بيئة حيّة وأزمنة؛ تُعلَّم PENDING بمالك (Ops) **ولا تُلفَّق** — حدّ الصدق («نُشِر≠نُفِّذ» يمتدّ إلى «أخضر CI ≠ مُعتمَد إنتاجيّاً»). |
