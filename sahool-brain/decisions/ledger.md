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
| **#550** | `2359cea` | **استرجاع تحصينات raster** على `main` الحاليّ بعد محو ٦ PRs بدفع مباشر: قناع `cog_writer` (إصلاح **جذر** الشرائط من المصدر) + تعقيم `str(e)` + `cloud_pct`/SCL + سقالة `register_routers` — **فرع واحد مدمج**، حفظ تامّ لمساري CDSE. السبب: استعادة العمل دون فقد ودون إرجاع مسارات cdse الجديدة. |
| **#551** | `51d650c` | **تفكيك مسارات raster** (٤٥ `@app` → ١٠ `routers/`، محفوظ السلوك، ٤٩ مساراً، CDSE محفوظة). `register_routers` يُلحِق `APIRoute` مباشرةً (Starlette 1.3.1 `include_router` كسول لا يُسطّح). السبب: تقليص `main.py` (٣٠٠٥→١٦٢٥) دون كسر العدّ/الحارس/الـcdse. حُرّاس `tests_v9` صارت تمسح `routers/` (لا إضعاف). |
| #552/#553/#554 | `a3b29ff`/`df02c06`/`efea4c6` | واجهة CDSE (حذف `date=latest`) · nginx `/api/raster/` لبوّابة الواجهة 3003 (**بلا** `auth_request` — بوّابة تطوير، لا تكرار منطق الإنتاج) · وثيقة مقارنة `v9↔fixed` مُتحقَّقة. |
| #555/#556 | `f2d5f0b`/`852fb5b` | تحديث العقل (#550/#551) · **إعادة مرآة `mirror.gcr.io`** في *Integration Tests* — يُصلح رفرفة Docker Hub (CI-MIRROR ⇒ fixed). |
| **#557** | `f92c994` | **تفكيك `auth/main.py`** (٢٧ `@app` → ٩ `routers/`، محفوظ السلوك، حسّاس أمنيّاً، N=31 ثابت). السبب: تقليص المتجانس بنفس نمط raster دون كسر التفويض/الحُرّاس. |
| **#558** | `522a47e` | **قصّ CDSE على مضلّع الحقل** لا الـbbox (إزالة الصحراء الحمراء): تمرير `geom=GeoJSON` ⇒ Sentinel Hub يقصّ على المضلّع. السبب: bbox وحده يصبغ الصحراء بـNDVI منخفض. **علم تحقّق ميدانيّ** (يلزم CDSE حيّ). |
| **#559** | `1bef0cf` | **تطبيع تاريخ CDSE:** `date=""` الفارغ كان ينتج `date_from` فاسداً ⇒ يُعامَل كـ`latest`؛ وإسقاط `date` من رابط `cdse-tilejson` حين لا يُطلَب محدَّداً. السبب: مراجعة النسخة المرفقة (الملاحظة #2). اختبار وحدة (٨). |
| **#560–#563** | `77123b3`/`d40f1a9`/`0abe6de`/`7a36511` | **تفكيك ٤ خدمات متجانسة** (odoo-bridge 14 · video-processor 12 · vegetation 12 · supervisor 14) بنفس نمط raster/auth، محفوظ السلوك، عدد المسارات ثابت. #563 احتاج مساعِد `supervisor_route_source.py` (حارس مصدر يمسح main+routers بعد انتقال `/agent/*`). السبب: تقليص المتجانسات دون كسر الحُرّاس. |
| **#564** | `d9d9694` | **MapHub→CDSE + عقد `poly` + قناع rasterio + السبب الجذريّ للقصّ:** `HubMap.tsx`→`cdse-tiles`؛ nginx `^~ /api/raster/` + `X-Tenant-Id` من `$arg_tenant_id`؛ WebSocket الإشعارات (`python-jose` + توصيف + `websockets<14`). **الجذر (اكتشاف المستخدم):** `fetch_field_geometry` بلا `set_config(app.current_tenant)` ⇒ RLS يحجب ⇒ `geometry=None` ⇒ لا قصّ — أُصلِح عبر `sahool_field_owner_tenant`. + عقد `poly` موحَّد + `tile_render.apply_polygon_mask` بكسليّ + ملوحة SWIR + نافذة ٦٠ يوماً. السبب: قصّ دقيق على حدّ الحقل من المصدر لا العَرَض. |
| #565 | `ba29bba` | تحديث العقل لسلسلة #552–#564. |
| **#566** | `e6f98f5` | **H5 — سياسة الريّ المشروطة بالملوحة:** `net` دائماً + Ks عند توفّر EC موثوق + غسل **مشروط**؛ ٤ سياسات + `requires_expert_review`. راوتر `/api/v1/irrigation-recommendation` (لا يكسر `/water-balance`). السبب: توحيد صيغتَي الريّ كسياسة قابلة للضبط لا «كود فقط» — تبقى `fixed` (معايرة EC ميدانيّة). |
| **#567** | `273ee34` | **C5 — سياسة دليل NDVI:** `informational`/`supporting`/`decision_blocking`؛ الافتراضيّ `supporting` (لا يحجب وحده)؛ الحجب فقط بمعايرة + سياق + جودة مشهد. حارس بنيويّ: القرار يأخذ عُمر NDVI لا قيمته. السبب: منع NDVI من قلب قرار قانونيّ دون معايرة. |
| **#568** | `008c330` | **H2 — عقد ناشري الأحداث + حارس عكسيّ:** `event_publish_contracts.yaml` (منتِج أو waiver لكلّ مُستهلَك) + `check_nats_publisher_coverage` يفشل على «مُستهلَك بلا منتِج». كشف `weather.forecast.updated` الذي فات الفحص القديم. السبب: إغلاق H2 بناشرين عبر outbox موثَّقين ومحروسين، لا تقليم اشتراكات ولا اختلاق ناشر. |
| #569 | `a8f0b0b` | تحديث العقل: إغلاق H5/C5/H2 (`fixed`) + ledger #564–#568. |
| **#570–#573** | `d340e60`/`7f642a2`/`bcb6c15`/`b4c0be6` | **تفكيك ٤ خدمات أصغر** (soil 10 · tts 11 · actuator 10 · guardrails 11) بنفس نمط raster/auth، محفوظ السلوك، عدد المسارات ثابت. **soil:** CI كشف كسر حُرّاس عزل المستأجرين ⇒ إعادة تصدير المعالجات + مساعِد مصدر مُجمِّع + تحديث allowlist (`tenant_query_audit`) + تنظيف sys.modules — بلا إضعاف. actuator/guardrails حسّاسان أمنيّاً (تفويض مطابق بايتاً). السبب: إكمال تقليص المتجانسات دون كسر الحُرّاس الأمنيّة. |
| #574 | `b180553` | تحديث العقل: SVC-DECOMP-2 (#570–#573). |
| **#575** | `35a4565` | **بوّابة الواجهة التطويريّة (`frontend/nginx.conf`، 3003):** ٥ كتل `location ^~` **قبل** catch-all `/api/` لخدمات تناديها `api.ts` بقواعد خاصّة (vegetation→`sahool-vegetation-analysis:8000/` · indicators/weather→`sahool-platform:8000/api/v1/…` · agent→`sahool-supervisor-agent:8000/agent/` + `=/api/agent/health`→`/health` · guardrails→`sahool-guardrails-engine:8000/`) بلا `auth_request` (تطوير؛ تمرير `Authorization`+`X-Tenant-Id`). أهداف مطابقة لـ`nginx.v9.conf`. حارس `test_frontend_nginx_service_proxy_guard`. السبب: بلا الكتل تسقط لـ catch-all ⇒ المنصّة بلا هذه المسارات ⇒ 404 (دردشة/غطاء/مؤشّرات/طقس). |
| **#576** | `2244145` | **D — عقد TileJSON (واجهة):** `FieldIndicatorMap.tsx` كان يبني طلب TileJSON بـ`params:{index,date}` بلا شرط ⇒ تسريب `date=latest`/`date=`؛ صار مشروطاً (`date && date!=='latest' ? {index,date} : {index}`، نفس حارس باني رابط البلاطة). backend يتحمّل ⇒ تنظيف عقد لا كسر. حارس ساكن `test_frontend_tilejson_date_contract_guard` (٤). السبب: إغلاق آخر تسريب لعقد latest/date من الواجهة (متابعة مراجعة النسخة). |
| **#577** | `63c2f03` | **C — الموضوع اليتيم (NATS):** `sahool.weather.field.overlay.completed` يَنشُره `weather-polygon-worker:161` بلا مشترِك ⇒ WARN «حدث طريق مسدود» (غير حاجب). **توثيق** القرار: قسم `published_no_consumer` في `event_publish_contracts.yaml` (منتِج فعليّ + سبب) + `check_nats_subjects` يقرؤه ويحترمه (WARN⇒PASS) دون إضعاف `CRITICAL`/H2. +٣ اختبارات (سلبيّ: إزالة الـwaiver تُعيد WARN). السبب: توثيق قرار معماريّ لا إخفاء تحذير ولا اختلاق مشترِك. |
| — | (تشخيص مفتوح) | **`sahool-auth` unhealthy** يمنع إقلاع حزمة v21. `/readyz` موصول صحيحاً ⇒ ليست انحدار تفكيك #557؛ السبب runtime/config (lifespan fail-closed). الأرجح دور قاعدة يتجاوز RLS (`assert_db_role_rls_safe` يرفض الإقلاع، `services/auth/main.py:229`) — الإصلاح دور مقيّد `sahool_app` أو `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1` للتطوير. **ينتظر سجلّ المشغّل** (`docker logs … auth`) قبل أيّ إصلاح. |
| — | (مؤجَّل B) | **journal الوكيل** (`supervisor-agent/tool_contracts.py:325`) ما زال in-memory للـMVP — يلزم Postgres append-only/outbox لدوام تدقيق إنتاجيّ للأدوات ذات الأثر. PR مستقلّ لاحقاً (أكبر من متابعة صغيرة). |
| — | (تنبيه) | **دفع مباشر متزامن على `main`** من المالك محا PRs مدموجة (#544–#549). الدرس: لا بناء على `main` أثناء ذلك؛ الاسترجاع في فرع واحد سريع. وفقدُ `mirror.gcr.io` من `ci.yml` (فجوة CI-MIRROR) سبب رفرفة Docker Hub. |

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
| **توحيد main + فرع الاعتماد Phase 1–22 (س)** | (`96003bf`) — `main` وفرع `certification/final-readiness-evidence` افترقا من `89d848e`؛ وُحِّدا في superset واحد (Phase 1–22 + v99–v123 + production-gates + 470 ملفّاً ⊕ تفكيك/CDSE/H5/C5/H2/بوّابة). 22 تعارضاً مُحلّاً (إضافيّ آليّاً · متداخل بقاعدة cert + اتّحاد). السبب: خيار المستخدم «وحّد الخطّين»؛ لا أحدهما superset فالدمج ضروريّ. تحقّق: compileall · inspector PASS · 1931 اختبار · الحُرّاس. |
| **🔑 السبب الجذريّ لـauth «unhealthy»: Dockerfile لا ينسخ وحدات التفكيك** | السجلّ كشف `ModuleNotFoundError: 'router_registry'` (main.py:889). Dockerfile auth/vegetation ينسخ ملفّات مفردة لا المجلّد ⇒ `router_registry.py`/`routers/` غائبة في الصورة ⇒ uvicorn يفشل ⇒ unhealthy. **فرضيّات RLS/JWT السابقة خاطئة** (بلا سجلّ). الإصلاح: Dockerfile ينسخهما + حارس CI `test_decomposed_service_dockerfile_guard`. السبب: الاختبارات تستورد main من مجلّد الخدمة فلا تكشف نقص الصورة؛ الحارس يسدّ الفجوة. التطبيق: `--build`. |
| **تجديد بصمات الإصدار بعد الدمج التوحيديّ** | الدمج غيّر بصمة 85 ملفّاً سجّلها فرع الاعتماد في `release/FILE_CHECKSUMS.sha256` ⇒ فحص Phase 14 (`validate_release_package`) فشل على ci.yml. أُعيد توليد الحزمة بالسكربت القانونيّ `build_release_bundle.py` (2584 بصمة). السبب: حزمة الإصدار يجب أن تعكس الحالة الموحّدة؛ لا تعديل يدويّ للبصمات. |
| **توحيد الفرع المخصّص + إغلاق PR #579** | دُمج `main` في `claude/code-review-34hO3` (`c0174e6`، شجرة مطابقة لـmain، حلّ تعارض cdse_tiles لصالح main) + أُغلِق PR #579 (unify→المخصّص، مُتجاوَز). السبب: المهمّة الأصليّة تُطوّر/تدفع على هذا الفرع؛ توحيده مع main القانونيّ يُنهي ضوضاء التعارض. 0 PR مفتوح · 0 تعارض. |
| **تفكيك main.py للمنصّة: استخراج النماذج + إصلاح حارس المصدر (ع)** | (`a806251`+`c8fc78b`، الفرع المخصّص `044e1ff`) — نُقِل ٧٣ نموذج Pydantic من `api/main.py` (3282→2735) إلى `api/api_models.py` (ترتيب AST). كسر ذلك حارس `test_disease_field_state_feed::test_diagnose_request_has_optional_field_id` (مسح `main.py` فقط بـ`.index("class DiagnoseRequest(")` ⇒ `ValueError`). الإصلاح: مسح `main.py`+`api_models.py` معاً. السبب: حُرّاس المصدر النصّيّة يجب أن تتبع الرمز أينما انتقل بعد التفكيك (درس supervisor #563 مُكرَّر)؛ شغّل **كامل** `tests_v9 -m unit` لا عيّنة. التوقيع: الالتزامات موقَّعة SSH (`gpgsig`)؛ `%G?`=N محلّيّ فقط (لا `allowedSignersFile`). |
| **تحصين JWT RS256: المنصّة + ٨ خدمات ترفض HS256 في الإنتاج (ف)** | (`030c01a` المنصّة + `ddd2434` الخدمات) — المنصّة كانت HS256-فقط بلا `JWT_PUBLIC_KEY` ⇒ لا تتحقّق من توكنات auth الـRS256 (كسر عابر-خدمات)؛ أُضيف مسار RS256 + حارس `_refuse_hs256_in_production` (محاكاة auth). ٨ خدمات تتحقّق JWT أُضيف لها حارس إقلاع fail-closed يرفض HS256 في الإنتاج (مهرب `SAHOOL_ALLOW_HS256_IN_PROD=1`)؛ vegetation كانت HS256 مُصمَّت بلا RS256 (أُضيف المسار). السبب: HS256 سرّ متماثل مشترَك لا يُنهي shared trust domain (أيّ خدمة تحمله تُزوّر)؛ مراجعة المستخدم الجنائيّة (#1 الأهمّ). القرار: حارس import-time (موضع واحد/خدمة، مرساة `_ALLOWED_ISS` موحَّدة، `os.getenv("JWT_PUBLIC_KEY")` مباشرةً فالكتلة متطابقة) — لا يُطلَق في CI (لا اختبار production-mode يستوردها). صدق: #3/#4 من المراجعة غير قابلتَين لإعادة الإنتاج (لقطة أقدم)؛ #6 موثَّق مؤجَّل. حُرّاس مصدريّان جديدان. `pytest -m unit` 1971 ✓. |
