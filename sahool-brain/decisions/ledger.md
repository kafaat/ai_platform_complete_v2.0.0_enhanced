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
| **AUTH-BOOT (حُسِم)** | `abf1731` | **السبب الحقيقيّ لـ`sahool-auth` unhealthy لم يكن دور RLS** (التشخيص المفتوح أعلاه) بل: `services/auth/Dockerfile` لم ينسخ `mfa_crypto.py` (وحدة v29.5 يستوردها `main.py:163`) ⇒ `ModuleNotFoundError` عند الإقلaع ⇒ uvicorn يموت ⇒ `/readyz` مرفوض ⇒ unhealthy. نفس صنف router_registry/otp. الإصلاح: `COPY mfa_crypto.py` + **حارس معمَّم** `test_dockerfile_ships_local_sibling_modules` (يمسح استيرادات main.py الشقيقة). السبب: إغلاق صنف العطل لا الحالة فقط. الدرس: عند إضافة وحدة شقيقة لخدمة مُفكَّكة، تحقّق من نسخ Dockerfile قبل الادّعاء بسبب runtime آخر. |
| **P0-MFA (مُثبَت)** | `cb4ea31` | **اختبارات تكامل MFA/v57.5 كانت تتخطّى بصمت في CI** (قرأت `DATABASE_URL` وهميّ بدل `TEST_DATABASE_URL`) — تصحيح ادّعاء «مُتحقَّق على Postgres» السابق. أُعيدت لاستخدام `TEST_DATABASE_URL`؛ اختبار MFA قُسِّم إلى asyncpg نقيّ (يعمل في CI) + TestClient (`importorskip`). **إثبات:** `test_mfa_migrations_applied_on_real_postgres PASSED` في run 28553630120 ⇒ MFA مغلق إنتاجيّاً (شرط المستخدم). السبب: لا ادّعاء تحقّق بلا سطر سجلّ CI يثبت التشغيل الفعليّ. |

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

## 11) حوكمة الوكيل + أدلّة + تصلّب MFA + إصلاحات runtime (جلسة 2026-07-01، رأس `main`: `4a3f1a4`)

سلسلة دفعات مستقلّة، كلٌّ CI 11/11 خضراء ثمّ ff-merge إلى main (Integration يطبّق كلّ ترحيل على Postgres+PostGIS حقيقيّ). المبدأ الحاكم: نطاق ضيّق لكلّ دفعة، تحقّق قبل التنفيذ (كثير من «الفجوات» مُغلَق downstream)، لا اختلاق إصلاح لعطل بلا سجلّ.

| المكوّن | القرار + السبب |
|---|---|
| **v58.2a — مخازن قابلة للاستبدال** | (`eb3cf89`) `agent_stores.py`: Protocol + InMemory (افتراضيّ) + Redis (خلف `SAHOOL_AGENT_STORE_BACKEND`، سقوط آمن) + `/approvals/resume`. السبب: الموافقة/التدقيق كانا in-memory (يضيعان بإعادة التشغيل)؛ العقد يبقى ثابتاً فالإنتاج يستبدل الخلفيّة. |
| **v58.2b — تحقّق + تعقيم + mutating⇒approval** | (`151851a`) `tool_governance.py` + ثابت وقت-البناء في `tool_registry.py`. السبب: تسميم نتائج الأدوات خطر prompt-injection؛ والعَلَم `requires_approval=False` لأدوات mutating كان غير صادق (البوّابة كانت تحوّلها pending أصلاً). |
| **v58.2c — حماية إساءة الحلقة** | (`0b5a13b`) ميزانية run + dedupe + stop-on-pending في `tool_loop.py`. كلّ الوسائط اختياريّة (توافق V56). السبب: max_rounds×MAX_TOOL_CALLS = 24 أداة نظريّاً؛ يلزم سقف إجماليّ + منع حلقة على نفس الاستدعاء. |
| **v49.5 — أدلّة tenant-scoped (دمج انتقائيّ)** | (`abe0c51`) `field_ai_context.py` (tenant filter صريح + redaction + budget + provenance) + ترحيل **v127** (رُقِّم من v49_5 لحارس التكرار). السبب: `_optional_events` كان بلا فلتر مستأجر صريح (دفاع مضاعف)؛ **رُفِضت** عودة الحزمة إلى ما قبل v58.2a/b (متطابقة بايتيّاً مع السلف `75ba7f9` — تحقّقتُ). |
| **v29.5 — تصلّب MFA** | (`8810321`) `mfa_crypto.py` (Fernet، لا default key) + v128 (encrypted secret + قفل DB + recovery hash-only + audit). مسار توافق: مشفّر→نصّ قديم→ترحيل عند نجاح الدخول. السبب: `mfa_secret` كان نصّاً صريحاً بلا recovery/قفل DB/تدقيق؛ القيد: لا تُخزَّن أسرار نصّيّة جديدة ولا يُكسَر مستخدم قائم. `cryptography>=44` (pip-audit نظيف). |
| **v29.6 — إصلاحات مراجعة MFA (P0 قبل التضييق: إثبات)** | (`4a3f1a4`) v129: تضييق هروب RLS إلى `app.current_role='admin'` **بعد إثبات** أنّ auth pool يضبطه على كلّ اتّصال (`main.py` `_init_auth_conn`:278 يُمرَّر `init=`؛ `_acquire`:218 يُعيده بعد `RESET ALL`). `mfa_recovery_codes` خدمة-فقط بلا self-read · `mfa_audit_events` append-only. كود: step-up محكوم (قفل+تدقيق) · التقاط `MfaSecretUndecryptable` · عدّاد فشل ذرّيّ (SQL CASE، لا read-modify-write) · rotation في transaction · HMAC للـIP · key_missing→503 مميّز · رفض مفتاح ضعيف في الإنتاج. السبب: مراجعة المستخدم الأمنيّة — لم أضيّق RLS قبل إثبات سياق الخدمة (وإلّا كسر كتابة auth). اختبار Integration يقرأ جداول MFA بسياق role=admin ويؤكّد `current_setting('app.current_role')='admin'`. |
| **إصلاح 422 backfill** | (`2e353af`) `MapHub.tsx` كان يرسل `'truecolor'` ضمن `indices`، لكنّ عقد raster `HistoricalBackfillRequest.indices: list[IndicatorKind]` لا يحوي truecolor (تصيير لا مؤشّر) ⇒ pydantic 422 قبل المعالِج. الإصلاح: ترشيح للمجموعة المدعومة (واجهة فقط، الخلفيّة صحيحة) + حارس ساكن. |
| **إصلاح bandit B613** | (`5202907`) `tool_governance.py` احتوى محارف bidi حرفيّة (U+202A…) في regex `_ZERO_WIDTH` ⇒ Security Scan HIGH يحجب. الإصلاح: بناء النمط من code points وقت التشغيل (`chr()`)، فالمصدر بلا محارف خام. السبب: bandit يمسح المصدر؛ النمط يعمل بلا تغيير سلوك. |
| **JWT_SECRET لخدمة النبات** | (`62989c6`) `docker-compose.v9.yml`/`fixed.yml` مرّرا `JWT_SECRET` لكلّ الخدمات المحوكَمة **عدا** `sahool-vegetation-analysis` ⇒ 503 «JWT_SECRET غير مضبوط» على «تحليل الآن» (`vegetation-analysis-service/main.py:161`). الإصلاح: إضافة `JWT_SECRET`+`JWT_PUBLIC_KEY` (كبقيّة الخدمات). صدق: عطل «المؤشرات المكانية→خروج» مسار مختلف (raster `/indicator-grid` 401) — موثَّق مفتوحاً بلا اختلاق إصلاح. |

## 12) شقّ v57.5-DB + إصلاح بوّابة الإنتاج (جلسة 2026-07-01، رأس `main`: `f9dc4c8`)

استكمال تصلّب الأساس (migrations إضافيّة idempotent، تُتحقَّق عبر Integration على Postgres حقيقيّ)، ثمّ إصلاح دَين تشغيليّ كشفه المستخدم.

| المكوّن | القرار + السبب |
|---|---|
| **v57.5-DB: التحقّق قبل التنفيذ** | قبل كتابة أيّ ترحيل، تحقّقتُ من الإغلاق downstream: **v54 imagery** ≈ مُغلَق (v105 + `_scene_quality_score`) · **RLS WITH CHECK على soil_lab** مُغلَق (v70) · **v52 tenant AI policy** له جدول DB (v124/v125) لكنّ مخزن ai_agronomist ملفّيّ عمداً (الخدمة بلا DB). المفتوح فعلاً: soil_lab analytes + imagery-quality remnants + field_state provenance. السبب: تفادي عمل مكرّر (درس متكرّر: معظم «الفجوات» مُغلَقة). |
| **v130 soil-lab evidence** | (`01fd600`) أعمدة analytes مُصنَّفة/مُتحقَّقة (pH 0–14 · EC · N/P/K · SAR…) + عمق/طريقة العيّنة + سلسلة عهدة + إصدار النتيجة. JSONB الخام يبقى المصدر. السبب: soil_lab_tests (v50) كان JSONB عامّاً بينما VRA (`vra_prescription_engine.py`) والريّ يستهلكانه ⇒ يلزم عقد دليل مُصنَّف؛ CHECK يمنع قيمة مستحيلة من قيادة وصفة. |
| **v131 imagery quality** | (`fc75f59`) `valid_pixel_ratio`/`coverage_ratio` (0..1، CHECK) + `index_quality_flags` + فهرس التقاط على raster_assets. السبب: إشارات الثقة الوحيدة المفقودة (v14/v105 غطّيا الباقي) لتقرير صلاحيّة مؤشّر لـVRA/المناطق. |
| **v132 field_state provenance** | (`1d89af9`) `version` أحاديّ التزايد (يمنع دهس إسقاط أحدث) + `source_event_id` (كشف الانحراف) + `recomputed_at`. السبب: field_state (v53) read model بلا provenance لإعادة الحساب. |
| **🔧 إصلاح بوّابة الإنتاج (دَين كشفه المستخدم)** | (`f9dc4c8`) **Sahool Production Gates** بقيت حمراء من `0b5a13b` (v58.2c) حتى الآن — كنتُ أراقب ci.yml (أخضر) دون الانتباه إلى بوّابة منفصلة تعمل **على main فقط**. سببان: (1) بصمات `release/FILE_CHECKSUMS.sha256` قديمة (ملفّات أُضيفت بلا تجديد) ⇒ `release-package`/`pytest-contracts` يفشلان؛ (2) حارس legacy رصد `agent_stores.py` (in-memory default) ⇒ `production-validation-gate` يفشل. الإصلاح: تجديد الحزمة بـ`build_release_bundle.py` (2805 بصمة) + إضافة `agent_stores.py:mvp_in_memory` لـ`legacy_quarantine_allowlist.json` (مبرّر متطابق مع المُدرَج: افتراضيّ fail-safe مع مسار Redis، لا اختصار MVP). النتيجة: #209 أخضر. **الدرس (في hot.md):** جدِّد البصمات + شغّل production_validation_gate.sh بعد كلّ دمج. |

## 13) دفعة أمان SEC-1..7 (مراجعة أرشيف المستخدم، جلسة 2026-07-02، رأس الفرع المخصّص: `1755c9c`)

راجع المستخدم أرشيف `sahool_main_0b85c84.zip` وأخرج ٨ فجوات. تحقّقتُ منها **جميعاً بالكود** (لا قبول بلا دليل). الثلاث الأخطر أُغلقت في مدخل log (ن)؛ الباقي هنا. المبدأ: نطاق ضيّق، فحص-قبل-تنفيذ، لا إضعاف حارس قائم.

| المكوّن | القرار + السبب |
|---|---|
| **SEC-3 — هويّة البوّابة الموثوقة (Option-B، اختيار المستخدم)** | (`5623934`+`d1ae020`) الخلل الجوهريّ: `ai_agronomist/main.py` كان `req.tenant_id or x_tenant_id` (body يسبق الترويسة). القرار: البوّابة سلطة JWT؛ داخل الخدمات `X-Tenant-Id` **مصدر الحقيقة الوحيد** (body≠header⇒403 tenant_mismatch؛ غياب⇒403). `shared/security/{trusted_tenant,gateway_deps}.py`. **تصحيحي:** approvals بوّبها الوكيل بـservice-token لكنّ nginx يمسحه ⇒ كسر الموافقة البشريّة؛ صحّحتُها لـ`require_trusted_tenant`. |
| **SEC-3.1 — user/role authz للموافقات** | (`5fee147`) سلسلة ذرّيّة: auth يُصدِر `X-User-Id`(sub)/`X-User-Role`(role) كرؤوس استجابة من الحمولة المُتحقَّقة → nginx يحقنهما للمسار (`proxy_params` يمسح الوارد) → `require_authenticated_user` (403 `missing_user`) فوق `require_trusted_tenant`. **الموافِق المُسجَّل = الهويّة الموثّقة لا حقل `approver` في الـbody** (يُغلق انتحال «مَن وافق»). السبب: الموافقة قرار حوكمة بشريّ يجب ربطه بمستخدم موثّق لا بحمولة JSON. الشحن ذرّيّ (emit→inject→require) كي لا تُرجِع أيّ بيئة 403 على كلّ موافقة. |
| **SEC-4 — rag /ingest + منافذ مساعِدة** | (`98a4327`) `/ingest` كتابة داخليّة ⇒ `require_service_token` (403 `service_token_required`) + منافذ إدارة `fastbee`/`zlmediakit` رُبطت بـloopback. السبب: كتابة بيانات المعرفة يجب أن تتطلّب سرّ خدمة-لخدمة كبقيّة الكتابات (KG)؛ منافذ الإدارة لا يجب كشفها. |
| **SEC-5 — رفع أرضيّة التغطية** | (`1332c3e`) `--cov-fail-under` 20→**40** في ci.yml (المُقاس 44.55٪ وقت القرار؛ 48.12٪ بعد SEC-3.1/4) + `docs/testing/coverage_ratchet.md`. السبب: رفع محسوب على قياس فعليّ لا اعتباطيّ — يمنع انحدار التغطية دون كسر CI. |
| **SEC-6 — قفل التبعيّات (نطاق آمن مرحليّ)** | (`1755c9c`) حارس `test_requirements_pinning_guard.py` (يمنع انحدار التثبيت على المسار الحرج) + `docs/security/dependency_locking_plan.md`. السبب: القفل الكامل للمستودع خطر تراجُع كبير؛ التدرّج بحارس أوّلاً ثمّ توسعة موثَّقة. |
| **SEC-7 — بوّابة smoke التشغيليّ** | (`0353265`) توثيق: هجرات/RLS/schema **إلزاميّة أصلاً** على main (Integration job)؛ smoke حيّ `/healthz` جاهز-للتفعيل خلف قرار مشغّل (compose ثقيل ⇒ خطر flakiness). السبب: قرار واعٍ موثَّق لا إغفال — لا أُحمِّر main ببوّابة compose غير مُتحقَّقة. |

**الحصيلة:** البنود الثمانية مُغلَقة. مؤجَّل بوعي (موثَّق): تثبيت tenant لكلّ chunk في rag `/ingest` · القفل الكامل للتبعيّات · تفعيل smoke الحيّ (مشغّل).

## 14) مقارنة أرشيفَي المستخدم: ERP bridge + بوّابة عقد UI (جلسة 2026-07-02، رأس الفرع: `5ea89a5`)

طلب المستخدم مقارنة أرشيفَين (كلاهما cef830b) وتنفيذ الصحيح. القرار: **zipB**.

| المكوّن | القرار + السبب |
|---|---|
| **اختيار zipB على zipA** | (`5ea89a5`) الأرشيفان متطابقان وظيفيّاً؛ zipA رشّ aliases الجسر على **كلّ** خدمة في v9/fixed compose ⇒ اسم `erp-bridge` يتحلّل إلى ~24 حاوية (DNS مبهم) وأغفل الـalias على خدمة الجسر في odoo-snippet/unified. zipB يضع الـalias على خدمة الجسر **وحدها**. السبب: صحّة DNS للشبكة — alias الخدمة يجب أن يكون فريداً للحاوية المقصودة. |
| **ERP bridge rename** | إعادة تسمية هويّة التشغيل `sahool-odoo-bridge`→`sahool-erp-bridge` (مفتاح الخدمة + logging + RLS-guard + عنوان FastAPI) مع إبقاء `sahool-odoo-bridge`/`odoo-bridge`/`ODOO_BRIDGE_URL` كـaliases DNS/env و`/api/odoo/` كمسار توافق. `ERP_BRIDGE_URL` القياسيّ الجديد. **المجلّد `services/odoo-bridge/` مُبقى** (سياق بناء/اختبار/إصدار). السبب: تعميم الجسر (ERPNext/Odoo/none) دون كسر النشرات القائمة. |
| **service-feature-ui-contract-gate** | بوّابة CI (`scripts/ci/service_feature_ui_contract_gate.py` + `config/service_feature_ui_contracts.json`) تثبت أنّ كلّ خدمة تشغيليّة/حسّاسة لها مستهلِك (UI/موبايل · بروكسي بوّابة · عقد داخليّ · عقد مهمّة). PASS 26/26. السبب: منع خدمات «يتيمة» بلا مستهلِك موثَّق. |
| **تصحيح توليف (لا نسخ أعمى)** | سطر `market_server.py` (109 حرف) كان يُلفّ بـruff format فيكسر اختبار المسح المتّصل (`os.getenv("ODOO_BRIDGE_URL`) ⇒ `# fmt: skip` (E501 متجاهَل بالمستودع). الفشل السباعيّ (sklearn + تصادم `main`) مُتطابق على الشجرة النظيفة ⇒ ليس انحداراً. |

## 15) FieldView كـ«متعاون يحقّق هدفاً»: محرّك الأهداف + دورة حياة التوصية (جلسة 2026-07-04، رأس: `777582b`)

طلب المستخدم — استلهاماً من مقال فلسفة تصميم الوكيل — تحويل FieldView من «أداة تعرض بيانات» إلى «متعاون يحقّق هدفاً حقليّاً». القوس: ٢٥ التزاماً (أساس→حوكمة→P0–P4→بطاقات إلهام→الطبقة المتوّجة).

| المكوّن | القرار + السبب |
|---|---|
| **بوّابة الدليل `canAct` (منع التوصية على دليل ناقص)** | (`777582b`) `buildObjectivePlan` يحسب `missingSources` من `EvidenceAvailability` الحيّة ويجعل `canAct = ready` فقط حين تكتمل كلّ المصادر المطلوبة. السبب الجوهريّ (من المقال): الوكيل لا يجب أن يوصي على دليل ناقص — الصدق يعني منع الإجراء وإظهار الناقص، لا تخمين تشخيص. التشخيص نفسه يبقى من محرّكات الحوكمة/الصحّة/الماء لا من الطبقة. |
| **دورة حياة التوصية كآلة حالات صريحة** | (`777582b`) `advanceLifecycle` يسمح بانتقالات صريحة فقط (مسوّدة→دليل→اعتماد→مهمّة→تنفيذ→متابعة→مراجعة→جودة)؛ لا قفز. الأثر (`outcome`) يبقى `unknown` حتّى مراجعة حقيقيّة (المستخدم/الصورة القادمة) — لا اختلاق نتيجة. `recommendationQuality` = `unknown` قبل المراجعة. السبب: قابليّة التتبّع الصادقة تتطلّب حالات صريحة وأثراً مقيساً لا مفترَضاً. |
| **`EvidenceAvailability` من الاستعلامات الحيّة فقط** | (`777582b`) في `MapHub`: كلّ مصدر = `true` حين تكون بياناته حاضرة فعلاً (imagery=imageryReadyCount>0 · weather=!!current · moisture=reading!=null …)، وإلّا `false`. السبب: لا افتراض تفاؤليّ — التوفّر يعكس الواقع فتمنع البوّابة الإجراء بصدق. |
| **«أنشئ مهمّة» موصول بأفعال حقيقيّة فقط** | (`777582b`) `onCreateTask` يوصل تشخيص الإجهاد ⇒ وضع تثبيت دليل ميدانيّ (`setPinMode`) الموجود أصلاً؛ لا نقطة backend مُختلَقة لإنشاء مهمّة مُستمرّة. السبب: لا زرّ أجوف — دورة الحياة تتتبّع محليّاً بصدق حتّى تتوفّر نقطة حقيقيّة. |
| **بطاقات الإلهام تعيد استخدام محرّكات backend القائمة** | (`d10c889`→`74df847`) مركز الموسم (`/phenology`+`/stage-actions`) · تكلفة الريّ (دفتر المياه `/water-efficiency`) · التتبّع (مواسم+مهامّ مكتملة). السبب: القيمة في تنسيق الإشارات الموجودة لسؤال واحد للفلاح، لا في بناء backend جديد. |

**درسان CI مُثبَتان:** (١) `ruff format --check` يمسح `services/` كاملةً — تنسيق ملفّين جديدين محليّاً لا يكفي (احمرّ `0d171f8` ⇒ مسح كامل `ba5e9d2`). (٢) خطأ enum الـruntime `FIELD_IMAGERY_BACKFILL_REQUESTED` (كان يُصدَر بلا تعريف ⇒ KeyError→500) ضبطه حارس المنصّة `test_emit_event_names.py` في Platform Unit Tests **لا** في `-m unit` — مؤلّفو الأرشيفات يشغّلون `py_compile` فقط (`2987c5e`).

**الحصيلة:** الطبقة مكتملة ومدفوعة (الفروع الثلاثة) وخضراء ١١/١١. **مؤجَّل بوعي:** SPATIAL-401 (يحتاج status/body) · MAP-QA (Playwright حيّ) · auth v21 (يحتاج docker logs) · v57.5-DB (Postgres/CI) · متابعتا D/C.

## 16) حارس مصدر الراستر ↔ الأنابيب الداخليّة (جلسة 2026-07-04، ن-22 — هذا الالتزام)

بلاغ تشغيل المستخدم: كلّ مهامّ `backfill_*` تفشل «HTTPException» بعد بناء الـVRT مباشرةً، والسجلّ لا يقول لماذا.

| المكوّن | القرار + السبب |
|---|---|
| **قبول المسار المحلّيّ الخام تحت `UPLOAD_DIR` فقط** | `_safe_raster_source` كان يقبل `file://`/http(s) فقط بينما backfill/process-from-stac/CDSE تمرّر مخرجاتها (VRT/GeoTIFF) كمسار خام ⇒ 400 يُسقط كلّ المهامّ. القرار: معاملة المسار المطلق كـ`file://` بنفس احتواء realpath تحت `UPLOAD_DIR` — **لا اتّساع أمنيّاً** (traversal/`/etc/passwd` مرفوضان كما كانا)، بديل «بادئة file:// عند كلّ مُستدعٍ» أهشّ (ثلاثة مواضع اليوم ومَن يضمن الرابع؟). |
| **`build_band_vrt(out_dir=main.UPLOAD_DIR)` في البوّابتين** | الـVRT كان يُكتب في `/tmp` — خارج المجلّد المسموح أصلاً، فقبول المسار الخام وحده لا يكفي. حارس ساكن يثبّت الوسيط في كلّ استدعاء. |
| **سجلّ فشل المهمّة يُلحِق `[status] detail` لـHTTPException** | النوع وحده («HTTPException») جعل البلاغ غير قابل للتشخيص. detail نصّنا المتحكَّم به (رسائل عربيّة ثابتة) — يُسجَّل داخليّاً فقط؛ `error_message` المكشوف عبر API يبقى رمزاً عامّاً (عقد #542 وحارسه الساكن أخضران). |

## 17) إنجاز «المؤجَّل» من تدقيقات سجلّ الأقمار v2/v3/v4 (جلسة 2026-07-05، ٥ مراحل)

خطّة عميقة شاملة لبنود مؤجَّلة بصدق (كانت تحتاج عاملاً/معماريّة). ٥ commits مستقلّة، بوّابات خضراء لكلٍّ.

| المرحلة/SHA | القرار + السبب |
|---|---|
| **م1 `fe4426b`** (v3-F1/3/4 + v4) | `list_available_asset_dates`: الحدّ على التواريخ المميَّزة (CTE) لا صفوف (تاريخ×مؤشّر) — كان يبتر خطّ السنتين. `DISTINCT ON` لصفّ متماسك بدل `MIN(cloud_pct)`+`MIN(scene_id)` من صفَّين. `fetch_latest_asset` واعٍ بالجودة بعد التاريخ. **v4 حرج:** `insert_raster_asset` كان لا يكتب أعمدة v105 (quality_score/aoi_cloud_pct/cloud_mask_sources) ⇒ الترتيب بالجودة بلا أثر — تُكتب الآن من stats؛ + cloud_mask_sources في provenance. بديل مرفوض: ترك quality_score NULL (يجعل م1.C زخرفة). |
| **م2 `8ed6272`** (v2-007/v3-6/7/8/9) | MapHub: حارس `has_cog` — لا معالجة لتاريخ تاريخيّ له COG جاهز. CDSE cache key: +tenant +بصمة هندسة (تصادم/تسريب عبر المستأجرين). حذف bbox اليمن الثابت (fail-closed). cdse-tilejson: +tid في رابط البلاطة (البلاطات `<img>` بلا auth ⇒ 403 بلا tid) + urlencode. object_store: fail-closed عند فشل رفع S3 المُهيّأ (لا file:// صامت غير قابل للخدمة). |
| **م3 `f440b3f`** (v2-011/004، v143) | عمود `asset_status` (pending/ready/stale/failed) + `geometry_revision` على raster_assets + فهارس. النَّسَب end-to-end: النماذج الأربعة تحمل geometry_revision، كلّ مواضع بناء ProcessRequest تمرّره، والمنصّة تحلّ `MAX(revision)` من field_geometry_history وتمرّره عبر imagery_automation. النَّسَب None عند الجهل (لا اختلاق). |
| **م4 `bdf703a`** (v2-005/010) | عامل `cache_invalidation_worker` (Pattern A): يستهلك طابور raster_cache_invalidations (كان بلا مستهلِك) — يحذف بلاطات الحقل + يعلّم الأصول stale + ينهي الصفّ. `tile_cache_maint` (وحدة خفيفة بلا FastAPI) للإبطال+الإخلاء (TTL/حصّة — لم يكن هناك). خدمة compose خلف راية `RASTER_CACHE_INVALIDATION_ENABLED` (نشر ثمّ تفعيل). +allowlist tenant-audit +RLS role-gate. **درس عزل يتكرّر:** اسم `main` العامّ يتصادم عبر الخدمات ⇒ استخرجتُ الدوالّ لوحدة فريدة بدل حقن sys.modules في الاختبار. |
| **م5 `5f52b63`** (v2-008/009) | جسر الكتالوج: `insert_raster_registry_entry` (يملأ raster_registry من كلّ أصل ناجح — كان يملؤه فقط REST يدويّ) + `insert_stac_item` (يستمرّ مشاهد backfill في stac_item_registry — كان بلا كاتب). كلاهما ON CONFLICT + ضبط مستأجِر (RLS FORCE+WITH CHECK) + `_clamp_score_0_100` للقيد. best-effort لا يُفشل المعالجة. |

**الحصيلة:** كلّ بنود المؤجَّل من v2 + كلّ v3 (عدا F2 المُصلَح سابقاً 528203b) + النتائج الحقيقيّة من v4 — مُنجَزة ومدفوعة. unit gate 2576 · production_validation_gate أخضر (v143، 149 ترحيلاً، 54 خدمة) · tenant-audit 0 · ruff/release نظيفة. **مؤجَّل بوعي:** التحقّق التكامليّ (`-m integration` بعد رفع Postgres+PostGIS) لتفعيل عامل الإبطال وملء الكتالوج فعليّاً على DB حيّ.

## 18) متابعات ما بعد الدمج: أمن bandit + v5 + بوّابة الإنتاج (2026-07-05)

| SHA | القرار + السبب |
|---|---|
| `65c96cd` | `hashlib.sha1(..., usedforsecurity=False)` لبصمة كاش CDSE — استعمال غير أمنيّ؛ يُرضي bandit B324 HIGH (كان يحجب Security Scan) وFIPS بلا تغيير سلوك. |
| `5cd765d` | رصد حفظ raster_assets (bool + سطر منظَّم + `persisted` في المهمّة) [v5-F1] + ملخّص فحص backfill [v5-F8]. F2/F4 (فحص لاتزامنيّ) مؤجَّل بصدق. |
| `947c9af` | إضافة `sahool-raster-cache-invalidation-worker` لقائمة سماح JOBS **الثانية** (`tests/security/test_phase12`) — بوّابة الإنتاج main-only سقطت لأنّ القائمة تعيش في موضعَين. + تجديد بصمات الإصدار. |

## 19) تحقّق تكامليّ على Postgres حيّ + إصلاح خلل الجسر الإنتاجيّ (2026-07-05)

| SHA | القرار + السبب |
|---|---|
| `12329c4` | إضافة ٦ اختبارات `-m integration` (عامل الإبطال + جسر الكتالوج + STAC + v143 + Phase-1 SQL) على Postgres+PostGIS الحيّ في CI. دُفِعت للفرع أوّلاً وحُجِز main حتّى الخضرة. |
| `c564d65` | إصلاح `$N::date`/`$N::timestamptz` ⇒ `$N::text::date`/`::timestamptz` في insert_raster_registry_entry/insert_stac_item — كانا يفشلان صامتاً (best-effort) فيُبقيان الكتالوج فارغاً في الإنتاج. كشفه الاختبار التكامليّ فقط. |

**تحديث الفجوة:** «التحقّق التكامليّ» — الطبقة القاعديّة (worker/bridge/STAC/SQL على DB حيّ) **مُنجَزة ومُثبَتة في CI**؛ يبقى التفعيل الحيّ الكامل عبر compose (رفع + RASTER_CACHE_INVALIDATION_ENABLED) بيد المشغّل (يحتاج Docker).

## 20) بنية backfill اللاتزامنيّة + STAC single-flight (2026-07-05، شريحتان)

| SHA | القرار + السبب |
|---|---|
| Slice A | single-flight في عميل STAC (خريطة key→Future) — miss متطابق متزامن = POST واحد؛ يتفادى stampede على Earth Search عند backfill متوازٍ [v6-F6]. |
| `10cb133` | v144 (backfill_runs/run_items + idempotency فريد + RLS) · نقطة تُرجِع run_id فوراً خلف راية · عامل فحص (Pattern A) يمسح خارج مسار الطلب + preflight + idempotent + threadpool؛ يعيد استخدام دوالّ main [v5-F1/F2/F4 · v6-F1/F2/F4]. |
| `c564d65` | إصلاح ربط تاريخ جسر الكتالوج (`::text::date`) — كان يفشل صامتاً؛ كشفه اختبار تكامليّ حيّ. |
| `ecc0061` | إزالة U+200F خفيّ (bandit B613 HIGH) من docstring العامل. |

**قرار انضباط مؤكَّد:** الشرائح ذات migration/worker/best-effort تُدفَع للفرع أوّلاً، ويُحجَز main حتّى خضرة *Integration Tests* (PostGIS حيّ) و*Security Scan* — لأنّ هذه الأخطاء لا تظهر في `pytest -m unit` المُحاكى.

## 2026-07-05 (ل) — تحويل CDSE + صدق «الحقيقة» (تدقيقات v8–v11)

| SHA | القرار + السبب |
|---|---|
| `fa19e83` | تدقيقات v8–v11 مجمّعة: CDSE historical search + persisted-truth + v145/v146 + قرّاء ready + tilejson poly. **السبب:** المُدقِّق شغّل على `d85673c` القديم فمعظم نتائجه أُغلِق سلفاً؛ الجديد ركّز على «الحقيقة الكاذبة» (completed≠persisted، stale يُقدَّم كصالح، dedupe على cog_uri). |
| `ff11e69` | إصلاح ترحيل v146: `DROP CONSTRAINT IF EXISTS backfill_runs_status_check` بالاسم الاصطلاحيّ (قيد v144 المضمَّن يُطبَّع `IN`→`= ANY` فتعذّر مطابقته ديناميكيّاً). **السبب:** فشل «Apply migrations» في Integration — اصطاده الفرع قبل main. مُثبَت على Postgres حيّ. |
| `820cd41` | البحث التاريخيّ **fail-closed 503** بلا اعتمادات CDSE (لا ارتداد صامت لـElement84) + `_run_processing` exc_info=True. **السبب:** طلب المستخدم «بالكامل من Copernicus» + تقرير copernicus_historical_backfill_fix (لوج «TypeError» عارياً بعد بناء VRT). |

**درس migration مؤكَّد:** القيد المضمَّن `CHECK (col IN (...))` يُسمّيه Postgres `<table>_<col>_check` ويُطبّعه `= ANY (ARRAY[...])` — فبحثه عبر `ILIKE '%IN%'` يفشل؛ استعمل `DROP CONSTRAINT IF EXISTS <conventional_name>` (idempotent). **مؤجَّل بصدق:** V8-05 (فصل مُنتقي التاريخ عن المعالجة — قرار UX) · V8-09 (fixed.yml dev-only موثَّق) · إخلاء `_layers` عبر العمليّات (يحتاج Redis pub/sub).

## 2026-07-05 (م) — إغلاق المؤجَّل المتبقّي

| SHA | القرار + السبب |
|---|---|
| `8a6d023` | V8-09: fixed.yml→sahool_app + إزالة تعطيل RLS (اتّضح أنّ sahool-migrate ينشئ الأدوار؛ التعليقات القديمة stale) + حارس يمنع sahool_user في DATABASE_URL. V8-05: MapHub لا يُطلق معالجة صامتة عند اختيار تاريخ (CTA صريح). v11-F3/F5: إخلاء `_layers` عبر قناة Redis (pub/sub) — لم يعد مؤجَّلاً. **السبب:** طلب المستخدم «أصلِح المتبقّي». |

**درس تلوّث اختبار (مُعاد):** لا تحقن `sys.modules["boto3"]` في حارس ساكن (لوّث sam2 في المجموعة الكاملة) — أكّد نصّيّاً بلا استيراد `main` الثقيل.

## 2026-07-05 (ن) — Landsat thermal-unique

| SHA | القرار + السبب |
|---|---|
| `2df1cf5` | Landsat = طبقة حرارية فريدة فقط (LST مباشر + مشتقات؛ لا تكرار NDVI/NDMI من Landsat). ترحيل v147 (backfill_runs.source). **السبب:** طلب المستخدم (تقرير+diff+zip) — CDSE/Sentinel-2 يبقى مصدر المؤشّرات النباتية. |

**درس تحقّق-قبل-دمج (مؤكَّد):** رقعة خارجيّة «9 passed» أخفت ثغرتَين لأنّ اختباراتها لم تُشغّل `_process_run`: (١) متغيّر مستعمَل بلا تعريف (NameError على كلّ تشغيلة)؛ (٢) ترحيل في MANIFEST فقط لا `run_migrations.sql` (يُفشِل بوّابة الإنتاج التي تطلب تطابق المُشغّلَين). لا تُطبّق رقعة خارجيّة بلا قراءة كاملة + تشغيل بوّاباتنا.

## 2026-07-05 (ن) — مصغّرات True Color + خنق CDSE + إعادة محاولة backfill التزايُديّ

| SHA | القرار + السبب |
|---|---|
| `03281cb` | (١) مصغّرات السجلّ الزمنيّ تُعرض True Color دائماً (معاينة طبيعيّة)؛ اختيارها يبدّل التاريخ فقط دون تغيير المؤشّر التحليليّ للخريطة. (٢) خنق Process API لـCDSE: بوّابة تباعُد على مستوى العمليّة (`CDSE_PROCESS_MIN_INTERVAL_SECONDS`) + حلقة إعادة محاولة محدودة تحترم `Retry-After` تمنع العامل من إغراق حساب CDSE بـ429 وفقدان مشاهد بصمت. (٣) صدق backfill التزايُديّ: عند تصادم idempotency-key لا يُسقَط العنصر بصمت — يُخطَّى إن كان الأصل ready، وإلّا يُعاد ربطه ويُعاد إلى queued ليُعاد سحبه (عنصر فشل سابقاً بـ429/عطل مؤقّت يُعاد فعلاً)؛ التصادم غير القابل للاستعادة يُحتسَب failed لا نجاحاً كاذباً. **السبب:** رقعتان + diff من المستخدم. بلا migration. unit 2623 · vitest 1047 · release 3147 checksums. |
| `ad49e73` | اعتماد الخطّ الزمنيّ التاريخيّ الأغنى لـMapHub (خيارات 3/6/12/24 · dedup · شريط مصغّرات · نطاق يحدّه الخادم لا قصّ 730 عميل) + جسر geometry صادق في platform `/imagery/refresh` (يقبل هندسة صريحة عند غياب صفّ fields، بلا هندسة يبقى 404) + `limit` في `/available-dates`. **السبب:** طلب المستخدم «اعتمد واجهة الزيب الأغنى» من `..._backfill_incremental_retry_hotfix.zip`. **تحقّق-قبل-دمج اصطاد عيبَين في الزيب:** اختبار `MapHubTwoYearTimeline` يؤكّد قصّ 730 مُزالاً + تسمية قديمة (كان سيفشل ضدّ MapHub نفسه)؛ و`platform_field_missing` ميّت (ruff F841). بلا migration. unit 2623 · vitest 1054 · release 3151. |

## 2026-07-06 (ن) — تحديث MinIO مع الانتباه للتبعيّات (تثبيت آخر إصدار بـconsole كامل)

| SHA | القرار + السبب |
|---|---|
| _(هذا الالتزام)_ | تحديث MinIO بحذرٍ للتبعيّات: **تثبيت `RELEASE.2025-04-22T22-12-26Z`** (آخر إصدار يحتفظ بالـadmin console الكامل) عبر `${MINIO_IMAGE:-…}` مُوحَّداً في كلّ ملفّات compose الأربعة + `.env.example`. **السبب:** بحث ويب أثبت أنّ MinIO المجتمعيّ جرّد الـconsole في `RELEASE.2025-05-24`، وأُرشِف المستودع (2026-04)، وسُحبت الصور من Docker Hub، وحملت الصورة الأخيرة CVE عالية؛ ونشرنا **يعتمد الـconsole** (`--console-address :9001`). لذا رفضنا «الأحدث» واخترنا آخر إصدار بـconsole كامل، قابلاً للتجاوز بـ`MINIO_IMAGE` للمشغّل. عميل S3 `boto3>=1.34.0` بلا ثغرات (`pip-audit` نظيف) ولا يتأثّر بإصدار خادم MinIO (S3 API مستقرّ). حارس `minio_s3_contract_gate` وُسِّع ليمنع الانحدار: كلّ صورة MinIO في compose يجب أن تكون بصيغة `${MINIO_IMAGE:-<الإصدار-المثبَّت>}` (لا hardcode/لا إصدار ما بعد إزالة console). المصادر: github.com/minio/minio/releases · blocksandfiles.com/2025/06/19 · chainguard.dev. الحُرّاس خضراء · compose config صالح. |

## 2026-07-07 (ن) — عنقدة مناطق الإدارة متعدّدة المؤشّرات (V60.3)

| SHA | القرار + السبب |
|---|---|
| 0b024af | **وصل المؤشّرات المساعدة (NDMI/RECI/MSAVI) + الانحدار بعنقدة مناطق الإنتاجيّة** (منهجيّة Management Zone Analyst — تجميع متعدّد المتغيّرات لا NDVI وحده). **السبب:** تدقيق التغطية (4 وكلاء) أظهر أنّ `basis="multi_index"` هو الافتراضيّ لكنّ العنقدة كانت NDVI فقط (`productivity_zones_clustering.py:209-215` قبل التعديل) — تسمية شكليّة، والمؤشّرات المحسوبة أصلاً (`band_math.py`) والطوبوغرافيا (`terrain_render.py`) غير موصولة. البحث الموثَّق أكّد أنّ العنقدة متعدّدة المتغيّرات (NDVI متعدّد الأزمنة + ECa + طوبوغرافيا) هي معيار الزراعة الدقيقة (Fridgen et al. 2004). النهج: `kmeans_nd` حتميّ نقيّ + معايرة min-max (تمنع هيمنة المقياس) + تعويض محايد للمفقود + ترتيب بمتوسّط NDVI الفعليّ (يحفظ score/التصنيف). **صدق:** توافق خلفيّ تامّ (بلا مساعدة ⇒ مطابق V60.1)، سقوط آمن (مساعدة مشوّهة/غير مُتراصفة تُسقَط)، `basis="ndvi"` صريح يُلغيها، والموجِّهات تعكس الميزات الفعليّة (لا اختلاق). المصادر: تدقيق `tasks/*.output` (4 وكلاء) · Fridgen et al. 2004 (MZA) · FAO WaPOR/WorldCereal للسياق. التحقّق: 28/28 وحدة · ruff نظيف · manifest 3256 checksum · CI معلّق. |

## 2026-07-07 (ن) — نموذج المشهد الموحَّد + الاقتراح الاحتياطيّ المُهيكَل (V63)

| SHA | القرار + السبب |
|---|---|
| 200b163 | **سدّ فجوتَين من تدقيق التغطية/التقرير الخارجيّ: `NormalizedScene` + سِجِلّ مزوّدين + اقتراح احتياطيّ مُهيكَل.** **السبب:** التقرير الخارجيّ أبرز غياب «نموذج مشهد موحَّد + سِجِلّ مزوّدين» (Phase 1) و«اقتراح بديل مُهيكَل عند فشل CDSE» (كان نصّ 503 حرّاً). النهج: منطق صرف بلا I/O (`raster_scene_model.py`) قابل للاختبار حتميّاً — `NormalizedScene` يلفّ مخرَج `stac_search_*` القائم دون تغيير سلوك (إضافيّ)، و`cog_ready` **مُشتقّ** من توفّر روابط النطاقات فعلاً (لا اختلاق)، و`PROVIDER_REGISTRY` يعلن `active=False` صراحةً لِـnasa_hls/planetary_computer (غير موصولَين) — صدق لا طموح. `provider_fallback_suggestion` مُدمَج في تفاصيل 503. **رفضتُ بناء WaPOR/NASA HLS الآن:** مسار تكامل HTTP خارجيّ لا يمكن التحقّق منه end-to-end بلا خدمة حيّة + اعتمادات (Earthdata) + تأكّد تغطية اليمن — نصف تنفيذه يخالف «لا نصف حلّ». المصادر: التقرير الخارجيّ · تدقيق `tasks/*.output` · بحث المزوّدين (Element84 بلا مصادقة، CDSE وحدات معالجة). التحقّق: 13 اختباراً أخضر (8 جديدة + 5 CDSE guard) · 200/1 نطاق raster · ruff نظيف · manifest 3257 · CI معلّق. |

## 2026-07-07 (ن) — وصل NormalizedScene + إثراء السِجِلّ بتغطية اليمن (V63.2)

| SHA | القرار + السبب |
|---|---|
| 8227fa1 · 4a9eeef | **وصلتُ NormalizedScene في استجابة `/imagery/timeseries` (بجانب الخام، غير كاسر) وأثريتُ PROVIDER_REGISTRY بتغطية اليمن.** **السبب:** المُراجِع طلب (١) حُرّاس عقد ثلاثة [مزوّد-غير-نشط · اقتراح-CDSE-محصور · acquisition_date≠processed_at]، و(٢) استهلاك فعليّ للنموذج لا عقداً معلَّقاً، و(٣) تصنيف تغطية اليمن المُتحقَّقة لـWaPOR/WorldCereal/HLS. النهج: التطبيع عند حدّ الاستجابة (يبقى مسار backfill رشيقاً) + حارس انحدار يمنع إسقاط `scenes`؛ وإضافة wapor/worldcereal كمُسجَّلَين **active=False** ببيانات وصفيّة (coverage_yemen/resolution/recommended_use) — **صدق: لا تفعيل قبل مُحوِّل + اختبار عقد** (نفس مبدأ «لا نصف حلّ»). WaPOR L2 100م يغطّي اليمن (الشرق الأدنى)، WorldCereal 10م عالميّ، HLS 30م عالميّ — الأولويّة WaPOR→WorldCereal→HLS. المصادر: تحقّق المُراجِع لتغطية اليمن · FAO WaPOR v3 (L1 300م/L2 100م/L3 20م، 2018→) · ESA WorldCereal (10م، CC-BY) · NASA HLS v2 (30م، كلّ اليابسة). التحقّق: 21 اختبار V63 أخضر · 193 نطاق raster · ruff · manifest 3259 · CI معلّق. |

## 2026-07-07 (ن) — عدم يقين نموذج المحصول (V64)

| SHA | القرار + السبب |
|---|---|
| b2c9897 | **فرض «لا غلّة بلا عدم يقين» على `wofost_adapter.simulate` + تمرير مدى الربح في `profit_planner`.** **السبب:** تدقيق المراحل 9–15 أبرز أنّ الغلّة تتدفّق كنقطة عارية (`wofost_adapter:135`, `profit_planner:49`) — مخالفة مبدأ عدم إظهار غلّة بلا عدم يقين. النهج: نطاق **نموذجيّ** صريح (`deterministic_model_band`) مُرفَق عند نقطة الاختناق الوحيدة (كلّ مسار يحمله)، يتّسع بأمانة بنقص المدخلات وقرب عتبة العامل المُقيِّد، كلّ موسِّع مُدرَج (لا رقم بلا سبب)، سقف 60٪، حتميّ. **صدق حاسم:** فصلته صراحةً عن نطاق conformal التجريبيّ القائم (`core/engines/yield_interval.py`) الذي يتطلّب بيانات حصاد محلّية ويعيد pending دونها — لم أدّعِ تلك الصرامة. `profit_planner` يمرّر مدى ربح توافقيّاً. المصادر: تدقيق `tasks/a3f58244058676ed9.output` (P10) · `yield_interval.py` (Vovk/Lei conformal). التحقّق: 9 حُرّاس + 18 اختبار قائم أخضر · ruff · manifest 3260 · CI معلّق. |

## 2026-07-07 (ن) — بطاقة ذكاء الحقل الموحّدة (V65)

| SHA | القرار + السبب |
|---|---|
| 9822dda | **بناء مُجمِّع بطاقة ذكاء الحقل + وصله في `/field-intelligence/analyze`.** **السبب:** تدقيق المراحل 9–15 + التقرير الخارجيّ (P5/P9): الأوليّات موجودة لكن لا بطاقة قرار **واحدة** تجمع المشهد/المزوّد/NDVI-تاريخيّ/العجز/المناطق/التنبيهات/الأدلّة/الثقة. النهج: منطق صرف بلا جلب (يستهلك مخرَج analyze + إشارات مُمرَّرة)، كلّ قسم حاضر أو `missing` بسبب (لا اختلاق)، `completeness` يعكس توفّر البيانات فقط. وصل إضافيّ غير كاسر. **صدق:** لم أُلفّق أقساماً غائبة (مشهد/مزوّد/تاريخ NDVI تظهر missing في المسار الحاليّ حتّى يُغذّيها المُنسّق). المصادر: تدقيق `tasks/a3f58244058676ed9.output` (P9) · التقرير الخارجيّ P5. التحقّق: 8 حُرّاس + 285 شريحة منصّة + 5 endpoint أخضر · ruff · manifest 3261 · CI معلّق. |

## 2026-07-07 (ن) — سِجِلّ المصادر البحثيّة منفصلاً عن مزوّدي الصور (V63.3)

| SHA | القرار + السبب |
|---|---|
| d2da16e | **فصل مصادر Gitee البحثيّة/المكتبات في `RESEARCH_REGISTRY` مستقلّ عن `PROVIDER_REGISTRY`.** **السبب:** بحث المُراجِع في Gitee أظهر مكتبات قيّمة (PaddleRS للـsegmentation/boundary/change-detection، GeoTrellis Landsat لتصيير NDVI/NDWI ديناميكيّ، CDSystem لنمط خدمة استدلال GPU) لكنّها **ليست مزوّدي صور**. لمنع الخلط: سِجِلّ منفصل، `provides_imagery=False` لكلّ عنصر، حُرّاس تضمن انفصال المجموعتين ومنع تسرّب مصدر بحثيّ إلى active/planned. **صدق:** Gitee مصدر أفكار/مكتبات لا صور خام — المزوّدون يبقون CDSE/Element84/PC/NASA HLS. المصادر: بحث المُراجِع (Gitee) · PaddleRS/GeoTrellis/CDSystem. التحقّق: 23 اختبار V63 أخضر · ruff · manifest 3263 · CI معلّق. |

## 2026-07-07 (ن) — النشرة الإقليميّة لحالة المحاصيل (V66)

| SHA | القرار + السبب |
|---|---|
| _(هذا الالتزام)_ | **بناء نشرة حالة المحاصيل الإقليميّة (P12) كمنطق صرف آمن الخصوصيّة.** **السبب:** المرحلة 12 كانت غائبة كلّيّاً (لا تجميع حقل→مديريّة→محافظة). النهج: تصنيف GEOGLAM من شذوذ NDVI مقابل التاريخ، مع **أرضيّة k-anonymity** (مجموعة < العتبة تُكتَم بلا أرقام) ومنع معرّفات الحقول — تجميع آمن عبر المستأجرين. **صدق:** بلا تاريخ ⇒ unknown لا تخمين؛ الثقة من التغطية. الجلب/RLS يبقيان في الراوتر (الوحدة لا ترى إلّا المُمرَّر). المصادر: تدقيق `tasks/a3f58244058676ed9.output` (P12) · GEOGLAM Crop Monitor (بحث المزوّدين). التحقّق: 8 حُرّاس · ruff · manifest · CI معلّق. |

## 2026-07-07 (ن) — أدوات المستشار: get_water_productivity + generate_report (V67)

| SHA | القرار + السبب |
|---|---|
| _(هذا الالتزام)_ | **إضافة أداتَي المستشار المفقودتين (P13) كقراءة فقط + إعلانهما للمزوّد.** **السبب:** التقرير الخارجيّ/تدقيق P13: الأداتان غائبتان من السجلّ (`get_water_productivity` مفقودة، `generate_report` مفقودة). أُضيفتا بثوابت القراءة (low/mutating=False/approval=False)، مُعلَنتين فعليّاً في `provider_tooling` (لا مجرّد تعريف)، ومرآتهما في `_TOOL_META` (حارس no-drift). **صدق:** `generate_report` تكوين/قراءة لا إرسال — تُميَّز عن الأدوات عالية الخطر. المصادر: تدقيق `tasks/a3f58244058676ed9.output` (P13). التحقّق: 6 حُرّاس + 190 نطاق أدوات/حوكمة أخضر · ruff · manifest · CI معلّق. |

## 2026-07-07 (ن) — راوت النشرة الإقليميّة (V66.1)

| SHA | القرار + السبب |
|---|---|
| _(هذا الالتزام)_ | **وصل V66 بنقطة HTTP مُقيَّدة بالمستأجِر (`/api/v1/regional/bulletin`).** **السبب:** تقرير تحقّق السلسلة أبرز V66 كوحدة بلا راوت — الفجوة الوحيدة الصريحة. اكتشفتُ أنّ `fields.gov` موجود (المحافظة) و`zonal_stats.mean` يوفّر NDVI لكلّ حقل عبر الزمن ⇒ استعلام حقيقيّ ممكن. النهج: محوّل صرف `bulletin_rows_to_records` (مُختبَر وحدةً) + راوت رفيع يستعمل `tenant_connection` (RLS) + `require_permission(FIELD_VIEW)`، مع إغلاق آمن صادق (DB معطّلة ⇒ فارغ+سبب؛ تعذّر ⇒ 503؛ لا NDVI ⇒ unknown). أرضيّة الخصوصيّة + لا معرّفات حقول من المنطق الصرف. SQL يُغطّى بالتكامل (لا الوحدة) — نمط المستودع القائم. المصادر: تقرير التحقّق · `fields.gov` (v9_foundation:68) · `zonal_stats` (v14_imagery_storage). التحقّق: 13 حارساً أخضر · 69 شريحة منصّة · التطبيق يسجّل الراوت · ruff · manifest · CI معلّق. |

## 2026-07-07 (ن) — تغذية بطاقة ذكاء الحقل من قاعدة المنصّة (V65.1)

| SHA | القرار + السبب |
|---|---|
| _(هذا الالتزام)_ | **تغذية أقسام المشهد/NDVI-التاريخيّ في بطاقة V65 من قاعدة المنصّة (لا cross-service).** **السبب:** تقرير التحقّق P1: الأقسام كانت `missing` لأنّ الراوت لم يغذّها. اكتشفتُ أنّ `zonal_stats.mean` (تاريخ NDVI) و`raster_assets` (أحدث مشهد) في **قاعدة المنصّة ذاتها** ⇒ لا حاجة لنداء raster-service. النهج: محوّل صرف `card_signals_from_db_rows` (مُختبَر) + تحويل الراوت إلى async مع جلب مُقيَّد بالمستأجِر (RLS) **بسقوط آمن**: أيّ تعذّر ⇒ إشارات فارغة ⇒ البطاقة مطابقة لسلوك ما قبل التغذية (لا انحدار ممكن). **صدق:** التزمتُ «evidence حقيقيّ أو missing صريح» — provider_status يبقى missing عمداً (خدمة أخرى، لا mock). SQL يُغطّى بالتكامل. المصادر: تقرير التحقّق P1 · `zonal_stats`/`raster_assets` (v14). التحقّق: 4 حُرّاس + 133 شريحة منصّة + endpoint أخضر · الراوت async ومُسجَّل · ruff · manifest · CI معلّق. |

## 2026-07-07 (ن) — جسر provider_status عبر الخدمات (V65.2)

| SHA | القرار + السبب |
|---|---|
| _(هذا الالتزام)_ | **تغذية provider_status في البطاقة من raster-service (`/v1/providers/status`).** **السبب:** المُراجِع طلب جسر أدلّة platform→raster لملء provider_status. النهج: `fetch_provider_status` عبر `_get_json` القائم (آمن الفشل: raster متعذّر/بلا httpx ⇒ None) + محوّل صرف `provider_status_signal` (مُختبَر) + تغذية في الراوت **خارج معاملة القاعدة** بسقوط آمن. **صدق:** raster متعذّر ⇒ القسم missing بسبب صريح (لا mock)؛ active يعكس الوصل الفعليّ. المصدر الواحد الصادق = V63.4. نداء HTTP يُتحقَّق بالتكامل. التحقّق: 4 حُرّاس + 12 بطاقة + endpoint أخضر · ruff · manifest · CI معلّق. |

## 2026-07-07 — fast-forward main/develop → 27be67c (المسار الداخليّ evidence-driven)
- **القرار:** بعد CI أخضر على 27be67c، fast-forward `main` و`develop` من 712890a → 27be67c (تقديم سريع نظيف؛ 712890a سلف مباشر).
- **المحتوى:** V68.2/68.3 (ERA5-Land) · إلغاء حجب ecdsa · V65.3–65.5 (حالة/تربة/طقس) · V72 (تضاريس) · V71/V73/V73-UI (رياح/مصدّات + NASA POWER) · V74/74-UI (Evidence Graph) · V75/75.1 (Evidence Graph Persistence + إصلاح تصنيف internal).
- **السبب:** المسار الداخليّ (بطاقة الذكاء/تضاريس/رياح/رسم أدلّة/استمرار) مكتمل، مُختبَر، وأخضر. المؤجَّل (WaPOR/WorldCereal/OlmoEarth) خارجيّ الاعتماد؛ Drift-Geometry + normalized graph مرحلة 2.

## 2026-07-08 — إغلاق حلقة التوصية (٤ جسور) + fast-forward → 69596a1
| SHA | القرار + السبب |
|---|---|
| `09fcc71` | **جسر #2 نَسَب مصدر التعلّم (v151).** **السبب:** تحديثات التعلّم بلا رابط مصدر ⇒ لا يُستعلَم «أيّ نتيجة أنتجت هذا التحديث». النهج: أعمدة مصدر + traceability_status؛ تحديث غير مُتتبَّع ⇒ rejected_untraceable فلا يُطبَّق. **صدق:** لا سياسة من مصدر مجهول. |
| `3651764` | **جسر #3 موفِّق نموذجَي النتائج.** **السبب:** outcome_record و recommendation_outcomes متوازيان؛ أيّ مستهلِك يجب أن يوفّق. النهج: موحِّد قراءة واحد بوسم source_model/kind يربطهما عبر dispatch_decisions. **قرار:** متكاملان لا مكرّران (لا دمج جدولَين). |
| `16d8d8a` | **جسر #4 إيقاف recommendation_feedback (v152).** **السبب:** الفحص الأعمق أثبته مكرّراً ميّتاً (الموطن الحيّ recommendation_outcomes/farm_operations_ledger/water_ledger). **قرار:** إيقاف موثَّق بتعليق + حارس ساكن يمنع كاتباً؛ **لا كاتب** (يُعيد تجزئة #3) و**لا DROP** (سلامة بيانات). |
| `69596a1` | **جسر #5 سلامة مرجعيّة — كشف لا فرض FK.** **السبب:** التدقيق رصد إمكان الأيتام؛ الفحص أثبت غياب FK **مقصوداً** (recommendation_id نصّيّ vs UUID · decision_id ربط ليّن يحفظ RLS · كُتّاب متعدّدون — فرض FK يكسر الإدراج). **قرار:** بناء **كشف أيتام** دوريّ (`core.loop_referential_integrity`) للمراجعة لا الحجب؛ **لا migration**. يُكمِل آخر بند التدقيق. |
| `3651764→69596a1` | **fast-forward main+develop.** **السبب:** الجسور الأربعة خضراء (CI #3428/#3431/#3434/#3435)، 69596a1 سلف خطّيّ لـ3651764 ⇒ تقديم سريع نظيف بلا دمج. |

## 2026-07-08 — دمج أرشيف المستخدم: حدود الملكية P0→P1.4 (`2602ba6`)
| SHA | القرار + السبب |
|---|---|
| `2602ba6` | **دمج طبقة تصلّب حدود الملكية P0→P1.4 من أرشيف المستخدم.** **السبب:** طبقة متماسكة مبنيّة على `017d38f` (تحقّق-قبل-دمج أكّد الأساس) تُثبّت حدود الخدمات بحُرّاس CI قبل أيّ استخراج، وتوصِل موحِّد النتائج (جسر #3) بمسارات القراءة (الخطوة الآمنة التالية التي أشرتُ إليها). **صدق مصون:** stub الطقس يعلن عقداً صادقاً لا runtime وهميّاً · النتائج المعلّقة لا تضخّم success_rate · الجداول الاختياريّة تسقط لصفر لا 503. **قرار حدّ:** لا استخراج فعليّ (تجميد الحدود أوّلاً) — راستر/طقس/قرار تبقى في المنصّة خلف حُرّاس منع النموّ. **صدق الدلتا:** عُزِلت 35 ملفّاً حقيقيّاً في `work_p13` لا جذر الأرشيف (الجذر نسخة قديمة). التحقّق: 61+198 اختباراً · ruff · release 3428 · CI معلّق. |

## 2026-07-08 — دمج أرشيف المستخدم: تنظيف واجهة الراستر P2 (`bdbd2ae`)
| SHA | القرار + السبب |
|---|---|
| `bdbd2ae` | **دمج طبقة واجهة الراستر P2 من أرشيف المستخدم (فوق df1a706).** **السبب:** توحيد نداءات الراستر عبر `raster_service_client` يمنع تسرّب تفاصيل النقل داخل المنصّة ويثبّت الحدّ بحُرّاس CI (خطوة نحو الاستخراج بلا استخراج محفوف). **صدق مصون:** RBAC/tenant قبل التوكيل · raster المالك الوحيد · لا X-Agent-Token للمتصفّح · لا تلفيق. **رفض دماغ الأرشيف:** 3 ملفّات brain ارتدّت لـ69596a1 ⇒ حُفِظ الدماغ الحاليّ ومدخل P2 كُتِب يدويّاً (قاعدة احفظ إضافاتك). **عيبان أُصلِحا:** تصادم اسم `get_field_terrain` (كان يُعطّل DEM auto-fill صامتاً بـTypeError مبتلَع ⇒ None دوماً) بـalias؛ وE402/ترتيب في imagery_automation. التحقّق: 47 حارس + 3416 اختبار منصّة · ruff · release 3456 · CI معلّق. |
