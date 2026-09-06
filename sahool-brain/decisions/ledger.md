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

## 2026-07-08 — دمج أرشيف المستخدم: تحقيق runtime لخدمة الطقس P3 (`017c035`)
| SHA | القرار + السبب |
|---|---|
| `017c035` | **دمج تحقيق runtime لخدمة الطقس P3 (فوق P2).** **السبب:** حدّ P1 جمّد ملكيّة الطقس على stub؛ P3 هو الاستخراج المُخطَّط — سطح runtime حقيقيّ (Open-Meteo/نوافذ عمليّات/بلاطات) مع إبقاء مسارات المنصّة التوافقيّة (لا قطع). **صدق مصون:** لا توصية عمليّات بلا دليل طقس · بلاطات JSON لعرض العميل لا مزوّد خارجيّ · العقد يعلن runtime صراحةً. **تطبيق جراحيّ:** طُبِّقت 13 ملفّ P3 حقيقيّ فقط؛ رُفِضت 13 نسخة قديمة من الأرشيف (fields/imagery_automation/raster_service_client/اختبارات P0-P2/brain) لأنّها تسبق تنسيقي وإصلاح تعطّل DEM الصامت (get_field_terrain) — النسخ الأعمى كان سيُرجِع الإصلاحات. التحقّق: حُرّاس + 3420 اختبار منصّة + 3 خدمة · ruff · release 3470 · CI معلّق. |

## 2026-07-08 — قطع واجهة الطقس P3.4/P3.5 + إصلاحا انحدارَين
| SHA | القرار + السبب |
|---|---|
| `c47e077` | **إصلاح انحدار البلاطة المحايدة في weather-service.** **السبب:** استخراج P3 أسقط ضمان «بلاطة محايدة لا 500/إغراق» (طلب مستخدم صريح). أُصلِح في الخدمة + مُثبَت. مستقلّ عن القطع (لذا commit منفصل مبكّر). |
| `f6d2a9f` | **جعل raster_service_client آمن الاستيراد بلا fastapi.** **السبب:** رقعة P2 كسرت طبقة CI unit (تُشغَّل بلا fastapi) عبر imagery_automation→raster_service_client→fastapi. الحلّ: استيراد HTTPException كسولاً + حارس AST. قرار: hotfix منفصل لأنّه إصلاح P2 يفكّ حجب CI. |
| `21c59cd` | **قطع واجهة الطقس P3.4 + الكنس P3.5 (مع هجرة 16 اختباراً).** **السبب:** المستخدم اختار «إنجاز القطع مرحلةً-مرحلةً مع هجرة الاختبارات». المسارات التسع صارت واجهات؛ السلوك الذي انتقل للخدمة نُقِلت اختباراته إليها؛ اهتمامات المنصّة حُوِّلت لـmock الواجهة. صدق: بلاطة محايدة عبر الحدّ · لا تلفيق · بقايا مركّبة موثَّقة معلّقة لـP4. subagent نفّذ الهجرة، والمنسّق تحقّق مستقلّاً. |

## 2026-07-09 — Decision SoR final certification (P0-5) + رفض إصلاح CI مُكرَّر أضيق (`9cc6b2a`)
| SHA | القرار + السبب |
|---|---|
| `9cc6b2a` | **دمج طبقة الشهادة النهائيّة (P0-5) قراءة-فقط لترقية decision-service.** **السبب:** الطبقة الأخيرة قبل السماح بترقية إنتاجيّة فعليّة يجب أن تكون قابلة للتدقيق وبلا كتابة. تحقّقتُ يدويّاً من الثلاثة سكربتات الجديدة (`production_promotion.py`/`read_side_compare.py`/`rollback.py`): لا `INSERT`/`UPDATE`/`DELETE` في أيٍّ منها؛ `rollback.py` تحديداً يطبع خطّة نصّيّة ثابتة فقط بلا تنفيذ. **قرار حدّ:** لم يُنسَخ ملفّ الـworkflow من الأرشيف (يفتقر إصلاح jwt/pip-install من `5af67ea`) — طُعِّمت خطوة/حارس P0-5 يدويّاً على النسخة الحاليّة. **رفض مُكرَّر:** تقرير + أرشيف `ci_pyjwt_fix` منفصلان اقترحا استبدال خطوة تثبيت التبعيّات الحاليّة (الأوسع، تشمل `tests_v9/requirements-test.txt`+`pillow`) بخطوة أضيق — رُفِض الاستبدال بصفته انحداراً، واعتُمِد فقط حارس الانحدار المُكيَّف على نصّ الخطوة الفعليّة لمنع تراجع الترتيب مستقبلاً. التحقّق: بوّابة P0-5 مستقلّة · 62 حارس منصّة · 2806 اختبار unit · ruff نظيف · YAML صالح · release 3611 checksum · CI معلّق. |

## 2026-07-11 — Zero-Legacy راتشِت ET0 #1 (field_state_projection → منتج المحرّك) (`50b21b5`)
| SHA | القرار + السبب |
|---|---|
| `50b21b5` | **ترحيل `field_state_projection._et0_from_weather_payload` من نواة ET0 محلّيّة إلى مستهلِك لمنتج محرّك الطقس (`get_et0_product`)، وإفراغ مدخلته من allowlist (6→5).** **السبب:** توجيه المستخدم الاستراتيجيّ (Ratchet Strategy) — كلّ إزالة من allowlist يجب أن تكون **ترحيلاً حقيقيّاً** للمحرّك لا إعادة تسمية/تفاديَ حارس. النواة المحلّيّة (`water_balance.compute_et0`⇒`core.engines.et0`) استُبدِلت باستدعاء المنتج المرجعيّ؛ صيغة FAO-56 تُنفَّذ في المحرّك حصراً. **قرار عقد:** أُبقيَ **fail-closed→None** (لا 503) للحفاظ على دلالة best-effort للحالة القانونيّة (إسقاط تكميليّ؛ غياب المحرّك يُغيّب `etc_mm` دون كسر التحكيم) — يختلف عن مسارات season/crop_twin التي صارت 503 لأنّها استجابات مباشرة. **قرار حارس:** حُذفت heuristic الاسم `_et0_from*` (كانت لتتبّع هذا المُنتِج المحلّيّ حصراً؛ بعد الترحيل الدالّة مستهلِك لا نواة، فالإبقاء عليها كان سيَشِمُّ مستهلِكاً بريئاً) — دفاعيّ ومُبرَّر. التحقّق: CI أخضر 12/12 job (weather-engine-formula-guard canonical+5 · Platform Unit 3678 · Unit 2870 · Integration · Security) · inventory 884 route · bundle 3921 checksum. main/develop تقدّمتا fast-forward لـ`50b21b5`. أرشيف مُرسَل. |

## 2026-07-11 — Zero-Legacy راتشِت ET0 #2 (water_balance → منتج المحرّك) (`0b354d7`)
| SHA | القرار + السبب |
|---|---|
| `0b354d7` | **حذف نوى ET0 التشغيليّة من `api/water_balance.py` (compute_et0/et0_penman_monteith/et0_hargreaves/_extraterrestrial_radiation/ET0Method) وترحيل مساراتها إلى منتج محرّك الطقس بالحقن؛ allowlist 5→4.** **السبب:** استمرار Ratchet Strategy — أكبر نواة ET0 حيّة (مسار الريّ/ميزان الماء) رُحِّلت فعليّاً لا تفادياً. `water_balance()`/`water_balance_auto()` صارتا تستقبلان `et0_mm` محقوناً؛ المُوجِّهات (`/water-balance`, `/scenario/temperature`, `/scenario/rainfall`) async تجلب `get_et0_product` وتحقن. **قرار عقد (تغيير سلوكيّ مُتبنّى):** هذه المسارات صارت **fail-closed 503** عند تعذّر المحرّك — متّسق مع سابقة season/crop_twin/scenario-GDD وفلسفة fail-closed (استجابات مباشرة، لا قراءة تكميليّة كـfield_state). **حذف ظلّ ET0 الإرثيّ** في irrigation_recommendation: غرضه المُعلَن (إثبات إعادة المحرّك للصيغة بأمانة قبل الحذف) تحقّق عبر الراتشِتات، فحُذف الآن. **قرار اختبارات:** اختبارات النوى المحذوفة أُزيلت (النواة تُختبَر في خدمة الطقس)؛ تحقّق FAO-56 الزراعيّ أُعيد توجيهه لنواة `core.engines.et0` الباقية (لا إضعاف — النواة الكنسيّة نفسها)؛ حُقنت قيمة et0 مرجعيّة ثابتة في اختبارات منطق الميزان (تختبر الحساب/السياسة لا نواة ET0). subagent نفّذ حقن tests_v9 المُوجَّه، والمنسّق تحقّق مستقلّاً بالبوّابة الكاملة (لا اعتماد على تقرير subagent). التحقّق: guard (canonical+4) · unit 2868 · platform 3666 · inventory 884 route · bundle 3921 checksum · ruff. CI معلَّق قبل التقديم السريع. |

## 2026-07-11 — Zero-Legacy راتشِت ET0 #3 (weather_server MCP → منتج المحرّك) (`ed21a56`)
| SHA | القرار + السبب |
|---|---|
| `ed21a56` | **حذف نواة Hargreaves السطريّة المستقلّة من خادم MCP للطقس وترحيل أداة `calculate_hargreaves_et0` لاستهلاك منتج ET0 من محرّك الطقس عبر HTTP؛ allowlist 4→3.** **السبب:** استمرار Ratchet Strategy — هذه كانت **نواة ET0 ثانية حقيقيّة** خارج المحرّك (لا مجرّد غلاف)، عاشت بسبب عزل خادم MCP (يستورد shared/ فقط، لا core/). بدل «نقل core→shared» المؤجَّل، الحلّ الأنظف والأصحّ معماريّاً: الأداة تصبح **مستهلِكاً للمحرّك الكنسيّ** عبر `POST /v1/weather/agro/et0` (خدمة weather-service على نفس شبكة compose، بلا مصادقة داخليّة). **قرار عقد (بتوجيه المستخدم):** fail-closed **بنتيجة أداة مُهيكَلة** لا 503 خام — `{status:"unavailable", reason, et0_mm:null, quality_status:"insufficient", limitations}` عند تعذّر المحرّك/5xx/et0 مفقود (أنظف لمستهلك أداة MCP من خطأ HTTP)؛ `t_min>t_max` يبقى 400 (خطأ عميل متمايز). حُذف `ra_mj_m2_day` صراحةً (grep: صفر مستهلك). **قرار توصيل/هويّة:** `WEATHER_SERVICE_URL` + `SAHOOL_AGENT_TOKEN` (كلاهما في `.env.example`) وُصِلا في بلوك `sahool-weather-mcp` v9/fixed/light؛ العميل يُرسِل `X-Agent-Token` (defense-in-depth؛ النقطة الداخليّة بلا مصادقة اليوم) + `X-Service-Name` (correlation) + timeout 20s. **قرار حارس:** لا تغيير في الحارس القائم (بصمة Hargreaves اختفت) + **اختبار قبول جديد** (`test_mcp_weather_et0_engine_delegation.py`, 8 يمرّ): حارس انحدار ساكن (لا ثوابت/لا نواة محلّيّة، يفوّض للمحرّك) + 6 سلوكيّ (تعيين المنتج · توكن · unavailable لكلّ مسار فشل · مدخل غير صالح 400). التحقّق: guard (canonical+3) · compose-env-contract-gate · unit **2876** · inventory 884 route · bundle 3921 checksum · ruff · 3 YAML صالحة. CI معلَّق قبل التقديم السريع. |

## 2026-07-11 — Zero-Legacy راتشِت ET0 #4 (weather_analytics → سلسلة المحرّك) + خارطة WX-10..CI-11 (`38a1ea9`)
| SHA | القرار + السبب |
|---|---|
| `38a1ea9` | **ترحيل weather_analytics عن نواة Hargreaves محلّيّة إلى منتج سلسلة ET0 من محرّك الطقس؛ allowlist 3→2.** **قرارا المستخدم:** (١) **المحرّك يملك الفلك** — بدل تمرير DOY مشتقّ، وُسِّع `et0_series_product` ليقبل `daily_dates` (تواريخ ISO) فيشتقّ المحرّك DOY لكلّ يوم؛ يُلغي الانجراف الفلكيّ في السجلّات المتفرّقة/متعدّدة السنوات (أدقّ من DOY-start التسلسليّ، والتاريخ هو الحقيقة). (٢) **تدهور جزئيّ لا 503** — تعذّر المحرّك ⇒ `analysis_status="partial"` مع بقاء تحليل الحرارة/الصقيع/الرياح/المطر كاملاً و`availability` map + `unavailable_products` صريحة (لا null-guessing، لا اختلاق). التحقّق: guard (canonical+2) · unit 2880 · platform 3666 · weather-service 82 · inventory 884 · bundle 3922 · ruff. CI معلَّق قبل التقديم السريع. |
| roadmap | **اعتماد خارطة معماريّة لِما بعد Zero-Legacy** (WX-10 CanonicalWeatherState كـ**State Product** ⇒ ET0/VPD/GDD مشتقّات منه → WX-11 Capability Registry → CI-7 Canonical Inputs → CI-8 CropRecommendationContext → CI-9 Policy Engine → CI-10 Knowledge Layer → CI-11 Crop Learning Engine → Agricultural OS). **السبب:** توحيد العقود والملكيّة يقلّل التعقيد الحاليّ وينسجم مع Zero-Legacy/Crop Intelligence؛ الشرط المسبق إتمام allowlist=0 (ملكيّة المحرّك). التفصيل: [`decisions/architecture_roadmap_wx10_ci11.md`](architecture_roadmap_wx10_ci11.md). البذرة: `availability` map في راتشِت #4. |

## 2026-07-11 — Zero-Legacy راتشِت ET0 #5 (fao56 → ET0 محقون + حذف الميّت) (allowlist 2→1)
| SHA | القرار + السبب |
|---|---|
| _(commit branch-first)_ | **حذف نوى ET0/GDD/الريّ من `core/engines/fao56.py` وجعل `compute_etc_dual` يستهلك ET0 محقوناً حصراً؛ allowlist 2→1.** حُذفت `penman_monteith_et0` (غلاف لـcore.engines.et0) + `gdd_daily`/`gdd_accumulate` (ميّتة إنتاجيّاً؛ GDD يملكه weather-service) + **`compute_irrigation`+`SoilZone`+`IrrigationResult` كاملةً**. **قرار المستخدم (حاسم):** `compute_irrigation` **تُحذَف لا تُرحَّل** — لا مستهلك إنتاجيّ (irrigation_plan يستعمل `compute_irrigation_plan`)، وتحقّقتُ صراحةً من **صفر dynamic dispatch** (لا getattr/registry/tool-manifest/string-map) قبل الحذف؛ إبقاء مساعد مُهمَل يترك سطحاً إرثيّاً. `compute_etc_dual` يتطلّب `et0_override` مطلوباً (يرفع ValueError بدونه). **قرار معماريّ (قاعدة المستخدم الحاسمة):** الدالّة العلميّة تبقى **نقيّة** تستهلك ET0 محقوناً — الاستدعاء الخارجيّ للمحرّك يبقى في طبقة router/service **فقط**، لا داخل الدالّة. `routers/etc_dual.py` يجلب `get_et0_product` بطقس اللقطة، **fail-closed 503** بلا احتياطيّ/كاش بائت/يوم-سابق، ويُلحِق **نَسَب ET0** (method/quality_status/formula_version/valid_time/weather_snapshot_id/source) بالمخرَج. **قرار حارس:** بعد حذف penman/gdd_daily اختفت البصمات ⇒ fao56 خرج من الرصد ⇒ حُذف من allowlist (باقٍ **et0.py الجذر فقط**). **قرار اختبارات:** حُذفت اختبارات النوى المحذوفة (test_h5_irrigation_unify كاملاً · 3 test_engines · test_gaps_v91 gdd · test_pm_unified غلاف penman · test_compute_irrigation)؛ صيغتا الملوحة/الغسيل تبقيان مُختبَرتَين في test_engines + مسار water_balance؛ استعمال forensic أُعيد بـ`kc_for_age×ET0` محقون؛ subagent حقن et0_override في مستهلكي compute_etc_dual والمنسّق تحقّق مستقلّاً بالبوّابة الكاملة. التحقّق: guard (canonical+1) · unit 2875 · platform 3660 · inventory 884 route · bundle 3922 checksum · ruff. CI معلَّق قبل التقديم السريع. |

## 2026-07-11 — Zero-Legacy راتشِت ET0 #6 (النهائيّ): حذف نواة et0.py الجذر ⇒ allowlist=0 ⇒ LOCKED
| SHA | القرار + السبب |
|---|---|
| _(commit branch-first)_ | **حذف `core/engines/et0.py` (النواة الجذر: Hargreaves/Ra/Penman-Monteith) وإفراغ+قفل allowlist (1→0)؛ محرّك الطقس صار المالك الوحيد لـET0.** **السبب:** إتمام Ratchet Strategy — آخر نواة ET0 في المنصّة. **قرار حذف لا ترحيل (بتوجيه المستخدم «delete or relocate as internal canonical home»):** المنزل الكنسيّ موجود أصلاً في المحرّك (`services/weather-service/et0.py`+`vapor_pressure.py`) ومُختبَر ضدّ FAO-56 مباشرةً؛ فإبقاء نسخة منصّة = سطح إرثيّ بلا فائدة. أُثبِت الموت الإنتاجيّ (صفر مستهلك: imports + رموز + dynamic dispatch؛ 3 اختبارات فقط تستورده) قبل الحذف. **قرار اختبارات:** حُذف `test_et0_unified`+`test_pm_unified` (يختبران نواة محذوفة + فرضيّة H4 المتجاوَزة)؛ `test_fao56_agronomic_validation` قُلِّم لـKc/ETc/المطر (يخصّ water_balance؛ Ra/es/PM/Hargreaves مملوكة+مُختبَرة في المحرّك — لا فقدان تغطية). **قرار القفل (الرَّاتشِت النهائيّ):** الحارس اكتسب `assert len(temporary_legacy_allowlist)==0` + فحص صريح fail-closed + رسالة "Zero-Legacy LOCKED" + اختبار وحدة `test_zero_legacy_allowlist_is_empty_and_locked` — إعادة إضافة أيّ مدخل إرثيّ = فشل CI بالتصميم. **قرار خارج-النطاق:** `wofost_real` (R&D خارج services/، خارج رصد الحارس) يبقى بنسخة Hargreaves محلّيّة؛ حُدِّث تعليقه للمحرّك الكنسيّ + وُثِّق كمتابعة R&D منفصلة. **الأثر:** allowlist=0؛ الشرط المسبق لخارطة WX-10..CI-11 (ملكيّة المحرّك الكاملة) تحقّق. التحقّق: guard (canonical+0، LOCKED) · unit 2866 · platform 3650 · ruff · inventory 884 · bundle. CI معلَّق قبل التقديم السريع. |

## 2026-07-11 — WX-10.1: CanonicalWeatherState (State Product) — العقد + المُجمِّع + مستهلك واحد
| SHA | القرار + السبب |
|---|---|
| _(commit branch-first)_ | **بدء WX-10 (الحقيقة الوحيدة للطقس) بإنكرمنت أوّل إضافيّ: عقد CanonicalWeatherState كـState Product + Composer يجمع المنتجات القائمة بلا إعادة حساب + نقطة قراءة + مستهلك واحد + حارس عقد.** **قرار المستخدم:** منهجيّة الراتشِت (تغيير صغير قابل للتحقّق ببوّابة واضحة ثمّ توسّع) بدل WX-10 كامل في دفعة (يفقد تتبّع الـRegression). حدود WX-10.1: (١) العقد State Product لا DTO؛ (٢) Composer واحد يجمع دون إعادة حساب؛ (٣) endpoint قراءة واحد؛ (٤) حارس عقد يثبت schema/owner/availability/quality/confidence/provenance/evidence/limitations؛ (٥) مستهلك واحد (تقرير) يقرأ الحالة لإثبات التصميم. **قرار النَّسَب (توجيه المستخدم):** إضافة `state_id`/`state_version`/`source_snapshot_id` من البداية ليشير أيّ Consumer (قرار/تقرير/توصية) لاحقاً إلى نسخة حالة الطقس التي بُني عليها (lineage عند ربط Weather↔Crop↔Decision↔Learning). **قرار fail-closed:** خانة بلا مدخلات ⇒ availability=false + قيد، لا قيمة مُختلقة؛ `generated_at`=valid_time لا ساعة حائط؛ الخانات المؤجَّلة (I/O/سلاسل) مُصرَّحة صراحةً (لا ادّعاء تغطية). **مُؤجَّل صراحةً لإنكرمنتات مستقلّة:** تحويل ET0/VPD/GDD/Crop Intelligence/Decision إلى Views فوق الحالة. التحقّق: weather-service 111 · guard LOCKED · unit 2866 · ruff · inventory 886 · bundle. CI معلَّق قبل التقديم السريع. |

## 2026-07-11 — WX-10.2: ET0 كـView مُشتقّ من CanonicalWeatherState (أوّل تحويل مشتقّ)
| SHA | القرار + السبب |
|---|---|
| _(commit branch-first)_ | **ترحيل منتَج ET0 (`agro_et0`) ليكون View مُشتقّاً من CanonicalWeatherState بدل نداء النواة مباشرةً؛ توافقيّ للخلف.** **السبب:** تطبيق الانعكاس المعماريّ لـWX-10 على أوّل مشتقّ (ET0) بمنهجيّة الراتشِت — إنكرمنت واحد قابل للتحقّق. الـView (`et0_view`) يقرأ خانة et0 من الحالة (نفس حقول العقد بدقّة — حفظ سلوك) ويُضيف نَسَب الحالة (canonical_state_id/source_snapshot_id/derived_from) فيربط أيّ مستهلك ET0 بنسخة حالة الطقس. **قرار توافق:** مجموعة فائقة (يُضيف لا يحذف) ⇒ مستهلكو `/v1/weather/agro/et0` القائمون غير متأثّرين؛ عقد snapshot override محفوظ عبر تمرير `weather_snapshot_id_override` للمُجمِّع. النواة (`et0_agro_product`/`compute_et0`) تبقى مالكة الحساب؛ المُجمِّع يستدعيها (طبقة تجميع لا «View يقرأ المحرّك»). التحقّق: weather-service 115 · guard LOCKED · bandit High=0 · unit 2866 · ruff · inventory 886 · bundle. CI معلَّق قبل التقديم السريع. |

## 2026-07-11 — WX-10.3: VPD كـView مُشتقّ من CanonicalWeatherState
| SHA | القرار + السبب |
|---|---|
| _(commit branch-first)_ | **إضافة `vpd_view` + endpoint `POST /v1/weather/agro/vpd` يشتقّ VPD من الحالة الكنسيّة (ownership inversion بحفظ سلوك كامل).** **السبب:** تطبيق انعكاس WX-10 على المشتقّ الثاني بنفس منهجيّة الراتشِت. **قرار الحفظ الحرفيّ (توجيه المستخدم):** دلالات VPD المميّزة (`quality_flags`/`cross_check`/`input_consistency`) تُمرَّر حرفيّاً عبر الـView — لا تبسيط ولا رفع جودة؛ كامل عقد VPD byte-compatible + نَسَب الحالة مُضاف فقط. **قرار اللقطة:** VPD لا يُنتِج `weather_snapshot_id` في نواته ⇒ الـView يضيفه من `state.source_snapshot_id` فيتماسك مع ET0 تحت لقطة واحدة (override = source_snapshot_id = vpd.weather_snapshot_id، ويدخل state_id). **قرار endpoint:** لم يكن لـVPD endpoint ⇒ يُنشأ View من البداية (لا تحويل موجود). **خارج النطاق صراحةً:** أيّ تحسين دقّة VPD/عتبات = increment مستقل. بوّابات الإغلاق (قبل الدفع): حارس ساكن محصور بجسم agro_vpd · لا إعادة حساب · انتشار validated/degraded/insufficient · تماسك override · حتميّة + state_id متمايز · HTTP lineage · route/registry inventories مُجدَّدة و`--check` أخضر قبل الدمج. التحقّق: weather 133 · guard LOCKED · bandit High 0 · unit 2866 · inventory 887 · bundle. CI معلَّق. |

## 2026-07-11 — WX-10.4: GDD كـView تراكميّ فوق سلسلة canonical يوميّة
| SHA | القرار + السبب |
|---|---|
| `b8a98e5` (بناء) · `1ff0add` (إصلاح parity) · **مُغلَق main+develop @ `1ff0add`** | **إضافة `CanonicalDailyWeatherSeries` + `gdd_view` وترحيل `agro_gdd` ليشتقّ GDD من سلسلة canonical يوميّة (ownership inversion تراكميّ).** **قرار المستخدم الحاسم:** GDD ليس لقطة واحدة كـET0/VPD بل تراكم فوق سلسلة — لا يُضغَط في snapshot واحدة لتوحيد الواجهة. النواة تبقى سلطة التراكم حرفيّاً (byte-compatible). **الضوابط الثلاثة المُطبَّقة:** (١) `gdd_lineage_id` = hash(ordered_daily_state_ids + crop_config + method + accumulation_window + timezone + reset_policy) — مستقلّ عن آخر يوم، reorder-invariant، حسّاس للعتبة/الطريقة؛ (٢) فصل الهويّة العلميّة عن التغطية (coverage: expected/observed/missing/ratio + contributing_state_ids) ومنع: احتساب يوم مفقود صفراً · إسقاط مكرّر صامت · validated لسلسلة ناقصة · خلط coverage بجودة البيانات؛ (٣) تطبيع يوميّ حتميّ **قبل** الحساب (dedup صريح لا حسب-الوصول). **قرار توافق:** حقول طلب اختياريّة؛ الطلب القديم محفوظ byte-compatible. **خارج النطاق صراحةً:** لا تصحيح معادلة/عتبات/يوم-زراعيّ/interpolation/gap-fill/إعادة تشكيل عقد. بوّابات الإغلاق (قبل الدفع): legacy parity · cumulative lineage · dedup · coverage-vs-quality · route/registry `--check` أخضر. التحقّق: weather 152 · guard LOCKED · bandit High 0 · unit 2866 · inventory 887 · bundle. CI معلَّق. |

## 2026-07-11 — WX-10.5: Crop Intelligence مستهلِك منتج GDD القانونيّ (consumer-only)
| SHA | القرار + السبب |
|---|---|
| `d2d7dc4` (**مُغلَق main+develop**) | **ترحيل `crop_twin_state` لاستهلاك منتج GDD القانونيّ من weather-service (انعكاس ملكيّة، مستهلِك فقط).** **قرار المستخدم الحاسم (بعد سؤال):** «Integrate on landed shape» — طُبِّق دلتا المستهلِك فقط فوق `1ff0add` المُغلَق؛ **لا يُمَسّ weather-service ولا يُعاد تشكيل diagnostics لمطابقة لقطة WX-10.5 البديلة**؛ WX-10.4 = عقد منتِج ثابت (immutable)، WX-10.5 = increment مستهلِك. `crop_twin` يقرأ الحقول المشتركة التي ينتجها الشكل المُغلَق فقط (لا اعتماد على موضع `input_*_count`/`legacy_mode`/شكل diagnostics). **السبب:** لا فائدة وظيفيّة من فتح عقد مُغلَق ومُتحقَّق؛ أقلّ خطراً بلا انحدار. **المُستهلَك آمِراً:** `accumulated_gdd` (لا إعادة جمع daily_gdd)؛ method/version من `thresholds_used.method`+`calculation_version`؛ نَسَب GDD (`contributing_state_ids`+`gdd_lineage_id`) → `evidence_ids`؛ حفظ limitations وحالة degraded/insufficient بلا رفع جودة؛ حذف markers المُعلَّقة؛ `gdd_daily_override` جسر توافق يحمل `canonical_gdd_product_missing`. **خارج النطاق:** لا خوارزميّة/عتبات/biomass/yield/سياسة قرار. بوّابات: focused 15 · regression 44 · boundary guard · unit 2866 · ruff · inventory 887 · bundle 3925 · CI 12/12 · FF · main-only أخضر لا drift. |

## 2026-07-11 — WX-10.6: Crop Intelligence → Decision Candidate Boundary
| SHA | القرار + السبب |
|---|---|
| `1735ebf` (بناء) · `4dffbac` (waiver) · `db3df94` (إصلاح ميزانيّة+حزمة، **مُغلَق main+develop**) | **نقطة `POST /api/v1/crop-twin/decision-candidate`: تفسير CI ⇒ مرشّح قرار يملكه decision-service (لا قرار نهائيّ).** **قرارات المستخدم المُطبَّقة:** بناؤها فوق tip WX-10.5 المُغلَق (`d2d7dc4`)، لا weather-service ولا WX-10.4/10.5 يُمَسّ. عقد decision-service عند الحدّ الأدنى (POST candidate → tenant-scoped → evidence preserved → pending_approval → candidate_id آمِر). `gdd_product` المصدر الوحيد لـaccumulated_gdd/gdd_lineage_id/contributing_state_ids (يُحسَب مرّة، داخليّ فقط، لا اشتقاق ثانٍ، لا استبدال). البناء مرّة واحدة ⇒ preview==submit lineage. إثبات submit من ردّ الخدمة لا استنتاج محلّيّ (authoritative∧persisted∧decision_id∧stage echo)؛ mirror-ack SoR-off ⇒ fail-closed. لا تنفيذ (auto-approve/dispatch/task/معدّات) — حارس boundary ثابت (AST يجرّد docstrings). **قرار الإعفاء:** تغطية-واجهة ضيّقة مؤقّتة (owner/tracking=WX-10.7/expiry=2026-10-11) + gaps `WAIVER-WX10.6-001`/`WAIVER-EXPIRY-GUARD`. **قرار الميزانيّة:** زيادة منصّة +1 مقصودة موثَّقة (BFF على سطح crop-twin). **تصحيح مسار:** المستخدم رصد فشلَي CI (route-budget + release-checksum) على 1735ebf/4dffbac؛ أُصلِحا في db3df94 (تسجيل المسار في الخريطة + رفع الميزانيّات + إعادة بناء الحزمة). بوّابات: focused 31 · regression 81 · guards · unit 2866 · platform 3683 · bundle 3928 · CI 12/12 · FF · main-only أخضر لا drift. |

## 2026-07-11 — WAIVER-EXPIRY-GUARD: إنفاذ ذاتيّ لانتهاء الإعفاءات
| SHA | القرار + السبب |
|---|---|
| `9551eba` (**مُغلَق main+develop**) | **إضافة حارس CI يرفض أيّ waiver منتهٍ (expiry < today) أو مؤقّت بلا expiry.** **السبب (نقطة المستخدم الحاسمة):** حقل `expiry` في JSON زخرفيّ ما لم يُنفَّذ في CI ⇒ الإعفاء المؤقّت يصير دائماً بصمت؛ هذا يجعل انتهاء WAIVER-WX10.6-001 ذاتيّ-الإنفاذ. **قرار التاريخ:** حارس Python في CI يستخدم `date.today()` الحقيقيّ (مسموح — القيد على `Date.now()` يخصّ سكربتات أداة Workflow لا حُرّاس CI). **قرار الاختبار:** الدالّة النقيّة تُختبَر بتواريخ محقونة (حتميّة لا تتعفّن بعد 2026-10-11)؛ الفحص الحيّ يؤكّد بنية config لا يمرّر تاريخ اليوم عليه كي لا يفشل الاختبار عند الانتهاء الفعليّ (ذاك دور الحارس نفسه في CI). **قرار النطاق:** الإعفاءات الدائمة بالتصميم (admin-ops) تُتجاهَل؛ فقط المؤقّتة/ذات-expiry تُفحَص. بوّابات: guard · 8 tests · validate_ci_gates · unit 2874 · CI 12/12 · FF · main-only أخضر. |

## 2026-07-11 — WX-10.7: Decision Candidate → Reviewer/Policy → approved|rejected (Decision-Service-owned)
| SHA | القرار + السبب |
|---|---|
| `44db020` (بناء) · `05dbbc8` (عزل اختبار) · `4a370de` (جرد main-only، **مُغلَق code/contract main+develop**) | **انتقال حالة تنافسيّ آمِر مملوك لـDecision-Service: candidate(pending_approval) → approved\|rejected.** **قرارات المستخدم المُطبَّقة (بعد تحقيقه):** (١) الملكيّة كاملةً لـDecision-Service لا crop-twin؛ (٢) الحالة على عمود `review_state` مستقلّ لا `decision_value`/`stage`؛ (٣) migration additive عبر migration_runner (لا startup auto-apply)؛ (٤) **Option A**: fail-closed 503 في mirror، authoritative فقط تحت SoR منشور — لا mirror-ack للمراجعة؛ (٥) idempotency عبر request_hash (same key+payload→replay، مختلف→409)؛ (٦) append-only فعليّ (DB trigger)؛ (٧) نتيجة authoritative من الصفوف المحفوظة، facade لا يُخلِّقها؛ (٨) بيت CI مستقلّ لاختبارات decision-service + real-Postgres concurrency race. **قرار العزل:** فشل CI الأوّل = مفاتيح idempotency مشتركة في الاختبار (المنطق صحيح: أعاد mismatch بحقّ) ⇒ إصلاح بيانات-اختبار فقط، لا retry/تغيير schema. **قرار الحالة (تصحيح المستخدم):** WX-10.7 = **CLOSED كـcode/contract increment** (الكود مصمَّم ليفشل مغلقاً في mirror)؛ `DEPLOYED-DECISION-SOR-PROMOTION` = OPEN (قلب الملكيّة/التفعيل مسار منفصل). بوّابات: CI 13/13 · Decision Service Tests 19/19 على Postgres حقيقيّ · FF · main-only أخضر (بعد إصلاح جردَي health/residual). |

## 2026-07-11 — DEPLOYED-DECISION-SOR-PROMOTION cutover-prep (WX-10.7 cutover toolkit review-aware)
| SHA | القرار + السبب |
|---|---|
| `23e49e5` (بناء) · `4a7488c` (إصلاح compose-env، **مُغلَق code/contract main+develop**) | **جعل طقم الـcutover القائم WX-10.7-aware، تشغيليّ-فقط بلا تغيير منطق/schema WX-10.7.** **قرارات المستخدم المُطبَّقة:** (١) SoR-promotion أوّلاً قبل WX-10.8 (بناء UI فوق endpoint يعيد 503 غير مُجدٍ)؛ (٢) الـcutover تشغيليّ فقط — لا إعادة هندسة أثناءه؛ (٣) backfill يشمل حقول WX-10.7 لكن لا يُخمّن: أيّ مرشّح مُبهَم (NULL lineage / status مخالف) → quarantine report لا كتابة (NULL lineage = fail-closed un-reviewable، آمن بالتصميم لا mis-approve)؛ (٤) DATABASE_URL opt-in بافتراض فارغ (sor_enabled يبقى false) — لا قلب ملكيّة، لا cutover إنتاجيّ من الكود؛ (٥) migrate خطوة قبل-نشر مرصودة مُبوَّبة لا startup auto-apply؛ (٦) readiness يثبت DB reachable + migrations current + حالة الراية؛ (٧) rollback يصون audit المراجعة append-only. **قرار الحالة:** cutover-prep = مُنجَز؛ `DEPLOYED-DECISION-SOR-PROMOTION` يبقى **OPEN** لأنّ قلب الملكيّة/التفعيل الإنتاجيّ فعل مشغّل لا كود. **درس CI:** `compose_env_contract_gate` يفرض إعلان كلّ `${VAR}` في `.env.example` (فشل منتصف-طيران، أُصلِح) ⇒ شغّل كامل structural-lint محلّيّاً. بوّابات: CI 13/13 · unit 2884 · runtime_real_smoke 173 · bundle 3941 · FF · main-only أخضر لا drift. |

## 2026-07-11 — WS-E: CI consumer-contract gate (يقفل عقود مستهلك WS-A..D)
| SHA | القرار + السبب |
|---|---|
| (WS-E build) | **حارس بنيويّ يقفل عقود المستهلك للمنتِجات الكنسيّة WS-A..D.** **السبب:** جوانب المنتِج محروسة، لكن جانب مستهلك الـViews الكنسيّة ونَسَبها كان بلا حارس ⇒ تعديل مستقبليّ قد يعيد حساباً موازياً أو يُسقِط lineage بصمت. **قرار النطاق:** يقفل ما أنزلته WS-A..D فقط (لا توسيع) — WS-C.1 نَسَب الـViews · WS-C.2 تفويض المعالجات للـViews دون نوى مباشرة · WS-A غلاف ValidatedIndicatorProduct · WS-D depletion≠صفر. **قرار التقنية:** AST-strip للـdocstrings (agro_gdd يذكر gdd_agro_product في وصفه — التجريد يمنع الاصطياد الكاذب) + required/forbidden per-function، على نمط decision_candidate_boundary_gate. **قرار الاختبار:** 6 حالات تشمل الاصطياد السلبيّ (يُثبت أنّ الحارس يفشل عند الانحدار، ليس no-op). بوّابات: 24 حارس structural-lint · unit 2890 · ruff. |

## 2026-07-11 — WX-10.8: Reviewer/Approvals UI (يزيل WAIVER-WX10.7-001)
| SHA | القرار + السبب |
|---|---|
| (WX-10.8 integrate zip) | **دمج WX-10.8 reviewer UI على `2122978` بمبدأ integrate-on-landed-shape.** **قرارات:** (١) طابور المراجعة نقطة **قراءة** آمِرة في decision-service (`review_state` مصدر الحالة، الأدلّة تُقرأ لا تُمَسّ) — fail-closed 503 في mirror لا طابور فارغ؛ (٢) BFF يفرض *مَن* (`DECISION_APPROVE`) + إثبات fail-closed (authoritative∧persisted∧count==len)؛ (٣) الواجهة تعرض 503 بصدق (retry:false) لا قائمة فارغة، ولا تُسلسِل حمولة المرشّح كاملةً؛ (٤) لا تغيير في منطق WX-10.7 الآمِر (الطابور إضافيّ صرف)؛ (٥) إزالة WAIVER-WX10.7-001 مقرونة بتغطية-واجهة فعليّة (reverse-gate يفرض التطابق)؛ (٦) ميزانيّة +1 موثّقة لنقطة review-queue؛ (٧) نقل اختبار نقطة decision-service إلى tests_v9 (unit) كي يُجمَع فعليّاً. **قرار الأساس:** رأس تعليق عربيّ في approvalsConsole.ts استُعيد؛ إعادة ترتيب config تُجوهِلت (المجموعة متطابقة ±الإضافتين). بوّابات: unit 2892 · frontend typecheck+8 · 24 structural-lint · runtime_real_smoke 173. **واقع النشر:** المسار حيّ فقط بعد operator flip (يعيد 503 حتّى ذلك، بالتصميم). |

## 2026-07-11 — WX-10.9..10.12: سلسلة التنفيذ بعد الموافقة (خمس مراحل، increment واحد)
| SHA | القرار + السبب |
|---|---|
| (WX-10.9..10.12 integrate) | **دمج السلسلة الآمِرة plan→authorize→request→receipt→outcome كـincrement واحد على tip WX-10.8، integrate-on-landed-shape.** **قرارات:** (١) لَحَّم الدلتا من zip تراكميّ مع صون إصلاحات WX-10.8 CI (ci.yml جراحيّ: أبقى خطوة review-queue + أضاف 4 حُرّاس + 5 خطوات اختبار تنفيذ + migrations 001-007)؛ (٢) نقل الاختبارات التعاقديّة الجذر → tests_v9 (unit، ساكنة) كي تُجمَع فعليّاً؛ (٣) إصلاح ثغرتين مُسلَّمتين: اقتطاع اختبار 11b + إعفاء/تصنيف مسار execute المفقود؛ (٤) لا تغيير في منطق WX-10.7؛ (٥) ميزانيّة +4 موثّقة + 4 مدخلات ملكيّة. **واقع النشر:** السلسلة كلّها fail-closed 503 حتّى operator flip. بوّابات: unit 2906 · platform 3702 · 28 structural-lint · runtime_smoke 173 · frontend tsc. |

## 2026-07-11 — WX-10.13→11.6: سلسلة حوكمة النموذج/MLOps (سبع مراحل، increment واحد)
| SHA | القرار + السبب |
|---|---|
| `b2192bd` | **دمج سلسلة learning-attribution→registry activation/receipt/rollback كـincrement واحد على tip `6c8cf8d`، integrate-on-landed-shape.** **قرارات:** (١) طبّقتُ دلتا سلسلة النموذج فقط، صُنتُ إصلاحات WX-10.9..10.12؛ (٢) وصّلتُ 7 حُرّاس + 7 خطوات اختبار بنفسي بدل نسخ ci.yml الناقص من الحزمة (وصّل 5/7 فقط)؛ (٣) أصلحتُ 3 ثغرات مُسلَّمة: حدّ حارس promotion-decision (كان يلتقط `registry_alias` الشرعيّ عبر قطع-حتّى-EOF) + ترقية مخطّط الإعفاءات للتشغيليّ الكامل + حذف `row` غير مستخدَم/ruff؛ (٤) إعادة قاعدة تصنيف dispatch-authorizations التي دهسها نسخ config + قاعدة outcomes/ + إعفاءات machine؛ (٥) ميزانيّة 582→591 (baseline 594) موثّقة. **واقع النشر:** السلسلة كلّها fail-closed 503 حتّى operator flip. بوّابات: unit 2906 · platform 3702 · 24 model + 43 exec real-pg · structural-lint كامل · runtime_smoke · bundle 3996. |

## 2026-07-11 — WX-11.7→11.12: إغلاق حلقة دورة حياة النموذج + إصلاح نطاق بوّابة التغطية
| SHA | القرار + السبب |
|---|---|
| `e032c67` | **دمج closed-loop completion (rollback receipt→verify→rollout→monitor→retrain) كـincrement واحد على tip `f47b810`، integrate-on-landed-shape من لقطة شجرة كاملة.** قرارات: (١) نسخ main.py/persistence.py التراكميّين (منطق مطابق لـWX-11.6 + closed-loop، فرق تنسيق فقط، مُتحقَّق بكامل الاختبارات) لكن **رفض تبنّي config/gates/tests المتباعدة** (اللقطة تسبق إصلاحاتي)؛ (٢) migration 014 = ٦ جداول append-only + ٧ نقاط decision-service داخليّة (لا BFF/ميزانيّة)؛ active-state مُشتقّ من الإيصالات لا alias؛ (٣) إصلاح ثغرتين: حدّ test_wx11_3 (EOF-slice يلتقط active_model) + تنسيق تأكيد العقد للشكل القانونيّ لـruff؛ (٤) درس pollution: تحقّق كلّ ملفّ عمليّة مستقلّة على DB نظيف بترتيب CI. |
| `058bd81` | **استثناء `services/decision-service/*` من مقياس تغطية الوحدة عبر `.coveragerc` جذر — إصلاح نطاق لا تخفيض أرضيّة.** السبب: decision-service مُختبَر بـPostgres حقيقيّ في وظيفة CI مخصّصة، غير قابل لـ`-m unit`؛ أسطره الصفريّة في مقام `--cov=services` عاقبت النسبة مع كلّ زيادة (انهارت دون ٤٠٪). الأرضيّة تبقى ٤٠٪؛ بوّابة المنصّة (.coveragerc خاصّة) لم تُمَسّ. لا كود غير مُختبَر يُخفى. |

## 2026-07-11 — WX-12: خدمة model-registry-adapter لتنفيذ الحوكمة (runtime consumer)
| SHA | القرار + السبب |
|---|---|
| `81b1351` | **دمج WX-12 كـincrement إضافيّ بحت على tip `d3e44b0`؛ اللقطة المُسلَّمة تسبق WX-10.13→11.12 فأخذتُ دلتا WX-12 فقط (خدمة+scripts+gates+workflow+docs) وتجاهلتُ فروق الملفّات المتباعدة.** خدمة stdlib صرف تقرأ نقاط حوكمة decision-service وتنفّذها (compare-and-swap/verify/rollout/monitor/retrain) بلا تدريب/actuate ذاتيّ (DRY_RUN + حارس token). بوّابتان في structural-lint + اختبارات في وظيفة decision-service (بلا DB). لا compose (نشر مُشغَّل-مُوجَّه). لا BFF/migration/ميزانيّة. تغطية بلا تغيير (٤٧٪). |
| `d3e44b0` (FF) | **FF main+develop `6c8cf8d`→`d3e44b0` بعد CI 13/13 أخضر** (WX-10.13→11.6 + closed-loop WX-11.7→11.12 + coverage-scope fix). بوّابة التغطية (كانت تفشل على f47b810) خضراء بعد استثناء decision-service. main-only (runtime-smoke·inventory-drift) مُتحقَّق بلا drift. |

## 2026-07-12 — WX-12.1: إغلاق عقد runtime<->decision-service (تدقيق دمج خارجيّ)
| SHA | القرار + السبب |
|---|---|
| `1f53f63` | **إصلاح فجوات عقد WX-12 التي كشفها تدقيق خارجيّ لـ`c7913fd` (بعد التحقّق منها في الكود).** migration 015 (جدولا إيصال append-only) + 3 نقاط decision-service (runtime-work feed بحمولة كاملة عبر JOIN، rollout receipt، retraining dispatch receipt) + إصلاح adapter (target_environment، ترويسات فاعِلة، idempotency حتميّة، مستهلك activation/rollback في supervisor). **درس منهجيّ: الحُرّاس البنيويّة (وجود ملفّ/رمز) لا تُثبت تكامل عقد HTTP حيّ — تلزم اختبارات contract تُعيد تشغيل طلبات الـclient الحقيقيّة ضدّ التطبيق، وقد كشفت خللاً أعمق (حمولات feed رقيقة).** لا BFF/ميزانيّة. بوّابات كاملة + main-only. fail-closed حتّى operator flip. |

## 2026-07-12 — WX-12.2: تصلّب ما بعد التدقيق الجنائيّ الثاني
| SHA | القرار + السبب |
|---|---|
| `ad8156d` | **إغلاق فجوات الصحّة/الأمان المُحتواة من التدقيق الجنائيّ الثاني، وتأجيل البنية بصدق.** migration 016 (claim/lease دائم لأنواع العمل ذات الأثر الجانبيّ — أمان متعدّد-النُسخ) · middleware توكن-خدمة opt-in (لا يُوثَق header على المنفذ الداخليّ) · replay semantics للإيصالات (request_hash) · CAS digest من الإيصال · LOOP_TABLES · readiness مُدرِكة-التبعيّة. **درس: الحُرّاس + عقد API لا يُثبتان سلامة متعدّد-النُسخ ولا أمان حدود-الخدمة — يلزم claim/lease + مصادقة خدمة.** أُجّل (لا نصف حلّ): مجدولات monitoring/reconciliation (High 1) + تقسيم متعدّد-المستأجرين (High 5) كفجوات OPEN بتصميم مُوصى. fail-closed حتّى operator flip. |

## 2026-07-12 — WX-12.3: المجدولات الدائمة (إغلاق WX-12-RUNTIME-SCHEDULERS)
| SHA | القرار + السبب |
|---|---|
| `9e308d5` | **تنفيذ التصميم المُوصى: config دائم + تقدّم مُشتقّ من أدلّة append-only (لا last-run متغيّر) + انبعاث الـfeed للنوعَين + استهلاك supervisor + دليل reconcile قابل للتدقيق.** قرارات: (١) رصف النوافذ من anchor مقطوع-الثواني كي يدور ISO بدقّة عبر الـruntime إلى صفّ الـsnapshot (وإلّا فرق microseconds يمنع NOT EXISTS للأبد)؛ (٢) work_key = schedule_id (صفّ claim واحد لكلّ جدولة — تخزين محدود؛ تأخير أقصاه lease_seconds بعد الاستحقاق، موثَّق)؛ (٣) لا backfill رجعيّ للنوافذ الفائتة (المراقبة عن الحداثة — صادق وموثَّق)؛ (٤) إصلاح جانبيّ: DecisionClient.get كان يرسل "None" حرفيّاً للمعاملات الفارغة. Medium 2 (إغلاق health server) ضُمّ. المتبقّي OPEN: multitenancy + شقّ High 4 الخارجيّ. |

## 2026-07-12 — AC-1 (توصية الخطّة الرئيسيّة) + دمج VEG-AGRIAI المُسلَّمة
| SHA | القرار + السبب |
|---|---|
| `b1d3809` | **AC-1: العقود الثلاثة الثابتة (context/history/feature-manifest) + composer هيكليّ fail-closed + ربط قرار إلزاميّ مرحليّ.** قرارات: (١) ترقيم 018 لا 016 (الخانات مشغولة)؛ (٢) content-addressing لإعادة استخدام الـsnapshots؛ (٣) مجموعات المجال jsonb مُتحقَّق + أعمدة الهويّة/PIT أوّليّة (لا 60 عموداً)؛ (٤) point-in-time انتهاكات مُصنَّفة قبل أيّ كتابة — لا تخليق صامت؛ (٥) الإلزام خلف `DECISION_REQUIRE_AGRONOMIC_CONTEXT` كنمط الرايات المرحليّة، والربط الجزئيّ رفض دائماً. Phases B–E خارطة قائمة. |
| `6658d86` | **دمج زيادة vegetation/agriai المُسلَّمة (دلتا ١٤ عنصراً) + توصيل حارسَيها في structural-lint + إصلاح اختبار قديم فاتته الحزمة (وسم LAI الصادق "vegetation-model").** درس متكرّر: الحزم المُسلَّمة تفوّت اختبارات الجذر القديمة — الانحدار الكامل يكشفها. توثيق تصادم اسم `agronomic_context` (عزل عمليّات CI). |

## 2026-07-12 — إغلاق الخطّة الكاملة veg-agriai + تسوية الهجرة المتصادمة
| SHA | القرار + السبب |
|---|---|
| `a53c206`+`4b1bafd` | **إصلاحا CI:** working-directory لخطوة veg-agriai (سقوط pytest إلى testpaths/conftest jwt) ثمّ PyJWT+prometheus-client + إعادة توليد مانيفست الإصدار. درسان مُرسَّخان في log. |
| `41211c6` | **دمج `full_plan_closed` على الشكل المُنزَل مع رفض هجرة الحزمة المتصادمة.** الأسباب: (١) `018_agronomic_context_snapshots` المُسلَّمة تُكرّر جدول AC-1 المُنزَل بمخطّط أضعف (season_id NOT NULL، بلا idempotency/request_hash/replay) وتتصادم بالاسم؛ (٢) جداولها الإضافيّة بلا أيّ كاتب/قارئ في الحزمة — إنزال مخازن غير موصولة دَين لا إغلاق (تُبنى مع كاتبها: VEG-EVIDENCE-STORE)؛ (٣) بوّابة الإغلاق المُسلَّمة عُدّلت لتؤكّد `018_ac1` (سابقة إصلاح البوّابات المُسلَّمة)؛ (٤) محوّل بطاقة المحصول يشتدّ عند وجود `version` فقط — طلبات legacy الهزيلة لا تنقلب 500؛ (٥) تحويل valid_pixel_ratio→pct وحدةً فقط، لا اختلاق بروفينانس (qa_mask_version يبقى ناقصاً من raster ⇒ فشل مُغلَق صادق في الإنتاج، فجوة RASTER-PROVENANCE-ENRICHMENT). |

## 2026-07-12 — AC-6/AC-6.1 على الشكل المُنزَل
| SHA | القرار + السبب |
|---|---|
| `4b35809` | **تسوية 019+020 المُسلَّمتين في هجرة واحدة على عقود AC-1:** (١) مخزن النباتيّ يُنزَل الآن لأنّه جاء **مع كاتبه** وتحقّقه — عكس رفض الجولة السابقة للجداول غير الموصولة؛ (٢) كاتبا السياق/التاريخ الدفعيّان مرفوضان — الـcomposer أقوى دلالة ومصدر حقيقة واحد؛ (٣) `field_history_snapshot_id` يُعيَّن على العمود المُنزَل `field_historical_context_snapshot_id`؛ (٤) سياسة الموسم في الـtrigger: تناقض فقط عند إعلان الطرفين (قرارات legacy بلا موسم تستمرّ)؛ زيادة مُتعمَّدة: تحقّق hash المانيفست في الـtrigger؛ (٥) أخطاء trigger/FK تُحوَّل رفضاً مُصنَّفاً fail-closed لا 500؛ (٦) RLS بلا FORCE = نافذة فقط بدور غير-مالك — موثَّق بصدق ضمن عمل الـcutover. |

## 2026-07-12 — نَسَب الكوهورت الشامل (حزمة خماسيّة)
| SHA | القرار + السبب |
|---|---|
| `6e7d0fa` | **تسوية خماسيّة على المخطّط المُنزَل:** (١) إعادة ترقيم 021→024 ⇒ 020→023 وإعادة استهداف عمود/جدول التاريخ المُنزَلين؛ (٢) رفض FORCE RLS غير المُختبَر (برهان الحزمة البوستغرسيّ مُتخطّى) — ENABLE+policy حتى دور غير-مالك؛ (٣) إصلاح ترميز jsonb المزدوج في كلّ مواقع الوراثة (علّة كانت ستُفشل النظام بأكمله على PG حقيقيّ)؛ (٤) إعادة تأسيس اختبارات runtime القائمة بسلسلة تفعيل أمينة بدل إضعاف القيود؛ (٥) الإبقاء على دلالات الحزمة القاسية (مراقبة⇐إيصال مفعَّل، إعادة تدريب⇐انحراف) لأنّها الدلالة الصحيحة زراعيّاً وتشغيليّاً. |

## 2026-07-12 — إغلاق ذاتيّ لفجوتَي ما-بعد-الحزم
| SHA | القرار + السبب |
|---|---|
| (هذا الكوميت) | **qa_mask_version يُنشر فقط عند تطبيق قناع فعليّ** — NDVI من مشهد غير مُقنَّع يفشل بوّابة السلطة بصدق (الصرامة هي العقد لا عيباً)؛ **algorithm_version ثابت مُصدَّر من موضع الصيَغ** لا سلسلة حرّة؛ **دفع الأدلّة fail-soft خلف راية** لأنّ التحليل يجب ألّا يُكسَر بغياب decision-service (mirror 503 قبل قلب SoR) والنتيجة تُبلَّغ دائماً في الردّ. |

## 2026-07-12 — WX-12 multitenancy
| SHA | القرار + السبب |
|---|---|
| (هذا الكوميت) | **إنفاذ تدريجيّ بالتسجيل:** العامل غير المُسجَّل يبقى على سلوك env (لا كسر للتنصيبات)، وأوّل تسجيل يقلب العامل إلى القسمة المُفرَضة — يوازن أمن SaaS مع التوافق الخلفيّ. **جدول التفويض بلا RLS بالتصميم** (خريطة التفويض ذاتها، عابرة للمستأجرين، مضبوطة بالمشغّل). **الاكتشاف الخادميّ هو مسار SaaS** وenv يبقى للمثبَّت الواحد. |

## 2026-07-12 — تصلّب multitenancy بعد التدقيق الجنائيّ FORENSIC_AUDIT_SAHOOL_73666EE
| SHA | القرار + السبب |
|---|---|
| (هذا الكوميت) | **تحقّقتُ من البنود التسعة ثمّ عالجت الحقيقيّ منها بنداً بنداً:** **F-01 (حرج، مؤكَّد)** ⇒ راية مرحليّة `DECISION_STRICT_WORKER_TENANTS` — العامل غير المُسجَّل يُرفض كلّ مستأجر (fail-closed) عند تفعيلها؛ الافتراض off يصون تنصيبات env-pinned (نمط رايات القلب المرحليّة نفسه، وقائمة تفعيل الإنتاج للمشغّل). **F-02 (حرج، مؤكَّد)** ⇒ migration 025: سجلّ أوامر append-only `decision_runtime_worker_tenant_commands` بمفتاح `UNIQUE(worker_id, idempotency_key)` + `resulting_revision`، والجدول القائم صار **إسقاطاً حاليّاً** بعمود `revision` رتيب؛ إعادة إرسال أمر قديم تُرجِع نتيجته الأصليّة **دون لمس الإسقاط** — الإلغاء نهائيّ ولا يُحييه retry بائت (برهان PG: enable→disable→replay-enable يُبقي الإسقاط معطَّلاً rev=2). **F-06/F-07** ⇒ trigger append-only على السجلّ + قيود CHECK (طول worker_id/created_by/idempotency_key + `request_hash ~ hex64`) على السجلّ وNOT VALID على الإسقاط. **F-08** ⇒ البوّابة الساكنة عُمِّقت (رموز 025 + الراية + مسار الـreplay) **والدليل الأوّليّ صار اختبارات سلوك على PG+HTTP حقيقيّين** (5 اختبارات: strict-403، stale-replay، append-only/CHECKs، رتابة revision، شراكة feed). **F-09** ⇒ قاعدة جاهزيّة مرحليّة `DECISION_REQUIRE_AUTH_TOKEN`: SoR بلا `DECISION_SERVICE_AUTH_TOKEN` ⇒ `/readyz` degraded، مع كشف حالة الإنفاذ في الحمولة (`enforcement.auth_token_configured/strict_worker_tenants`) + تمرير compose و`.env.example`. **F-03/F-04 (صحيحان، معماريّان)** ⇒ فجوة OPEN صادقة `WORKER-IDENTITY-BINDING` — ربط هويّة العامل/المشغّل باعتماد مُوقَّع (mTLS/SPIFFE/JWT لكلّ عامل) قرار بنية تحتيّة لا نصف حلّ؛ الموجود الآن: توكن الخدمة المشترك (opt-in) + actor غير فارغ. **F-05 (مُستوعَب لا بند مستقلّ)** ⇒ تحت strict mode رفضُ الخادم 403 هو الحدّ الفعليّ: env pins لا تستطيع التوسّع خارج المجموعة المُفوَّضة (الـfeed يتحقّق لكلّ طلب)؛ التقاطع الصريح في الـadapter تحسين لاحق ضمن الفجوة المعماريّة. لا تغيير على أيّ سلوك افتراضيّ — كلّه خلف رايات مرحليّة. |

## 2026-07-12 — ربط نشر الـmodel-lifecycle-adapter (تقرير التتبّع التشغيليّ)
| SHA | القرار + السبب |
|---|---|
| (هذا الكوميت) | **خدمة compose اختياريّة `sahool-model-lifecycle-adapter` بprofile `model-lifecycle` لا خدمة افتراضيّة:** runtime الإنتاج يفرض `_env(required_prod=True)` على URLs/tokens المنافذ الخارجيّة (traffic controller/inference verify/metrics/training) — تشغيله في الرصّة الافتراضيّة بلا تهيئة يعني crash-loop أو تشغيلاً غير إنتاجيّ صامت؛ الـprofile يجعل التفعيل قراراً صريحاً للمشغّل مع تهيئة كاملة. **العامل القديم `sahool-model-registry-worker` يبقى:** مكمِّل (جدول منصّاتيّ) لا مكرَّر — حذفه كان سيكسر مسار promotion المنصّاتيّ. **`DECISION_SERVICE_TOKEN: ${DECISION_SERVICE_AUTH_TOKEN}`:** توكن واحد يضبطه المشغّل فيتطابق الطرفان تلقائيّاً (لا سرّان ينحرفان). بوّابة WX-12 تحرس الربط ضدّ الانحدار. |

## 2026-07-12 — Phase E: Decision Evidence UI
| SHA | القرار + السبب |
|---|---|
| (هذا الكوميت) | **لوحة الدليل في كونسول الموافقات لا صفحة جديدة:** جمهور الدليل الأوّل هو المراجِع لحظة البتّ (approve/reject) — فالقراءة بصلاحيّة `DECISION_APPROVE` نفسها ولوحة قابلة للفتح لكلّ مرشّح، لا مسار تصفّح منفصل يشتّت. **قراءة آمِرة fail-closed:** mirror ⇒ 503 يُعرَض كخطأ صريح في الواجهة — عرض «لا يوجد دليل» على خدمة غير-آمِرة كان سيُضلّل المراجِع في أخطر شاشة. **`evidence_complete` مُشتقّ خادميّاً** (ربط ac-1 + وجود اللقطات الثلاث) لا شارة مُدَّعاة. **stub الـlineage القديم بقي كما هو:** عقده مختلف (outcomes/stages) ويخصّ زيادة لاحقة — استبداله هنا كان سيوسّع النطاق بلا تفويض. **صدق legacy:** القرارات قبل الإلزام تُعلَن `legacy_unbound` حرفيّاً في الواجهة بدل إخفائها أو تجميلها. |

## 2026-07-12 — ACTUATOR-DISPATCH-CONSUMER
| SHA | القرار + السبب |
|---|---|
| (هذا الكوميت) | **kill-switch قبل المطالبة لا بعدها:** مفتاح مُشتبَك يترك الطلبات مصفوفة (تُنفَّذ بعد الفكّ) بدل استهلاكها بإيصالات فاشلة — الإيقاف الطارئ تأجيل لا إلغاء. **مخاطرة غير مُعلَنة لا تحجب:** السلسلة محكومة أصلاً (مراجعة بشريّة + تفويض توزيع)؛ الحجب فقط عند إعلان مخاطرة خارج المسموح — حجب كلّ ما لا يحمل risk_level كان سيشلّ الجسر بلا مكسب أمان. **تعيين المستأجرين صريح:** قائمة فارغة = حلقة خاملة مُعلنة، لا خدمة «كلّ المستأجرين» ضمنيّاً. **الإيصال يصدُق:** published≠executed منصوص في الحمولة — تحقّق النتيجة الفيزيائيّ خطوة منفصلة (WX-10.12). **feed يستثني قيد-التسليم:** NOT EXISTS على إيصال فارغ — والبوّابة الذرّيّة تبقى المطالبة نفسها (سباق adapterين يحسمه 409). |

## 2026-07-12 — Brain consumes governed truth
- **Decision:** Sahool Brain/Supervisor must consume canonical Raster observations and may not recompute spectral indices or dispatch physical effects.
- **Rationale:** prevents ownership drift, synthetic evidence, and bypass of Decision-Service governance.
- **Evidence:** `shared/contracts/intelligence_governance.json`; `scripts/ci/intelligence_governance_gate.py`; focused tests green.
- **Status:** verified locally; runtime MCP/Raster integration remains staging-certified only.
- 2026-07-12 — دمج riv_brain_governance (2a68d16): تبنّي توحيد RIV وحوكمة الدماغ كاملَين؛ رفض عامل ::uuid (الثالث)؛ إصلاح مولِّد manifest الواجهة (كسر useIndicatorRegistry)؛ إضافة فحص الصدق (g) لسدّ ثغرة إعادة وسم المشتقّ real؛ إعادة كتابة الاختبارات القديمة على العقود الجديدة. السبب: integrate-on-landed-shape.
- 2026-07-12 — دمج riv_truth_contract (فوق ebd4494): إزالة synthetic_grid نهائيّاً + 424 fail-closed + prescription حقيقيّ فقط + contract-only للمؤشّرات + raster_production_truth_guard في CI. السبب: صدق الإنتاج — لا منتج تركيبيّ في أيّ مسار serving. تحديث الاختبارات القديمة المعتمدة على المحاكاة.
- 2026-07-12 — دمج riv_durable_identity (v154): مطالبة PostgreSQL ذرّيّة + إيجارات قابلة للاسترداد + هويّة منتج كاملة (algorithm/mask/geometry). السبب: يمنع طيّ إعادة معالجة مشروعة (خوارزميّة/هندسة جديدة) في صفّ قديم، ويسترد الدفعات بعد تعطُّل العامل. مؤجَّل: تصنيف السجلّ v2 (يمنع البدائل الدلاليّة الحاملة + يعيد انحدار manifest الواجهة).
- 2026-07-12 — دمج riv_three_containers_runtime_truth (على 6498f97): تبنّي حقيقة مصدر الحقل التشغيليّة (سجلّ تركيبيّ فارغ + قراءة كتالوج المنصّة المستأجَر + لا تلفيق، legacy dead-ends None) + wiring PLATFORM_API_URL. السبب: صدق الإنتاج — vegetation لا تُلفّق حقولاً تركيبيّة؛ الحقول الحقيقيّة من المنصّة أو فشل مرئيّ. عيوب الحزمة (بواباتها/اختباراتها فشلت على شجرتها لأنّ برهانها SKIPPED) صُولِحت: p1 guard (fetch_from_cdse→banned) · consumer_contract_gate (run_analysis/bundle) · 3 اختبارات/بوّابات على العقد الجديد · asyncio غير مستخدم. مؤجَّل بصدق: تصنيف السجلّ v2 + شهادة PostgreSQL/CDSE/MinIO الحيّة.

- **`23676d4` — adopt bundle-authoritative soil supersession/current-pointer table design over divergent column attempt.** Reason: the delivered bundle (soil_observation_supersessions + soil_profile_current, atomic supersession validation, readiness-through-pointer) is the canonical line future bundles build on; a parallel `supersedes`/`is_current` column approach would permanently fork. Kept my real-PG certification value + fixed 4 delivered bugs their SKIPPED proofs missed. v157–v160 registered in both migration runners.

- **`9f24a2a`→`d988d45` — integrate full P0–P5 soil chain (v155–v165) on landed shape, one gated increment per bundle; FF main/develop to the confirmed-green P0–P4 tip `9f24a2a`, P5 tail pending its green run.** Reason: bundles arrived stacked and rapid; each was reconciled onto the prior landed tip (bundle-authoritative designs win as the canonical line future bundles build on), certified on real PostgreSQL here (their proofs SKIPPED), and only fast-forwarded to tips CI confirmed green. Coverage-floor break handled honestly via .coveragerc integration-surface omit (decision-service precedent), not by lowering the floor.

- **Lexicographic irrigation MPC — P1.1: fixed a proven P0 lineage-collision bug + governance-contract & yield-floor honesty hardening (forensic-driven).** Reason: a forensic analysis proved `candidate_lineage_id` collided across genuinely different decisions (37.5/5/2 mm under different budget/app-cap → identical `mpc_67d5…`) because the digest omitted the constraint inputs (season_budget/max_application/water_price/depletion_confidence/data_degraded/selected_policy/plan) and truncated to 16 hex. Reproduced, then fixed: full 64-hex `content_digest` over canonical JSON of ALL facts; separated `idempotency_key` (logical request slot) from `content_digest` (exact content) from `candidate_lineage_id` (short display). Added governance fields (tenant_id, season_id, solver_version, execution_allowed=False, constraint_trace, modeled_capabilities). Yield-floor honesty: explicit `forecast_horizon` scope (not seasonal), generic-stage Ky never certifies the floor, and the preserved decision uses a lower-confidence bound (Ky-uncertainty worst-case propagation). Separated first_action_depth_mm from horizon_total_irrigation_mm; renamed predicted_water_m3_per_ha→recommended_gross_water_m3_per_ha; standardized not_modeled spelling; fail-closed on NaN/Inf/out-of-range inputs. Execution/MQTT/authorization untouched; pure/additive. Honest correction: the earlier zip label "…_verified" over-claimed — the accurate status is computational core verified, not yet production-connected. Verified: 32 unit tests (lineage-varies-with-constraints, idempotency-slot-stable, tenant/season isolation, 64-hex, fail-closed inputs, generic-no-cert), ruff clean, Ky guard green, bandit HIGH clean, ADR-0032 updated. P1.1b (route reads water_ledger + wire solver into water_decision_bridge as a lexicographic_irrigation candidate + PG persistence + lineage propagation through execution→outcome→learning) is next, before Phase 2 — needs the decision-service chain + real PG.

- **Lexicographic irrigation MPC — Phase 1: real J3 via the canonical FAO-33 Ky yield-response, sourced registry, no invented values.** Reason: the user directed Phase 1 before Phase 2 (Ky is a logical extension over Phase 0 that turns J3 from `not_modelled` to a real objective without new operational infra or wide migrations; the energy/well layer is a separate data project that must not start before production behaviour is fixed). New `core/engines/ky_registry.py` holds FAO-33 (Doorenbos & Kassam 1979, Table 24) crop×stage Ky with per-entry `ky_source`/`version`/`effective_from`/`uncertainty` — no invented values; resolution is crop-specific → labeled generic-stage → None (missing Ky/stage ⇒ `insufficient_data`, no silent fallback). J3 = `1 − Ya/Ym` where `Ya/Ym = 1 − Ky·(1 − ETa/ETm)`, ETa/ETm from daily Ks (FAO-56). `yield_floor_preserved` is True only with complete data (valid ETa/ETm + known stage + Ky available + within model bounds + floor target met), else None; severe deficit with Ky>1 ⇒ `out_of_bounds` (clamped). J3 is linked to `objective_trace` + `candidate_lineage_id`. Strict economic isolation: no revenue/margin is derived from Ky — enforced by the CI guard `scripts/ci/ky_no_economic_coupling_guard.py` and `economic_margin_delta=None`, until an explicit economic model exists. J1 stays top (the ε-lexicographic order guarantees the yield floor never breaks crop protection). Execution/MQTT/authorization untouched; additive (no migration/endpoint). Verified: 21 unit tests (all acceptance gates), `pytest -m unit` 2935 passed @ 45.47%, ruff clean, Ky guard green, baseline 613→614, ADR-0032 updated. Next: Phase 2 (energy/well data layer) as an independent package.

- **Lexicographic irrigation MPC — Phase 0 (solver core + contract) adopted per the user's spec; strict non-financially-tradeable priority ladder over the existing FAO-56 substrate.** Reason: water/energy scarcity and stress risk in Yemen cannot be collapsed into one weighted cost — a mistake at a critical stage kills a crop and must never be traded for energy savings. A three-layer scout confirmed the governed skeleton already exists (water_ledger Dr, canonical_water_stress AWF, fao56 ETc/TAW/Zr/Ks, candidate→review→execute→verify→learning chain) plus a self-described non-QP greedy planner `api/irrigation_mpc.plan_irrigation` = the generalization point; net-new = the lexicographic solver, the canonical Ky yield model (FAO-33 values exist only as a gate), and the entire energy/well/solar constraint layer (absent as data — schema only in COMPETITIVE_ANALYSIS.md). Chose to start with Phase 0 because it builds entirely on existing data; energy is declared `not_modelled` rather than fabricated. `api/lexicographic_irrigation_mpc.py` generalizes the greedy planner to an ε-constrained lexicographic selection J1 crop-protection ≻ J2 water(+energy not_modelled) ≻ J3 yield-floor(stress-proxy pending Ky) ≻ J4 margin(water-cost proxy), with an operating-state machine (incl. EMERGENCY_FAIL_CLOSED on missing critical inputs), a ReasonCode enum, and a recommendation-only contract (`approval_required=True` always — no direct pump command; it emits through the Decision Center). Pure/additive: no migration, no endpoint, no execution. Verified: 11 unit tests, full `pytest -m unit` 2925 passed @ 45.33%, ruff clean, ADR-0032. Phases 1–4 (Ky model; energy/well data layer; hourly horizon; UI + irrigation_runs writer + closed-loop) mapped.

- **SOIL-GOVERNANCE-WORKSPACE — first real UI consumer for the P4 soil closed-loop, surfaced by a gateway/backend/frontend review; fixed the orphaned `soilWorkspace.ts` scaffold to the real `soil-profile.v1` contract.** Reason: the review found the entire P4–P6 soil governance chain fully reachable via the `/api/soil/` proxy but with zero frontend consumer, and `frontend/src/lib/soilWorkspace.ts` was dead scaffolding (imported only by its test) that mismapped the canonical snapshot — computing completeness from a non-existent `completed_properties` (always 0%) instead of `completeness_score`, with `historyCount`/`conflicts` shape errors. Built a read-only `SoilGovernanceCard` (evidence level, quality gate, allowed/blocked uses, closed-loop counts) fed by `useSoilWorkspace` over `soilApi` with honest 404/503 empty states — no mock, no fabricated profile. Also fixed a latent default-URL bug the review surfaced (`soil_evidence_bridge.py` `soil-service:8134` → canonical `sahool-soil-service:8000`). Read-only and additive (no new endpoints, no migration); the P4 write/approve path stays in the Decision Center. Verified: tsc + field-workspace-contract tsc clean, soil vitest 8/8, vite build ok, endpoint-ui-coverage-gate PASS, ruff clean, release 4231. P5/P6 (validation/calibration/certification/runtime) remain UI-less — next candidates on the same pattern.

- **soil P6 runtime/production certification (v166) integrated on landed P5 shape; regenerated stale generated-inventories that had turned `main`@`9f24a2a` red.** Reason: P6 (`RuntimeCertificationRun` + content-addressed evidence, 2 FORCE-RLS tables, fail-closed CLI) adopted the bundle's canonical design and was certified on real PostgreSQL (v166 0-error apply, P6 unit 3/3, P6 real-PG integration 3/3 after fixing a delivered NOT NULL bug that omitted `depth_from_cm`/`depth_to_cm`). The user's shared CI job link exposed that the *Service Inventory Drift* job was failing on `main`@`9f24a2a` (`SERVICE_REGISTRY.md`) — the P0–P5 integration never regenerated the generated inventories. Fixed by `generate_service_inventory.py --write-registry` (29 services/997 routes) + `route_mount_contract_guard.py --write` (25 entries) + release rebuild (4222 checksums), folded into the P6 commit. Ratcheted lesson: pre-commit checklist for router/module-adding work now explicitly regenerates the generated inventories, not just the static guards. FF main/develop to the green P5/P6 tip (past the red `9f24a2a`) after branch CI confirms green.

- **MPC P1.1b — bridge + production route: first production consumer connecting the lexicographic solver to the governed decision chain (recommendation-only, default-off, full lineage propagation).** Reason: the P0-P1 forensic proved the solver was a verified computational core but not production-connected; P1.1b closes that with a governed `irrigation_mpc`-type candidate bridge (`lexicographic_mpc_bridge.py`) that propagates content_digest(64-hex)/idempotency_key/solver_version/candidate_lineage_id both at top-level and inside decision_value, plus a `POST /api/v1/irrigation/mpc/plan` route that reads server-truth depletion from `water_ledger` (no fabrication — absent row ⇒ Dr=0 + data_degraded declared) and derives tenant_id from the authed user. Structurally recommendation-only (execution_allowed=False, requires_human_review=True, no authorize/execution/MQTT path), default-off behind `LEXICOGRAPHIC_MPC_BRIDGE_ENABLED`, fail-closed on EMERGENCY — same posture as `water_decision_bridge`. A dedicated bridge module (not modifying water_decision_bridge) keeps the two irrigation paths decoupled. Enforced by a new static CI guard `mpc_lineage_propagation_guard.py`. Verified: 2957 unit (11 new), coverage 45.58%, ruff, Ky+lineage guards, bandit HIGH clean, module baseline 614→616, inventory synced, both routes honestly waived (recommendation surfaces via existing Decision/Approvals console; dedicated MPC UI tracked `MPC-P2-UI`). Full PG lineage propagation through execution→outcome→learning is staging-certified (simulation until then). SHA: pending branch CI green on claude/code-review-34hO3.

- **`0da934a3612eb7efce20f478c8f12203dfdb3cc9` — merged PR #584 (field-management-service extraction SEC-3/Option 2 + tile-401 cookie fix + VEGETATION_REAL_ONLY governance) by CLEAN fast-forward of main AND develop (`61fd7fc..0da934a`, no merge-commit).** Reason: the full Ratchet gate chain passed on this exact SHA, so the FF preserves the exact gate-tested commit rather than minting an untested merge/squash/rebase SHA. Three gates cleared: (1) CI 13/13 green (+30 standalone workflows) on 0da934a; (2) live staging gate `scripts/staging/field_management_live_gate.sh` — 8/8 acceptance, exit 0: SHA-pin · `sahool_app` NOSUPERUSER+NOBYPASSRLS · transaction-local `set_config` · isolation pytest ACTUALLY executed (1 passed, 0 skipped — a skip is a gate FAILURE) · HTTP 200/404/401/401 (owner sees field, spoofed tenant→404) · connection-reuse GUC-leak-free; (3) DB-cleanliness gate on `sahool`@`v22-sahool-postgres-1` — dev/seed only (users=2 dev accounts, fields=10 seed, operational tables seasons/recommendations/work_orders/raster_assets/decision_record=0), not shared across environments, drop/recreate-safe. False-alarm dismissed with evidence: `sahool_jobs BYPASSRLS=true` is BY DESIGN (cross-tenant background workers via `JOBS_DATABASE_URL`), documented in `migrations/v72/v73/v74/v93/v140` + `docs/audits/TENANT_QUERY_AUDIT.md:80-81` — NOT changed; the gate's NOBYPASSRLS criterion targets `sahool_app` only. Follow-up pending on the live env only: fresh migration test (drop→recreate→migrate). Branch `claude/code-review-34hO3` is now merged/spent; further work restarts from the new main.

- **`a60ecdc` — deleted three confirmed-dead frontend items (orphan-inventory follow-up): `ProtectedRoute.tsx`, `fieldWorkspaceCompletionContract.ts`, and the `useFieldIntelligence` hook export.** Reason: all three had zero references at HEAD and were superseded or scaffold — `ProtectedRoute` is unused since the app moved to `canAccess`+tab-render (not a route wrapper); `fieldWorkspaceCompletionContract` is a static contract object ("not a data source") imported nowhere; `useFieldIntelligence` is a superseded variant (the app uses `useFieldIntelligenceCard`/`useFieldIntelligenceJob`), and its now-orphan `analyzeFieldIntelligence` import was dropped with it. Kept out of scope: the exported service fn `analyzeFieldIntelligence` in `services/api.ts` (now unused but exported API surface) — follow-up candidate. `frontend/src` is tracked in `release/FILE_CHECKSUMS.sha256`, so the release bundle was rebuilt (4560→4519). Verified: tsc --noEmit exit 0 · vitest 1261/1261 (185 files) · validate_release 4519 · no residual refs. Pushed to `claude/code-review-34hO3`; main/develop untouched at `0da934a`.

- **CORRECTION to `a60ecdc` — `fieldWorkspaceCompletionContract.ts` was NOT dead; restored. Only `ProtectedRoute.tsx`, `useFieldIntelligence`, `NotificationCenter.tsx`, `FieldEntryWizard.tsx` are truly removed.** Reason: my orphan scan checked TS imports only and missed that `fieldWorkspaceCompletionContract.ts` is a guarded FE↔BE contract mirror — `services/sahool-platform/tests/test_ui31_ui35_workspace_completion_guard.py::test_ui34_completion_contract_exists_on_frontend_and_backend` asserts it exists and mirrors `api/field_workspace_completion_contract.py`, and `scripts/ci/field_workspace_production_closure_gate.py` also reads it. Deleting it turned the branch CI red (`a60ecdc`/`69a6607`); main/develop were never affected (stayed `0da934a`). This violated the already-recorded lesson "Python guards read frontend source, not just vitest." Fix: restored the file from `0da934a`; kept the genuinely-safe removals — `useFieldIntelligence` is safe because its guard `test_field_intelligence_async_job_guard.py` requires `useFieldIntelligenceJob`/`useStartFieldIntelligenceJob` (not the sync hook), and `ProtectedRoute`/`NotificationCenter`/`FieldEntryWizard` have no guards (only doc/SBOM mentions). Hardened lesson: before deleting any frontend file, sweep Python+JSON+CI+md (`grep -rln '<basename>' --include=*.py --include=*.json`), not TS imports alone. Verified green: tsc 0 · vitest 1261/1261 · pytest -m unit 3180 passed 0 failed · both guards 8/8 · validate_release 4518.

- **`9e38080` — FF main AND develop from `0da934a` to `9e38080` (`0da934a..9e38080`, no merge-commit), merging the branch cleanup+wiring chain.** Reason: the branch `claude/code-review-34hO3` CI completed green on `9e38080` (ci.yml success, confirmed via MCP + owner), and FF preserves the exact CI-tested SHA rather than minting an untested merge/squash/rebase commit. The merged chain: `7846689` (brain: PR #584 merge record) → `697cfa8` (fix: restore the guarded `fieldWorkspaceCompletionContract.ts` I had wrongly deleted + finish the safe dead-code removals ProtectedRoute/useFieldIntelligence/NotificationCenter/FieldEntryWizard) → `9e38080` (wire the orphan IrrigationEngineeringWorkspace to a real page + `/irrigation/engineering/calculate` endpoint). The broken deletion commits `a60ecdc`/`69a6607` remain in branch history but are superseded by `697cfa8` (contract restored); the merged end-state is correct and green. Pre-FF verify: branch CI green on 9e38080 + local tsc 0 · vitest 1265/1265 · pytest -m unit 3180/0 · endpoint-ui-coverage PASS · validate_release 4520. FF only, no auto-merge.

- **FII Safety FULL_DELTA (Increment 1) integrated onto main — RLS write fail-closed + 3 migrations v192–v194 + chemical_lineage shared governance module (audit-only).** Reason: previously-produced unmerged safety work (built on `0da934a`); the user directed integrating it as the base for the FII cross-service governance. Applied the 35-file delta onto the current tip (all its backend targets were byte-identical to `0da934a` on main — clean apply, no manual merge); excluded the stale `release/*` and rebuilt the bundle fresh. Migrations `v192` (RLS write fail-closed WITH CHECK), `v193` (prescriptions season-context expand), `v194` (chemical-chain RLS fail-closed) slot cleanly after `v191` (no collision) and are registered in BOTH runners (MANIFEST.txt + run_migrations.sql). Roles: `sahool_app`(NOBYPASSRLS)/`sahool_jobs`(BYPASSRLS, by design)/`sahool_user`(owner). Re-ran ruff (current config reformatted 3 + fixed 5 datetime.UTC) so Lint&Format stays green. Verified: fii_rls_write_policy_gate PASSED · fii_rls_role_gate PASSED · pytest -m unit 3180/0 · all 49 FII tests explicit 0-fail · validate_release 4543 · ci.yml valid + "FII RLS safety gates 1C" step references existing scripts. **Still required before FF: a LIVE PostgreSQL staging gate (RLS write fail-closed + role NOSUPERUSER/NOBYPASSRLS + tenant isolation), same discipline as #584 — CI green alone does not certify RLS.** FII cross-service (Increment 2) queued after this.

- **FII migration hardening (forensic findings #11 + #12) — make partial-schema absence of an FII-critical table a HARD fail-closed error, not a silent skip.** Reason: v192's `COMMENT ON POLICY` statements were outside the `to_regclass` guard (crash on partial schema after the DO-block claimed the table optional — finding #11), and v194's `IF to_regclass(...) IS NOT NULL THEN` silently skipped any absent chain table, which would then be writable without tenant isolation (fail-OPEN — finding #12). For a fail-closed security migration, a missing table that MUST exist by this point in the chain (v192: scouting_pins v94 / prescriptions v95; v194: recommendations v77 / decision_record v78 / work_orders v75 / actuator_command_dedup v81 / outcome_record v79 / lineage_link v82) is schema drift that must abort loudly. Fix: v192 inverts to `IF to_regclass(...) IS NULL THEN RAISE EXCEPTION` for both required tables and moves each `COMMENT ON POLICY` inside the guaranteed-existence block; v194 splits explicit `required_tables` (RAISE EXCEPTION if absent) vs `optional_tables` (empty today; RAISE NOTICE + skip) while keeping the positive `IS NOT NULL` branch (gate test forbids the literal `IS NULL`). Both stay idempotent (`DROP POLICY IF EXISTS`+`CREATE`). Only v192/v194 edited — no shipped history <=v191 touched; historical gate scope (BASELINE_MAX=191) unchanged. This is the lowest-risk P1 item (SQL logic only, no live infra). Verified: fii_rls_write_policy_gate + fii_rls_role_gate PASSED · 5 fii security tests pass · runners-in-sync 2 pass · ruff clean · release bundle rebuilt + validate 4544. enforce readiness still NO; live RLS staging gate still required before any FF. SHA: pending branch CI green on claude/code-review-34hO3.

- **IRR-F01 Gate A (Phase-2 DB) مُعتمَد على PostgreSQL 16 + PostGIS حيّاً — RLS/FK/GiST/قفل معاملاتيّ/قبول/rollback كلّها خضراء بقيادة المُحوّل الحقيقيّ عبر asyncpg كـsahool_app (NOSUPERUSER/NOBYPASSRLS).** Reason: البيئة أتاحت Postgres محليّاً، فبدل تأجيل «بوّابة PG الحيّة» كاملةً، نُفِّذ شطرها الأوّل فعليّاً — طُبِّقت v195+v196 الحقيقيّة، وأُثبِت أنّ ما لا تُثبِته CI (العزل fail-closed، منع overcommit على الذروة لا المجموع، تسلسل الأقفال بجلستَين، سلامة rollback) صحيحٌ على محرّك حقيقيّ. أُودِع اختبار دائم `tests_v9/test_irr_f01_reservation_live_pg.py` (integration، يتخطّى بلا DB). Gate B (ربط emit_event/EventType + تسليم حيّ + دلالات الإيصال) يبقى مؤجَّلاً ويظلّ شرطاً قبل أيّ FF لـmain/develop. لا يُبدَّل هذا القرار موقف «لا FF قبل اكتمال بوّابة PG» — فقط يوثّق اجتياز شطرها الأوّل. SHA: pending branch CI green على claude/code-review-34hO3.

- **Gate-Trust reconcile (canonical wholesale + revocation kill-switch) — أصلح عيباً بنيويّاً في جذر الثقة: التوقيع المزدوج كان غير متسق الحمولة.** Reason: تبنّى الفرع نموذج الإيصالات الموقَّعة canonical بالجملة، لكنّ التوقيع كان يُحسَب بطريقتين مختلفتين — ingest يوقّع *مع* `gate_name` وبـ`payload` كـdict؛ resolve يعيد التحقّق *بدون* `gate_name` وبـ`payload` كنصّ (asyncpg يعيد jsonb نصّاً) — فكلّ receipt مقبولة عند ingest تُرفَض عند resolve (`evidence_signature_invalid`). التحقّق المزدوج كان شكليّاً وقيمته الدفاعيّة صفر حتّى وُحِّد. العيب عاش خلف skip (جناح PG الحيّ كان دائماً متخطّى) — تأكيدٌ لقاعدة «المتخطيات ليست نجاحاً». الإصلاح: دالّة قانونيّة واحدة `canonical_evidence_signature()` يستهلكها المنتِج+ingest+resolve (تربط gate_name، UTC ISO للطوابع، jsonb→dict). أُضيف: جدول `activation_evidence_revocations` INSERT-only + فحص NOT EXISTS ذريّ عند resolve + endpoint إبطال بمصادقة actor (Condition 2 المُرقّى)؛ deploy_build_sha fail-closed + conftest حتميّ (Condition 1)؛ سقف 24h + PROVENANCE_RE canonical + الفهرس الدلاليّ الفريد (تحقّق 1c) + extra="forbid". تحقّق على شجرة نظيفة `3abc127`: تفعيل 53/53 (0 skipped) · raster race 17/17 · Gate B 18/18 · PROD guard 12/12 · release 4594. إصلاحات CI في `c3c461e` (persistence import-sort · ci.yml → ملفّات الاختبار الجديدة · SERVICE_REGISTRY.md · حارس P0 يقبل create_pool · pytest-asyncio لبوّابة الريّ). SHA النهائيّ: `c3c461e` على `claude/code-review-34hO3` (main/develop لم تُمسّ، 9e38080). السجل المفتوح للإنتاجيّ: IRR pre-reservation guard · middleware slice · عزل مفاتيح المنتجين · شهادة PG حيّة نهائيّة في بيئة المالك على SHA المدموج.

- **`dae894b` — FF main from `9e38080` to `dae894b` (`9e38080..dae894b`, 51 commits, no merge-commit), landing the activation-gate ledger (①②④) live-certified + the WebSocket auth reconnect-loop fix.** Reason: the user's adopted ordering was WS-slice-on-tip → re-certify → one FF on the final SHA. Live PostgreSQL cert on `bf6fcf3` then final tip `dae894b` = **53/53 activation suite, 0 skips** (fresh `decision_cert` DB, 030 receipts+revocations+6 CHECK constraints+immutable trigger verified, revocation behavioral path passed); `git diff bf6fcf3 dae894b -- services/decision-service` empty ⇒ cert transfers to the final tip. Branch CI #4193 green on `dae894b`; FF preserves the exact CI+PG-tested SHA (no minted merge SHA). The WS fix (`dae894b`, sole commit over `bf6fcf3`): `notifications.py` closed(1008) before accept() with URL-only token and no auth_ok → infinite reconnect loop (FE-10) + locked FE-09 outbox; fixed to accept-first → token from first `auth` frame (or `Sec-WebSocket-Protocol` fallback, `?token=` removed) → single `get_current_user` verify → `auth_ok`; 6 behavioral + 1 static guard. **HONESTY CAVEAT:** the 51 commits also carried the FII safety work (`v192`/`v194` RLS write fail-closed + chemical_lineage governance, 5 commits) whose own ledger entry states "a LIVE PostgreSQL staging gate is still required before FF — CI green alone does not certify RLS." That FII live-RLS gate was NOT separately re-run before this FF. Mitigants: the migrations are defensive (fail-closed, tighten not loosen), chemical governance is audit-only/enforce=NO, `fii_rls_write_policy_gate`+`fii_rls_role_gate` static gates green in CI, and IRR-F01 Gate A (adjacent v195/v196) was live-certified on PG+PostGIS as `sahool_app` NOSUPERUSER/NOBYPASSRLS. Open verification item logged in `gaps/registry.md`. Verify: `git ls-remote` → `main == claude/code-review-34hO3 == dae894b`, 0 merge commits in `9e38080..main`.
- **Post-FF main-CI drift fix (folded in the branch commit immediately after `dae894b`) — regenerated 3 main-only drift artifacts + closed a fastapi CI-env gap so main CI goes green.** Reason: the FF to main fired main-only workflows invisible to branch CI, exposing accumulated drift from the 51 commits: `route_residual_classification.*`, `REPORT_INDEX.md`, `health_readiness_inventory.*` were stale (regenerated with each guard's `--write`; `runtime_real_smoke.sh` consumes the first+third so it greened transitively), and `raster-validated-product.yml` (main-only, `branches:[main]`) grew a `satellite_cdse` P2-c step that imports `raster_cdse_tile_runtime → raster_date_geo → fastapi` while the job installs only `tests_v9/requirements-test.txt` → `ModuleNotFoundError: fastapi` (fixed by adding `fastapi` to the install line — the httpx lesson repeated). Ratcheted lesson: a large FF fires main-only gates that branch CI never runs; watch main CI immediately after any FF, not just branch CI. Verified locally: the three `--check` gates ok · imagery-source-gate 17/17 · release bundle rebuilt. SHA: this branch commit, FF'd forward to main after main CI confirms green.

- **2026-07-18 — إصلاح InterfaceError في PATCH /api/v1/fields/{id} (علّة حرجة في البيئة الحيّة).** SHA: محليّ (جلسة رنبوك التحقّق الحيّ، فرع claude/code-review-34hO3). Reason: عبر رنبوك التحقّق الحيّ (§⑦ التدفّقات المكانيّة) اكتُشِفت علّة: `conn.fetchrow("SELECT … WHERE field_id = $1 AND tenant_id = $2::uuid", field_id)` يمرّر معاملاً واحداً لاستعلام يحتاج اثنين ⇒ `asyncpg.exceptions.InterfaceError: the query requires 2 arguments, but 1 were given`. الموضع: `routers/fields.py:1316` (مسار تعارض الإصدار) + `:1339` (مسار الدمج التلقائيّ) + `:1396` (المسار العاديّ). الإصلاح: إضافة `str(user.tenant_id)` في المواضع الثلاثة. النتيجة: 10/10 تدفّقات E2E مكانيّة نجحت (pytest integration: 1/1 PASSED).
- **2026-07-18 — إصلاح توافق Windows في حارسَي CI + اختبارات الوحدة + nginx رستر (3163/0 فشل).** SHA: `c6cb6d5a` (فرع `claude/code-review-34hO3`). Reason: فشلت 2 حالة متبقّيتان بعد كلّ إصلاحات الترميز: (1) `weather_engine_formula_guard.py` وحارس `endpoint_ui_coverage_gate.py` كلاهما استخدم `str(path.relative_to(root))` الذي يُعيد خطوط مائلة عكسيّة على Windows فلا يُطابق المسارات ذات الخطوط الأماميّة في JSON/PHANTOM_EVIDENCE_FILES → الإصلاح: `.as_posix()`. (2) `frontend/nginx.conf` — كتلة `/api/raster/` لا تحوي `if ($cookie_sahool_at)` الذي يتطلّبه اختبار `test_raster_location_uses_cookie_auth_request` → الإصلاح: إضافة كتلتَي `if` للـcookie والـquery-token مطابِقةً لـ`nginx.v9.conf:235-236`. النتيجة: `pytest -m unit` → 3163 ناجح، 0 فشل، 23 متخطَّى.

## 2026-07-18 — ADR-0033 FIELD-SVC tenant-claim trust (تصميم مُجمَّد، لا تنفيذ)
- **القرار:** كتابة ADR-0033 يجمّد تصميم تصليب رباط المستأجر لـ`/internal/fields` (مطالبة موقَّعة بدل ترويسة X-Tenant-Id الحرّة)، **بلا تنفيذ الآن**. بإذن المالك الصريح: «آذن بالتصميم الموثَّق فقط، لا التنفيذ».
- **السبب:** التصليب يمسّ عقد #201 الحيّ عبر كلّ مستهلكي النقطة الداخليّة؛ تعديله لحظة استقرار main بلا ضغط حادث يخالف انضباط الشرائح الأمنيّة (تهبط مع اختباراتها في نوافذ عمل، لا كمبادرات منعزلة). لكن تأجيل بلا تصميم = نسيان مؤجَّل؛ الـADR يجمّد ما كلّف اكتشافه غالياً ويجعل التنفيذ لاحقاً ترجمةً لا إعادة اكتشاف.
- **المحفّز:** أوّل تعديل جوهريّ على field-management-service أو إضافة مستهلك جديد لـ`/internal/fields`.
- **SHA:** يُدفَع مع هذا القيد. **الأثر الكوديّ:** صفر (وثيقة فقط).

## COMPARATIVE-STUDY-01 — تصحيح ثلاث مزاعم في الخطة الموحّدة بأدلّة حيّة (2026-07-18)
- **القرار:** اعتماد `docs/audits/COMPARATIVE_STUDY_PLAN_VS_REALITY_20260718.md` مرجعاً حاكماً للأولويّات، مع **ثلاثة تصحيحات** لخطّة التطوير الموحّدة قبل أيّ تنفيذ.
- **التصحيح 1 (A3):** الخطة افترضت «wofost_adapter قائم»؛ الواقع placeholder حتميّ (PCSE غير مُركَّب/غير صالح، `requirements.txt:12` معلّق، `_pcse_simulate` سقالة). ⇒ **SIM-PCSE-01 يسبق SIM-GOLDEN-01**.
- **التصحيح 2 (A4):** الخطة افترضت «التوصيل غائب»؛ الواقع الحدود التلقائيّة موصولة end-to-end في onboarding + ثقة + تأكيد بشريّ. ⇒ A4 يتقلّص لـUX suggest-on-open + نشر GPU.
- **التصحيح 3 (B2):** الخطة قالت «لا طبقة تربة مؤسسية»؛ الواقع SoilGrids مُدمَج بتراتبيّة صارمة (`profile_composer.py:22-41`). ⇒ B2 يسقط لـP2 صغير (tier إقليميّ وسيط).
- **السبب:** قاعدة «لا تحليل يُقبل دون grep على الوجهة الفعليّة أوّلاً» — الأولويّات مبنيّة على الواقع المُثبَت لا على الزعم؛ التخطيط على افتراض خاطئ يهدر جهداً (golden قبل محرّك، توصيل قائم أصلاً، بناء طبقة موجودة).
- **الأولويّات المُعتمَدة:** A2 OCSM + A5 عقد ملوحة → B1 SCOUT-INGEST (P0) → SIM-PCSE→golden → A6/A7 (P2).
- **SHA:** يُدفَع مع هذا القيد. **الأثر الكوديّ:** صفر (دراسة تحقّق + وثيقة).

## WATER-SALT-01 (A5) — عقد قدرة الملوحة يُعلِن حدوده (يمنع fail-open المقنّع)
- **القرار:** إعلان قدرة الملوحة القائمة في عقد واحد (`core/salinity_capability.py`) **يذكر الحدود قبل القدرة** — كلّ ادّعاء `covers` بمرجع `file:line`، و`limits`/`status_enum` إلزاميّة يفرضها حارس ببرهان سلبيّ.
- **السبب (ملاحظة المالك، مُعتمَدة):** عقد قدرة لا يقول متى يتوقّف عن الثقة = fail-open مقنّع. الحارس يرفض بنيويّاً `supported:true` بلا حدود ⇒ يستحيل شحن قدرة صمّاء عن حدودها. صفر تغيير لرياضيّات الملوحة (عميقة وصحيحة أصلاً) — تجميع + إعلان فقط.
- **SHA:** يُدفَع مع هذا القيد. **الأثر:** ملفّ قدرة صرف + حارس + وثيقة؛ لا مسار runtime، لا تغيير عقد قائم.

## SEM-OCSM-01 / ADR-0034 — crosswalk OCSM كخريطة مرجعيّة (لا تبنٍّ)
- **القرار:** توثيق تعيين عقود SAHOOL الأربعة إلى OCSM (`agstack/OpenAgri-OCSM @ 12863f1b`، CC-BY-4.0) بقرار لكلّ انحراف، دون أيّ تغيير عقد/تبعيّة/مُسلسِل. حارس يمنع تسرّب OCSM إلى `shared/contracts/`.
- **السبب:** يوفّر مفردات مستقرّة محاذية لمعيار لمظروف B1 (كي يُعيّن الطرف الثالث مرّة واحدة) — والعنقود الأقوى (`sosa:Observation`) هو المرشّح الأوّل. المرجع مُثبَّت بالجلب لا الذاكرة (قاعدة grep-الوجهة-الفعليّة). Season/Irrigation `absent` في OCSM الأساسيّ = نتيجة حقيقيّة.
- **محفّز التنفيذ:** أوّل حاجة فعليّة لتشغيل بينيّ (مظروف B1 أو شريك OCSM). حتى ذلك: مرجع فقط.
- **SHA:** يُدفَع مع هذا القيد. **الأثر:** ADR + حارس؛ صفر تغيير عقد/runtime.

## SCOUT-INGEST-01 / B1.2b — قرار (ج) مُصحَّح: خدمة مالكة مستقلّة لا مسار منصّة
- **القرار:** بناء `scout-ingest-service` مستقلّة تملك مسار الإدخال الخارجيّ (`/internal/ingest/submissions/odk`) + جدول `external_submissions` (db_ownership نُقِل platform→scout-ingest-service)، بدل مسار على المنصّة كما اقترحت المواصفة أوّلاً.
- **السبب:** حُرّاس المنصّة الأربعة (route_budget_does_not_grow · route_budget_reduced · route_ownership · mutating_auth) **رفضت** أيّ مسار منصّة جديد — انضباط strangler: المنصّة تُقلّص لا تنمو. الحُرّاس ليست عقبة بل الهندسة تُصحّح قراراً أقدم. **السابقة #201** (field-management-service) حسمت النمط: مدخل خارجيّ ⇒ خدمة مالكة. الحُرّاس الأربعة **لم تُعدَّل** (هم اتّخذوا القرار، فلا نكافئهم بالتعديل).
- **الأمان:** اعتماد لكلّ مصدر (X-Scout-Ingest-Token→resolver DEFINER، لا توكن مشترك/JWT) · دور `sahool_ingest` NOBYPASSRLS بأقلّ منح (SELECT+INSERT، لا UPDATE/DELETE) · الهويّة من السجلّ لا المُرسِل · خلف SCOUT_INGEST_ENABLED. حارس ملكيّة `test_scout_ingest_service_ownership.py` يُثبّت الكاتب الوحيد بنيويّاً.
- **تصحيح مرافق (مفتاح dedup):** `derive_dedup_key` = هويّة الخانة `sha256(provider|server|form|instance)` فقط — **أُزيل content_hash** (كان يجعل حالة التباين مستحيلة)؛ content_hash يُقارَن منفصلاً. التقطه البرهان الحيّ (divergent كان يعيد accepted بدل quarantined).
- **SHA:** يُدفَع مع هذا القيد. **الأثر:** خدمة جديدة + دور DB + نقل ملكيّة + كتلة compose + حارس؛ صفر تعديل لحُرّاس المنصّة الأربعة. برهان HTTP حيّ 6/6 + أقلّ-منح على PG16.

## SCOUT-INGEST-01 / B1.3 — القرار (أ): نموذج قراءة مملوك، لا كتابة scouting_pins
- **القرار:** scout-ingest يملك `external_field_observations` + عامل إسقاط + نقطة قراءة خاصّة؛ لا يكتب `scouting_pins`/`observations` المملوكَين للمنصّة. توحيد العرض مع FieldView = دَين موثَّق مؤجَّل (B1.3b).
- **السبب:** (ب) [عامل منصّة يكتب scouting_pins] يُنمّي المنصّة فيعاكس قرار (ج)/الحراس الأربعة في الشريحة التالية مباشرةً. (أ) يحترم single-writer مرّتين (المنصّة وحدها لـscouting_pins، scout-ingest وحده لجدوله). الازدواج دَين لا خطأ — الـstrangler يؤجّل التوحيد حتى تنضج الحدود.
- **الشرطان (المالك):** ① محفّز B1.3b مكتوب (أوّل مستهلك قرار يحتاج رؤية موحّدة أو مصادر القراءة > 2). ② عقد قراءة مُعلَن بتوكن خدمة مخصّص (لا direct-DB).
- **قرار فرعيّ (least-grant↔scan):** claim/complete = SECURITY DEFINER يملكهما resolver (BYPASSRLS) ⇒ sahool_ingest يبقى بلا UPDATE. + trigger BEFORE UPDATE يصون immutability الخامّ (يُسمح projection_* فقط).
- **SHA:** يُدفَع مع هذا القيد. **الأثر:** v199 + عامل + نقطة + دور DEFINER×2 + كتلة compose + حارس؛ صفر كتابة لجداول المنصّة، صفر نموّ منصّة. برهان حيّ PG16 (accepted-only + idempotent + dead_letter).

### قرار: السجلّ التشغيليّ #3 — حارس انجراف env↔compose (تقرير→مراجعة→حارس)
- **القرار:** بناء حارس CI يمنع «كود يقرأ env بلا افتراضيّ وcompose/.env.example لا يزوّدها ولا هي مُصنَّفة» — بدأ تقريراً ثمّ قُلِب حازماً بعد مراجعة الـ32 كلّها.
- **السبب:** صنف عضّ مرتين (httpx، JWT_SECRET) اكتُشِف بالصدفة ⇒ سيعضّ ثالثة؛ يُبنى الآن رخيصاً في ذروة الحُرّاس.
- **الصدق:** لا تعليب أعمى — الـ5 المشتبَهة فُحِصت سطراً-سطراً؛ لا شيء كسر صامت (خاصّة RLS-bypass: غيابه fail-closed = لا تجاوز أبداً). أسرار الفئة B يجب ألّا تظهر في compose (غيابها هو الأمان).
- **SHA:** يُدفَع مع هذا القيد. **الأثر:** guard + allowlist(32 مُبرَّرة) + خطوة ci.yml + حارس unit(6 ببرهان سلبيّ).

## SEASON-RECORD-ENTRY-01 (شريحتا 2a+2b) — 2026-07-19
- **القرار:** واجهة إدخال المواسم كلّها على scout-ingest المالكة (صفر مسار منصّة)، بمخزن كائنات عامّ جديد `shared/storage/blob_store` يعيد استخدام S3_* المشترك، وتصديق حافّة HMAC للقبول الحسّاس.
- **السبب:** الوصول ≠ الثقة — القبول يحرّر calibration_eligible فيحتاج هويّة إنسان مُصدَّقة من الحافّة لا مجرّد توكن خدمة؛ والمخزن عامّ لأنّ object_store ملوّث بدلالات COG/GDAL.
- **الانحرافات المُعلَنة:** لا تحقّق وجود الحقل هنا (اقتران فضفاض v201، لا منح عابر للعزل) · accept يرفض file:// في الإنتاج (إضافة فوق عقد المخزن) · draft_key مفتاح dedup لا مرجع ثقة (v202).
- **SHA:** `41fb073`+`0d5990f` (2a) · `66f65f0` (2b) · `360e3f3`+`288f5ad`+`7bb82e5` (ضريبة التسجيل) · `78ff445` (إصلاح طبقة CI الخفيفة) · **`87a3d2e` (مناعة تصادم اسم shared — الطرف الأخضر المُقفَل، Unit Tests xdist ✅)**. **الفجوتان:** MINIO-PER-SERVICE-CREDENTIALS · RUFF-FORMAT-DRIFT-SHARED.

## SEASON-RECORD-ENTRY-01 (الشريحة 3: 3a + 3b + 3c) — 2026-07-20
- **القرار:** القبول الحسّاس يُصدَّق عند البوّابة بتوقيع HMAC **مقيَّد الوجهة** يوقّعه auth ويتحقّقه scout-ingest، بمصدر قانونيّ **واحد** في nginx؛ وسلطة المُراجِع مُشتقّة لـ{owner, expert} فقط (admin مستثنى عمداً)؛ والواجهة تُرقّم عبر السطح الخلفيّ الموجود فقط.
- **السبب:** (①) توقيع الهويّة فقط يُعاد لعبه عبر المسارات ⇒ التقييد بـmethod/path/body يقتل إعادة اللعب؛ (②) مصدر قانونيّ واحد (`map $request_uri`) يمنع انحراف ما يوقّعه auth عمّا يُمرَّر upstream؛ (③) البوّابة تكتب X-Canonical-* وتُفرِغ ترويسة العميل فلا تصل المزوَّرة؛ القبول فعل زراعيّ لا تشغيليّ فـadmin مستثنى.
- **الانحرافات/الحدود المُعلَنة:** `SEASON_EDGE_HMAC_KEY` فئة B (لا في compose، غيابه fail-closed) · البرهان السلبيّ ③ حيّ لا وحدة ⇒ مؤجَّل لـstaging (فجوة SEASON-EDGE-LIVE-PROOF + مهمّة #225) · نقاط events/harvest/costs غير مبنيّة ⇒ الواجهة لا تبني نماذج لها (لا نصف حلّ؛ فجوة SEASON-ENTRY-EVENTS-UI).
- **درس CI:** ضريبة التسجيل سبعة مولَّدات لا ستّة — `route_mount_contract_guard` هو السابع (فاتني ⇒ أوقع Structural Lint + Runtime Real Smoke).
- **SHA:** `6158688`+`81a9fc4` (3a) · `19c4e63` (3b-core) · **`d9f5aa4`+`047486b` (3b-infra، الطرف الأخضر)** · `9f92c7d` (3c). **الفجوتان الجديدتان:** SEASON-EDGE-LIVE-PROOF · SEASON-ENTRY-EVENTS-UI.

## SEASON-ENTRY-EVENTS-UI — 2026-07-20
- **القرار:** إكمال سجلّ الموسم بأربع نقاط أبناء (events/harvest/costs/detail) على scout-ingest المالكة + خطوات واجهة مقابلة؛ الأهليّة للمعايرة تُقرأ من الـVIEW المُشتقّ لا تُعاد حسابها.
- **السبب:** الجسر بلا events/harvest = نصف أداة (لا معايرة). الحصاد بدقّة يوميّة هو ما يفتح SIM-GOLDEN؛ وقراءة الأهليّة من الـVIEW تُبقي قاعدة الأهليّة مصدراً واحداً (لا منطق مُكرَّر في النقطة).
- **الانحرافات/الدروس المُعلَنة:** low_confidence يُوسَم تلقائيّاً لا يُخمَّن (قاعدة ٤) · الأبناء untrusted فقط (409، فوق trigger التجميد) · **منح SELECT على الـVIEW لـsahool_ingest** كان ناقصاً (البرهان الحيّ كشفه 503 — لا تمسكه الوحدة) فأُضيف للمُشغّلَين.
- **SHA:** `7419b13`. **الفجوة المُقفَلة:** SEASON-ENTRY-EVENTS-UI. **يبقى OPEN:** SIM-PATHS-DUAL (يُحسَم عند SIM-GOLDEN-01) · SEASON-EDGE-LIVE-PROOF (#225، staging).

## SIM-PATHS-DUAL — اتّجاه الحسم المعتمد مسبقاً (2026-07-20)
- **القرار (اقترحه المراجع الرئيسيّ — تحليل الازدواج، الخيار ب «أميل لـ(ب)» — اعتمده المالك 2026-07-20؛ يُصدَّق رسميّاً في SIM-GOLDEN-01، لا كود الآن):** تسلسل هرميّ مُعلَن للمحاكاة — **PCSE/WOFOST مرجعيّ (نقطة المعايرة الوحيدة)** · `season_simulation` استكشافيّ `screening_only` (يُمنَع جنب PCSE) · AquaCrop للمسار الملحيّ (ec_e≥2.0، محسوم). QUEFTS يتبع PCSE لا يُعايَر مستقلّاً.
- **السبب:** لا تُعايَر غلّة حقيقيّة (`season_harvest.yield_kg_ha`) ضدّ نموذج موسميّ ساكن المعاملات بينما يتوفّر محرّك يوميّ الخطوة قابل للمعايرة (PCSE). الدمج يخلط فلسفتين؛ المنصّة-أوّلاً تُورِث قيد ±20٪ للمرجع؛ الهرميّ يُبقي قيمة الخفيف (screening/what-if) دون منازعة المرجع.
- **الشرطان عند المصادقة:** `screening_only` حارس سلبيّ في عقد `simulation_capability.py` (لا تعليق) · QUEFTS يقرأ مخرجات WOFOST.
- **SHA:** توثيق اتّجاه فقط (لا بناء) — يُدفَع مع تحديث الدماغ هذا. **الحالة:** SIM-PATHS-DUAL يبقى OPEN حتى المصادقة + البراهين في مواصفة SIM-GOLDEN-01.

## SEASON-RECORD-01 تدقيق مطابقة — v203 (قيد البذار DB-level) + انحراف quarantine مقبول — 2026-07-20
- **القرار (تدقيق المالك spec↔مبنى):** ① فرض قيد النزاهة 2 (بذار ضمن نطاق المشاهدة) على القاعدة بـ`v203` trigger (كان تطبيقيّاً فقط، خلاف نصّ المواصفة «DB-level لا تطبيقيّة فقط») · ② قبول انحراف `quarantined` (رفض مبكّر للمتزامن، الحجر لغير المتزامن).
- **السبب:** الواجهة عميل مؤدّب لا حارس — مستدعٍ مباشر يتجاوزها؛ الترقيم الورقيّ جلسة متزامنة فالرفض المبكّر يردّ الخطأ لمن يصلحه فوراً (quarantine يُنتج كومة سيّئة تنتظر مراجعة قد لا تأتي).
- **الصدق:** رسالة رفض v203 تذكر النطاق الفعليّ (حارس لا عائق)؛ قواعد 4ب/4ج تبقى سارية كرفض مبكّر (تغيّرت آليتها لا وجودها).
- **SHA:** يُدفَع مع هذا. **الأثر:** فجوة مطابقة واحدة أُغلِقت + انحراف موثَّق؛ مطابقة spec↔مبنى بعد الإقفال (تُؤجَّل عادةً للأبد) وجدت فجوة صلابة واحدة فقط في مخطّط بهذا الحجم.

## BRANCH-RECONCILE — main (7 hardening) ↔ claude/code-review-34hO3 (build branch) — 2026-07-20
- **السياق:** جلسة التدقيق العميق دفعت 7 التزامات hardening إلى `main` (honest-readiness · CORS/TLS/secrets guards · ERP readiness · provenance-wire · lint-fix · migrate-fix)، بينما فرع البناء/التطوير المخصَّص هو `claude/code-review-34hO3` (25 التزاماً: INGEST + Windows/encoding + routes…). تباعَدا عند `84e14f0`.
- **القرار (المالك):** **الخيار 3 — اترك `main` كما هو الآن.** إصلاح المهاجرة أُعيد تطبيقه على فرع البناء (`1032392`) فـstaging غير محجوب؛ دمج 25+7 وحلّ تعارضات (migrations.sh · release bundle · agriai) **قبل** براهين #225 = مخاطرة توفيقيّة عشوائيّة على مسرح البراهين الحيّة → مرفوض توقيتيّاً.
- **إحياء الفرع:** `claude/code-review-34hO3` كان في **قائمة دفن الفروع** («22 متقدّماً» + قوس «الحصاد قبل الدفن»). صار الآن فرع البناء النشط (25 التزاماً) ⇒ **الحذف مُلغى قطعاً، يُشطَب من دفعة الدفن**.
- **التزام ما بعد #225 (رسميّ):** التوفيق الكامل = دمج `claude/code-review-34hO3` في `main` (الاتحاد 7+25) بحلّ التعارضات + CI أخضر على SHA الاتحاد → **ثمّ يُدفَن الفرع فعلاً ويعود العمل على `main` مباشرة**. لا فرع بناء موازٍ دائم (هكذا وُلدت كارثة `8c2373d`).
- **الصدق:** «leave main as-is» قرار **تأجيل توقيتيّ لا تخلٍّ** عن الـ6 hardening المتبقّية (CORS/TLS/secrets/ERP/provenance) — قيمتها حقيقيّة، لا تحجب التشغيل، وتوفيقها بعد #225 يجعل البراهين تختبر الشجرة المتّحدة النهائيّة.
- **SHA:** القرار مُسجَّل مع `1032392` (فرع البناء). **main tip:** `fbaccd2`.

## SEASON-EDGE-LIVE-PROOF — ✅ مُغلَق (البراهين الحيّة رُصِدت على staging) — 2026-07-20
- **القرار/الإقفال:** المهمّة #225 (البند الحيّ الوحيد المتبقّي لـSEASON-RECORD-ENTRY-01) مُغلَقة — البراهين الثلاثة خضراء على staging عبر `scripts/e2e/season_gateway_live_gate.py` (المالك): (أ) ترويسات مزوَّرة بلا جلسة ⇒ deny · (ب) مُراجِع شرعيّ ⇒ 200 · (ج) إعادة قبول ⇒ 409. «ALL PROOFS PASSED ✅».
- **الأثر:** حدّ الثقة الإنتاجيّ للبوّابة (تجريد nginx للترويسات + تصديق HMAC مقيَّد الوجهة) مُثبَت **حيّاً** لا تصميميّاً فقط. SEASON-RECORD-ENTRY-01 مكتمل end-to-end (2a→3c + الأحداث + البراهين الحيّة).
- **يفتح:** التزام التوفيق (فرع البناء → main، الاتحاد، دفن الفرع) لم يعد محجوباً بـ#225 — انظر BRANCH-RECONCILE.
- **SHA:** فرع البناء `claude/code-review-34hO3` (staging مبنيّ منه).

## 2026-07-20 — BRANCH-RECONCILE مُنفَّذ: دمج فرع البناء في main (اتحاد)
- **القرار:** بعد إخضار فرع البناء على CI (fa6a128 أخضر تماماً)، دُمِج `claude/code-review-34hO3` في `main` عبر merge `--no-ff` (b01c75b، أبوان fbaccd2+fa6a128). حُلّت 8 تعارضات: migrate ⇐ صيغة `\gexec` المُعتمَدة · SERVICE_REGISTRY/service_inventory ⇐ أُعيد توليدها · release bundle ⇐ أُعيد بناؤه (4700).
- **السبب:** توحيد الفرعين المتباعدين (منذ 84e14f0) في تاريخ واحد: 7 hardening على main + سلسلة المراجعة (migrate-fix + #225 + إصلاحات raster) دون فقد أيّ جانب.
- **الصدق:** لم يُدمَج أحمر — اكتُشِف أنّ الفرع كان أحمر على CI (لا محليّاً فقط)، فأُصلِحت 3 عِلَل (حارسان ساكنان هشّان + رابط DB اختبار + سياق TLS مُضمَّن) قبل الدمج وبعده. برهان الاتحاد أخضر محليّاً (`-m unit` 3364) قبل الدفع.
- **يبقى:** دفن فرع `claude/code-review-34hO3` (حذفه) يحتاج إذناً صريحاً — لم يُحذَف بعد.
- **SHA:** `b01c75b` (main).

## 2026-07-20 — 🌾 سجلّ الجنازة: دفن `claude/code-review-34hO3` بعد خضرة الاتحاد
- **الطرف المُؤرشَف:** `fa6a128186369eebd6c3bfdec8dcbef0e074ae66` (2026-07-20T14:15:31Z) — «fix(migrate-tests): v201 append-only guard tolerates \gexec form + refresh release bundle».
- **المصير:** **أُدمج في `b01c75b` (main)** بعد خضرة الاتحاد. 34 التزاماً منذ merge-base `84e14f0`، جميعها الآن مبلوغة من `main` (فحص `--not origin/main` فارغ ⇒ لا عمل غير مدموج يُفقَد).
- **⏳ الحذف الفيزيائيّ مؤجَّل:** بيئة الوكيل تحظر ref-deletion (HTTP 403، لا MCP بديل). يُنفَّذ من واجهة GitHub أو جهاز بصلاحيات دفع عادية. المرجع غير ضارّ: fa6a128 محتوًى بالكامل في main (0/34 غير مُدمَجة). — أي أنّ هذا السجلّ **لا يدّعي دفناً لم يحدث**: الحكاية مكتوبة والمرجع باقٍ حتى الحذف الشكليّ.
- **شرطا الإذن (تحقّقا):** (١) main CI أخضر بالكامل على الاتحاد — بما فيه البوّابتان main-only اللتان لم ترَيا الاتحاد قط: *Runtime Real Smoke* ✅ و*Sahool Production Gates* ✅ (production_truth_readiness_gate)، إضافةً إلى *SAHOOL v9.1.0 CI* ✅ (run 29751291136، success) على طرف `main` c7c25c0 الحاوي شجرة الاتحاد كاملةً. (٢) هذا السجلّ.
- **الحكاية:** الفرع الذي نجا من الجنازة الأولى بـ«22 التزاماً مجهولاً»، فعاد وبنى نصف المنظومة الحديثة (CDSE truecolor · terrain · decision SoR · MPC · الموسم · إلخ)، ثمّ أدّى غرضه الأخير (إصلاح \gexec + براهين #225) — يُدفَن بشرف فور تنفيذ الحذف الشكليّ (محتواه مُدمَج ومؤرشَف). أمر الدفن: `git push origin --delete claude/code-review-34hO3`.
- **SHA:** الاتحاد `b01c75b` · الطرف المدفون `fa6a128` · طرف main `c7c25c0`.

## 2026-07-20 — MIGRATE-ID-COLLISION مُغلَق: فضاءان منفصلان لنظامَي الهجرة
- **القرار:** فصل صريح — `alembic/versions/` = مراجعات alembic `NNNN_*.py` حصراً · `migrations/` = `vNNN_*.sql` حصراً. أُزيل الزومبيّان `alembic/versions/v101_field_runtime_cohesion.sql` و`v105_marketplace_ecosystem.sql` (بقايا ما قبل phase19، ميّتان بثلاثة محاور: لا MANIFEST · لا runner · خارج سلسلة alembic + صفر استعمال جداول).
- **السبب:** التصادم «نفس الرقم، ملفّان» قنبلة صامتة (rollback/مطابقة بيئات)؛ إصلاح صغير بلا أثر رجعيّ (الزومبيّان لا يطبّقهما أحد) يُغلق الفجوة فوراً بدل توثيقها ونسيانها.
- **الحارس:** `tests_v9/test_migration_id_namespace_separation_guard.py` (unit، في مسار CI) + برهان سلبيّ. لا يُعاد المنهج مستقبلاً — الحارس يمنع الانحدار.
- **SHA:** `d4a622a` (main).

## 2026-07-21 — PR #585 GAP-FIELD-FORMS-01 (v204): حكم المراجع + دمج (مساهمة وكيل المالك)
- **الدور:** الميزة بناها وكيل آخر (فرع `claude/field-forms-01`). دوري: (١) إخضار CI؛ (٢) المراجعة النهائيّة المستقلّة + براهين PG16 الحيّة قبل الدمج (مسار C).
- **إخضار CI:** ثلاثة فحوص حمراء جذرها واحد — روتّر `field_forms_api.py` أضاف مسارات بلا إعادة توليد الجرد (`drift` · `Repository Structural Lint` على `--check` · `Lint & Format` على checksum `SERVICE_REGISTRY.md`). أعدتُ توليد الجرد (32 خدمة · 1081 مساراً +8) + حزمة الإصدار — ملفّات مُولَّدة حصراً، لا مسّ منطق. الطرف `d7861c3` أخضر 62/62.
- **البراهين الستّة الحيّة (PG16 · دور `sahool_ingest` الحقيقيّ NOSUPERUSER NOBYPASSRLS LOGIN):** ① RLS (A لا يرى B قراءةً + WITH CHECK يرفض إدراج A صفّاً موسوماً B) · ② state machine على INSERT/P0-1 (published عند الإدراج ⇒ رُفض؛ draft→published بلا published_by ⇒ رُفض؛ published→draft ⇒ رُفض) · ③ REVOKE DELETE طبقتان (permission denied كـingest · trigger `hard DELETE prohibited` كـsuperuser على versions+definitions) · ④ no_active_assignment/P0-3 (اختبارات القرار خضراء + تخزين حيّ) · ⑤ invalid_sync_proof/P0-2 (اختبارات الربط خضراء + تخزين حيّ + رفض خارج-enum بـCHECK) · ⑥ concurrency (نشرتان متزامنتان ⇒ واحدة تنجح، الأخرى `duplicate key ux_field_form_versions_one_published`). **6/6 خضراء.**
- **الحكم:** جاهز للدمج — spec✓ build✓ static✓ unit(79)✓ CI(62/62)✓ live-PG16(6/6)✓.
- **الدمج:** المالك دمج (squash) إلى main — `5eded1d`. main CI ما بعد الدمج أخضر شامل بما فيه main-only gates (Runtime Real Smoke · Sahool Production Gates · Service Inventory Drift). الميزة خلف راية `FIELD_FORMS_ENABLED` (مغلق افتراضاً).
- **SHA:** الطرف الأخضر `d7861c3` · دمج main `5eded1d`.

## 2026-07-21 — PR #587 ERP-BRIDGE-FIX-01: تصليب RLS جسر Odoo لمعيار v204 (FORCE + WITH CHECK)
- **القرار:** رفع جداول جسر Odoo ذات `tenant_id` من `ENABLE` إلى `FORCE ROW LEVEL SECURITY` + سياسات `WITH CHECK ( tenant_id::TEXT = current_setting('app.current_tenant', true) )` داخل حلقة `v9_odoo_bridge.sql` المُمْنَعة — يوحّد الجسر مع معيار v204.
- **السبب:** `ENABLE` وحده لا يُخضِع مالك الجدول؛ FORCE + WITH CHECK يمنع تسريب/إدراج عبر المستأجرين. تغيير هجرة صرف بلا مسّ منطق.
- **البرهان الحيّ:** PG16، جدول مؤهَّل مملوك لدور غير-superuser ⇒ FORCE فعّال + WITH CHECK يرفض مستأجِراً مخالفاً. (CI الأخضر لا يغطّي RLS — live PG proof قبل الدمج.)
- **SHA:** بصمات `061ba3b` · دمج main `6fccc32`.

## 2026-07-21 — PR #588 PHYSICS-AI-CALIBRATION-01: أرشفة ADR المصادَق (وثيقة فقط)
- **القرار:** أرشفة حكم المالك المصادَق في `docs/architecture/ADR_PHYSICS_AI_CALIBRATION_01.md` بلا تغيير منطق/هجرة. تصحيح تحريريّ فقط؛ صناديق build_unlock حرفيّة غير مؤشَّرة (ليست backlog قابلاً للتنفيذ).
- **السبب:** توثيق القرار المصادَق كمصدر مرجعيّ؛ لا حاجة براهين PG (وثيقة). `validate_release_package` متساهل مع الملفّات غير المُدرَجة ⇒ شغّلتُ `build_release_bundle` لإدراج ADR في البصمات (4716).
- **الانضباط:** تحقّقتُ من خضرة الـ58 فحص CI الفعليّة على `15535d0` قبل الدمج (Security Scan آخر بوّابة).
- **SHA:** بصمات `15535d0` · دمج main `04862e6`.

## 2026-07-21 — #589 axios security bump + رفض #586 كلغم رجعيّ
- **القرار:** ترقية axios 1.17→1.18 (أمنيّ) تُطبَّق **معزولةً** على فرع من main (ملفّان: package.json + lock)، لا عبر Dependabot #586.
- **السبب:** #586 قاعدته الفرع البائد `34hO3`؛ فرقه الفعليّ ضدّ main حمل نسخة أقدم من ملفّات جسر ERP ⇒ دمجه يدهس عمل #587 المدموج. أُثبِت ببصمات فعليّة. أُغلِق #586 كمُستبدَل.
- **SHA:** بصمات `76999c4` · دمج main `e3ff38f`.

## 2026-07-21 — #590 field-forms integration (P1): الخيار أ المُنقّح (بيئة نقيّة + خطوة معزولة)
- **القرار:** لا تُضاف fastapi إلى بيئة `-m unit` المشتركة (تُوقظ ~15 اختباراً خامداً importorskip تبني api.main كاملاً ⇒ فشل بيئيّ). بدلاً منها **خطوة CI معزولة** في وظيفة Unit Tests (بعد بوّابة التغطية) تُثبّت `requirements-field-forms.txt` (fastapi فقط) وتشغّل ٣ ملفّات صراحةً بالمسار.
- **السبب:** يحفظ فلسفة CLAUDE.md «الوحدة = منطق صرف بلا خدمات»، ويُبقي هدف الـPR (تغطية field-forms حيّة). + إصلاح عطب ترتيب HMAC (إصدار التوكن بمفتاح البيئة لا سرّ مُثبَّت) ⇒ مستقلّ عن ترتيب التشغيل.
- **ملاحظة صلاحيّات:** رقعة `ci.yml` دفعها هذا الوكيل (توكن المالك بلا صلاحيّة `workflows`).
- **SHA:** رأس أخضر `8f5634e` (الخطوة: 36 passed) · دمج main `35a4ae0`.
- **⟲ نُقِض في 2026-07-28** — انظر القرار أدناه (`UNIT-TEST-DORMANCY-01`). القرار كان
  صحيحاً يوم اتُّخِذ؛ ما سقط هو **شرطه** لا منطقه.

## 2026-07-21 — #591 ADR-0035 relocation
- **القرار:** نقل حكم PHYSICS-AI-CALIBRATION-01 من `docs/architecture/` إلى `docs/adr/ADR-0035-physics-ai-calibration.md` (الترقيم المتسلسل) + فهرسته + حذف القديم.
- **السبب:** اتّفاقيّة ADR في المستودع تعيش في `docs/adr/` بترقيم متسلسل. النصّ حرفيّ (تحقّقتُ بمقارنة) — فرق وحيد: بادئة `ADR-0035:` + ملاحظة provenance. الفرع كان متأخّرًا عن main فدمجتُ main فيه وأعدتُ توليد البصمات (4718).
- **SHA:** رأس أخضر `90b871e` · دمج main `ccf262e`.

## 2026-07-22 — #593 field-forms Slice 2 (UI+BFF) دُمِج
- **القرار:** دمج `5fb4166` (squash). GAP-FIELD-FORMS-01 Slice 2 مُغلَق.
- **السبب:** كلّ 61 فحص CI أخضر/مُتخطّى فعليًّا على `c4e0f68` بعد إصلاح جذرَين متمايزَين (drift/lint/checksum ← إعادة توليد الجرد+الحزمة+ruff؛ Platform Unit Tests ← تسجيل مسار BFF في `platform_extraction_map.json` + رفع الميزانيّة 614→615). المصدر: سجلّ الوظيفة الفعليّ (لا حدس).
- **SHA:** رأس `c4e0f68` · دمج `5fb4166`.

## 2026-07-22 — #595 compose redis-state (Part A) دُمِج
- **القرار:** دمج `ed57004` (squash). عزل حالة الأمان عن كاش Redis.
- **السبب:** كلّ 62 فحص CI أخضر على `d64e786`. Part B (دور odoo_app) أُجِّل لغياب تهيئة الدور.
- **SHA:** رأس `d64e786` · دمج `ed57004`.

## 2026-07-22 — #596 72h infra-hardening دُمِج + #594 أُغلِق
- **القرار:** دمج `1152c76` (squash). v206 RLS fail-closed + odoo_app + redis-state auth/guardrails. #594 Dependabot أُغلِق (مكرَّر، axios على main عبر #589).
- **السبب:** كلّ 63 فحص CI أخضر على `77d4182`؛ عقد no-context-write حُسِم fail-closed (Option A، قرار المالك).
- **SHA:** رأس `77d4182` · دمج `1152c76`.

## 2026-07-23 — field-forms Slice 3 (خادميّ) #600 + تشديد MQTT #601 دُمِجا
- **القرار:** دمج #600 (merge → `fc034f6`) ثمّ #601 (merge → `3f2a010`) تحت انضباط الراتشِت (لا دمج إلّا على رأس أخضر مُثبَت بالكامل على SHA الدقيق؛ التحقّق من كلّ الفحوص لا عيّنة).
- **السبب:** #600 كلّ 64 فحص success/skipped على `042f18d`؛ #601 كلّ 68 فحص success/skipped على `48ed5ae` (بعد إصلاح `compose_env_contract_gate` بإعلان `MQTT_USERNAME/MQTT_PASSWORD` في `.env.example`، وإعادة رصف على main المدموج بحلّ تعارضات مولَّدة فقط عبر إعادة التوليد). main بعد الدمجين: 29 مسار CI success على `3f2a010`.
- **قرار فرعيّ (تحديث حارس أمنيّ):** `test_device_binding_mandatory` عُدِّل ليطابق شكل §9.2.1 ذا السطرين مع الإبقاء على منع تراجع الربط المشروط — تتبُّع إعادة هيكلة مُحافِظة على السلوك (grace=0 مطابق بايتيًّا)، لا إضعاف.
- **حدود بصدق:** تهيئة MQTT مكتملة لكنّ الإثبات الحيّ (رفض مجهول/قبول موثّق) معلّق؛ شريحة Flutter موقوفة (ملفّات copy-as-is غائبة + لا بيئة Flutter)؛ براهين PG16/E2E الحيّة مؤجَّلة؛ `FIELD_FORMS_ENABLED=0`.
- **SHA:** #600 رأس `042f18d` دمج `fc034f6` · #601 رأس `48ed5ae` دمج `3f2a010`.

## 2026-07-23 — IRR-F01 دورة حياة الحجز + field-forms Slice 3 عميل Flutter #602 دُمِج
- **القرار:** مراجعة حزمة تكامل مرفوعة (أساس `3f2a010`) وتنفيذ الصحيح منها فقط على فرع/PR واحد، ثمّ دمج `7606901` (merge) تحت انضباط الراتشِت (لا دمج إلّا على رأس أخضر مُثبَت بالكامل على SHA الدقيق؛ التحقّق من كلّ الفحوص لا عيّنة).
- **السبب:** كلّ 69 فحص success/skipped على الرأس `a8a3d5a` بعد قيادة CI عبر 3 رؤوس؛ كلّ حمراء كانت ثغرة تسجيل (gitignore/باقة الوحدات/قائمة JOBS/فهرس التقارير/call-site إلزاميّ) لا عيب منطق في الدلتا.
- **قرارات فرعيّة:** (١) إرجاع تعديل `to_emit_args()` الميّت الذي كسر حارس العقد (خيط التتبّع يبقى عبر payload). (٢) العامل الجديد opt-in default-off تحت بروفايل `irrigation-runtime`؛ سُجِّل في قائمة `JOBS_DATABASE_URL` (سكربت+اختبار) وميزانيّة وحدات المنصّة 652→653. (٣) تمرير `deviceId` الإلزاميّ في مستدعٍ قائم خارج الدلتا.
- **حدود بصدق:** براهين PG16/RLS الحيّة + NATS durable + actuator E2E + سيناريوهات Flutter الحيّة معلّقة؛ لا SoR ريّ مُوازٍ؛ `FIELD_FORMS_ENABLED=0`؛ العامل default-off.
- **SHA:** رؤوس `416b9c6`/`f3e7669`/`a8a3d5a` · دمج `7606901`.

## 2026-07-23 — إغلاق RUFF-FORMAT-DRIFT-SHARED #603
- **القرار:** فتح/تنفيذ/دمج فرع مستقلّ يُنظّف `shared/` (format+lint) ويوسّع بوّابتَي ruff في CI لتشمله. دمج `b18a1c1` على رأس أخضر مُثبَت (61/61 على `294b1fd`).
- **السبب:** أوّل فجوة قابلة للتنفيذ مناسبة (مُسجَّلة، غير مبكّرة، تشدّ السقّاطة). محايد سلوكيًّا؛ إعادة التصدير محميّة بـ`ruff.toml`.
- **قرار انضباط:** تجنّبتُ عمدًا بنود «لا لمس حتى المحفّز» (FIELD-SVC-TENANT-HEADER-TRUST) و«MVP مؤجَّل» احترامًا لمنع التجريد المبكّر — تُنفَّذ فقط بقرار مالك صريح على البند.
- **SHA:** رأس `294b1fd` · دمج `b18a1c1`.

## 2026-07-23 — HISTORICAL-SEASON-BRIDGE-01 (v207) #605 دُمِج
- **القرار:** مراجعة حزمة `historical_season_bridge_v2` (أساس `9a218c7`) وتطبيق الصحيح منها على main (`ccfa03b`) عبر فرع/PR واحد، ثمّ دمج merge-commit `bbfbf95` تحت انضباط الراتشِت (لا دمج إلّا على رأس أخضر مُثبَت بالكامل على SHA الدقيق؛ التحقّق من كلّ الفحوص لا عيّنة).
- **السبب:** كلّ 65 فحص success/skipped على الرأس `428e508` (production-validation-gate · Repo Structural Lint · Platform Unit Tests · Structure Inspector · migration drift/contract · Security Scan). v207 مُدرَج قبل v206 (v206 يبقى آخِراً ويُعيد تغطية RLS)؛ الجدولان يعلنان RLS ذاتيّاً عبر المساعد القانونيّ.
- **قرارات فرعيّة:** (١) توسيع `sahool_inspector.check_rls_coverage` ليقبل `sahool_effective_tenant_id()` كمسنِد tenant صحيح (غير مُضعِف؛ v206 نفسه يستعمله). (٢) تسجيل جدولَي v207 في `db_ownership.yml` كـsahool-platform + رفع ميزانيّة الوحدات 653→654 + `modules[]`/note لـ`core/historical_season_context.py` — الحُرّاس تعيش في `tests/test_p0_*` (وظيفة Platform Unit Tests) لا في `-m unit` المحلّيّ. (٣) `HISTORICAL_SEASON_DECISION_CONTEXT_ENABLED=false` default-off.
- **حدود بصدق:** تطبيق PG16 + برهان RLS بجلستَين على جدولَي v207 مؤجَّل؛ مرآة decision-service SoR default-off حتى الشهادة؛ لا SoR موازٍ للموسم/المحاكاة.
- **SHA:** رأس `428e508` (سابقه `243ec93`) · دمج `bbfbf95`.

## 2026-07-23 — تحقّق مستقلّ من مراجعة توصيل المحرّكات↔مركز القرار (`9a218c7`) — REQUEST CHANGES مؤيَّد
- **القرار:** التحقّق من ادّعاءات مراجعة REQUEST CHANGES بأربعة وكلاء قراءة-كود عدائيّين مستقلّين (كلٌّ مكلَّف بالدحض) بدل قبولها؛ الحكم: **الادّعاءات 11 كلّها CONFIRMED** بأدلّة `file:line` ⇒ **أؤيّد حجب الاعتماد الإنتاجيّ على مركز القرار.**
- **السبب:** المسارات المتوازية (`/crop-twin/decision`، `/profit-aware`، `run_field_intelligence`) تلتفّ حول البوّابة fail-closed للمرشّح القانونيّ؛ المرشّح مبنيّ على مدخلات العميل لا عقود canonical حيّة (GDD وحده مجلوب خادميّاً)؛ `weather_state` غير ممرَّر ⇒ heat/frost/crop_water معطّلة.
- **الفعل:** لا تغيير كود في هذه الجولة (تحقّق فقط)؛ اقتراح فجوة `DECISION-CENTER-UNIFY-01` (المسار 3/4/5: منع submit على compose + تحويل المسارين إلى preview + منع executable الالتفافيّ — قابل للتنفيذ الآن بلا migration) بانتظار موافقة المالك على التسجيل/التنفيذ.
- **SHA:** المراجَعة عند `9a218c7`؛ لا commit في هذه الجولة.

## 2026-07-23 — REGISTRY-CLASSIFICATION-SETTLEMENT (main=38ed755، بعد #616)
- **القرار:** تجميد العمل الكوديّ العامّ + تسوية تصنيفات السجل بدل محاولة إغلاق بنود محجوبة من الكود.
- **السبب:** الجرد أثبت صفر بند قابل للإغلاق كوديّاً دون نصف-حلّ؛ العمل القسريّ يخالف الصدق. المالك صحّح: تصنيف دقيق (OPERATIONAL/GOVERNANCE-TRIGGER/SPEC-DATA/DESIGN-RUNTIME/ACCEPTED_RISK) لا إعلان «خالٍ كوديّاً».
- **التغييرات:** `SHARED-PACKAGE-NAME-COLLISION`→ACCEPTED_RISK/WONTFIX · `DECISION-CENTER-UNIFY-01`→BLOCKED-DESIGN+RUNTIME · قسم `#CODE-CLOSABLE-DEFERRED-SWEEP` · تصنيف 3 خدمات UNCONSUMED-INTENTIONAL/INTERNAL-FUTURE (بلا اختراع مستهلك).
- **التالي:** بانتظار فتح المالك لمسار PG16 staging (P0×2) أو تأكيد محفّز/قرار PKI. السرّ env-only. لا force-push على main.

## 2026-07-23 — ACCEPTED_RISK-GOVERNANCE-METADATA (ملاحظة حوكمة المالك)
- **القرار:** أيّ تصنيف ACCEPTED_RISK/WONTFIX يجب أن يحمل حوكمة صريحة (مالك مخاطرة · تاريخ اعتماد · محفّز إعادة فتح · تاريخ مراجعة) كي لا يصير إغلاقاً دائماً غير مراقَب.
- **التطبيق:** أُضيفت الحقول الأربعة لـ`MINIO-PER-SERVICE-CREDENTIALS` و`SHARED-PACKAGE-NAME-COLLISION` (مالك=المالك kafaat · اعتماد=2026-07-23 · محفّزات موثَّقة · مراجعة=2026-10-23 ربع سنويّ).
- **المسار النشط الوحيد:** PG16 staging (P0×2)؛ لا فتح ADR-0033/WORKER-IDENTITY بالتوازي قبل المحفّز/PKI؛ لا إجراء صادق حتى توفّر اتصال PG16 عبر env/secret (لا نشر اعتماد في المحادثة). التحقّق المستقل من محتوى SHA/`file:line` مرهون بوصول الشجرة.

## 2026-07-23 — U3+U4: تبنّي مُكيَّف لحزمة U3_U4_hardened داخل مُصرِّفنا (eae59a2)
- **القرار:** تمديد مُصرِّف الكتالوج القائم ببوّابتَي حَوكمة U3 (سلك مدفوع بالأدلّة عبر بوّابة العقود المُقوّاة fail-closed + صفر تعارضات ملكيّة بعد إزالة مدخل IF الزائف من مصدره) وU4 (قرارات التكرارات 14/14 + حَوكمة الإعفاءات الـ50 في overrides) — **رفض** استبدال المُصرِّف بمُصرِّف الحزمة الموازي، ورفض ملفّات BFF/nginx/evidence-lab فيها (أقدم من إصلاحاتنا المدموجة ce91d3b) وتعديلها لهجرة v211 المدموجة (v212 قائمة).
- **السبب:** مُصرِّفنا مُثبَّت ببوّابة واختبارات مُدمَجة في ci.yml؛ الفريد الحقيقيّ في الحزمة هو دلالات U3/U4 لا بنيتها. تحسين إضافيّ: فحص الانتهاء زمنيّ فقط (--enforce-expiry) خارج المخرجات حفاظاً على الحتميّة البايتيّة المستقلّة عن تاريخ اليوم (تصميم الحزمة كان يضمّن إخفاقات الانتهاء في JSON المولَّد).
- **الدليل:** SHA `eae59a2` على `claude/code-review-34hO3`؛ 3431 unit خضراء؛ بوّابة الكتالوج 12/12؛ العقود 32/32.

## 2026-07-23 — U0–U4 مدموج عبر PR #617 (main=0c01642)
- **القرار:** دمج الكتالوج الموحّد U0–U4 + consumer-routes إلى main بعد اخضرار كلّ الـ71 فحص CI (success/skipped) على الرأس fa2a16f، بإذن المالك الصريح («انتظر الاخضرار ثم ادمج»).
- **السبب:** الـRatchet مُستوفى؛ الأعطال الخمسة الأوّليّة كلّها أُصلحت من الجذر (حارس تحليل IF · evidence-lab compose · انجراف الجرد المُقنَّع) بلا تليين عقد حقيقيّ (ephemeral-dependencies best-effort حيّ لا يُصدِر شهادة إنتاج بتصميمه).
- **الدليل:** merge SHA `0c01642`؛ zip `sahool_main_0c01642.zip` (5191 ملفّاً).

## 2026-07-23 — U5–U9 الكتالوج الموحّد (فرع claude/code-review-34hO3)
- **القرار:** استكمال كلّ شرائح الكتالوج المتبقّية كمُشتقّات ساكنة حتميّة، بلا اختلاق حَوكمة (السياق/idempotency/approval كلّها مُكتشَفة من مسارات/مصدر) وبلا سقالة بلا مستهلك (بيان U6 موصول بلوحة حقيقيّة) وبلا ادّعاء شهادة إنتاج (U9 production_certified=false دائماً).
- **السبب:** طلب المالك «استكمل الكل»؛ والحدّ الصادق أنّ ما يُبنى ساكناً يبقى ساكناً — الشهادة الحيّة S1..S12 خارج نطاق مُصرِّف ساكن.

## 2026-07-24 — استرداد شريحة Composer الطيفيّة (PR #621)
- **القرار:** إعادة تطبيق شريحة DECISION-CENTER-UNIFY-01 المفقودة (خطأ دمج #620) + توجيه جلب الطيف عبر الواجهة القانونيّة `get_indicator_grid` بدل المسار الخامّ، بلا إضافة crop_twin لقائمة السماح (الواجهة تحفظ الحدّ).
- **السبب:** الحدّ raster يجب أن يبقى داخل الواجهة الوحيدة (نمط etc_dual/field_ai_context) — أنظف من توسيع قائمة السماح؛ والراوتر يبقى مستهلِكاً صرفاً. الـRatchet مُستوفى (64 فحصاً success/skipped) والتحقّق grep>0 على main يمنع تكرار خطأ #620.
- **الدليل:** merge SHA `64dea36`؛ إصلاح الحدّ `82ce4cc`؛ إعادة التوليد `16ff308`؛ zip `sahool_main_64dea36.zip`.

## 2026-07-24 — الشريحة 1: مُجمِّع السياق الزراعيّ الخادميّ (`3c9c3c2`)
- **القرار:** بناء نصف «الجمع» المفقود كوحدة نقيّة في المنصّة تُغذّي `compose_agronomic_context` القائم (لا جامع موازٍ في decision-service، لا استيراد داخليّات عبر الحدّ) — راية default-off، fail-closed، تركيب لا كتابة.
- **السبب:** تدقيق الذكاء الزراعيّ حدّد P0-3 كأخطر فجوة (أهمّ من أيّ نموذج AI جديد). العقد AC-1 يحمل أصلاً حقول النَسَب المطلوبة (P0-2) ⇒ الناقص هو المُلئ الخادميّ فقط. برهان اجتياز بوّابة PIT الحقيقيّة يمنع بناء شكل غير متوافق.
- **الدليل:** commit `3c9c3c2`؛ `agronomic_context_composer.py` + 6 اختبارات؛ توافق عبر-الخدمات مُثبَت (ContextComposeIn + validate_composition = 0 مخالفات).

- **PR #623 (`853f353`) — DECISION-CENTER الشريحة 2:** أُزيلت راية `CROP_TWIN_DIRECT_DECISION_ENABLED`
  من نقطتَي crop-twin السيناريوهيّتَين (`/crop-twin/decision` + `/decision/profit-aware`) ⇒ معاينة
  دائمة (`persisted=false`, `preview_only=true`). السبب: إغلاق باب الكتابة الجانبيّ بعد تحقّق شرطه
  (جامع الشريحة 1، `3c9c3c2`). النطاق محدود بصدق: بوّابة `/decision-candidate submit→403` بقيت خلف
  الراية (إغلاقها يحتاج وصل الجامع، عمل منفصل). Ratchet: 64 فحصاً success/skipped على الرأس `1a529b7`.

## 2026-07-25 — إصلاحات مسار الصور الثلاثة (PR #629، main `9e0967d`)
- **القرار:** (١) قصّ الشريط الزمنيّ بنافذة `months` على **كامل** التواريخ لا المزوّد وحده، محكوماً بـ`include_provider` فقط (منتقي المشهد يبقى كاملاً). (٢) المزامنة التلقائيّة 6→24 ساعة + حارس per-field «24 ساعة من وقت التقاط الصورة السابقة» (fail-open على غياب/فشل تحليل التاريخ). (٣) تسجيل #627 في الدماغ.
- **السبب:** «3 شهر» كان يعرض 24 شهراً لأنّ التواريخ المعالَجة تُعاد بلا قصّ؛ والمالك طلب كادينس يوميّاً مُثبَّتاً على آخر التقاط بدل الكنس الأعمى كلّ 6 ساعات. القصّ محصور بنداء الشريط كي لا يُخفي مشاهد جاهزة عن المنتقي (صدق). الحارس يقلّل تكرار الكنس عبر النسخ لكن لا يُغني عن قفل موزَّع (مؤجَّل).
- **الدليل:** commits `4837cf9` (raster) · `28aaf58` (cadence) · `639e665` (brain) + `e8e3d11`/`2fb724c` (ضريبة تسجيل: جرد+حزمة). Ratchet: 67 فحصاً success/skipped على head `2fb724c`. **درس:** تعديل مصدر ⇒ إعادة توليد الجرد والحزمة **معاً** (تقسيمهما كسر CI جولةً).

## 2026-07-25 — قفل نسخة-واحدة للمُجدوِل (PR #630، main `5cd063a`)
- **القرار:** لفّ كلّ مهمّة مجدولة دوريّة بقفل استشاريّ Postgres غير حاجب على مستوى الجلسة (`pg_try_advisory_lock`) عبر `scheduler.cluster_singleton`، فتُشغّلها نسخة واحدة فقط لكلّ تكّة عبر النسخ.
- **السبب:** المُجدوِل asyncio داخل العمليّة بلا تنسيق ⇒ تكرار المهامّ عبر النسخ (فجوة صادقة سُجِّلت مع PR #629). اخترتُ قفل الجلسة لا المعاملة كي لا يُبقي كنس STAC الطويل transaction مفتوحاً؛ fail-safe بلا مسبح (no-op في نسخة واحدة). اتّبعتُ مصطلح `pg_advisory_xact_lock` القائم بدل إدخال تبعيّة/نمط جديد.
- **الدليل:** commit `be2c56c` (الميزة+الجرد+الحزمة) + `6019575` (subinventory المفقود + إعادة الحزمة). Ratchet: 64 فحصاً success/skipped على `6019575`. **درس:** تعديل main.py ⇒ إعادة توليد service_inventory + platform_main_subinventory + release bundle معاً (قاعدة الثلاثة).

## 2026-07-25 — بطاقة الأصناف + إغلاق ست فجوات كود (PR #632، main `10a8fae`)
- **القرار:** (أ) بناء `VarietyCatalogPage` كأوّل مستهلك UI للكتالوج المحكوم مع **ترقية** نقطتَي varieties من إعفاء backlog-ui إلى `core_endpoints` (لا إبقاؤهما إعفاءً بعد وجود دليل UI حقيقيّ). (ب) إغلاق ست فجوات كود مكتشَفة ببحث عميق: B1 تزامن محدود في `all_fields` · B2 «أحدث غلّة» بدل `MAX` · B3 فكّ العدّ المزدوج في مصالحة النتائج بمفتاح `decision_id` · F1 دبابيس MapHub دائمة على الخادم · F2 تعليقات بائدة · F3 استيرادات ميّتة.
- **السبب:** الترقية إلزاميّة لأنّ `test_no_waiver_has_real_ui_evidence` يفشل عمداً حين يكتسب إعفاء دليلاً حقيقيّاً (الإعفاء يجب أن يعكس غياب UI لا وجوده). الفجوات الستّ اختيرت لأنّها **قابلة للإغلاق بكود** دون قرار مالك/PG16 حيّ/محفّز (باقي فجوات التدقيق مؤجَّلة بصدق). B2 كان `MAX` يتحيّز صعوديّاً مع حصاد جزئيّ؛ B3 يمنع نسبة نجاح مُلفّقة بعدّ قرار مرّتَين؛ F1 يتبع مرجع SatellitePage المُثبَت (لا اختراع مشاهدات — الفراغ من القاعدة يبقى فراغاً).
- **الدليل:** commits `85a0a1a`/`5fd1926` (بطاقة الأصناف + ترقية الإعفاء) · `71ddbc8` (الفجوات الستّ) · `000e809` (ضريبة تسجيل: جرد+حزمة بعد انزياح LOC). Ratchet: 68 فحصاً success/skipped على `000e809` ⇒ squash `10a8fae`. **درس مُقوّى:** **أيّ** تعديل مصدر متتبَّع (Python **أو** واجهة) يزيح LOC/أرقام أسطر ⇒ أعِد توليد `service_inventory`/`route_inventory`/`SERVICE_REGISTRY` **وحزمة الإصدار** معاً؛ تعديل `main.py` وحده يضيف `platform_main_subinventory` (قاعدة الثلاثة).

## 2026-07-25 — إغلاق ثغرات Dependabot الأربع (PR #633، main `63a70a7`)
- **القرار:** رفع postcss `8.5.15→8.5.23` (HIGH) و**react-router `6.30.4→8.3.0`** (إزالة react-router-dom المُدمَج في v8)، مع رفع node البيئة 20→22 (Dockerfile + وظيفتَي CI للواجهة). النتيجة `npm audit` = 0.
- **السبب:** v8.3.0 هي النسخة **الوحيدة** النظيفة من الاستشارات الأربع؛ خطّ v7.18.x يُصلح الثلاث الأصليّة لكنّه يقع في نطاق ثغرة RSC-CSRF high (7.12–8.2). وثّقتُ المفاضلة (v8-كامل / v7-جزئيّ / إبقاء-v6) للمالك عبر AskUserQuestion فاختار الترقية الكاملة — تراجُعاً صريحاً عن تأجيل react-router الكاسر في #628. صدق: ثغرتا RSC-CSRF وSSR-hydration تخصّان RSC/SSR فقط والتطبيق SPA عميل Vite لا يستخدمها؛ الوحيدة ذات الصلة بـSPA = open-redirect. لم أُخفِ أنّ الترقية تراجُع قرار سابق ولم أُقلّل من حجمها (21 ملفّاً + node bump).
- **الدليل:** commit `89135b2` (الترقية+الهجرة+node+الحزمة). Ratchet: كلّ الفحوص success/skipped (وظيفتا node-22 خضراوان) على `89135b2` ⇒ squash `63a70a7`. **درس:** ترقية أمنيّة لتبعيّة قد تكشف ثغرة أحدث في النسخة الوسيطة — تحقّق أنّ الهدف خارج **كلّ** نطاقات الاستشارات لا الأصليّة فقط (v7.18 كان يبدّل moderate بـhigh).

## 2026-07-25 — V8-05 PR2: اختيار بلا أثر جانبيّ + معالجة صريحة + سحابة AOI (PR #640، main `aee19cf`)
- **القرار:** فصل «اختيار التاريخ» عن «المعالجة» في الواجهة — التأثير يبمّ كاش البلاطة فقط، والمعالجة فعل صريح عبر زرّ ⇒ بروكسي منصّة جديد يعيد استعمال نموذج single-scene (PR1-a). تسجيل المسار كشقيق `field_imagery_backfill_proxy` (target_owner=raster-service, compute-store) ورفع ميزانية مسارات المنصّة +1 مُوثَّقاً (baseline 629→630، سقف P2.6 625→626).
- **السبب:** الأثر الخفيّ (auto-`refreshFieldImagery` عند الاختيار حتّى لـ`latest`) كان يُطلق معالجة صامتة — يخالف صدق «الاختيار ليس معالجة». البروكسي على المنصّة (لا مسار مباشر لـraster) لأنّه يحمل حارس الملكيّة + geometry_revision عند الحدّ، تماماً كشقيقه backfill_proxy؛ التوجيه حوله كان سيُضعِف التخويل. رفع السقف P2.6 قرار حوكمة متعمَّد عبر المسار المُصرَّح (نفس نمط الرفعات السابقة) لا نموّ صامت — المسار الوحيد الذي يوفّر فعلاً واجهيّاً طلبه المالك في مواصفة PR2.
- **الدليل:** commit `10ca962` (الشيفرة+الواجهة+الحارس+التسجيل) · `c1bdfdf` (إصلاح حرّاس حوكمة المسارات P0/P1/P2.6 + حزمة). Ratchet: 64 فحصاً success/skipped على `c1bdfdf` + mergeable clean ⇒ squash `aee19cf`. **درس مُقوّى: مسار بروكسي منصّة جديد ⇒ شغّل حزمة `services/sahool-platform/tests` الكاملة (3896، `PYTHONPATH=. pytest tests`) محلّيّاً؛ حرّاس حوكمة المسارات (extraction_map + budgets) خارج `pytest -m unit` في `tests_v9`.**

## 2026-07-25 — H5 PR3: ربط ECw بمصدر ماء + إنفاذ maximum_allowed_ec fail-closed (PR #641، main `24e8ed7`)
- **القرار:** وصل منطق ملوحة الماء fail-closed القائم (`canonical_well_capability`) في مسار توصية MPC اليوميّ المخدوم عبر ربط خادميّ لـECw بـ`water_source_id`، لا اختراع منطق جديد ولا هجرة جديدة. استخراج القاعدة في دالّة نقيّة واحدة `evaluate_water_salinity_gate` يستهلكها كلٌّ من بناء قدرة البئر والمسار المخدوم.
- **السبب:** الإنفاذ كان مبنيّاً بالكامل لكن ميتاً (لا مستهلك مساريّ)، وECw قيمة عميل غير موثوقة. الربط عبر `water_source_id` في الطلب يجعل مصدر الملوحة خادميّاً-موثوقاً (يُقرأ من SoR)، ويُفشِل المسار مُغلَقاً عند تجاوز الحدّ أو غياب/قِدَم العيّنة أو تعذّر حلّ المصدر — لا توصية بلا تحقّق. رفضتُ إضافة `fields.water_source_id` FK في هذه الشريحة لأنّه بلا مُعبّئ = سقالة غير مستهلَكة؛ أعلنتُه متابعة صريحة.
- **الدليل:** commit `2a78426` (الدالّة النقيّة + dedup + الربط المساريّ + الاختبارات + جرد/حزمة). Ratchet: 64 فحصاً success/skipped على `2a78426` + mergeable clean ⇒ squash `24e8ed7`. **درس:** منطق سلامة مبنيّ لكن غير موصول = دَيْن صامت؛ الوصل الحقيقيّ يحتاج مصدر حقيقة خادميّ (لا قيمة عميل) وإلّا صار المنع قابلاً للتجاوز.

## 2026-07-25 — WX-10.6 PR4: تغطية-مصبّ مُثبَتة بدل إعفاء الواجهة (PR #642، main `012605a`)
- **القرار:** إزالة إعفاء WX-10.6 المؤقّت لـ`/crop-twin/decision-candidate` واستبداله بتغطية-مصبّ حقيقيّة: تعليم البوّابة العكسيّة أن تقبل `downstream_surface` (سطح مراجعة WX-10.8 الذي يستهلك المرشّح)، نقل النقطة إلى core، وإثبات الاستهلاك بـE2E مصبّ حقيقيّ. C5 يبقى بلا بناء (calibration-blocked).
- **السبب:** سبب الإعفاء («pending reviewer UI») بائت — الشاشة وصلت في WX-10.8 وواجهتها (`review-queue`+`review`) يستدعيها الأمام. البوّابة العكسيّة كانت عمياء عن المنتِجات التي واجهتها مصبّ (تفحص جذع المسار المنتِج فقط)؛ الإصلاح يجعل التغطية حقيقيّة لا مؤكَّدة. رفضتُ اختلاق بناء لـC5 — الكود مبنيّ (#567) والمتبقّي معايرة ميدانيّة صرفة، فيبقى صادقاً كما هو.
- **الدليل:** commits `9715066` (البوّابة+الكونفيغ+الإعفاء+E2E+خطوة CI) · `251934e` (إصلاح انجراف الجرد+الكتالوج+تثبيت الإعفاءات) · `578df7b`/`4a569f6` (gitleaks: تشخيص خاطئ ثمّ صحيح — allowlist تاريخيّ-آمن). Ratchet: 65 فحصاً success/skipped على `4a569f6` ⇒ squash `012605a`. **درسان مُقوَّيان:** (أ) مدخل `endpoint_ui_coverage.json` core ⇒ أعِد توليد كتالوج المنصّة + ثبّت ui_waivers. (ب) لأسرار في تاريخ الفرع استعمل `.gitleaks.toml` allowlist لا العلامة السطريّة.

### 2026-07-25 — DECISION-SOR REVOKE أداة cutover عكسيّة (SHA `3ebd618`)
- **القرار:** إنفاذ منع كتابة المنصّة على جداول SoR على مستوى DB (REVOKE) كأداة cutover عكسيّة خارج `migrations/`، لا كـmigration.
- **السبب:** الحارس التطبيقيّ (بايثون) وحده يُتجاوَز بمسار جانبيّ/psql؛ REVOKE في migration يُطبَّق قبل التحويل فيكسر عقد platform-as-SoR. الأداة خارج migrations + fail-closed خلف بوّابة cutover = إنفاذ مُكمِّل بلا كسر مسبق. الخمسة platform-owned فقط (decision_outbox_events مملوك لـdecision-service).

### 2026-07-25 — WORKER-IDENTITY ربط هويّة العامل بمفتاح assertion مشترك (SHA `9330407`)
- **القرار:** ربط النقطتَين المقودتَين-بالعامل بـX-Worker-Assertion (مفتاح مشترك بين الـadapters) لا PKI لكلّ عامل.
- **السبب:** يضيّق المُنتحِلين من «كلّ حامل bearer» إلى «حاملي مفتاح الـassertion» + يربط الطلب/الإعادة — بنفس نموذج ثقة field-management. PKI لكلّ عامل قرار بنية تحتيّة (governance-blocked)، لا نصف حلّ ندّعيه. مرحليّ: prod-required، fail-open في التطوير كي لا نكسر التنصيبات القائمة.

### 2026-07-25 — PR #644 مدموج: الثغرتان الأمنيتان + تقوية DECISION-SOR (SHA `7046ee0`)
- **القرار:** دمج شريحة الأمن (REVOKE + شهادة أدوار precursor + اختبار امتياز بدورَين + ربط هويّة العامل + مطابقة السجلّ) تحت Ratchet (72 فحصاً success/skipped على `f306ca5`).
- **السبب:** التحقّق الحيّ أثبت topology: فصل الاتّصال مؤكَّد وفصل الدور غير مُثبَت ⇒ REVOKE محجوب على شهادة الأدوار. البرهان الأقوى (تمييز GRANT عن RLS بالرسالة) اكتُشِف بتشغيل PG16 محلّيّ. لا شيء VERIFIED؛ المتبقّي تشغيليّ/حوكميّ.

### 2026-07-26 — H5.1: مصدر ماء الريّ مُشتَقّ من الخادم + درجات ثقة العيّنة (SHA `3033765`)
- **القرار:** ربط الحقل بمصدر الماء عبر جدول وصل خادميّ `field_irrigation_source_assignments` (بدل `fields.water_source_id`)، و**رفض** عيّنة estimated/measured في البوّابة الحسّاسة (قبول field_validated/certified=laboratory_verified فقط). خريطة enum DB↔canonical موثّقة كافتراض صريح قابل للتصحيح لا تخمين صامت.
- **السبب:** جدول الوصل يدعم تعدّد المصادر والتغيّر الزمنيّ والخلط دون إعادة تصميم (قرار المالك)، ويجعل المصدر خادميّاً فيُغلق تجاوزَي «حذف water_source_id» و«توجيه لمصدر أنظف». الدرجات: بوّابة قرار حسّاسة لا تثق بقراءة غير مُصادَقة — fail-closed أصدق من قبول estimated. لم أُثبِت شيئاً VERIFIED بلا برهان: شهادة PG حقيقيّة بدور مقيَّد تُثبت الحلّ+RLS+فلتر الدرجة على PG16 محلّيّ. المتبقّي (H5.2 ملف جودة موحَّد، H5.3 متعدّد أخطار، معايرة) يبقى BLOCKED_DESIGN_DATA_AUTHORITY.

### 2026-07-26 — WORKER-IDENTITY-BINDING: برهان endpoint-level PG (SHA `ff3a11d`)
- **القرار:** إثبات ربط هويّة العامل على النقطتين الفعليّتين (feed + discovery) بـPG حقيقيّ + HTTP مع تفعيل الـassertion — لا الاكتفاء بالمُتحقِّق النقيّ ولا باختبار القسمة (الذي يشتغل بلا تفعيل).
- **السبب:** الاختبار القائم يثبت القسمة لا الهويّة؛ الثغرة الحقيقيّة (انتحال عامل لسحب قسمة آخر) تحتاج برهاناً على المسار الفعليّ مع الـassertion مُفعَّلة. أضفتُه ذاتيّ الاحتواء ومُثبَّتاً في wx12_gate، وشغّلته أخضر على PG16 محلّيّ. يبقى PKI/SPIFFE لكلّ عامل قراراً بنيويّاً (governance-blocked)، لا نصف حلّ.

### 2026-07-26 — دمج Capability-Governance + Architecture-Graph (SHA `3b02b07`)
- **القرار (اختيار المالك «ادمج النظامين»):** إدخال أدوات الحوكمة/الرسم المعماريّ الإضافيّة من المرفق إلى main، مع إعادة توليد كلّ الأدلّة على الكود الحاليّ لا اللقطة القديمة، وإبقاء `capability-governance.yml` workflow مستقلّاً (يحجب فحوص الانجراف + الاختبارات) لا مدموجاً في ci.yml.
- **السبب:** أدوات evidence-only حتميّة، لا تلمس كود التشغيل، تُغلق ثغرة «لا خريطة قدرات/معماريّة محكومة». أعدتُ التوليد على 20c19bd كي لا تُشحَن أدلّة قديمة (أرقام أسطر/نضج). لم أُبالغ: التقرير يعترف بصفر قدرة مُعتمَدة. `capability_linker --check` غير idempotent (أداة المؤلّفين) فتُرِك غير محجوب بصدق لا مخفيّاً. كلّ الفحوص المحجوبة تمرّ + ruff كامل الشجرة نظيف.

### 2026-07-26 — دمج Runtime-Contracts + Execution-Dependency-Audit (SHA `fe97da5`)
- **القرار (اختيار المالك «ادمج النظامين»):** إدخال أداتَي instrumentation إضافيّتَين (عقود تشغيل ساكنة + تدقيق تبعيّات/كود ميّت) وربطهما إضافيّاً في `capability-governance.yml`، مع إعادة توليد الأدلّة على الكود الحاليّ لا اللقطة.
- **السبب:** أدوات evidence-only حتميّة (stdlib)، لا تلمس كود التشغيل، لا حذف تلقائيّ. أعدتُ التوليد على 5ff255b كي لا تُشحَن أدلّة 12c10fa قديمة. **أسقطتُ** خطوة `decision_lineage_graph.py` المرفقة (أداة غير موجودة) بصدق بدل حجب على ملفّ مفقود. راجعتُ الأثر الوحيد الملموس (تكرار strong_password) وأثبتّه حميداً. لم أُبالغ: التقارير تعترف بـ`live_runtime_verified: 0` و«لا ادّعاء وصوليّة». كلّ البوّابات المحجوبة تمرّ.

### 2026-07-26 — الطبقة الختاميّة PATH-3: attestation policy (SHA `d52a6b6`, #656)
- **القرار (نمط المالك «قوم بالدمج» المستمرّ):** دمج آخر شريحة PATH-3 (تصديقات HMAC موقَّعة + سياسة ترقية بيئة + بوّابة قبول fail-closed) كطبقة evidence-only فوق الـworkflow اليدويّ.
- **السبب:** يُكمِل إطار PATH-3 دون أيّ ادّعاء تشغيل/إنتاج (كلّ الأدوات fail-closed، مفتاح env فقط، `production_certified` ثابت false). حصرتُ التعديل على الـworkflow في السطرين الإضافيّين اللازمين وأبقيتُ تثبيت الـactions بـSHA (المرفق حاول إرجاعها إلى @v4/@v5 غير المثبَّتة — رفضتُ). الأدوات التشغيليّة (تتطلّب ملفّ تصديق) بقيت خارج فحوص PR؛ فقط الاختبارات الساكنة البيئيّة-المستقلّة دخلت البوّابة. لا انجراف في سلسلة الـ19 فحص. دُمِج تحت Ratchet (62 فحص نظيف).

### 2026-07-26 — دمج Capability Parity & Investment (المُصحَّح) تحت Ratchet (SHA `c1c5422`, #658)
- **القرار (نمط المالك «ادمج بعد اخضرار CI» المستمرّ):** دمج النظام الفرعيّ evidence-only (4 محرّكات fail-closed فوق `docs/capability-registry/`) بعد إخضار CI بالكامل.
- **السبب:** بعد تصحيح المالك (استثناء `generated`/`release`/`.generated.`) بقي انجراف mapping على CI فقط. شخّصتُه عبر diagnostic (`494ad09`) الذي كشف `files_scanned` 4767 محليّ مقابل 4765 CI؛ الجذر: `rglob` يمسح ملفّات محلّيّة غير مُتعقَّبة غائبة على CI. الإصلاح (`50eac02`): مسح `git ls-files` المُتعقَّب فقط ⇒ حتميّة. أبقيتُ workflow الخاصّ بي (path3 محفوظ). 62 فحص نظيف تحت Ratchet.

### 2026-07-26 — تكامل roadmap linker + PR capability-impact gate (على main c1c5422)
- **القرار (نمط المالك المستمرّ):** إضافة أداتَي roadmap→capability linkage و PR capability-impact declaration كطبقة حوكمة evidence-only فوق سجلّ القدرات، على main الطازج بعد دمج #658.
- **السبب:** الأداتان fail-closed، لا ادّعاء تشغيل/إنتاج. أبقيتُ محرّكاتي (إصلاح المسح المُتعقَّب `50eac02`) ولم أعتمد نسخ المرفق d52a6b6. وصلتُ الخطوات في workflow الخاصّ بي حفاظاً على path3 + الأربعة محرّكات. ruff 0.15.8 نظيف. إعادة توليد كاملة على شجرتي (mapping files=4770 حتميّ). قيد جوهريّ: بوّابة الأثر تعامل تعديل الحوكمة-النواة كـgovernance_wide ⇒ وصف الـPR يحمل `Capability-Impact: ALL`. bundle 5087، `pytest -m unit` 3494.

### 2026-07-26 — إصلاح PHOTOMETRIC لـtruecolor RGBA COG (على main be85939)
- **القرار (تقرير المالك، نطاق «Fix + backfill note»):** تصريح `photometric=RGB`+`alpha=YES` وقت إنشاء COG في `write_rgba_cog`، مع اختبار سلوكيّ يثبت على ملفّ ناتج + حارس ساكن + رَنبوك إعادة معالجة انتقائيّة. لا bulk rewrite. لا توسيع لـblank-thumbnail.
- **السبب:** الوسم الافتراضيّ MINISBLACK يكسر تفسير RGB لأيّ مستهلِك GDAL ويحذّر عند القراءة. التصريح وقت الإنشاء حتميّ عبر إصدارات GDAL (بعضها ينشر من colorinterp، بعضها لا — الإنتاج منها). صدق: القديم لا يتغيّر تلقائيّاً. bundle 5088، raster gate 277 نجح، الحوكمة نظيفة.

### 2026-07-26 — دمج #660 + توحيد حتميّة مولّدات الحوكمة (SHA `9d08568`)
- **القرار:** تصريح PHOTOMETRIC=RGB وقت إنشاء truecolor COG + تحويل 4 مولّدات حوكمة من `rglob` إلى مسح `git ls-files` المُتعقَّب فقط + تشخيص انجراف لبوّابة الإغلاق الساكنة.
- **السبب:** إضافة ملفّ خدمة واحد كشفت هشاشة عدّ الملفّات الفلسفريّ (local≠CI) في مولّدات تُعيد الكتابة على `--check`. المسح المُتعقَّب يجعل المخرَج حتميّاً عبر الآلات/الإصدارات (3.11==3.12). لم أوسّع للمولّدات غير الهشّة (أنماط وحدات لا عدّ). COG fix حقيقيّ (raster gate 277)، صدق محفوظ، bundle 5088.

### 2026-07-26 — دمج #661: PA-003 + طبقة إدارة القدرات + mapper صادق (SHA `f15a4ee`)
- **القرار (نمط المالك المستمرّ):** تكامل مرفق PA-003 (yield-map-ingestion) ثمّ مرفق capability-management-layer على فرع واحد؛ إغلاق ثغرة بوّابة التتبّعيّة بتحقّق رسم استيراد Dart؛ إصلاح mapper إدارة القدرات ليحتسب أدلّة السجلّ المُعلَنة الموجودة (fail-closed)؛ **الإبقاء على INT-004 كفجوة تنفيذيّة وحيدة (80/81)** لا رفعها إلى 81/81.
- **السبب:**
  - **بوّابة التتبّعيّة:** روابط FM-003/OPS-004 صادقة على شجرتنا (الملفّات موجودة ومستورَدة) — حذفها يقلّل الدقّة. الثغرة الحقيقيّة = البوّابة تفحص وجود المؤشّر لا رسم الاستيراد؛ أُغلِقت بتحقّق استيراد Dart (`test_capability_dart_imports_resolve`) الذي يفشل على ملفّ مستورَد مفقود.
  - **mapper:** الـ76/81 كانت under-crediting في الماسح الحدسيّ لقدرات تُعلِن أدلّة حقيقيّة (IRR-010/OPS-001/OPS-006/OPS-008). الإصلاح: اتحاد الماسح ∪ أدلّة السجلّ الموجودة على القرص، بأبعاد محدّدة فقط (استبعاد other_evidence/governance)، مع `validate()` fail-closed لأيّ مؤشّر مفقود.
  - **INT-004 (حكم بالمحتوى):** «تكاملات آلات خارجيّة» — ملفّاتها مسلسلات تصدير ISOXML/VRT ساكنة بلا adapter/upload/consumer حيّ (docstrings + صفر مستهلِك). ⇒ groundwork لا دورة تكامل ⇒ فجوة صادقة، لا تُغلَق بالتوثيق ولا تُرفَع بأسماء ملفّات. الصياغة الصحيحة: 80/81 mapped + INT-004 unmapped، وليس 81/81.
  - **حتميّة/صدق:** تخطّي `tests/architecture/**` + `docs/capability-registry/**` في mapper (تلوّث مرجعيّ-ذاتيّ). runtime_verified/production_certified=0/false في كلّ القدرات والأسس. حوكمة-نواة ⇒ `Capability-Impact: ALL`. bundle 5118، static-closure PATH-1 20/20، 28 اختبار قدرات معماريّ أخضر. الفرع أُعيد تأسيسه من main بعد دمج #660 (استصلاح حاوية) واستُرجِع بـrebase لا force-push.

### 2026-07-26 — فحص وظيفيّ v215 حيّ ⇒ PG_PROVEN (لا SHA كود؛ تحقّق تشغيليّ)
- **القرار:** ترقية حالة نموذج RLS/append-only/scope لـv215 (خرائط الغلّة، PA-003/#661) من «حارس ساكن» إلى **PG_PROVEN** بعد فحص حيّ على PostgreSQL 16.13 + PostGIS 3.4.2.
- **السبب:** ١٦ برهاناً حيّاً تحت دور NOBYPASSRLS (عزل USING/WITH CHECK، append-only، مُشغّل نطاق الموسم، مُشغّل الدفعة ST_Covers، قيود المجال/idempotency) — كلّها خضراء، صفر تسرّب. صدق: تحقّق مخطّط/DB فقط؛ لا يُرقّي `runtime_verified` (يبقى false — لا برهان end-to-end للخدمة). مصدر: `migrations/v215_yield_map_ingestion.sql` + جلسة psql PG16 محلّيّة.

### 2026-07-26 — إغلاق INT-004 بتنفيذ حقيقيّ (مستهلِك آلات حيّ) ⇒ 81/81 صادق
- **القرار:** إغلاق فجوة INT-004 ببناء مستهلِك حيّ (`api/machinery_export.py`) يربط تصدير ISOXML الساكن بنقطة `export?format=isoxml`، بدل إبقائها فجوة أو إغلاقها بالتوثيق.
- **السبب:** المالك اشترط «لا 81/81 إلّا بتنفيذ حقيقيّ لـINT-004». التنفيذ الآن حقيقيّ: وصفة محفوظة + ملفّ مُتحكِّم ⇒ ISO11783 TaskData، fail-closed على كلّ عدم-توافق، 8 اختبارات سلوكيّة. حُدِّث `precision.yaml` بأدلّة تنفيذيّة حقيقيّة (services/apis/tests) فصار محرّك الإدارة يحتسبها mapped ⇒ 81/81 مشروع (لا رقم مُضخَّم؛ الحارس الثابت أصبح تركيبيّاً). حدّ الصدق محفوظ: يُنتِج ملفّ الرفع عند الحافّة، لا يقود جهازاً ⇒ `runtime_verified`/`production_certified`=false. رفع أساس الوحدات 665→666 موثّق؛ إعادة توليد كاملة + static-closure + bundle 5120؛ كلّ البوّابات خضراء.

### 2026-07-26 — إعادة تحجيم INT-004 إلى محوِّل الأثر (INT-004A) بإدامة حقيقيّة + براهين PG16
- **القرار:** إعادة بناء INT-004 من ملفّ-تحكّم-في-الطلب (مرفوض) إلى **محوِّل منصّة مُدام**: SoR ملفّات تحكّم (`machine_control_profiles`, v216) + لقطة غير قابلة للتغيير + حزمة ISOXML قابلة للرفع مُدامة (`machinery_export_artifacts`, append-only) + checksum + نقطة تنزيل. المسار القانونيّ `POST .../machinery-export {machine_profile_id}` (EQUIPMENT_MANAGE)؛ المسار المضمّن محجوب خلف PLATFORM_MANAGE (تطويريّ، لا يُدام).
- **السبب:** المالك حدّد أنّ ملفّ التعريف الحرّ من الطلب ليس مسار الإنتاج؛ المصدر الموثوق = ملفّ تحكّم مُدام معزول بالمستأجِر، ولقطة مجمّدة كي لا يغيّر تعديلٌ لاحقٌ معنى أثرٍ سابق. مُثبَت حيّاً على PG16: 11 برهان جدول (RLS/WITH CHECK/append-only/CHECK/FK/updated_at) + E2E (إدراج أثر حقيقيّ 525B/sha 32e7f4… ⇒ تنزيل مطابق بايتيّاً ⇒ عزل مستأجِر B).
- **دلالة الإغلاق (صدق):** يُغلق **INT-004A فقط** (adapter/artifact/upload-package verified=true)؛ **يبقى مفتوحاً** INT-004B (نقل CAN/ISOBUS) وINT-004C (تأكيد استهلاك/تنفيذ الآلة) — device_delivery/machine_consumption/physical_execution/runtime/production=false. maturity/evidence=3. مصدر: `migrations/v216_machinery_export.sql` + `api/machinery_export.py` + `routers/prescriptions.py:476,593` + `precision.yaml::INT-004.scope`. management 81/81 mapped بأدلّة حقيقيّة؛ PATH-1 20/20؛ bundle 5120؛ لا SHA دمج بعد (متابعة على `claude/code-review-34hO3`).

### 2026-07-26 — تصليب حوكمة: الماسح الخام حدّ أدنى صادق ⊆ المصفوفة المرجعيّة
- **القرار:** إصلاح `capability_mapping_engine` كي يقرّر `mapped` بالأبعاد التنفيذيّة المحدّدة فقط (لا يرقّي بـgovernance/other_evidence)، ووسمه صراحةً **غير مرجعيّ** (`authoritative=false`، المصدر المرجعيّ = لوحة الإدارة)، وإضافة ثابت عابر للقطع `raw_scanner_mapped ⊆ management_mapped` + احتياطيّ fail-closed للبيان المُوقَّع عند غياب git.
- **السبب:** مراجعة 5aeefe6 الجنائيّة رصدت تناقضاً دلاليّاً P1: الخام كان يربط قدرات بذكر ID عابر (INT-001/WX-001 حاليّاً) بينما محرّك الإدارة لا يفعل — قارئ يعتمد الخام يصل لنتيجة معكوسة. الاشتمال (لا المساواة) هو الثابت الصادق: المرجعيّ يربط أكثر عبر أدلّة السجلّ المُعلَنة (IRR/OPS)، والمساواة تفرض تكرار منطق ⇒ انجراف. مصدر: `scripts/ci/capability_mapping_engine.py` (mapped= + _tracked_files + _manifest_files) + `tests/architecture/test_capability_mapping_engine.py` (3 ثوابت جديدة). management ثابت 81/81 (يقرأ الدلاء لا `mapped`). صحّح أيضاً فوات v216 من حزمة 9f8044f (كان غير متعقَّب) ⇒ الحزمة 5121. لم يُعَد فتح #661. PATH-1 20/20.

### 2026-07-26 — طيّ شريحة INT-004A في نقطة export القائمة (Ratchet: صافي مسارات = صفر)
- **القرار:** إلغاء المسارَين الجديدين (POST machinery-export + GET download) وطيّ الوظيفة كاملةً في `GET .../export` عبر `machine_profile_id` (قانونيّ، EQUIPMENT_MANAGE، إدامة مُتماثِلة بإزالة تكرار على sha256) و`artifact_id` (تنزيل). تسجيل الجدولين في `db_ownership.yml`؛ تحديث fixture ترتيب الهجرات (v216 قبل v206)؛ تحديث precision.yaml apis.
- **السبب:** بوّابة `test_p2_6_platform_route_budget_reduction` تثبّت السقف بـ`assert budget <= 629` وسياسة «No route growth» ⇒ لا رفع baseline ولا سقف؛ ولا مسار تنزيل عامّ لإعادة استخدامه ⇒ صافي مسارات جديدة = صفر إلزاميّ. الحلّ يحفظ كلّ متطلّبات الإنتاج (SoR مُدام + لقطة غير قابلة للتغيير + أثر + checksum + تنزيل + fail-closed + RLS) دون مسار جديد. GET يبقى آمناً عبر الإدامة المُتماثِلة. مصدر: `routers/prescriptions.py:337` (export المطويّ) + `db_ownership.yml` + `test_simple_farm_book.py` + `precision.yaml::INT-004`. management ثابت 81/81؛ PATH-1 20/20؛ catalog حتميّ؛ bundle 5121؛ صفر drift. المراجع أوصى صراحةً بعدم رفع baseline وإعادة استخدام مسار قائم.

### 2026-07-27 — تعميم احتياطيّ التدقيق دون git على static_governance_closure (P2)
- **القرار:** دمج bundle يطبّق نمط `git ls-files → البيان المُوقَّع → fail-closed` على `static_governance_closure.py` (نظير `capability_mapping_engine`)، مع اختبارَي مسار.
- **السبب:** يرفع قابليّة تدقيق الأرشيف المستخرَج (بلا `.git`) دون مسح ملفّات غير متعقّبة (البيان المُوقَّع قائمة سماح). مسار git يبقى مطابقاً ⇒ صفر انجراف في الإغلاق. مصدر: `scripts/ci/static_governance_closure.py` + `tests/architecture/test_static_governance_closure.py`. bundle 5121؛ كلّ البوّابات خضراء. فرع مُعاد تأسيسه من main بعد #662.

### 2026-07-27 — طبقة functional probes + جسر الهويّة التشغيليّ (خامل) — #665 `7f8f3dd` · #666 `479c09d`
- **القرار:** فصل «التحقّق الوظيفيّ» عن liveness: خطّة probes نقيّة لـweather-service (#665) ثمّ جسر حوكميّ صريح (#666) يربط اسم الخدمة في سجلّ الأدلّة بمسارها في سجلّ القدرات — كلاهما **للقراءة فقط، لا يكتب `runtime_verified`/`production`**.
- **السبب:** الاكتشاف الحاكم أنّ سجلّ الأدلّة يفهرس بالاسم بينما سجلّ القدرات يفهرس بالمسار ⇒ لا قلب صادق دون جسر؛ والمالك اختار إبقاء `runtime_verified=0` حتى وجود دليل مطابق للتعريف بدل تليين التعريف. fail-closed على كلّ فجوة هويّة/دليل؛ `--dry-run` يُظهر ما سيتغيّر دون كتابة. مصدر: `runtime-verification/service_identity_map.json` · `scripts/ci/runtime_identity_bridge.py` · `functional_probes/weather-service.json`. management 81/81؛ كلّ البوّابات خضراء.

### 2026-07-27 — تعميم الجسر لخدمتين ثمّ ثلاث (soil، platform) — #667 `4ac10bf` · #668 `b8ddc5f`
- **القرار:** توسيع الجسر من خدمة إلى ثلاث (weather·soil·platform / WX-004·WX-006·SOIL-001·IRR-009·IRR-010) بـprobes نقيّة حتميّة، مع بقاء `runtime_verified`/`production`=0.
- **السبب:** يثبت عموميّة الإطار (ثلاث بنى مختلفة: `app.post` بلا مصادقة · router بتوكن · router بـJWT) ويُنجَز كلّه في التطوير دون بيئة معتمدة — بدل flip مستحيل صدقاً في sandbox. **حدّ الصدق:** رُفض ربط `agriai`/`guardrails` (غير مسجَّلين كـ`services` لأيّ قدرة)؛ القيم الحقيقيّة للـprobes مُتحقَّقة مقابل الوحدات النقيّة الحقيقيّة (`soil_science`، `salinity_management`+`fao56`). تصليب جانبيّ: `scripts/ci/no_report_only_change_guard.py` يعرف الآن `tests/`+`runtime-verification/`. bundle 5129؛ management 81/81؛ كلّ البوّابات خضراء. **Step 3** (تشغيل حيّ `--run` في بيئة معتمدة) و**Step 4** (flip على القدرات المثبتة) يبقيان لاحقين — فجوة `RUNTIME-FUNCTIONAL-LIVE-PROOF`.

### 2026-07-27 — إعفاء `sahool-brain/` من تصنيف «تقرير» في حارس no-report-only — #669 `a00891c`
- **القرار:** استثناء مسار `sahool-brain/` من `is_report_like` في `scripts/ci/no_report_only_change_guard.py`، مع إبقاء الحجب على `capabilities/` والتقارير المُولَّدة.
- **السبب:** الدماغ توثيق **مُلزَم** ببروتوكول `CLAUDE.md` (تسويغ لكلّ حقيقة بـ`path:line`/PR/SHA)، لا تقرير تقدّم/شهادة؛ وكان الحارس يحجب الصيانة المُلزَمة لمجرّد أنّ `gaps/registry.md` يطابق تلميح «REGISTRY» — ما يدفع لافتعال تغيير كوديّ لا لزوم له. وُسِّع الحارس بمبرّر مكتوب ولم يُضعَف (اختبارا انحدار: توثيق الدماغ يمرّ · سجلّ الشهادة يبقى محجوباً). مصدر: `scripts/ci/no_report_only_change_guard.py` + `tests_v9/test_no_report_only_change_guard.py`.

### 2026-07-27 — دمج طبقة ثقة الأدلّة التشغيليّة مع إبقاء الجسر للقراءة فقط — #670 `0dad1a1`
- **القرار:** دمج حزمة `runtime_trust_v2` كاملةً (إثبات صور OCI + منتِج محميّ + موقِّع منفصل + إيصال provenance + حارس إعادة تشغيل + بيان نشر بالـdigest + سياسة أدلّة أصرم) **دون** أيّ تغيير في `runtime_verified`/`production_certified`.
- **السبب:** الحزمة تُغلق فجوات الثقة على جانب المستودع **قبل** Step 3، فتجعل الدليل الحيّ المستقبليّ جديراً بالثقة تشفيريّاً (مربوطاً بصورة مُثبَتة وبيئة محميّة وموقِّع معزول وإيصال غير قابل للإعادة) بدل أن يكون مجرّد ملفّ JSON. تحقّقتُ قبل الدمج أنّها لا تقلب شيئاً (سجلّ القدرات مطابق بايتيّاً، لا كاتب Step-4، السياسة تشدَّدت فقط) — فالدمج يزيد **صرامة** الادّعاء لا يخفّفها. مصدر: `runtime-verification/trusted_environments.json` · `scripts/ci/{provenance_receipt,runtime_replay_guard,runtime_deployment_manifest,prepare_attested_runtime_images}.py` · `.github/workflows/{runtime-image-provenance,path3-runtime-verification}.yml`. management 81/81؛ runtime/production 0؛ 70/70 CI أخضر.

### 2026-07-27 — إسقاط مسار `/runtime-identity` من المنصّة حفاظاً على راتشِت المسارات — #670 `0dad1a1`
- **القرار (المالك):** عدم رفع سقف مسارات المنصّة؛ حُذفت نقطة `GET /runtime-identity` من `sahool-platform` نهائيّاً (لا في `main.py` ولا في راوتر)، وتبقى في weather/soil.
- **السبب:** النقطة في `main.py` تخرق `p1_main_decomposition_guard` (لا مسارات في main + سقف LOC)، وفي راوتر ترفع الميزانية المقيسة 633→634 و629→630 — وهو الراتشِت نفسه الذي أوصى المراجع صراحةً بعدم رفعه في INT-004. المخرج الصادق: هويّة صورة المنصّة تأتي من **بيان النشر المرجعيّ** (المصدر الأوّليّ في تصميم الحزمة نفسها)، والنقطة كانت تدقيقاً ثانويّاً — فحُذفت بدل تليين حارس. يُعاد النظر لاحقاً كقرار ميزانيّة صريح إن لزم Step 3 على المنصّة. مصدر: `services/sahool-platform/api/main.py` (بلا مسارات) · `tests/test_p0_platform_route_ownership_guard.py` · `tests_v9/test_p2_6_platform_route_budget_reduction.py` · `scripts/ci/runtime_deployment_manifest.py`.

### 2026-07-27 — صيانة الدماغ لـ#669/#670 + إسناد تنفيذيّ لادّعاءاته — #671 `f396221`
- **القرار:** تسجيل الدمجين اللذين لم يحملهما الدماغ (توقّف عند #668)، **ورفض** تليين `brain_state_transition_guard` (عمره يوم واحد) لتمرير تعديل توثيقيّ يذكر `runtime_verified=0`؛ وبدلاً منه إضافة إسناد تنفيذيّ `tests/architecture/test_brain_state_consistency.py`.
- **السبب:** الحارس كان يطابق **الرمز** لا معناه، فيحجب جملة تنفي الادّعاء («لا يضبط `production_certified=true` أبداً») كما يحجب جملة تدّعيه. الخياران السيّئان كانا: إضعاف حارس صدق جديد، أو تجريد الدماغ من الحقل الذي يقيس صدقه. المخرج الثالث: اختبار يقرأ الادّعاءات **الرقميّة فقط** (`_NUMERIC_CLAIM = r"\b(runtime_verified|production_certified)\s*[:=]\s*(\d+)\b"`) ويطابقها مع السجلّ المُولَّد — ضيّق عمداً كي يبقى النثر النافي شغّالاً، ومُثبَت أنّه قابل للتكذيب. مصدر: `tests/architecture/test_brain_state_consistency.py` · `sahool-brain/{hot.md,log.md,decisions/ledger.md,gaps/registry.md}`.

### 2026-07-27 — «Exclude infra from budget»: استثناء مسارات البنية من راتشِت النطاق — #672 `cae51f7`
- **القرار (المالك، ناقضاً قرار #670):** معاملة `/runtime-identity` كنقطة **بنية/provenance** لا نقطة نطاق؛ استثناء **allowlist مركزيّة صريحة** فقط (`/healthz` · `/readyz` · `/metrics` · `/runtime-identity`) من ميزانية النطاق، **دون رفع الميزانية** و**دون حذف** النقطة. شروط القبول الستّة التي فرضها المالك محقّقة: الجرد الخام يُسمَح له بالزيادة (630) · ميزانية النطاق ثابتة (629) · أيّ مسار خارج القائمة يُسقِط الراتشِت · المطابقة على method + مسار مُطبَّع لا substring · اختباران يثبتان بقاء `/fields/runtime-identity` و`/runtime-identity/export` محسوبَين · التصنيف مُسجَّل كـinfrastructure في خريطة الاستخراج.
- **السبب:** الميزانية أداة لكبح **نموّ سطح النطاق**؛ عدّ نقاط البنية ضمنها يخلط القياس بالسياسة. المالك رفض صراحةً كلا البديلين: «Grow budget by 1» يغيّر سياسة الحوكمة نفسها، و«Drop platform route» (وهو قرار #670) يحذف نقطة provenance لحلّ تعارض قياس. النصّ الحرفيّ للمنع: *«لا تستخدم منطقًا مثل: `if "health" in path or "metrics" in path: exclude()`»* — لذا الاستثناء بيانات مركزيّة `frozenset` من أزواج (method, path) مع `assert_infrastructure_allowlist_is_used` يمنع قائمة سماح ميّتة، واستخراج AST يفشل مُغلَقاً على أيّ مسار غير حرفيّ. مصدر: `scripts/ci/platform_route_classification.py:20-27,73-74,141-148` · `scripts/ci/platform_route_budget_guard.py` (خام 630 · بنية 4 · نطاق 626 ≤ 629).

### 2026-07-27 — تثبيت موضع الراوتر بعقد قابل للقراءة آليّاً (لا بعُرف) — #672 `cae51f7`
- **القرار:** اعتماد `docs/architecture/platform_route_placement_contract.json` من مصدر الحزم وتوسيعه من نقطة واحدة إلى الأربع، وفرضه بحارس مستقلّ `scripts/ci/platform_route_placement_guard.py` يعمل **بلا pytest**؛ وإسقاط نسختي المكرَّرة (`CANONICAL_DECLARATION_SITES` داخل ملفّ التصنيف).
- **السبب:** **أربع حزم متتالية** أعلنت `/runtime-identity` في `services/sahool-platform/api/main.py` فأسقطت `p1_main_decomposition_guard` على أشجارها هي — أي أنّ العُرف المكتوب في `CLAUDE.md` وحده لا يمنع التكرار عند مصدر الحزم. العقد كبيانات (المالك · المصدر المطلوب · الدالّة المطلوبة · المصادر المحظورة · `uniqueness: exactly_one`) يجعل الخطأ **مرصوداً آليّاً**؛ برهان سلبيّ: إعادة إضافة المسار إلى `main.py` تُخرِج `declarations: 2 [... main.py:2556, ... platform_health.py:23] — The route must have exactly one declaration.` كون الحارس بلا تبعيّات شرطٌ لا تجميل: وظيفة `platform-route-budget` عديمة التبعيّات عمداً (محاولتي السابقة لإقحام خطوة pytest فيها أخرجت `No module named pytest`). مصدر: `docs/architecture/platform_route_placement_contract.json` · `scripts/ci/platform_route_placement_guard.py` · `services/sahool-platform/api/routers/platform_health.py:23,30,37,58` · `CLAUDE.md` §«مسارات المنصّة».

### 2026-07-27 — ربط بيان حوكمة المسارات بالإصدار وأرشيفه — #672 `cae51f7`
- **القرار:** اعتماد `scripts/release/platform_route_release_binding.py` (`--write-source`/`--check-source`/`--archive`/`--check-archive-binding`) وإضافة تحقّقه إلى `validate_release_package.py`.
- **السبب:** أرقام الميزانية بلا ربط تشفيريّ بالحزمة تُصبح ادّعاءً غير قابل للتدقيق بعد الاستخراج. الربط يُثبت بيان الحوكمة داخل الحزمة (`release/PLATFORM_ROUTE_GOVERNANCE_BINDING.json`) وعلى الأرشيف نفسه (sidecar `.routegovernance.json`: sha256 الأرشيف + sha256 البيان الداخليّ + sha256 بيان الحوكمة). **ملاحظة تدقيق صادقة:** `--check-archive-binding` على sidecar حزمة المالك (`d18dd7d`، أرشيف `bf2cb89b…`) **يرفض** لأنّه يعيد البناء من شجرة أحدث (`0efba671…`) — الرفض سلوك صحيح لا عطل. مصدر: `scripts/release/platform_route_release_binding.py` · `scripts/release/validate_release_package.py` (يطبع `platform route release binding: PASS`).

### 2026-07-27 — ربط عقد الموضع بقائمة البنية ربطاً ثنائيّ الاتجاه (تدقيق المالك على `cae51f7`)
- **القرار:** اعتماد إصلاح المالك في `scripts/ci/platform_route_placement_guard.py`: مساواة **دقيقة ثنائيّة الاتجاه** بين مسارات `platform_route_placement_contract.json` و`INFRASTRUCTURE_ROUTES` بعد تطبيع method/path، + رفض التكرار، + fail-closed على قاعدة غير كائن أو method/path غير قابل للتطبيع.
- **السبب (فجوة حقيقيّة في نزاهة الميزانية لا مسك دفاتر):** الحارس كان يتكرّر على مسارات العقد **فقط**، فلا شيء يمنع انحرافه عن القائمة في أيّ اتّجاه. **أعدتُ إنتاجها على `cae51f7`:** إضافة `("GET","/api/agent/health")` إلى `INFRASTRUCTURE_ROUTES` **وإلى** allowlist خريطة الاستخراج تُعيد تصنيف مسار نطاق حقيقيّ كبنية وتُخرجه من الراتشِت — **النطاق 626 ⇒ 625، والهامش 3 ⇒ 4** — بينما حارس الموضع يخرج بـ0 وحارس الميزانية يطبع PASS. فحص الميزانية القائم يربط القائمة بـ**ملفّ السياسة فقط**، فتحريران متناسقان (ورسالة خطئه نفسها تدلّ عليهما) يشتريان هامش ميزانية دون أيّ قاعدة موضع. هذا ينقض عمليّاً شرط المالك «لا ترفع الميزانية».
- **البراهين السلبيّة الثلاثة (مُشغَّلة):** مسار بنية جديد بلا قاعدة ⇒ `missing placement rules: [('GET', '/api/agent/health')]` · حذف `/metrics` من القائمة ⇒ `non-infrastructure placement rules: [('GET', '/metrics')]` · تكرار قاعدة ⇒ `duplicate method/path entries: [('GET', '/healthz')]` · الشجرة النظيفة ⇒ exit 0.
- **تصليب اختبار (للمالك):** التأكيد الحيّ كان يقرأ `evidence["routes"][0]` لا المسار الذي يدّعي فحصه ⇒ إعادة ترتيب العقد كانت ستجعله يؤكّد على `/healthz` صامتاً؛ صار يختار `GET /runtime-identity` بالهويّة.
- **مصدر:** `scripts/ci/platform_route_placement_guard.py:53-84` · `tests/architecture/test_platform_route_placement_guard.py` (8 اختبارات). سطح المسارات وبيان الحوكمة **بلا تغيير** (`8a31320b…`)؛ runtime/production 0؛ management 81/81.

### 2026-07-28 — WX-10.4/10.5: الخانات الأساسيّة الثلاث دخلت CanonicalWeatherState — #674 `68d56e4`
- **القرار:** بدء WX-10 بترتيب **الطقس قبل المحاصيل** (عكس ترتيب المالك المقترح)، ثمّ إدخال `current`/`forecast`/`historical` إلى الحالة الكنسيّة وتحويل مُعالِجاتها الثلاثة من تمرير حمولة المزوّد إلى Views مُشتقّة.
- **السبب:** الترتيب المُعتمَد في `architecture_roadmap_wx10_ci11.md` يضع WX-10 قبل CI-7/CI-8، وCI-7 ينصّ «Crop لا يعرف المنتجات الجزئيّة إطلاقاً». والواقع كان مخالفاً: `CropIntelligenceInput` يحمل `gdd_cumulative` كـscalar، و`CanonicalWeatherState` بلا مستهلك إنتاجيّ خارج weather-service. بناء أكبر شريحة (المحاصيل) على ركيزة لم تُهاجَر بعدُ = إعادة عمل بحجم الشريحة.
- **الاكتشاف الذي غيّر النطاق:** WX-10.1/10.2/10.3 و`gdd_view` كانت **منجزة**، ومُعالِجات `agro_*` تفوّض سلفاً وWS-C.1/C.2 تقفلها. الفجوة الحقيقيّة كانت **الخانات الأساسيّة** لا الاشتقاقات: `current_weather` كان يُعيد حمولة Open-Meteo كما هي بلا غلاف/جودة/نَسَب. `_DEFERRED_SLOTS` نزلت **7 ⇒ 4**.
- **قرار تصميم يستحقّ التسجيل:** التوافق للخلف **بنيويّ لا تأكيديّ** — المنتَج ينسخ الحمولة كاملة ثمّ يركّب الغلاف؛ قائمة الجودة **تقيس ولا تُرشِّح**. نسختي الأولى رشّحت فكانت ستُسقِط `wind_speed_10m_kmh`/`soil_*`/`timestamp` من نقطة عامّة **وCI كان سيمرّ أخضر** (يؤكّد حقلين فقط). رُصِدت بمحاكاة fixtures الحقيقيّة قبل الدفع، ويحرسها اختبار انحدار الآن.
- **مصدر:** `services/weather-service/canonical_weather_state.py` (`_current_product`/`_daily_series_product`/`_slot_view`) · `weather_runtime.py` (المُعالِجات الثلاثة) · `scripts/ci/consumer_contract_gate.py` (WS-C.3/WS-C.4، مُثبَتتان بالتكذيب). 65/65 فحص · runtime/production 0 · management 81/81 · المسارات 626 ≤ 629 بلا تغيير.

### 2026-07-28 — إعادة تأسيس فرع القدرات فوق main بدل حلّ تعارض المولَّدات — #675 (قيد المراجعة)
- **القرار:** بعد دمج #674، أُعيد بناء فرع القدرات من `origin/main` وأُعيد تطبيق **ملفّات المصدر فقط**، ثمّ **أُعيد توليد كلّ المولَّدات** على الأساس الجديد — بدل `git rebase` يحلّ تعارضات في checksums/inventory/audit يدويّاً.
- **السبب:** التعارضات الستّة عشر كانت في أغلبها ملفّات مولَّدة؛ حلّها يدويّاً يُنتِج بصمات لا تطابق أيّ شجرة حقيقيّة — وهو بالضبط نوع «الأخضر الكاذب» الذي تحرسه هذه المنظومة. إعادة التوليد تجعل الصحّة **مشتقّة لا مُصانة**.
- **التعارض الوحيد الذي يحتاج حكماً بشريّاً:** `gaps/registry.md` — `ROUTE-ARCHIVE-BINDING-CLI-TAUTOLOGY` أُخِذ من الفرع (صار FIXED_IN_CODE)، و**`WEATHER-NORMALIZER-ZERO-COERCION` حُفِظ من #674** (ما زال مفتوحاً)، و`CAPABILITY-CORES-NOT-WIRED` بقي. إسقاط أيّ فجوة مفتوحة لحلّ تعارض = محو عيب معروف صامتاً — مرفوض.
- **برهان أنّ إعادة التأسيس لم تعكس #674:** 48 اختبار CanonicalWeatherState تمرّ على الشجرة المُعاد تأسيسها.

### 2026-07-28 — نقض قرار #590: fastapi تدخل بيئة `-m unit` المشتركة — `UNIT-TEST-DORMANCY-01`
- **القرار:** إضافة `fastapi==0.136.3` و`scipy==1.13.1` و`pillow>=10.0.0` إلى `tests_v9/requirements-test.txt`، وحذف `tests_v9/requirements-field-forms.txt`، ورفع أرضيّة التغطية 40→42. هذا **نقض صريح** لقرار 2026-07-21 (#590) القاضي بإبقاء بيئة `-m unit` «دنيا بلا fastapi».
- **السبب:** شرط ذلك القرار كان «إضافة fastapi تُوقظ خامدةً **تفشل** في البيئة الدنيا». الشرط سقط في خطوتين: `29809dc` أغلق `APP-ROUTES-EMPTY-01` (كان مصدر ١١ من الإخفاقات، وسببه ترقية fastapi غير المثبَّتة لا الإيقاظ)، والباقي كان `scipy` و`pillow` — وscipy مُعلَنة أصلاً في `api/requirements.txt:20`. القرار كان صحيحاً يوم اتُّخِذ؛ ما تغيّر هو الواقع تحته.
- **القياس الذي أوجب النقض** (نفس أمر CI، بيئة نظيفة): قبل 2999 نجح · 369 تخطٍّ · 0 فشل ⇒ بعد **3478 نجح · 26 تخطٍّ · 0 فشل**. الفارق ٤٧٩ اختباراً لم تكن تُنفَّذ في بوّابة الدمج قطّ. مطابق لقياس المالك رقماً برقم.
- **لزوم كلّ تبعيّة مُثبَت بالإسقاط لا بالتقدير:** بلا `scipy` يتوقّف الجمع كلّه (`api/trial_engine.py:28`)؛ وبلا `pillow` يفشل اختبار واحد بعينه (`test_segmentation_frontend_contract_20260702`). لم تُضَف تبعيّة «احتياطاً».
- **كلّ إصدار مثبَّت على إصدار الإنتاج لا على نطاق مفتوح** — درس `APP-ROUTES-EMPTY-01` مباشرةً: `fastapi>=0.115.0` بلا سقف هو ما أنتج الإخفاقات الأحد عشر أصلاً. وأُزيل `fastapi` غير المثبَّت من سطر تثبيت `raster-validated-product.yml:22` للسبب نفسه.
- **حدّ الصدق:** يُنهي سُبات **الوحدة** فقط. لا يُغلق `AUTH-E2E-UNDER-RESTRICTED-ROLE` ولا `MCP-PREAUTH-STATUS-01` (تكامل)، ولا `APP-ROUTES-INTROSPECTION-COUPLING-01` (الاقتران بـ`app.routes` باقٍ؛ التثبيت رفع الحاجب ولم يفكّه).
- **مصدر:** `tests_v9/requirements-test.txt:38-53` · `.github/workflows/ci.yml:506-527` · `docs/testing/coverage_ratchet.md` · `sahool-brain/gaps/registry.md#UNIT-TEST-DORMANCY-01`.

### مُستنقَذان من فرع غير مدموج — 2026-07-28
> المدخلان أدناه كُتبا على `claude/brain-session-close` ولم يصلا `main` قطّ. اكتُشفا أثناء
> جرد الفروع بطلب المالك: مقارنة سطريّة أظهرت **٨ أسطر** في `ledger.md` على الفرع وغائبة
> عن main، منها قرار المالك بربط النواة الرابعة **بعد اعتراضي المُسجَّل** — أي قرار حقيقيّ
> كان سيُمحى بحذف الفرع. نُقِلا حرفيّاً لا مُعاد صياغتهما؛ قاعدة CLAUDE.md «لا قرار بلا
> سبب + PR/SHA» تنطبق على القرار أينما كُتب، لا على الفرع الذي صادف أن حمله.

### 2026-07-28 — ربط `canonical_field_state` رغم غياب مُنتِجَيها — #682 `247c69c`

- **القرار:** رُبطت النواة الرابعة بمستهلك إنتاجيّ (`internal_field_state?canonical=true`) رغم أنّ اثنين من ثلاثة منتَجات مشترطة **بلا مُنتِج في الشجرة**.
- **السبب:** أمر المالك بعد اعتراضي المُسجَّل. اعتراضي كان أنّ الراتشِت سيشهد على **حالة فارغة** لا على قدرة مستخدَمة — وهو مقلوب القاعدة الملزِمة التي منعت إدخال أسماء بلا مستهلكين. الشكل المُنفَّذ يحفظ الصدق: النواقص تُسمّى (`required_weather_unavailable` · `required_soil_unavailable`) و`operational_eligible=false` دائماً.
- **المرفوض صراحةً:** تلفيق منتَج بمخطّط صحيح لإرضاء العقد — يجعل حالة غير صالحة تبدو صالحة، وهو نفس عيب `equipment_intelligence` (250 ساعة مُخترَعة).
- **شرط رفع الأهليّة:** وجود مُنتِج تربة ومُنتِج منتَج طقس. مصدر: `services/sahool-platform/core/canonical_field_state.py:69` (`required`) · `api/canonical_water_state.py:21` (المُنتِج الوحيد المتاح).

### 2026-07-28 — تقسيم شريحة إيقاظ الاختبارات بدل إخفاء فشلها — #681 مُغلَق ⇒ #683 `121ab09`

- **القرار:** لم تُوسَم ١١ اختباراً بـ`xfail` لإنجاح الشريحة؛ قُسّمت إلى أربع وسقطت واحدة نظيفة.
- **السبب:** الشريحة غرضها **إيقاف الإخفاء الصامت**؛ إخفاء ١١ اختباراً لإنجاحها يناقض غرضها. مصدر: `tests_v9/requirements-field-forms.txt:2-3` (المبرّر البائت) · `ci.yml:624` (وظيفة التكامل التي ظهر فيها الفشل).

### 2026-07-28 — استخراج زاوية الفرع الآخر بإعادة القياس لا بنقل النتيجة — `claude/project-exploration-dtjw3p`

- **القرار:** لم تُنقَل شيفرة `claude/verify-all-generated` (نسخة bash موازية للمكنسة تحت `GENERATED-CHAIN-UNDOCUMENTED-01`)، ولا نتائجُه. نُقِلت **الزاوية** — «مولّد يدعم `--check` ولا يذكره أيّ workflow» — وأُعيد قياسها على `780d0544`.
- **السبب:** نتيجة مقيسة على شجرة أخرى ليست معرفةً بل تاريخاً. وإعادة القياس أثبتت ذلك عمليّاً: **٦** مولّدات لا ثلاثة، و**٥** منحرفة لا ثلاثة — `capability_linker` غاب عن قياس الأصل، و`scripts/release` لم يُمسح فيه أصلاً.
- **المرفوض صراحةً:** إبقاء أداتين متوازيتين (bash + Python) لنفس الغرض تحت معرّفَي فجوة مختلفَين — يُنتِج انحرافاً بين ما تراه كلّ واحدة، وهو نفس عيب «القائمة المكتوبة يدويّاً» الذي بُنيت المكنسة لتفاديه.
- **قرار تابع — التصنيف لا ينفّذ افتراضيّاً:** خمسة من الستّة تكتب ملفّات متعقَّبة أثناء `--check` (`CHECK-STEPS-MUTATE-THE-TREE-01`)، فالتنفيذ خلف `--uncovered` صراحةً. البديل — تشغيلها في المسار الافتراضيّ — يُوسّخ شجرة من يُشغّل «فحصاً».
- **المصدر:** `docs/architecture/generated_chain_known_drift.json` · `scripts/ci/verify_all_generated.py::classify_uncovered` · `sahool-brain/gaps/registry.md#GENERATED-ARTIFACT-SWEEP-01` · `#TESTS-UNMARKED-DESELECTED-01`.

### 2026-07-28 — وسم ٥٥ ملفّاً وترك ثمانية فاشلة بلا وسم — `claude/project-exploration-dtjw3p`

- **القرار:** أُيقِظ ما يمرّ فقط. الثمانية الفاشلة بقيت **بلا علامة وفي أساس مُجمَّد**، ولم يُوسَم أيّ فشل بـ`xfail`.
- **السبب:** غرض الشريحة إيقاف الإخفاء الصامت؛ و`xfail` إخفاء بصيغة أخرى. القرار نفسه اتُّخذ في #681⇒#683 وسُجِّل هنا — تطبيقه ثانيةً اتّساق لا تكرار.
- **المرفوض صراحةً:** وسم الملفّات الفاشلة ثمّ «إصلاح» تأكيداتها لتمرّ. سبعة منها تؤكّد نصّاً في مصدر تفكَّك؛ تحديث التأكيد بلا حكم عن **أين** ينتمي الآن يُنتج اختباراً يمرّ ولا يحرس شيئاً.
- **قرار تابع — لم يُصلَح `_classify` في `api_versioning_policy_guard`:** العيب حقيقيّ ومقيس (٥١٧ من ٧٤٩ مُصنَّفة خطأً)، لكنّ تصحيحه يُعيد تصنيف ٥١٧ مساراً في جرد يقرأه غيره. دُسُّه في شريحة عن علامات الاختبارات يُخفيه عن المراجعة التي يستحقّها.
- **المصدر:** `docs/testing/unmarked_tests_baseline.json` · `scripts/ci/test_marker_coverage_guard.py` · `sahool-brain/gaps/registry.md#TESTS-UNMARKED-DESELECTED-01` · `#API-VERSIONING-GUARD-IS-A-MIRROR-01`.

### 2026-07-28 — إلغاء قائمة مسارات الاختبارات بدل إطالتها — `claude/project-exploration-dtjw3p`

- **القرار:** لم يُنفَّذ العلاج الذي اقترحتُه أنا في `gaps/registry.md` (حارس يقارن الشجرة بقائمة الـworkflows ثمّ يُطيلها). نُفِّذ بدله تشغيل شجرة `tests/` كاملةً ناقص أساس مُبرَّر، بالاستثناءات **مُشتقّة** من ملفّ الأساس.
- **السبب:** العلّة المُسجَّلة نفسها هي «قائمة سماح يدويّة». حارسٌ يحرس القائمة يُخلّدها ويجعل كلّ ملفّ جديد قراراً بشريّاً يُنسى. مُثبَت بالتكذيب أنّ الشكل الجديد يُغطّي ملفّاً في دليل جديد بلا أن يسمّيه أحد.
- **المرفوض صراحةً:** كتابة `--ignore` في الـYAML. كانت ستُنتِج قائمة سماح ثانية بلا سبب ولا شرط إغلاق — العلّة نفسها بشكل جديد. الحارس يفشل الآن على أيّ `--ignore=tests/` في أيّ workflow.
- **قرار تابع — لم تُحذَف القائمة القديمة:** ٣٥ سطراً في `capability-governance.yml` صارت زائدة، لكنّ حذفها من بوّابة حوكمة يستحقّ مراجعته لا أن يمرّ أثراً جانبيّاً.
- **المصدر:** `scripts/ci/tests_tree_coverage_guard.py` · `docs/testing/tests_tree_baseline.json` · `.github/workflows/ci.yml` (وظيفة *Repository Tests*) · `gaps/registry.md#ARCH-TESTS-UNLISTED-IN-CI-01`.

### 2026-07-29 — إغلاق PATH-3 بالتشخيص لا بالاختيار — #695 `6aef452b`
- **القرار:** أُعيد توليد `compose_runtime_targets.json` البائت بدل عرض «قرارين» على المالك.
- **السبب:** الخطّة تغيّرت ٤ مرّات والمُحلِّل لم يُعَد توليده منذ #670 — فالمُشتقّ متخلّف عن مصدره، لا حالة حوكمة انقلبت. البرهان: ملفّ واحد تغيّر، وأثر `path3` المُلتزَم لم يتغيّر بحرف.
- **ما نُقِض:** تشخيصي المُعلَن ثلاث مرّات بأنّ الأثر «يدّعي جاهزيّةً لا تسندها الشجرة» — العكس صحيح.
- **مصدر:** `gaps/registry.md#PATH3-READINESS-CLAIM-UNBACKED-01`.

### 2026-07-29 — #694 أُغلِق بلا دمج، وفرع #693 لم يُلمَس
- **القرار:** بناء الاتّحاد على فرع جديد بدل الدفع فوق فرع #693، ثمّ إغلاق فرعي حين دُمِج #693 بالاتّحاد نفسه.
- **السبب:** صاحب #693 كان يعمل عليه؛ دفع قسريّ يمحو عملاً جارياً. ولمّا هبط اتّحادهم صار فرعي يحمل نسخاً **أقدم** — دمجه تراجُع لا إضافة.

### 2026-07-30 — Option B قبل raster-service، لا العكس — #722 `aeb9b1a7`
- **القرار:** بعد اكتمال شرائح الوكيل D الخمس (السقف ٢٢٩⇒٨٩)، أمر المستخدم صراحةً بإصلاح عمى `APIRouter(prefix=...)` في `generate_service_inventory.py` (مُكتشَف وغير مُصلَح في شريحة الوكيل D الخامسة) **قبل** بدء هجرة raster-service — لا بالتوازي، ولا بعدها.
- **السبب المُعلَن من المستخدم:** أيّ هجرة واسعة على جرد بائت قد تُبنى على قياس ناقص أو تُنتج تكرارات وهميّة؛ والعطل نفسه يشبه ما أُغلِق في PR #717 فيجعله شريحة صغيرة منخفضة المخاطرة عالية الرافعة.
- **التحقّق أثبت صحّة القرار:** تطبيق الإصلاح كشف فعليّاً تكراراً وهميّاً ثانياً (`GET /stac`/`GET /stac/collections` — سحول-بلاتفورم مقابل raster-service) لم يكن مرئيّاً قبل القياس المُصحَّح — لو بدأت هجرة raster-service على الجرد البائت، لكانت غيّبت مفارقة قد تُفسَّر خطأً كتكرار مسار حقيقيّ يحتاج قرار حوكمة.
- **نطاق صارم مفروض من المستخدم:** إصلاح مُصنِّف فقط، بلا هجرة مسارات في نفس الالتزام — مُتحقَّق: `api_versioning_inventory.*`/`api_versioning_legacy_allowlist.generated.json`/`api_versioning_legacy_baseline.json` بقيت بلا حرف تغيير، السقف ٨٩ ثابت.
- **القرار التالي المُقرَّر مسبقاً:** raster-service على الأساس المُعاد قياسه — لا افتراض بقاء عدده ٣٠ (كان مقدَّراً قبل هذا الإصلاح)، يُقسَّم خمس PRs بالملكيّة لا الحجم. بعده: soil-service ⇐ mcp_servers ⇐ erp-bridge (odoo-bridge اسم مستعار تاريخيّ لا خدمة مستقلّة). Auth مؤجَّل حتى إثبات مستهلكين حيّين.
- **المصدر:** `gaps/registry.md#API-VERSIONING-GUARD-IS-A-MIRROR-01` · `log.md` (٣٠-٠٧-٢٠٢٦) · PR #722 (فرع `fix-route-inventory-classifier-prefix`).


## 2026-08-01 — إسقاط إصلاحي لخريطة كتّاب المكنسة لصالح إصلاح #750 (PR #754)

- **القرار:** أخذ `scripts/ci/verify_all_generated.py` واختباره من `main` **حرفيّاً**، وإسقاط ما أضافه `e35ed137` على الفرع نفسه، وتركُ الالتزام قائماً فارغ الأثر.
- **السبب:** #750 (`583d4f9d` + `9b0399d8`) أصلح `VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01` نفسه بعشرة كتّاب مقابل خمسة — والخمسة **مجموعة جزئيّة** منها — وأغلق كلّ مدخل بشرط مُعلَن في `docs/architecture/generated_sweep_unmapped_generators.json`: أفسِد مصنوعة يملكها ⇒ `--check` يرصد ⇒ شغّل العلم ⇒ `--check` بصفر **والملفّ مُستعاد بايتاً بايت**. إصلاحي كان يثق بوجود العلم؛ إصلاحه يقيس أثره.
- **البديل المرفوض:** إبقاء الكتلتين. كان سيُكرّر عشرة مداخل ويُبقي تعليقاً يدّعي اكتشافاً ليس لهذا الفرع.
- **الأثر:** `e35ed137` بلا أثر في الفرق النهائيّ. تُرِك بلا إعادة تشكيل — نتيجة صادقة لتلاقي جلستين على عطل واحد.
- **المرجع:** PR #754 · التزام الدمج `71effa5c`.

### 2026-08-01 — أُصلح العمى أوّلاً ثمّ وُصِلت الستّة، لا العكس — #752 `bbfe121f` وما بعده
- **القرار:** رفض وصل ستّة مولّدات بـ`_GENERATE_FLAG` رغم أنّ كلّاً منها يُعلن علم كتابة يقبله argparse؛ وإصلاح عمى `--check` عندها أوّلاً في وحدة واحدة (`scripts/ci/generated_artifact_contract.py`)، ثمّ وصلها بعد أن مرّ شرط الإغلاق المُعلَن كاملاً.
- **السبب:** شرط الإغلاق المكتوب في `docs/architecture/generated_sweep_unmapped_generators.json` يبدأ بـ«أفسِد مصنوعة ⇒ يجب أن يرصد `--check`». والستّة كانت عمياء عن **١٣ من ١٦** مصنوعة تملكها، فوصلها كان يجعل `--fix` «يُصلح» انحرافاً لا يستطيع أحد رصده — أي بوّابة خضراء فوق ملفّات بلا حراسة، وهو أسوأ من عدم الوصل لأنّه يُقرأ تغطيةً.
- **قرار ثانٍ داخله — قفل الانحدار لا يُفسِد ملفّات مُلتزَمة:** القياس نفسه (إفساد ملفّ ثمّ استعادته) لم يُحوَّل إلى اختبار دائم. تشغيله في كلّ `pytest -m unit` — محليّاً وفي CI — يترك الشجرة موسَّخة إن قُتِل التشغيل بين الإفساد والاستعادة، و`finally` لا يُنقِذ من SIGKILL. استُعيض عنه بثلاثة شروط قراءة صرفة مجموعها يُساوي ما قاسه الإفساد، ومنها تحقّق **بشجرة AST** أنّ كلّ حارس يُمرّر إلى `drift`/`enforce` نتيجة `artifacts(...)` الخاصّة به — لأنّ فحصاً نصّيّاً يقبل حارساً يستورد العقد ثمّ يقارن غيره.
- **المصدر:** `gaps/registry.md#GENERATED-CHECK-IGNORES-ITS-OWN-COMPANION-ARTIFACTS-01` (مُغلقة) · `gaps/registry.md#VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01` (الجولة الثانية، ٩ ⇒ ٣) · `log.md` (٠١-٠٨-٢٠٢٦) · `tests_v9/test_generated_artifact_contract.py`.

## 2026-08-01 — مادّة المفاتيح تُصنَّف بقاعدة مُغلَقة عند الفشل، لا بقائمة علامات موسَّعة (PR #757، `6182d9d8`)

- **القرار:** اللاحقة `_KEY`/`_KEYS` تعني مادّة مفتاح ⇒ **سرّ**؛ والاستثناء الوحيد إعلانٌ صريح في `docs/architecture/runtime_contract_nonsecret_keys.json` يحمل كلّ مدخل فيه **سطر المصدر المقروء**. وتعذُّر قراءة الإعلان يجعل الجميع أسراراً.
- **السبب:** `SECRET_MARKERS` سلاسل جزئيّة، فاللاحقة المجرّدة لا تطابق شيئاً ⇒ عشرة مفاتيح توقيع/HMAC مُصنَّفة تهيئةً. والعقد الذي يذكر مفتاح توقيع بجوار مستوى السجلّ يُبلِّغ سطح الأسرار **أصغر ممّا هو**.
- **البديل المرفوض ١ — توسيع `SECRET_MARKERS` بـ`KEY`:** يُصنّف `JWT_PUBLIC_KEY` سرّاً، وهو النصف العامّ لزوج غير متماثل. تضخيم السطح كذبٌ في الاتّجاه الآخر، لا احتياط.
- **البديل المرفوض ٢ — نمط أذكى يفصل التوقيع عن العامّ:** `MFA_ALLOW_DERIVED_KEY` (راية منطقيّة) و`MFA_AUDIT_HASH_KEY` (مفتاح) يفترقان بكلمة واحدة في الخدمة نفسها. أيّ نمط يفصلهما يكون مُفصَّلاً على ثلاثة عشر اسماً معروفاً — **قائمة في ثوب نمط**، تنهار عند الرابع عشر بلا إنذار.
- **لماذا الاتّجاه fail-closed:** العجز عن إثبات أنّ اسماً ليس مادّة مفتاح ليس إثباتاً أنّه ليس كذلك. والخطأ في هذا الاتّجاه يُنتِج سرّاً زائداً يُراجَع؛ وفي الاتّجاه الآخر يُنتِج مفتاح توقيع منشوراً بوصفه تهيئة.
- **حدّ القرار:** يُغيّر **ما يُبلِّغه العقد** فقط. لا يمسّ مكان تخزين القيم ولا يُعيد ضبط أيّ نظام أسرار — ومن قرأه على أنّه تصليب أمنيّ فقد قرأ أكثر ممّا فيه.
- **المرجع:** PR #757 · `RUNTIME-CONTRACT-KEY-SUFFIX-NOT-SECRET-01` في سجلّ الفجوات · تكذيب مزدوج (حذف اللاحقة ⇒ ١٢ تسقط · تجاهل الإعفاءات ⇒ ٣ تسقط).

## 2026-08-02 — العلاج الجذريّ لـ«فاحصٍ يُبلِّغ عن سؤال لم يطرحه» ثلاث آليّات لا واحدة (`00f1bf1a` · `d194f805` · `76fb4f40`)

- **القرار:** تُنفَّذ الآليّات الثلاث **متتابعةً** وكلٌّ منها شريحة مستقلّة بفجوتها واختبارها وتكذيبها، بدل آليّة واحدة جامعة.
- **السبب:** الحوادث الستّ تشترك في **الشكل** لا في **الموضع**: واحدة في حلّ التعارض (فقدان عمل صامت)، وواحدة في المصنوعات المُعلَنة (رقم بلا أساس)، وواحدة في الحرّاس أنفسهم (تغطية غير مقيسة). آليّةٌ واحدة تغطّي الثلاثة كانت ستكون تجريداً لا يفرض شيئاً في أيّ من المواضع الثلاثة.
- **قرار داخل ① — المصدر يُوقِف السكربت ولا يُحلّ آليّاً:** لا قاعدة آليّة تصلح لدمج كود؛ والدمج الخاطئ يُغيّر سلوكاً **ولا يُبلِّغ عن نفسه**. والتوقّف أرخص من اكتشافه بعد الالتزام.
- **البديل المرفوض في ① — قاعدة في الرأس بدل سكربت:** القواعد كانت معروفة ومكتوبة ومُطبَّقة يدويّاً خمس مرّات، ونُقِضت في السادسة. **معرفة القاعدة وترميزُها في ترتيب العمليّات شيئان مختلفان**، والفجوة الزمنيّة بين «حُلَّ» و«فُهرِس» هي ما لا تسدّه النيّة.
- **قرار داخل ② — البيات يُبلَّغ ولا يُحجَب:** الحجب على تقادم رقمٍ يُحوّل كلّ PR إلى حملة إعادة قياس ويُدرّب قارئه على تجاهل الحارس. المقصود أن **يُعرَف عمر الرقم** لا أن يُمنَع تقادمه؛ والمحجوب هو **غياب الأساس** أصلاً.
- **البديل المرفوض في ② — تصحيح `baseline_route_count` من ٦٣٣ إلى ٦٣٥:** تصحيح قياس **بلا إعادة اشتقاقه** يُنتِج رقماً آخر لم يحسبه أحد — وهو العطل نفسه بقيمة أحدث. أُعلِن ديناً بدليله.
- **قرار داخل ③ — شرطان لا واحد:** «أحمر» وحده ليس دليلاً؛ لا بدّ من سقوط الاختبار **المُسمّى**، لأنّ طفرةً تكسر الاستيراد تُحمِّر كلّ شيء وتُنتِج ادّعاء تغطية بلا تغطية. **ووقعتُ في هذا بنفسي** (`expect: "test_"` مرّت خضراء) فصار `expect` مُطابَقاً بوجود `def <name>(`، وصار ذلك تحت طفرة.
- **البديل المرفوض في ③ — «الحارس له ملفّ اختبار» معياراً:** أكثر من ثلثي الحرّاس تُحقّقه، وكان أخضر طوال عمى الثلاثة. اختبار الحارس المعتاد يقيس أنّه يمرّ على شجرة سليمة — وهي خاصّيّة يُحقّقها حارسٌ لا يفعل شيئاً.
- **قرار مشترك — سقوف الدَّين مشدودة بلا فسحة:** قائمةٌ يُقال عنها «تتقلّص ولا تنمو» **بلا سقف لا تمنع النموّ**: يكفي أن يُضاف إليها المدخل الجديد. والشدّ يعني أنّ المصنوعة أو الحارس **الجديد** لا يدخل الدَّين — من قاس اليوم يعرف على أيّ شجرة قاس، ومن عرف العطل عرف كيف يزرعه.
- **حدّ القرار:** الثلاثة تُزيل **أسباب** الحوادث الستّ ولا تُغلق **صنفها**: ① يُتاح ولا يُفرَض · ② خارج نثر الدماغ · ③ ١١٧ من ١٢٠ غير مقيسين.
- **المرجع:** `MERGE-RESOLUTION-BY-HAND-LOSES-WORK-01` · `CLAIMS-WITHOUT-A-MEASURED-BASE-01` · `GUARDS-WITHOUT-A-PLANTED-DEFECT-01` في سجلّ الفجوات · ١٨ طفرة مزروعة ومُشغَّلة + ١٣ طفرة تكذيب يدويّة في الشريحتين الأوّليَين.

## 2026-08-02 — توثيق آليّة CI بدل حفظها في رؤوس الجلسات (`54a91d8e` وما بعده)

- **القرار:** كتابة `docs/runbooks/CI_GATES_AND_PRE_PUSH_PROTOCOL.md` ووصل مدخله من `CLAUDE.md`. **السبب:** أصناف الفشل التي أسقطت البناء في هذه الجلسة كانت **معروفة ومقيسة سابقاً** ومُدوَّنة متفرّقة في `log.md` وتعليقات السكربتات — أي أنّ المعرفة كانت موجودة والوصول إليها لم يكن. المعرفة غير القابلة للاستدعاء عند نقطة القرار معرفةٌ غير موجودة عمليّاً.
- **لماذا `docs/runbooks/` لا `docs/`:** المسار في قائمة المسارات الجوهريّة لـ`no_report_only_change_guard`، فالوثيقة تمرّ وحدها. **مُكذَّب لا مفترَض:** نفس المحتوى باسم يحمل `CHECKLIST` خارج المسار ⇒ حجب (rc=1)؛ في موضعه ⇒ مرور (rc=0).
- **البديل المرفوض — كتلة واحدة بلا شرح الأصناف:** «شغّل هذه الأوامر» يُنتِج مُشغّلاً ينسخ ولا يُشخّص. الأصناف الثلاثة عشر مكتوبة بعَرَضها وسببها لأنّ الرسالة الحمراء تسمّي الوظيفة لا السبب.
- **البديل المرفوض — توسيع نمط `brain_state_transition_guard` بالكلمة العربيّة المجرّدة:** المقيس أنّ ١٦ من ١٠٠ عنوان فجوة يحمل حالة عربيّة يلتقطها الحارس **صفراً**، لكنّ التوسيع بالكلمة يُطابق **٤٠ سطراً** تصف «يفشل مُغلَقاً» تصميماً لا حالة — وهو حرفيّاً العطل المُصلَح في `BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01`. **الإيجابيّ الكاذب أسوأ من غياب الحجب:** الحجب الصحيح لسبب خاطئ يُرسل القارئ يبحث عن ادّعاء لم يُقَل. سُجِّلت الثغرة مفتوحةً مع اتّجاه بنيويّ (مطابقة على عنوان `## ` داخل `gaps/registry.md`) بدل ترقيع النمط.
- **قرار صدق مقصود:** تحديث حالتي الفجوتين المدموجتين يمرّ من ذلك الحارس **بسبب تلك الثغرة نفسها**. سنده `54a91d8e` وفحوصه الـ٦٥، لا خُضرة الحارس — ومُدوَّن في المدخل وفي `log.md` حتّى لا يُقرأ المرور شهادةً.
- **حدّ القرار:** الوثيقة تصف السطح الحاجب الشائع لا الـ٥٥ workflow كلّها، وأرقامها تَبيت بالنموّ. **توثيق البوّابة ليس اجتيازها.**
- **المرجع:** PR #769 ⇒ `54a91d8e` · `BRAIN-TRANSITION-GUARD-BLIND-TO-ARABIC-STATUS-01` في سجلّ الفجوات.

## 2026-08-02 — معالجة جذرَي التعارض منفصلين، وتأجيل تحويل نموذج التخزين

- **القرار:** تنفيذ L0 (حتميّة) + L2 (حارس) + L3 (`union`) + L4 (`rerere`) في شريحة واحدة، وتأجيل L1 (شظايا مستقلّة) إلى شريحة معماريّة. **السبب (قرار المالك):** L1 يُغيّر **مصدر الحقيقة وبروتوكول الكتابة**، والبقيّة تحسينات محدودة قابلة للرجوع. خلطهما يجعل الرجوع عن أيّ منها رجوعاً عن الكلّ.
- **التسمية مقصودة:** `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01` لا «إغلاق تعارضات الدماغ» — لأنّ L3 وL4 **لا يُزيلان الجذر** وL2 **يكتشف** الفشل الصامت ولا يمنعه. اسمٌ يَعِد بأكثر ممّا يُسلّم يُنتج ثقةً في غير محلّها.
- **البديل المرفوض — `merge=union` وحده كما توصي كلّ المصادر:** **GitHub يتجاهل `.gitattributes` المُعرَّف من المستخدم** (ردّ دعم صريح؛ المطلب مفتوح منذ 2021). فالوصفة الشائعة تُصلح سطر الأوامر ولا تُزيل لافتة التعارض على الـPR — وهي اللافتة التي دفعت السؤال أصلاً.
- **البديل المرفوض — «أخرِج كلّ المصنوعات من Git وافحصها في CI»:** أفضل ممارسة عامّة، لكنّ القياس يمنعها هنا: هذه المصنوعات **مقروءة** لا معروضة (`service_inventory` في ٨ ملفّات، `route_inventory` في ٧، `capability_mapping` في ٦، بيان الإصدار في ٤ منها المدقّق). إخراجها يكسر مستهلكين حقيقيّين ويحتاج تحليلاً لكلّ مصنوعة لا قراراً شاملاً.
- **البديل المرفوض — ارتداد `SOURCE_DATE_EPOCH` إلى `time.time()`:** يعمل في CI حيث المتغيّر مضبوط، وينهار عند المطوّر بلا رسالة تشرح لماذا انحرفت مصنوعته. **الصمت أسوأ من الرفض**: العقد يفشل صراحةً ورسالته تُسمّي العلاج.
- **البديل المرفوض — قاعدة «معرّف مكرّر ⇒ فشل» في L2:** أعطت **١١** إصابة على الشجرة، **عشرٌ منها سلاسل تاريخيّة مقصودة**. حارسٌ بعشرة إنذارات كاذبة يُعطَّل في أوّل يوم — وهو العطل الأكثر تكراراً في هذا المستودع. القاعدة الصحيحة **بنيويّة**: التلاصق، وهو بصمة ضمّ union لنسختَي سطر واحد.
- **البديل المرفوض — `sahool-brain/**/*.md merge=union`:** أوسع من الأربعة المقيسة. union على ملفّ ليس إلحاقيّاً يستبدل تعارضاً يُقرَأ بنصٍّ مضموم بلا معنى — أي فشلاً صاخباً بفساد صامت.
- **البديل المرفوض — جعل L4 بوّابة CI:** CI يبدأ من نسخة نظيفة بلا `rr-cache`؛ فإفشاله على غياب rerere إبلاغٌ عن سؤال لم يُطرَح. مُختبَر صراحةً أنّ السكربت غير مذكور في أيّ workflow.
- **حدّ القرار:** الشريحة تُزيل **سبب** التعارض في المصنوعات، وتضع **شبكة وكاشفاً** للملفّات الإلحاقيّة. لا تُزيل لافتة GitHub، ولا تُلغي الصنف. ذاك `BRAIN-FRAGMENTED-SOURCE-OF-TRUTH-01`.
- **المرجع:** PR على `claude/project-exploration-dtjw3p` · `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01` و`BRAIN-FRAGMENTED-SOURCE-OF-TRUTH-01` في سجلّ الفجوات · community/discussions/9288 · reproducible-builds.org/docs/source-date-epoch.

## 2026-08-02 — إصلاح أصل التسريب بدل تقنين المسار الذي طلبه التقرير (`b83c4ecf`)

- **القرار:** رفض التوصية الصريحة في تقرير SAHOOL v22 (حذف `GET /api/probe-newservice/readyz` أو تقنينه بصلاحيّة) وإصلاح **أصل التسريب** بدلها. **السبب:** المسار لا وجود له — `git grep` على `main` ⇒ صفر، و`git log --all -S` ⇒ التزام واحد هو التزام الاختبار المُعرِّف. تنفيذ التوصية كان سيُضيف إلى `PUBLIC_ALLOWLIST` مساراً اصطناعيّاً، فيُحوّل مِسبار اختبار إلى **عقد دائم على سطح API العامّ** — أي يجعل التشخيص الخاطئ بنيةً.
- **البديل المرفوض — تعديل الاختبار ليستعيد أوثق:** `finally` أوثق لا يُغيّر شيئاً؛ العطل أنّ المقاطعة (SIGKILL / إلغاء وظيفة) **لا تُنفّذه أصلاً**. العلاج البنيويّ نقلُ المِسبار خارج الملفّات المتعقَّبة، فلا يوجد ما يُستعاد.
- **البديل المرفوض — منعٌ كامل بشجرة عمل معزولة:** يُغلق الشطر ② فعلاً، لكنّه أثقل ونفعه **لم يُقَس**. المُسلَّم كاشفٌ يُصرّح بأنّه كاشف، لا مانعٌ مُدّعى.
- **قرار نطاق — الحارس يمسح كلّ ملفّ متعقَّب لا `services/` وحدها:** ليس توسيعاً احتياطيّاً بل نتيجة **تكذيب فاشل**: نزع قائمة الاستثناء أبقى الستّة خضراء، فالاستثناء كان شيفرة ميتة والنطاق الأوّل أعمى عن أيّ تسريب خارج جروده الخمسة. بعد التوسيع تُسقِط الطفرة نفسها **أربعة** اختبارات.
- **قرار صدق — فصل ادّعاءات التقرير بدل قبولها أو ردّها جملةً:** سقوطُ ادّعائه الأوّل لا يُسقِط الباقي. `RASTER-IMAGE-SHA-NOT-INJECTED-01` و`GATEWAY-READINESS-PATHS-FALL-TO-SPA-01` سُجِّلتا **OPEN بقياسيهما** لا أُغلِقتا ضمن هذه الشريحة — نطاقهما تشغيليّ (إعادة بناء صورة · حسم عقد خارجيّ) لا ساكن. وفي المقابل `production_certified=0/81` **ليس عيباً**: ثابت صدق يفرضه `capability-governance.yml` حرفيّاً، ورفعه بلا دليل **يُفشِل البناء**.
- **وقراءة التقرير البنيويّة تُحفَظ لأنّها صحيحة:** ١٩ إخفاقاً = عيبٌ واحد وتتابعه، والصواب إصلاح الأصل وإعادة التوليد. هذا بالضبط ما نُفِّذ — على أصلٍ مختلف عن الذي سمّاه.
- **حدّ القرار:** يُغلق التسريب ولا يُغلق الفجوتين المُسجَّلتين، ولا يمنع انحراف الجرود عند المقاطعة — يجعله سطراً واحداً بدل تسعة عشر إخفاقاً لا يقول أيّها السبب.
- **المرجع:** PR #772 ⇒ `b83c4ecf` · `TEST-PROBE-LEAKS-INTO-THE-TREE-01` و`RASTER-IMAGE-SHA-NOT-INJECTED-01` و`GATEWAY-READINESS-PATHS-FALL-TO-SPA-01` في سجلّ الفجوات.

## 2026-08-03 — إعادة تشكيل #775: إسقاط موجة `v217`→`v231` بدل رفع الأساس لها (`bd7b86c5`)

- **القرار:** أُسقِطت موجتا القدرات (`dc4c1049` و`98283bca`، الرأس `98283bca`) من الـPR، وبقيت ترقيات Dependabot الخمس وحدها. **السبب:** وحداتها الأربع عشرة في `services/sahool-platform/api/` (٤٠٨٧ سطراً) لها **صفر مستهلك غير اختباريّ** في المستودع كلّه — قياسٌ بفحص الاستيراد على كامل الشجرة، لا انطباع. وهذا نصّ ما تمنعه القاعدة المُلزِمة في `sahool-brain/gaps/registry.md:383-385`، وسابقةُ #676 تحتها كانت **الإسقاط** لا التبرير.
- **البديل المرفوض — رفع الأساس 675⇒689 مع مذكّرة انحراف صادقة:** كُتِبت المذكّرة فعلاً ثمّ أُلغيت. هي بعينها الخطأ المنهجيّ المسجَّل في `registry.md:386`: **«الراتشِت لا يقرأ المذكّرات، يقرأ الأرقام. المذكّرة الأمينة لا تُصلِح رقماً يشهد زوراً.»** صدقُ الوصف لا يُبطِل زورَ الأثر.
- **البديل المرفوض — نقل الوحدات إلى خدماتها المالكة:** هو الحلّ الأصدق المذكور في السجلّ نفسه، لكنّه يحتاج **خريطة ملكيّة من المالك** (أيّ خدمة تملك phenology · salinity · nutrient ledger · yield · mobile offline · machinery delivery)، وتخمينها اختراعُ معماريّة لا تنفيذُ قرار.
- **البوّابات الأربع كانت تقيس الحقيقة نفسها من أربع جهات:** ٣٧ جدولاً خارج `db_ownership.yml` · الراتشِت 675→689 · التغطية **61.92%⇒59.44%** تحت أرضيّة 60 · و`Integration Tests`. وانهيار التغطية هو القياس الثاني للحقيقة الأولى: اختبارات الموجة تسكن `tests_v9/`، ووظيفة *Platform Unit Tests* تشغّل `services/sahool-platform/tests` وحدها بينما تعدّ `api/` في المقام — فدخل ٤٠٨٧ سطراً المقامَ بلا بسط.
- **عيبٌ حقيقيّ استُخرِج من الموجة ويُحفَظ لشريحة الوصل:** `v219_machinery_delivery_consumption.sql:10` يستشهد بـ`machinery_export_artifacts(tenant_id, id)` والعمود الحقيقيّ في `v216_machinery_export.sql:57` هو `artifact_id`. **لم يُكتشَف قطّ** لأنّ الترحيلات كانت مُعلَنة في `MANIFEST.txt` وغير موصولة بـ`scripts_v9/run_migrations.sql`، فلم تمسّ PostgreSQL في أيّ بوّابة. الإصلاح لا يُنزَل وحده: مكانه أوّل شريحة تصل الوحدات.
- **وحارسٌ للصنف لا للحالة:** `tests/test_migration_manifest_execution_guard.py` — لا ترحيل مُعلَن بلا وصل، ولا موصول بلا إعلان، ولا موصول مرّتين، و`v206_rls_final_hardening.sql` يبقى آخِراً في السجلّين. **مُثبَت بالتكذيب على زرعين:** إعلانٌ بلا وصل ⇒ FAIL، ووصلٌ بعد `v206` ⇒ FAIL على اختبارين. المقيس اليوم: ٢٢٢ مُعلَناً = ٢٢٢ موصولاً.
- **فخّ بوّابة ثانٍ انكشف في الطريق ويُسجَّل:** `capability-governance.yml` يُطلَق على `pull_request` **بلا `types`**، فالإقرار يُقرأ من حمولة الحدث لا من حالة الـPR الراهنة. بعد إعادة التشكيل بقي الإقرار القديم في الحمولة فانقلب الحجب من `missing_direct` إلى `unaffected_declared` — و**تعديل نصّ الـPR لا يُعيد إطلاقه**؛ الدفعة الجديدة وحدها تفعل.
- **حدّ القرار:** الموجة **مؤجَّلة لا مرفوضة**، ورأسها `98283bca` مثبَّت في سجلّ أحداث الـPR. إنزالها الصحيح شريحةً شريحة: كلّ وحدة مع مستهلكها الإنتاجيّ وحارسٍ يثبته، كما تنصّ القاعدة.
- **المرجع:** PR #775 ⇒ `bd7b86c5` · `sahool-brain/gaps/registry.md:383-387` · سابقة #676 · `CAPABILITY-WAVE-V217-V231-DEFERRED` في سجلّ الفجوات.

## 2026-08-03 — حزمة `canonical_projection_outbox_final`: تُؤخَذ معاملتُها، ويُرفَض مفتاحُها المُختلَق ونقضُها لحكم P0

- **القرار:** أُخِذ من الحزمة توحيدُ المعاملة وكُتّابُ الإسقاط الستّة؛ ورُفِض `_projection_command_id`، ورُفِض نقلُ `canonical_agronomic_context` خارج `provenance.input_snapshot`.
- **سبب رفض المفتاح — قياس لا رأي:** `events.command_id` هو `UUID REFERENCES commands(command_id)` (`migrations/v11_events_bus.sql:39`، حيّ في كلّ الترحيلات اللاحقة)، ولا يكتب `commands` إلّا `api/command_store.py:139`. أُعيد إنتاج الرفض على PostgreSQL 16 بمخطّط v11: `events_command_id_fkey`. الدوالّ الثلاث كانت ستفشل **في كلّ مرّة** على قاعدة حقيقيّة، وتُجهِض معها إدراجَ الحالة لأنّها في المعاملة نفسها. البديل المُنزَل: `NULL::uuid`، والتكرار محميّ بـ`dedup_key` المشتقّ من حالة غير قابلة للتغيّر.
- **سبب رفض النقل:** حكم المالك P0 نصّ على `enriched["provenance"]["input_snapshot"]`. الحزمة نقلته وعدّلت الاختبار ليوافق — وهو الصنف المرفوض صراحةً («لا تُعدّل الاختبارات لتوافق العقد؛ أصلِح العقد»). ومعه أُعيد مسارُ التدهور الصادق (`CANONICAL_CONTEXT_UNAVAILABLE`) الذي حذفته الحزمة.
- **صنف جديد يُحرَس:** «دالّة ميتة داخل وحدة حيّة». `test_canonical_writer_call_sites.py` يقيس مواضع الاستدعاء الإنتاجيّة للكُتّاب ويُثبِّت الستّة بلا مستدعٍ كمجموعة **تتقلّص ولا تنمو**؛ مُثبَت بالتكذيب بزرع كاتب جديد بلا مستدعٍ.
- **حدّ القرار:** الجداول الستّة تبقى **مقروءة-لا-مكتوبة في الإنتاج** — نزلت القناة لا المسار، و`db_ownership.yml` يقول ذلك نصّاً. مسار إدخال الرصدات الخام شريحة تالية.
- **المرجع:** الحزمة `sahool_v9_pr778_4f2dfe5c_canonical_projection_outbox_final_20260803.zip` فوق `caa7c704` · `CAPABILITY-WAVE-V217-V231-DEFERRED` في سجلّ الفجوات.

## 2026-08-04 — حزمة `stable_tree_and_root_wiring`: يُؤخَذ وصلُ الجذر، ويُصحَّح ما لم يُشغَّل قطّ

- **القرار:** أُخِذت الحزمة كاملةً **عدا** `api/routers/recommendations.py`، وأُصلِحت فوقها أربعة عيوب.
- **ما أغلقته الحزمة بحقّ:** العامل `sahool-canonical-execution-learning-worker` مُسجَّل في `docker-compose.v9.yml` ويستدعي الإسقاطات الثلاث ⇒ صنف «دالّة ميتة داخل وحدة حيّة» أُغلِق للثلاث. وتبنّت إصلاح الـFK بتمرير `None` بدل `uuid5` المُختلَق.
- **سبب رفض الراوتر:** ما زال يُلغي `_record_canonical_context` ويُخرِج السياق من `provenance.input_snapshot` ويحذف `CANONICAL_CONTEXT_UNAVAILABLE` — نقضٌ لحكم P0 رُفِض ثلاث مرّات متتالية.
- **العيب المُثبَت بالتشغيل:** بوّابة السببيّة الحيّة تمرّر `entity_id` بـ`::uuid`؛ تنجح على `v10+v11` وتفشل على `v10+v11+v18` (شكل كلّ قاعدة منشورة). ثلاثة `::text` أصلحتها، وأُعيد التحقّق على PostgreSQL 16.
- **وعيبان في حارسيّ أنا:** نطاق مسح مواضع الاستدعاء لم يشمل `scripts/workers/`، وتعبير جذور العمّال طابق `python -m api.X` فقط. كلاهما كان **يمرّ** بينما يصف واقعاً خاطئاً — وهو أسوأ من الفشل. وُسِّعا، وتقلّصت المجموعة المُثبَّتة ٦ ⇒ ٣ بالقياس لا بالتفضيل.
- **حدّ القرار:** العامل **مُسجَّل** لا **مُثبَت حيّاً**؛ `runtime_verified` و`production_certified` باقيان صفراً حتّى يُشغَّل مقابل PostgreSQL وNATS حقيقيّين. البوّابتان الحيّتان أداتان لذلك الإثبات، لا الإثبات نفسه.
- **المرجع:** الحزمة `sahool_v9_pr778_stable_tree_and_root_wiring_final_20260804.zip` فوق `337f48df`.

## 2026-08-04 — #780: يُؤخَذ ما صمد للقياس من حزمتَي الخطّ الزمنيّ، ويُرفَض الأفضل تغليفاً حين لا يحرس

- **القرار:** ثلاث شرائح على `main` المدموج (`685fff6e` · `04739fb7` · `731d263e`) وإصلاح CI (`2781d6e6`).
- **ما أُخِذ من الحزم بقياس:** الحساب بالأشهر التقويميّة + مرجع UTC + الترتيب على `acquisition_datetime` (أصلحت عيبين حقيقيّين فاتاني) · هيكل تحميل المصغّرة · `decoding="async"` · أزرار تمرير صريحة.
- **ما رُفِض ولماذا — والسبب مُسجَّل عند كلّ تأكيد لا محذوف صامتاً:** `dir="ltr"` (يضع الأحدث يساراً عكس القراءة العربيّة؛ والمشكلة الحقيقيّة اصطلاح أصل التمرير لا الاتّجاه) · تحويل الشاشة إلى واجهة `/imagery/timeline` (إعادة توصيل لها اختباراتها القائمة، لا يلزم لأيّ إصلاح هنا) · `d.thumbnail_url ?? …` (حقل لا يصل من `available-dates` أبداً ⇒ شيفرة ميتة بشكل احتياط).
- **وحزمتا ESLint رُفِضتا رغم تغليفهما الأفضل:** إحداهما تعزل التبعيّات في `frontend/tools/eslint/` — فكرة صحيحة تُوفّر ١١٦ حزمة على كلّ `npm ci` — لكنّها **بلا `eslint-plugin-react-hooks` إطلاقاً**، أي أنّها ما كانت لتكتشف انهيار ترتيب الـhooks الذي كشفه اللِّنت المُنزَل؛ ومُشغّلها يفرض `--max-warnings=0` بينما يُبقي `no-explicit-any` تحذيراً و٤٦ منها على الشجرة؛ **ولا خطوة لها في أيّ workflow**. لِنتٌ لا يحرس ما يهمّ، ولا يعمل، ليس ترقيةً على لِنتٍ يحرس ويعمل. **العزل يستحقّ شريحة لاحقة إن أزعج زمنُ التثبيت.**
- **حدّ القرار:** ٩٩ تحذيراً موروثاً لم تُرفَع إلى أخطاء — حجبها يوقف كلّ تغيير على دَين لم يُحدِثه. تبقى مرئيّة حتّى تُقلَّص. وقيد المالك على `±3 days` داخل نقطة المصغّرة لم يُمسّ.
- **المرجع:** PR #780 · `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01` في سجلّ الفجوات.

## 2026-08-04 — أختام الدمج: `910931b6` و`0df78a4e` (استكمال قاعدة «قرار + سبب + SHA»)

القراران السابقان كُتِبا **قبل** الدمج فحملا رقم الـPR بلا ختمه. القاعدة في `CLAUDE.md`
تشترط الثلاثة معاً — والرقم وحده لا يُمكّن قارئاً لاحقاً من الوصول إلى الشجرة المعنيّة.

- **`910931b6` ⇒ PR #779** — حلقة الإسقاط الكنسيّ صارت تعمل من طرف إلى طرف: الراوتر يقرأ
  ويكتب على معاملة واحدة، وعامل مُسجَّل في compose يستهلك `agronomy.projection.requested`
  ويقود الكُتّاب الثلاثة. **السبب:** الجداول الستّة كانت تُقرأ ولا تُكتَب، والوصل أُثبِت
  لا ادُّعي. ومعه ثلاثة عيوب كشفها التشغيل: `command_id` مُختلَق يكسر
  `events_command_id_fkey` (مُعاد إنتاجه على PG16) · بوّابة «حيّة» تفشل على كلّ قاعدة بعد
  v18 · وخدمة مُعلَنة تحت `networks:` لا يشغّلها Compose أبداً.
- **`0df78a4e` ⇒ PR #780** — الخطّ الزمنيّ صار يعرض شاهد تاريخه، و`npm run lint` صار
  بوّابة حقيقيّة. **السبب:** البطاقة كانت تدّعي تاريخ التقاط بلا شاهد رغم أنّ
  `acquisition_datetime` يعبر ثلاث طبقات؛ والنافذة كانت تُدخل ١٤ يوماً زائدة عند ٢٤ شهراً؛
  واللِّنت كان زخرفيّاً بأربع طبقات ناقصة، وأوّل تشغيل حقيقيّ له كشف انهيار ترتيب hooks.

**حدّ الجلسة كما هو، لا يُغلقه دمج:** `runtime_verified` و`production_certified` **صفران**.
أدوات الإثبات (بوّابة السببيّة · بوّابة RLS · جولة JetStream · مُشغّل الأدلّة المربوط
بالـSHA) نزلت كاملةً وقابلة للتشغيل في `910931b6`، ولم يُشغَّل شيء منها مقابل PostgreSQL
وNATS حقيقيّين. **الأداة ليست الإثبات**، وأين تُشغَّل قرار مالك.

## 5) قرارات 2026-08-04 (بعد #779/#780) — هبطت في `6b6ffe82` (PR #785)

**تصويب للحدّ أعلاه:** جملة «ولم يُشغَّل شيء منها مقابل PostgreSQL وNATS حقيقيّين» صارت
بائتة. شُغِّلت محلّيّاً على PG16 حقيقيّ وnats-server v2.10.22 حقيقيّ: بوّابة السببيّة
**PASS**، وبوّابة RLS **PASS** بعد تطبيق منح `bootstrap_postgres.sh:122-124`، و
`--preflight-json` **PASS**. الرحلة الكاملة لم تُشغَّل بعد (ينقص v224–v226 في المخطّط
الأدنى)، فيبقى `runtime_verified=0` و`production_certified=0` كما هما.

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| durable مستقلّ لكلّ موضوع في عامل التعلّم القانونيّ، مشتقّ من الموضوع **كاملاً** | المستهلك المُعمَّر يرتبط باشتراك واحد، فالاسم المشترك يقتل العامل في الدورة الثانية قبل معالجة أيّ حدث؛ ولاحقةُ المقطع الأخير تُعيد التصادم لأنّ `season.closed`/`irrigation.closed` يتشاركانه | `WORKER-REGISTERED-BUT-CANNOT-START-01` · `86e1738a` ⇒ `6b6ffe82` (#785) |
| لا هجرة ولا اسم durable انتقاليّ | مستهلِك الاسم المشترك لم يكن ليُنشَأ لأكثر من موضوع واحد، والعامل الذي يملكه لم يُقلِع قطّ ⇒ لا حالة قائمة تُهاجَر | القياس الحيّ على nats-server v2.10.22 · `86e1738a` |
| إعلان حافّة `depends_on` على وكيل الإشعارات بلا نقل ملكيّة الدفق | الدفق `sahool` ينشئه مستهلِك (`agents/notification/agent.py:449`)، ونقل الملكيّة قرار معماريّ يمسّ كلّ مشترِك على الناقل — خارج نطاق شريحة إصلاح عامل | `JETSTREAM-STREAM-TOPOLOGY-OWNED-BY-A-CONSUMER-01` · `86e1738a` ⇒ `6b6ffe82` (#785) |

## 6) قرارات 2026-08-05 — شريحة WOFOST what-if

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| إسقاط الطرح على `irrigation_needed_mm` واشتقاق «الماء الموفَّر» من `irrigation_applied_mm` | `total_etc_mm` متطابق بين الفرعين (٧٣٩.٩ مقيساً)، فالفرق بين الطلبين هو معامل `× 1.1` وحده: ٧٣.٩ = ٠.١ × الطلب. مقدارٌ لا يعلم بالسيناريو ولا بالماء المُطبَّق، بينما المُطبَّق مُراكَم في الحلقة بلا معامل ⇒ هو المتجانس الوحيد بين الفرعين | `WOFOST-WHAT-IF-SEVEN-DEFECTS-01` · `shared/wofost/engine.py:425` |
| **عدم** تغيير المعامل `× 1.1` نفسه | تغييره يحرّك كلّ رقم طلبِ ريٍّ في المنصّة، ودلالتُه (كفاءة تطبيق؟) غير مُعلَنة في أيّ عقد. تصحيحُه بترجيحٍ من داخل شريحة إصلاح نقطةٍ واحدة قرارٌ ليس لي | `WOFOST-IRRIGATION-EFFICIENCY-COEFFICIENT-01` (مفتوحة) |
| الإفصاح عن احتياط البارامترات بدل رفضه بـ`422` | جداول المحرّك تحمل ستّة محاصيل وأربع تُرَب؛ الرفض يمنع نشراً شرعيّاً لحقلٍ بمحصول غير مُدرَج. الخلل كان **الادّعاء الصامت** لا الاحتياط ⇒ عُولِج بـ`parameter_resolution.degraded` + اسم البديل | قيد مالك سارٍ: «لا يجوز منع deployment شرعيّ» |
| رفض `422` للتاريخ الفاسد (خلافاً للإفصاح أعلاه) | لا احتياط صادق هنا: `date.today()` يُحاكي **موسماً آخر** وينسب نتيجته إلى تاريخ المستخدم. الإفصاح يُصلح ادّعاءً عن بديلٍ معقول؛ ولا بديل معقول لسَنة أخرى | `services/sahool-platform/api/routers/simulate.py` |
| عدم قصّ `water_saved_mm` عند الصفر | نسبةٌ أقلّ تُشغّل عتبة الإجهاد أكثر، فقد تُطبَّق كمّيّة أكبر إجمالاً. القصّ يُخفي الزيادة خلف صفر؛ التوجيه يُعلَن في `water_use_direction` | تصحيح المالك: «`baseline − scenario` ليست مقلوبة دائماً — اختبر التخفيض والزيادة» |

## 2026-08-07 — `TESTS-UNMARKED-DESELECTED-01`: تصحيحُ قياسٍ لا توسيعُ أساس

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| وسمُ ملفّي `tests_v9/runtime_activation/` بـ`unit` بدل إضافتهما إلى الأساس | الأساس راتشِت **يتقلّص ولا ينمو**. الملفّان لم يكونا ديناً جديداً بل محجوبَين عن القياس، والثمانية تمرّ فعلاً — فإضافتهما كانت ستموّل تصحيح القياس بتوسيع الدَّين، وتُسجّل ديناً حيث لا دين | `4c9d96fc` · `docs/testing/unmarked_tests_baseline.json` (`correction_2026_08_07`) |
| إبقاء الأساس عند **٩** رغم أنّ القياس الجديد أعطى ١١ | الفارق هو الملفّان وحدهما، وقد وُسِما. رفعُ السقف إلى ١١ كان سيُثبِّت رقماً لا يقابله دينٌ قائم | `docs/architecture/guard_mutation_registry.json` |
| إعادة مرساة `test_phase2` إلى وحدات الخدمة مضمومة بدل حذف التأكيد | القدرة **سليمة** في `ai_evidence_runtime.py:61`؛ التأكيد بايت لا كاذب. الحذف كان سيُسقِط حراسةً قائمة بحجّة أنّها أزعجت | `tests_v9/runtime_activation/test_phase2_ai_gateway_web_binding_static.py` |
| إضافة تأكيد التفويض (`from .ai_evidence_runtime import`) مع نقل المرساة | مرساةٌ على «الوحدات مضمومة» وحدها تنجو من **حذف الربط** بين المسار والمنطق؛ التأكيدان معاً يقيسان القدرة لا وجود النصّ | مُكذَّب بشطريه |
| جعل المُصدِّق **يتخطّى مُعلِناً** بدل أن يصدُق فراغاً في بيئة لا تجمع `tests_v9` | وظيفة `capability-governance` تُثبِّت pytest وحده؛ مجموعتان فارغتان تُصدِّقان العلاقة بلا قياس — وهو الصنف الذي بُنيت الشريحة ضدّه | `tests/architecture/test_marker_coverage_guard.py` |
| **عدم** تعميم الكشف على `from pytest import mark` | لا ملفّ في الشجرة يستعمله (مقيس: صفر)، وإضافة مطابقة على اسم `mark` المجرّد تفتح إنذارات كاذبة على أيّ كائن بهذا الاسم. الحدّ مُعلَن بدل أن يُقرأ ضماناً أوسع | قياس على `9c0647a3` |

## 2026-08-07 — `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`: يُحرَس ما يُحسَم وحده

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| **عدم** حجب الـ٢٩٢ تأكيداً موجباً يثبّت نداءً | معيار الفجوة («هل يبقى التأكيد صحيحاً بعد إعادة صياغة صحيحة؟») غير قابل للحسم آليّاً. مُصنِّفٌ استدلاليّ يُنتِج قائمةً **تُقرأ ديناً وهي ما طابق نمطاً** — ولو حُجِب عليها لصار الحارس هو الصنفَ الذي يعالجه: يثبّت ما طابق نمطاً ويُسمّيه حقيقة | `source_text_assertion_inventory.json` · `test_the_heuristic_class_is_published_but_never_gates` |
| حجب المَنع بلا سببٍ مُعلَن وحده | قابل للحسم بلا استدلال: إمّا ثمّة رسالة أو لا. وهو نصفُ العلاج الذي أنزلَته #780 صراحةً | `scripts/ci/prohibition_reason_guard.py` |
| قصر النطاق على **نصّ المصدر** دون جسم الاستجابة | هناك التأكيد **هو** العقد وسببه في اسم الاختبار؛ وتعميمُه يطالب برسالة على كلّ تأكيد سالب في المستودع فيُنزَع الحارس في أوّل يوم | `test_a_prohibition_on_something_that_is_not_source_text_is_out_of_scope` |
| اشتقاق «نصّ المصدر» من **الإسناد** لا من اسم المتغيّر | `src` · `b` · `text` · `SRC` اصطلاحٌ لا عقد؛ والاسم يُخطئ في الاتّجاهين | `_source_text_vars` · طفرة مزروعة |
| **عدم** كتابة أسباب للمئة الباقية | لا أعرفها، واستخراجُها يحتاج قراءة كلّ سياق. **سببٌ خاطئ أسوأ من غيابه لأنّه يُصدَّق** — والأساس يقول صراحةً إنّه مَعدودٌ لا محكومٌ عليه | `$comment` · `test_the_inventory_says_what_it_does_not_claim` |
| سداد ١٧ فقط، وكلٌّ بسببٍ **مُستخرَج من سياقه** | ما يُسمّيه اسمُ اختباره أو تعليقٌ ملاصق أو عقدٌ مُعلَن في الملفّ. وحدُّ التوقّف مُعلَن: توقّفتُ حيث بدأ التخمين | ١١٧ ⇒ ١٠٠ |

## 2026-08-07 — `CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`: الأهليّة خارج الهاش

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| كيانٌ مشتقّ بدل حقل داخل اللقطة | اللقطة معنونة بمحتواها؛ حقلٌ داخلها يُغيّر كلّ هاش قائم عند أوّل تغيير سياسة ⇒ تنكسر إعادة التشغيل ويُقطَع نَسَب الأدلّة | `migrations/031` · نطاق المالك |
| إدخال `as_of` في البصمة و**استبعاد** `assessed_at` | ساعةُ الحائط تجعل «الحتميّة» ادّعاءً؛ واللحظة المنطقيّة مُدخَل حقيقيّ يُعاد به التقييم | `test_wall_clock_never_enters_the_digest` |
| أربع مراحل لا قيمة منطقيّة واحدة | لقطةٌ تكفي للاستكشاف قد لا تكفي للتنفيذ؛ وطيُّها هو الخلط الذي أوجب الفجوة — ويُرفَض بـ`CHECK` في القاعدة | `031` · الاختبار الحيّ |
| **عدم** وصل المُقيِّم بأيّ مسار طلب | نصّ النطاق: لا endpoint جديدة ولا خدمة. الوصل قرار منتَج، والادّعاء بلا مستهلِك يُقرأ قدرةً قائمة | حدّ صدق مُعلَن |
| **عدم** مسّ `decision_eligible` | يبقى حقيقةً عن المؤشّر ونقطةَ توافق للخلف كما نصّ التصميم المُقَرّ؛ توسيعُه هو العطل الأصليّ | `generate_indicator_artifacts.py` |
| إبقاء تتالي المراحل رغم أنّه لا يُطلِق اليوم | يحرس سياسةً مستقبليّة **غير مُطّردة** تُرخي مرحلةً متأخّرة ⇒ خطّة تُقترَح على لقطةٍ لم تُشخَّص. والاطّراد نفسه صار مُثبَّتاً باختبار يسقط يوم يبطل | `test_the_shipped_policies_are_monotone_across_stages` |
| رفض نسخة سياسة مجهولة بدل السقوط إلى الأحدث | السقوط يُعيد تقييماً قديماً بقواعد لم تكن قائمة، ويُنتِج بصمةً تُطابق بلا أن تُطابق الدلالة | `UnknownPolicyVersion` |

## 2026-08-07 (ب) — علاج مراجعة #810

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| البصمة عند رفض المستأجِر تُشتقّ من **الهويّة وحدها** | قراءة الجسد وبصمُه قبل الفحص تجعل `assessment_digest` أوراكل: يتغيّر بتغيّر جسد لقطةٍ لا يملك الطالب قراءتها | `test_a_tenant_mismatch_digest_does_not_depend_on_the_body` |
| رفض `data_available_at > as_of` | القرار على معلومةٍ لم تكن متاحة عند اللحظة يُفسِد كلّ إعادة تشغيل تاريخيّة، ولا يكشفه اختبار حتميّة | `NOT_YET_AVAILABLE` |
| رفض الرصد المستقبليّ بدل احتساب عمره | العمر السالب أصغر من أيّ عتبة ⇒ **يُكافأ** بدل أن يُرفَض | `FUTURE_OBSERVATION` |
| فرض `64-hex` في المقيّم لا في القاعدة وحدها | المقيّم الذي يمنح أهليّةً لِما لا هويّة له يُنتِج قراراً لا يمكن نسبُه إلى دليل | `MALFORMED_SNAPSHOT_DIGEST` |
| **إعلان `adjudicated=False`** بدل تحكيم العتبات ذاتيّاً | أعمار الطقس/التربة وعتبتا ٣٠/٨٠ من وضعي بلا مصدر قرار. سياسةٌ تُقدَّم مُحكَّمة بلا تحكيم أخطر من غيابها لأنّ من يقرؤها يبني عليها — والتحكيم قرار مالك | `provenance` · اختبار يفرضه |
| ربط `source == real` و`status == implemented` بالعقد القائم | هما المُحكَّمان فعلاً وأصل `decision_eligible`؛ فالسياسة تمتدّ من العقد بدل أن **توازيه** | `generate_indicator_artifacts.py:55-61` |
| توسيع نمط الحارس ليشمل `IF NOT EXISTS` و`ONLY` والأسماء المؤهَّلة | النمط يظهر ٢١ مرّة في هجرات الخدمة — فأرجح طريقٍ إلى العطل كانت الوحيدة التي لا يراها الحارس | مُثبَت بطفرة |
| `shutil.which` قبل استدعاء `psql` وقت الاستيراد | `FileNotFoundError` قبل `skipif` يُنتِج **خطأ تجميع** يُخفي الملفّ كلّه، لا تخطّياً مُعلَناً | مُقاس بـ`PATH` فارغ |

## 2026-08-08 — `RELEASE-MANIFEST-SELF-REGENERATION-01`

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| حذف `generated_at` من البيان المُلتزَم | الحقل **بلا مستهلِك واحد**، و**لا يمثّل وقت البناء الحقيقيّ** بل زمن التزامٍ سابق؛ ووجودُه يجعل المصنوعة عاجزةً عن مطابقة إعادة توليدها على التزامها نفسه | قياس على `fc79fbbe` · قرار المالك |
| **عدم** إعفاء البيان من فحص الانحراف | الإعفاء يُبقي العيب ويُطفئ الكاشف — والفحص هو ما كشف بطلان الافتراض أصلاً | معيار القبول ⑥ |
| إبقاء `deterministic_time.py` | يستهلكه `runtime_environment_preflight.py` أيضاً؛ لا يُحذف عقدٌ لأنّ أحد مستهلكيه استغنى عنه | جرد المستهلكين |
| **عدم** اشتقاق زمنٍ من الـSHA | التجزئة ليست طابعاً زمنيّاً — وقد نصّ المالك عليه | قرار المالك |
| إبقاء `payload_pathspec` مع إعلان أنّها بلا مستدعٍ إنتاجيّ | حذفها وحذف اختبارها خارج نطاق الشريحة؛ والإعلان يمنعها أن تكون شيفرةً ميّتة يحرسها اختبار أخضر | docstring |
| تحويل «الختم وحده يتبع المتغيّر» إلى «البايتات كلّها ثابتة» | الخاصّيّة الجديدة **أقوى** وهي ما يفحصه شرط النظافة مباشرةً | `test_the_manifest_is_byte_identical_under_any_source_epoch` |

### 2026-08-08 (ب) — `FAKE-CONNECTION-ENFORCES-NOTHING-01`: سداد الدَّين حيّاً

| القرار | السبب (rationale) |
|---|---|
| لكلّ ادّعاء **قبول ورفض** لا قبولٌ وحده | حالة القبول وحدها تمرّ على جدولٍ بلا قيدٍ أصلاً، فتُثبِت أنّ الإدراج يعمل لا أنّ القاعدة تمنع. |
| الرفض بـ`SQLSTATE` لا بنصّ الرسالة | النصّ يتغيّر بإصدار الخادم وبلغته؛ و`SQLSTATE` عقدٌ ثابت. تأكيدٌ على النصّ يمرّ اليوم ويُكذَب بترقية. |
| وظيفة PG مخصّصة **تفشل** عند غياب القاعدة، والوظائف العامّة **تتخطّى مُعلَناً** | تخطٍّ في الوظيفة المخصّصة خضرةٌ تعني «لم يُقَس» — وهو الصنف الذي أوجب الفجوة. وتعطيلُ بوّابات لا علاقة لها بالقاعدة ثمنٌ بلا مقابل. |
| إضافة `proven_live` بدل حذف الملفّات من `claiming_db_enforced` | الأخير مُشتقّ بماسحٍ من **نصّ** الملفّ، والإثبات الحيّ لا يغيّر النصّ — فالحذف يدويّاً يُعيده أوّل `--generate`، والمخرج المكتوب في `$comment` كان بلا وجود. |
| ملفّ الإثبات يجب أن **يذكر** مصدره | مدخلٌ يشير إلى إثباتٍ قائم لا علاقة له بمصدره يمرّ الفحصين السهلين ويترك الدَّين غير مسدَّد. الربط يُقاس ولا يُدَّعى. |
| `LIVE-PG-01` يُسجَّل ولا يُصلَح | إصلاحه تغييرُ نموذج أدوار يمسّ الترحيل والنشر؛ وخلط الإصلاح بشريحة الأدلّة يجعل مراجعتها مراجعةَ إصلاحٍ لم يُطلَب. |
| تأكيد `FORCE` مُعلَن **كتالوجيّاً لا سلوكيّاً** | أثرُه غير قابل للرصد تحت مالكٍ superuser، فادّعاءٌ سلوكيّ هنا كاذبٌ بالمعنى الدقيق — و`GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01` في ثوب آخر. |
| الملفّات الثمانية تبقى في `fake_connection_tests` | المُسدَّد هو الادّعاء عن القاعدة لا استعمال الوهميّ؛ والوهميّ نافع لمنطق التطبيق. |

## 2026-08-08 (هـ) — تقوية دليل PG: أربع خصائص تحجب، ودليلٌ يوجد يوم الفشل

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| الخصائص الأربع تحجب، لا اثنتان | الوظيفة **تُهيّئ** الدور بالأربع وتفحص اثنتين؛ و`rolcreatedb` كان يُقرأ ويُطبَع ولا يحكم — رقمٌ معروض لا حارس | `LIVE-PG-ROLE-CHECK-READS-FOUR-JUDGES-TWO-01` |
| إدراج `CREATEROLE` رغم أنّها لا تتخطّى RLS مباشرةً | مالكها يُنشئ دوراً يمنحه ما يشاء ثمّ يعمل تحته — يبلغ بخطوتين ما مُنِع منه بخطوة | `test_a_createrole_role_is_rejected` |
| قائمتان منفصلتان (الاستعلام ≠ قرار الرفض) لا اشتقاق إحداهما | الاشتقاق يجعل الطفرة الواحدة تُسقِط اختبارين، فيُقرأ ادّعاءان مغطّيَين وأحدُهما بلا حارس. **الاستقلال معيارٌ، والعدد ليس** | `_ROLE_CATALOGUE_COLUMNS` مقابل `_REJECT_IF_TRUE` |
| أربعة اختبارات مُسمّاة لا حلقة واحدة | آليّة الطفرات تطلب احمرار اختبارٍ **باسمه**؛ والحلقة تُسقِط اسماً واحداً مهما كانت الخاصّيّة المنزوعة | `guard_mutation_guard` |
| فشلٌ مغلق على عدد الحقول **وعلى** قيمتها — طفرتان لا واحدة | الأولى تحرس **محاذاة** الحقل والثانية تحرس **قيمته**؛ ادّعاءان مختلفان لا وجهان لادّعاء | `test_a_malformed_role_row_is_fail_closed` |
| كتابة الدليل **قبل** رمز الخروج، ومن مسار الفشل المغلق أيضاً | وثيقةٌ لا توجد إلّا يوم النجاح هي المعنى المقلوب لكلمة «دليل»؛ وخروجٌ صامت يُقرأ لاحقاً «لم يُشغَّل شيء» وهو يعني «شُغِّل وانهار» | `LIVE-PG-EVIDENCE-EXISTS-ONLY-WHEN-EVERYTHING-PASSED-01` |
| `github_sha` منفصلاً عن `checkout_sha`/`checkout_tree` | في `pull_request` تعمل الوظيفة على دمجٍ وهميّ؛ توحيدُهما يُنتِج وثيقةً تدّعي أنّ ما اختُبِر هو ما أطلق التشغيل — كذبٌ **بالبناء**. والفصل هو المعلومة | `test_the_evidence_binds_the_tested_commit_and_tree` |
| تسمية الحقل `direct_role_attributes` لا `role_isolation` | الفحص يقرأ `pg_roles` للدور نفسه ولا يُثبِت الإغلاق الانتقاليّ لعضويّات الأدوار ولا أثر `SET ROLE`. الاسم يقول مداه، وحدُّ الصدق **داخل** الوثيقة | `live_pg_evidence.json` §`$comment` |
| إزالة الطفرة البائتة لا إعادة ربطها | سلسلتها اختفت بصيرورة الرفض حلقةً؛ وإعادة الربط كانت ستُبقي ادّعاءً واحداً حيث صارت أربعة مستقلّة | `guard_mutation_registry.json` |
## 2026-08-08 — نتيجة الفحص الجنائيّ تُسجَّل تنفيذيّاً ولا تُصلَح، احتراماً لتجميد المرحلة 0 (`acb2c8ee5`)

- **القرار:** إصلاح M-01 وM-02 **مُنفَّذ ومُختبَر ثمّ أُرجِع**، ويُحفَظ رقعةً خارج المستودع؛ ويُدفَع بدله **توثيق تنفيذيّ** بـ`xfail(strict=True)`.
- **السبب:** v06 يمنع تعديل المسارات الفيزيائيّة قبل تثبيت evidence pack المرحلة 0، والحزمة تحمل `frozen_commit_sha: null` و`phase0_evidence_status: NOT_FROZEN` ⇒ GATE-01 لم تُفتح. و`REAL/CUTOVER: BLOCKED` قائم.
- **البديل المرفوض — «التعديل يزيد الإيقاف فيُستثنى»:** إضافة فحص إيقاف تبدو زيادةً في السلامة، لكنّها **تغييرٌ لمسار فيزيائيّ** كأيّ تغيير. واستثناءٌ يُمنَح بالنيّة الحسنة يُفرِّغ التجميد من معناه: كلّ من يُعدّل مساراً يظنّ تعديله تحسيناً.
- **البديل المرفوض — «سجلّ الفجوات وحده»:** أنقى التزاماً وأضعف أثراً؛ يترك الاكتشاف **نثراً** لا مصنوعةً تُشغَّل. والاختبار مسموحٌ في المرحلة 1 صراحةً.
- **ولماذا `strict=True` تحديداً:** علامةٌ غير صارمة تبقى خضراء بعد دخول الإصلاح فتُنسى إلى الأبد — «فاحصٌ يُبلِّغ عن سؤال لم يطرحه» بشكلٍ جديد. والصارمة تحمرّ يوم يدخل الإصلاح فتُطالِب بنزعها. **مُتحقَّق بالتطبيق:** الرقعة تُحوّل الثلاثة عشر إلى XPASS.
- **قرارٌ ثانٍ — M-05 لا تُسجَّل فجوةً تنفيذيّة:** ادّعاءٌ مردود بالدليل (`v161`/`v162`/`v163`)، ويُحفَظ **سجلّاً تحكيميّاً** لئلّا يُعاد اقتراح «إصلاحه» — وإصلاحه كان سيُعطّل RLS الصحيح في `p1/p2/p3`. البنود التنفيذيّة خمسة: M-01 · M-02 · M-03 · M-04 · M-06.
- **قرارٌ ثالث — الاتّصال الوهميّ يُعلَن بالاشتقاق لا باليد:** `fake_connection_debt_guard --generate` (38 ⇒ 39، و`claiming` ثابت عند 8). والتسمية لم تُغيَّر للتهرّب من الكاشف؛ غُيِّر **الشرح** الذي عدّد مصطلحات القاعدة لينفيها فصُنِّف ادّعاءً — تصحيح تصنيف لا تحايل عليه.
- **حدّ القرار:** لا يُغلق أيّ عيب. العيبان قائمان في الشجرة، وحاجبان لأيّ real/cutover، ويُصلَحان بعد تثبيت `frozen_commit_sha` وتوثيق callsites والملكيّة والأعلام على الـSHA نفسه.
- **المرجع:** `COMPENSATION-BYPASSES-KILLSWITCH-01` · `MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01` · `GUC-SCOPE-GUARD-SEES-ONE-FILE-01` · `GUC-NAME-MISMATCH-CLAIM-REFUTED-01` · `FORCE-WITH-LEASE-DEFEATED-BY-ITS-OWN-FETCH-01` · SAHOOL_MASTER_EXECUTION_PROGRAM-06 §0.10/§2.5.

## 2026-08-08 — #811: ترتيب `IF EXISTS`/`ONLY` في كاشفين

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| قبول `IF EXISTS` و`ONLY` **بأيّ ترتيب** في حارس اللقطة، لا بالترتيب القانونيّ وحده | كاشفٌ لا مُحلِّل نحويّ: الإفراط في الالتقاط مجّانيّ (SQL غير قانونيّة تفشل في الترحيل)، والتقصير هو العطل بعينه | `snapshot_eligibility_separation_guard.py` · طفرتان (٥ و٦) تُسقِطان اختبارين مُسمّيين |
| قبول النجمة الوراثيّة `<t> *` في النمط نفسه | جزءٌ من القواعد `ALTER TABLE … name [ * ]`، وغيابه ثغرةٌ بنفس الشكل | ثقبٌ ثالث بقي بعد تصحيح الترتيب في الجلسة الموازية (مدموجة في `fc79fbbef`)؛ وطفرة سادسة تنزعه |
| إصلاح `capability_mapping_engine.TABLE_RE` **داخل #811** رغم ضيق نطاق التعليمات | الالتزام كان سيشحن أربعة ادّعاءات تغطية كاذبة أحدثَها هو، ويرفع `capabilities_multidimensional` ٤٨ ⇒ ٤٩ على كذبة. توسيعٌ مُعلَن، والرجوع عنه قرار المالك | `capability_mapping_engine.py:168` · ١٦ ⇒ ٠ مدخلاً كاذباً |
| **نظرة أمام سالبة** في المُصنِّف بدل ترتيب البدائل | التراجع (backtracking) يُعيد إنتاج العطل مهما رُتِّبت البدائل؛ المطلوب منعُ **النتيجة** لا ترتيبُ المسار | `(?!(?:if\|not\|exists\|only)\b)` |
| اختبارٌ يقيس **المخرَج المُلتزَم** لا الدالّة وحدها | دالّةٌ تُصلَح ومصنوعةٌ لا يُعاد توليدها تبقى تُقرأ صادقة — والفارق بينهما هو ما أفلت | `test_the_shipped_tree_carries_no_keyword_named_table` |
| عدم تسجيل `capability_mapping_engine` في `guard_mutation_registry.json` | نطاق `GUARD_GLOBS` هو `*_guard.{py,sh}`؛ إقحامُه يجعل السجلّ يدّعي إنفاذاً لا يملكه. التكذيب يدويّ **وموثَّق بحدّ صدقه** | `guard_mutation_guard.py:55` |
| تأجيل إصلاح `generated_at` شريحةً مستقلّة | قرار المالك صراحةً؛ ولأنّ أولويّته **غير مُقاسة** لهذه المولِّدات الثلاثة بعد | `GENERATED-AT-STILL-WALL-CLOCK-IN-THREE-GENERATORS-01` |

## 2026-08-08 (ج) — #812 مُعاد بناؤه: الاقتباس والمُؤهِّل

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| نظرة أمام سالبة في `_COLUMN` لا دعم الاقتباس وحده | `ADD COLUMN "x"` كانت تُنتِج `['COLUMN']` لا صفراً — التقاطٌ خاطئ يمرّ على `FORBIDDEN` بوصفه «ليس محظوراً» | `test_the_word_column_is_never_captured_as_a_column_name` |
| **عدم** تسجيل طفرة للنظرة الأمام | نزعُها وحدها لا يُسقِط اختباراً (مقيس على خمس صيغ) — ومواصفةٌ تمرّ خضراء ليست دليلاً. كُتبت «دفاعٌ في العمق، لا حارسٌ مُثبَت» | `snapshot_eligibility_separation_guard.py` §`_COLUMN` |
| `\b(?!\s*\.)` بدل أيّ ذكرٍ لـ`public` في المُصنِّف | `public` اسمُ جدولٍ قانونيّ غير مؤهَّل؛ حظرُها بالاسم يُنتِج العمى المقابل. المرفوض **الموضع** لا الاسم | `test_public_unqualified_is_still_a_legitimate_table_name` |
| `\b` قبل النظرة لا النظرة وحدها | بدونها يتراجع `[\w]*` إلى `publi` فتمرّ النظرة على `c` — أوّل مرشَّح كان خاطئاً لهذا بالذات | مقيس على `public."<t>"` |
| تأكيدٌ يمنع أدلّة قاعدة بيانات من رَنبوك الحرّاس | نثرٌ مولَّد عن الحرّاس ليس مخطَّطاً؛ والتأكيد يمسك الحادثتين معاً بخلاف تأكيد الكلمات المفتاحيّة | `test_the_shipped_tree_takes_no_database_evidence_from_the_guard_runbook` |
| حفظ `28d252c0b` بمرجعين قبل إعادة الكتابة، وعدم دفعه | كان يشحن ٤ ادّعاءات كاذبة فوق أساسٍ بائت؛ والاعتماد على reflog وحده ليس حفظاً | `refs/wip/quoted-identifier-guard` + وسم |

## 2026-08-08 (د) — #812: عقد المؤقّت والدائم، وتأكيدٌ قبل التحميل لا بعده

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| بُعد `database` يقيس **العلاقات الدائمة** — عقداً مكتوباً لا ضمناً | البُعد يُقرأ «العلاقات التي تعيش في هذه المنصّة»؛ والمؤقّت يعيش في `pg_temp_N` ويختفي بانتهاء الجلسة، فإحصاؤه يرفع تغطية قدرةٍ على علاقةٍ لا توجد بعد `COMMIT` | `capability_mapping_engine.py` §«عقد المؤقّت والدائم» |
| استبعاد `TEMP`/`TEMPORARY` بنظرة نافية `_NOT_TEMPORARY` لا بترك النمط ضيّقاً | الاستبعاد قبلها كان **أثراً جانبيّاً**: النمط طلب `TABLE` مباشرةً بعد `CREATE` فسقط كلّ مُعدِّل. ويوم يُدعَم مُعدِّل — وقد دُعِم `UNLOGGED` في الشريحة نفسها — يعود المؤقّت **صامتاً** | `test_a_temporary_table_is_never_a_database_relation` (٧ صيغ) |
| دعم `UNLOGGED` بوصفه دائماً | يفقد **بياناته** عند انهيارٍ غير نظيف، لا **تعريفه**: مالكٌ وقيودٌ وفهارس وهجرةٌ تُنشئه، ويبقى بعد إعادة التشغيل جدولاً فارغاً لا معدوماً | `test_an_unlogged_table_is_a_permanent_relation` (أحمر قبل الإصلاح: ٣/٣) |
| تثبيت **حدّ النطاق** باختبارٍ لا بفقرةٍ وحدها | الفقرة لا تحمرّ. وتوسيعُ النطاق مشروع لكنّه يجب أن يكون **قراراً**: يحمرّ التأكيد فتُحدَّث قائمتُه وفقرةُ النطاق معاً، بدل أن يتّسع الرقم الحوكميّ بلا من يلاحظ أنّ معناه تغيّر | `test_the_declared_out_of_scope_forms_are_silent` |
| إعادة صوغ التعليق بدل تعديل الكاشف — للمرّة الثانية | مثالٌ حرفيّ على شكل DDL داخل `capability_mapping_engine.py` يُقرأ دليلَ «قاعدة بيانات» عن نفسه. الكاشف مُحقّ؛ النثر هو ما يُعاد صوغه — كما في حادثة `public` قبلها | مقيس: `db_items` على ملفّ المحرّك = `[]` |
| `assert spec is not None and spec.loader is not None` **قبل** `module_from_spec` | `spec` نفسه يكون `None` لمسارٍ غير قابل للتحميل، فيرمي `module_from_spec` خطأً خاماً عن `None` **قبل** بلوغ تأكيدٍ على `loader`. أي أنّ الترتيب السابق كان يحرس ما لا يُبلَغ | خمسة مواضع تحميل في دلتا #812 |
| نقل التأكيد **داخل `try`** في تجهيزتَي `actuator` | الأكعاب حُقِنت في `sys.modules` قبله؛ فخروجٌ من هنا بلا تنظيف يُسرِّبها — وهو **العطل نفسه** الذي يُكذِّبه `test_a_failed_load_does_not_leave_stubs_behind` | `test_manual_command_killswitch_scope.py` · `test_compensation_killswitch.py` |

## 2026-08-09 — رقعة متابعة #816: تهريبٌ عند الحدّ، وقناتان مفصولتان

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| تضعيف الاقتباس لا حذفه | `ops'role` اسمٌ **مشروع** في PostgreSQL؛ وحذفُ العلامة يُنتِج بحثاً عن دورٍ آخر **بصمت** — وهو أسوأ من الكسر لأنّه يُجيب عن سؤالٍ غير الذي طُرِح | `_sql_literal` · `test_a_role_name_reaches_psql_escaped` |
| تضييق وصف المدى: عطلُ سلامةٍ في الواجهة لا اختراقٌ قائم | CI يمرّر `sahool_app` ثابتاً؛ والادّعاء الأوسع كان سيكون أكبر من المقيس | `LIVE-PG-ROLE-NAME-ENTERS-SQL-UNESCAPED-01` |
| فصل القناتين بالبناء لا تنقية `stderr` بتعبير نمطيّ | تشخيصات libpq متعدّدة الصيغ، فقد تُسرِّب قاعدةً أو مستخدماً بعد حذف المضيف والمنفذ — ومُنقٍّ يُقرأ ضماناً وهو تخمينٌ عن صيغٍ لم تُحصَ (بنصّ المالك) | `GuardExit(raw, evidence_reason)` |
| إبقاء الخام في الاستثناء المُعاد رفعه | السجلّ هو موضع التشخيص؛ وتنقيةٌ تُعمي السجلّ تُبدِّل عطلاً بعطل | `test_a_psql_diagnostic_never_reaches_the_uploaded_evidence` |
| `UNCLASSIFIED_FAIL_CLOSED_EXIT` بدل الارتداد إلى الخام | الافتراضيّ الآمن هو الصمت عن التفصيل لا نشرُه — وإلّا صار الإصلاح مشروطاً بذاكرة كاتب المسار القادم | `test_an_unclassified_fail_closed_exit_still_leaks_nothing` |
| تأكيدُ اكتمالٍ يقرأ المصدر بـ`ast` | «صنّفتُ ما تذكّرت» ليس اكتمالاً؛ ومسارٌ سادس بـ`SystemExit` عارية كان سيمرّ صامتاً | `test_every_fail_closed_exit_in_the_guard_carries_an_evidence_reason` |
| **سحب** طفرة الاختبار البنيويّ | أسقطت اختباراً غير الذي سُمّيت له، ورفضها السجلّ. فوُصِف الاختبار بما هو: تقويةُ صياغةٍ بلا مُكذِّب مستقلّ — لا حارسٌ مُثبَت | `guard_mutation_guard` |
| حذف تأكيد «الحرف آخر الاستعلام» | واقعٌ عارض في الصياغة لا خاصّيّة أمنيّة، وتثبيتُه يُحمِّر أوّل إضافةٍ مشروعة لشرطٍ بعده | `test_an_injected_role_name_cannot_escape_its_literal` |
| تصحيح عقد اختبارٍ قائم | كان يقرأ «غير موجود» من نصّ الرسالة داخل الوثيقة — أي **يُثبِّت التسريب نفسه** | `test_a_fail_closed_environment_error_still_leaves_evidence` |
| تسجيل حادثة الدمج بنداً **مفتوحاً** لا مُغلَقاً | ما يمنع التكرار ليس هذه الرقعة: قراءةُ خيوط المراجعة قبل الدمج **غير مفروضة بأيّ حارس** | `MERGED-WHILE-A-REVIEW-WAS-IN-FLIGHT-01` |

## 2026-08-09 (ب) — مدقّقُ حماية الفرع: ما لا أملكه يصير أحمر بدل أن يصير نثراً

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| مدقّقٌ للإعداد لا بوّابةُ مراجعة | لا يوجد ما يُغلِق السباق داخل CI؛ وبوّابةٌ تقرأ الخيوط لحظةَ تشغيلها تُقرأ تغطيةً لا تملكها | `branch_protection_contract_guard.py` §المدى |
| الشبكة في الوظيفة والحكم في الحارس | يُرضي عقد `test_local_preflight_contract:83` (لا حالة GitHub في أداة) ودرسَ `resilient_docker_pull.sh` (لا منطق مدفون في `run:`) معاً | نمط `--pr-body-file` |
| بندٌ واحد لا جرد حماية عامّ | الجرد يَبيت مع كلّ تغيير مشروع فيُدرَّب قارئه على تجاهله — خطأ موصوف في `live_pg_schema_contract` | `CONTRACT_KEY` |
| `is not True` لا `if not enabled` | `"false"` نصّاً **صادقة** في بايثون؛ العقد قيمةٌ منطقيّة بعينها لا «شيءٌ يشبه الصدق» | `test_a_non_boolean_enabled_is_rejected` |
| المفتاح الغائب **رفض** لا قبول | «لم يُقرأ» ليست «مُفعَّل» — صنف «نتيجةٌ عن سؤالٍ لم يُطرَح» بعينه | `test_a_missing_key_is_not_read_as_enabled` |
| وظيفة مستقلّة لا خطوة في `capability-registry` | تحتاج سرّاً لا تحتاجه تلك، وفشلُها يقول «الحماية غير مضبوطة» لا «الحوكمة انحرفت» | `capability-governance.yml` |
| **إبقاء البند `open`** بعد الرقعة | المدقّق لا يمنع دمجاً ولا يرى خيطاً ولا يُغلِق السباق؛ إغلاقُه كان سيكون ادّعاءً أوسع من المقيس | `MERGED-WHILE-A-REVIEW-WAS-IN-FLIGHT-01` |
| تصحيح طفرة لم تزرع شيئاً | `FileNotFoundError` وريثةُ `OSError` فيلتقطها المُعالِج التالي — الطفرة كانت تُبلِغ تغطيةً لا تملكها | `guard_mutation_guard` |

- **0aede811**: Updated release package checksums and manifest to fix Lint & Format CI failure (checksum mismatch on `.github/workflows/capability-governance.yml`).

- **f4077e84**: مواءمة `#820` مع `main` بعد دمج `#821` — **الاتّحاد** في `guard_mutation_registry.json` (الجانبان إضافيّان؛ اختيارُ جانبٍ كان يحذف مواصفات طفرات حارسٍ قائم فيصير أخضرَ بلا قياس) وإعادة توليد للسبعة المولَّدة (حلٌّ يدويّ يُنتِج ملفّاً لا يطابق مولِّده فيحمرّ أوّل `--check`). ١٩ حارساً مُواصَفاً بعدها.
- **قرار: لا تليين للحارس ليخضرّ بلا تفعيل** — يجعله يُبلِغ خضرةً عن سؤالٍ لم يُطرَح، وهو الصنف الذي وُجِد ليطارده. الأحمر يبقى حتى `Enforcement=Active`؛ سببه إعدادٌ لا كود، فلا تُنتِج أيّ دفعة نتيجةً مختلفة.

## 2026-08-11 — #824 (`fc88d494`): إغلاقُ التحذيرات بالنوع، وصنفُ المرساة في الملفّ الخطأ

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| **حذف** حالة `pbCrop` لا إضافة مُنتقٍ ولا `_setPbCrop` | الحذف **حافظٌ للسلوك بالضبط** (بلا مُستدعٍ للـsetter تبقى `''` فيؤول <code>pbCrop &#124;&#124; defaultCrop</code> إلى `defaultCrop` دائماً)، وإضافة مُنتقٍ **قرار منتَج** لا تنظيف دَين، والإسكات بـ`_` يُرضي الحارس ويُبقي حالةً ميّتة ويُخفي أنّ العقد «الدليل مربوطٌ بمحصول الحقل» | `AgroAnalyticsCard.tsx` · #824 |
| تصدير `FieldData` من مصدره لا نسخةٌ ثانية | `tsc` نظيف فوراً بعد الاستبدال ⇒ العقد كان **متطابقاً** و`any` تُخفي ذلك؛ ونسخةٌ ثانية تنحرف بصمت | `AddFieldWithMap.tsx` · `FieldSetupWizard.tsx` |
| `EditablePolygon extends L.Polygon` لا `as any` ولا `eslint-disable` | التساهل يُحصَر في الحقل المجهول وحده، فيبقى الفحص النوعيّ قائماً على كلّ ما بعد النقطة بدل أن يسقط كلّه | `AddFieldWithMap.tsx` |
| راتشِت **لكلّ قاعدة** لا سقفٌ مجموع | المجموع وحده يسمح باستبدال عشرة `any` بعشرة `no-unsafe-assignment` بلا أثر؛ والرفع إلى خطأ دفعةً واحدة يوقف كلّ عمل الواجهة | `frontend_lint_debt_guard.py` |
| والنقصان بلا خفض السقف **يُحجَب** | سقفٌ يبقى بعد سدادٍ يبتلع عودة الدَّين صامتاً — والبند **حجبَ صانعه** أوّل سدادٍ حقيقيّ (٨٢ ⇒ ٧٢) فثبت أنّه ليس نظريّاً | `FRONTEND-LINT-DEBT-UNGUARDED-01` |
| **إعادة توجيه** مرساة `ui14` لا حذفها | الحذف كان سيُسقِط الحراسة بدل نقلها؛ والتوجيه أُتبِع ببندٍ ثانٍ (لا ربطَ موازياً في `App.tsx`) فصار الاختبار أشدّ لا أضعف | `test_ui14_field_workspace_route_shell_guard.py` |
| تسجيل «المرساة في الملفّ الخطأ» بنداً **مفتوحاً** لا مُغلَقاً | الحالتان أُصلِحتا، لكن **لا قياس** يسأل «هل المرساة في الملفّ الذي تعيش فيه الخاصّيّة؟» — وحالتان مستقلّتان في شريحةٍ واحدة مؤشّرُ صنفٍ لا صدفتين | `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01` |
| **عدم** تنفيذ ترقية `upload-artifact` رغم وصول مرشَّح | البند مؤجَّلٌ **بقرار مالك** (2026-08-01) ومُحفِّز إعادة فتحه («فشل حقيقيّ بدل تحذير») **لم يقع**؛ والبصمة المقترحة غير محقَّقة ونطاق الوكيل لا يقرأ المستودع الأعلى — ونقلُ بصمةٍ غير محقَّقة إلى ٢٣ موضعاً يكتب ادّعاءً غير مُثبَت | `ACTIONS-NODE20-DEPRECATION-01` |
| إعادةُ تشغيل لا تجاوزٌ لبوّابةٍ سقطت قبل `checkout` | بوّابةٌ ماتت قبل تنزيل الشجرة لا تشهد على محتواها، لكنّ دمجها بحجّة «سببها معروف» يجعل الأخضر شهادةً على النيّة لا على القياس | `release-package` · `3220b0fc` |
## 2026-08-11 — شريحة Phase 0 دُمِجت في `d3e09a60` (#825)

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| شريحة Phase 0 تحمل الأصناف الأربعة وحدها | GATE-01 غير مفتوحة و`PHASE_1_CODE_CHANGES: NOT_AUTHORIZED`؛ والكود التشغيليّ ليس أحد الأربعة | `d3e09a60` · #825 |
| المواضيع تُشتقّ من ١٤ ملفّاً مصدريّاً لا تُنتقى بالعين | إعادة البناء على **خمس قواعد** أعطت ٣٦ موضوعاً متطابقاً بايتاً بايت؛ والانتقاء اليدويّ أخطأ في ١٨ موضعاً | `d3e09a60` |
| السجلّ فئةٌ ثالثة مُعلَنة لا موضوع | طيُّه في المواضيع يجعل «subjects = N» عدداً لا يعني ما يقول، ويفتح باباً لمسارٍ محجوب | `d3e09a60` |
| تعارضات المصنوعات تُحلّ بإعادة توليد لا بحلٍّ نصّيّ | حلٌّ نصّيّ يُنتِج ملفّاً لا يُطابق مولِّده — انحرافٌ يُكتشَف بعد الالتزام | `d3e09a60` |
| `.csv` تُستثنى من `eol=lf` وتُعلَن `-text` | `csv.writer` افتراضُه `\r\n`؛ فالتثبيت كان سيفرض انحرافاً دائماً على كلّ المنصّات بما فيها CI | `d3e09a60` |
| ضبط الترميز داخل `run` لا `export` عامّ | العامّ يُبطِل خطوة ١٠ الّتي تقيس متّجه الترميز نفسه — مقيس بسقوط الاختبار معه ومروره بدونه | `d3e09a60` |
| حارسٌ لمسارات غير ASCII بدل تصحيحٍ ثالث | العطل وقع ثلاثاً على main نفسه، وكلّ تكرار يُحمِّر `preflight --full` للجميع | `d3e09a60` |
| الحزمة الفيزيائيّة (٢٣ ملفّاً) تبقى محجوبة | حكم المالك: لا دمج قبل تجميد evidence pack والقبول على SHA نهائيّ | حكم المالك |
| `WORKER-TENANT-GUC-…-01` يُسجَّل ولا يُصلَح | الملفّ في الحزمة المحجوبة؛ وقاعدة المالك «يُسجَّل ويوقف الملفّ المعنيّ» | `blocked` |
| مداخل الدماغ تُحمَل بالرقعة لا تُكتب من جديد عند إعادة التأسيس | اثنتا عشرة فجوة من أربع عشرة ضاعت لأنّها كُتِبت من جديد في كلّ جولة | `d3e09a60` |

`runtime_verified: 0` · `production_certified: 0` · `REAL/CUTOVER: BLOCKED`.

## 2026-08-11 (ب) — إغلاق سلسلة المعرفة القانونيّة إلى جدولة MPC

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| القياس **بالتشغيل** قبل قبول الحزمة | حزمةٌ تدّعي إصلاحاً تُقاس بنداءٍ حقيقيّ لا بقراءة نيّتها: بُنِي مُنتَج M2.2 ومُرِّر إلى M2.6 فأعاد `blocked` — والادّعاء صار مقيساً قبل أن يُطبَّق سطر | `KNOWLEDGE-CANONICAL-CONSUMPTION-01` |
| تسمية الحقل **سقفَ ملء** لا حدَّ حدثٍ نهائيّاً | RAW قيدُ منطقة الجذر وحدها؛ تسميتُه «أقصى حدث آمن» تجعل قيداً واحداً يُقرأ حكماً نهائيّاً بينما المعدّات والانجراف والميل والرياح قيودٌ downstream | `root_zone_refill_cap_mm` |
| `quality_status` عقداً بلا قبول `status` بديلاً | قبولُ البديل يُبقي الاسمين حيَّين فيتفرّع العقد صامتاً؛ والرفض يجعل أيّ مُنتِجٍ مخالف يُحمِرّ عند إدخاله لا بعد شهور | `test_m26_rejects_legacy_status_alias` |
| منعُ الاشتقاق من `raw_mm` عند غياب الحقل | fallback هنا يُعيد إنتاج العطل نفسه بصمت: يُنتِج رقماً معقولاً من مصدرٍ غير قانونيّ فيبدو النجاح | `test_m26_does_not_rederive_refill_cap_from_raw_mm` |
| **عدم** تسجيل طفرات للحرّاس الثلاثة | لا اختبار يُشغّلها (تُستدعى مباشرةً في `ci.yml`)، وتسجيلُ طفرةٍ باسم اختبارٍ لا يوجد يُبلِغ تغطيةً لا نملكها — والصمت أصدق من ادّعاء | `guard_mutation_registry.json` |
| إغلاق ثغرة أساس الترميز **بعددٍ لا باسم** | الأساس كان يُقارَن بمجموعات أسماء، فقراءةٌ ثالثة تُضاف إلى ملفٍّ مُدرَجٍ بقراءتين لا تُحمِر شيئاً — وقد وقع فعلاً في هذه الحزمة | `test_no_baselined_file_adds_a_new_offender_under_its_entry` |

## 2026-08-11 (ج) — #828 مدموج في `a2d07f46`

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| قراءة CI **على مستوى الخطوات** لا الوظائف | وظيفةٌ `in_progress · conclusion: null` وخطواتها مكتملة وفيها فشل — لم تُحتسَب فاشلة ولا ناجحة فسقطت من العدّ؛ وثبت أنّها منهجيّة لا حادثة | `JOB-STATUS-HID-A-FAILED-STEP-01` |
| إعادة اشتقاق `Capability-Impact` بعد **كلّ** تعديل | الإعلان صار كاذباً دون أن يتغيّر فيه حرف حين وسّع `ci.yml` الأثر — فهو دالّةٌ في الـdiff لا خاصّيّةٌ للـPR | `missing_direct: [OPS-004, SOIL-001]` |
| إعلان الـ**٢٩** (`affected`) لا الـ١١ (`direct`) | كلاهما يمرّ، والأوسع لا يُخفي شيئاً؛ وإعلانٌ أضيق ممّا قِيس هو الدَّين نفسه بصورة أصغر | `decision: PASS` |
| `--check` مستقلّاً **بعد** كلّ `--fix` | `--fix` أعلن الاتّساق بـ`rc=0` وترك `capability_mapping` منحرفاً؛ وعدّ الدورات ليس الفارق — الفارق أنّ التحقّق من خارج الأداة | `VERIFY-ALL-GENERATED-FIX-GREEN-IS-NOT-A-CHECK-01` |
| حلّ تعارض المصنوعات بـ`--theirs` ⇒ **توليد** ⇒ `add` | العكس يُثبِّت دمجاً نصّيّاً لملفّاتٍ لا تُدمَج نصّيّاً؛ والترتيب صنفُ فشلٍ مُسجَّل في §٢ | تسعة مصنوعات بعد `ad4510db` |
| إعادة بناء حزمة الإصدار عند تعديل **ملفّ اختبار** | الحزمة تبصم ملفّات المصدر ومنها الاختبارات — أُهمِل ذلك فاحمرّت خمسة فحوص جذرها واحد | `checksum mismatch: tests_v9/…` |
| غيابُ ملفّ رواية **فشلٌ** لا تخطٍّ | التخطّي كان يجعل أرخص طريقة لإسكات الحارس **حذفَ ما يقيسه**، وتمهيده يدّعي الفشل المغلق | `DELETING-A-JOURNAL-FILE-SILENCED-ITS-OWN-GUARD-01` |
| طباعة مخرجات git **قبل** الترجيح في رسائل الفشل | الزرعان كذّبا ترجيحي: `Not a valid object name origin/main` لا عمق، و`path … exists on disk, but not in <ref>` لا كائن مفقود | `FAILURE-MESSAGE-ASSERTED-A-CAUSE-IT-NEVER-MEASURED-01` |
| **عدم** بناء حارس ضدّ سوء قراءة حالة الوظيفة | لا شيء في CI يمنع تكراره؛ والإصلاح إجرائيّ ومُسجَّل — وتسجيلُه أصدق من ادّعاء سدّه | حدٌّ مُعلَن |

`runtime_verified: 0` · `production_certified: 0` · `REAL/CUTOVER: BLOCKED` · الحزمة الفيزيائيّة (٢٣ ملفّاً) محجوبة.
### SoT provenance simplification — P0 accepted with conditions

- القرار: Manifest حتمي واحد + GitHub/Sigstore attestation قائمة + verifier واحد fail-closed + gate واحدة.
- العدّ المرجعي مشتق من manifest، وليس من تقرير 23/25.
- الـmanifest subject موقّع مباشرة؛ لا self-hash دائري.
- PR synthetic merge يُربط بالشجرة، ولا يساوي SHA الإصدار النهائي افتراضاً؛ main/release يعيد البوابة.
- Rekor outage وقت التحقق لا يحجب إذا bundle + trusted roots تتحقق offline.
- assurance مشتق L0..L5؛ لا boolean يكتبه caller.
- CUTOVER/REAL يبقيان BLOCKED؛ هذا القرار يثبت هوية الأدلة ولا يثبت صحة v228 التشغيلية.


## 2026-08-11 (ج) — بوّابة المنشأ مدموجة، وطبقةُ المعرفة تبدأ بأصغر شريحةٍ تُثبِت نفسها

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| دمج بوّابة SoT بـ**١١/١١ طفرة** لا ٨ | ثلاث ملاحظات مراجعةٍ على حدود التنفيذ أُضيفت لها طفرات: إغلاقٌ يُعلَن ولا يُفحَص · خطأٌ في البيان يُبلَّغ عطباً في المُصادِق · بيانٌ يناقض نفسه. والمُصادِق لا يجوز أن يفترض أنّ البيان جاء من الأداة الرسميّة | `c56a7b8f` |
| المطابقة المتقاطعة تُفرَض في **الطرفين** لا في الأداة وحدها | أداةٌ تفرض والمُصادِق يثق = إنفاذٌ في مكانٍ واحد؛ ومن يكتب بياناً بيده يتخطّاه. الازدواج هنا ليس تكراراً بل استقلالاً | `c56a7b8f` |
| نزعُ `tested_merge_to_release` بدل تنفيذه | خيارٌ يَعِد بضمانٍ لا يُمنَح أسوأ من غيابه؛ ودليلُ ربطِ الدمج بالإصدار قرارُ تصميمٍ حقيقيّ لا حقلٌ يُخترَع لإسكات فرعٍ ميّت | `c56a7b8f` |
| السجلّ المعرفيّ **بياناتٌ محكَّمة** في `docs/architecture/` لا قاموساً في `.py` | قاموسٌ في كود يفلت من `claim_base_guard` و`manifest_registry_guard` معاً — فيتسلّل قرارُ ثقةٍ في مراجعة كود. وموضعه هناك يجعله يحمل `adjudicated_on` ويُحاسَب عليه | `knowledge_source_registry.json` |
| تصنيفه `decided` لا `measured` | أيُّ وحدةٍ هي مصدر الحقيقة لمفتاحٍ ما **حكمٌ معماريّ** يتّخذه إنسان؛ ولا ماسح يشتقّه من الشجرة. والقياس يَبيت بحركة الشجرة والقرار لا يَبيت بها | `claim_base_registry.json` |
| `dataclass` لا `BaseModel` في طبقة المعرفة | جيرانُها المباشرون (`canonical_*`) كلّهم `frozen dataclass`؛ وطبقةُ ربطٍ تُخالِف أسلوب ما تربطه تضيف ترجمةً عند كلّ حدّ | `shared/knowledge/contracts.py` |
| `require()` **ترفع** ولا تُرجِع `None` | الإرجاع الصامت هو ما يدفع المستهلك إلى `value or fallback` — أي الالتفاف الذي تمنعه الشريحة نفسها. فالطبقتان تحرسان الشيء ذاته من طرفيه: المُحلِّل عند التشغيل والحارس عند الترجمة | `shared/knowledge/contracts.py` |
| توسيع الكشف بدل حذف الفرع الميّت | الطفرة كشفت أنّ فرع `ast.Dict` لا يفعل شيئاً؛ وحذفُه كان يُصحّح المواصفة ويُبقي العمى عن `d[F]` و`read_field(d, F)`. التوسيع جعل الفرع حاملاً وزاد ما يراه الحارس | `canonical_consumer_bypass_guard.py` |
| **عدم** إعلان `field.geometry` و`weather.et0` في العقد الآن | متطلَّبٌ يُعلَن بلا مُنتِجٍ مُسجَّل ومستهلِكٍ مقيس يُنتِج عقداً يبدو أشمل ولا يفرض شيئاً — وهو «الطبقة المعماريّة التجميليّة» التي تستثنيها الشريحة صراحةً | `shared/knowledge/irrigation_context.py` |
| **عدم** البدء بـ`relation_registry` | آخِر الترتيب المُعلَن؛ والبدء به قبل أن يُثبِت الحارسُ الأوّل نفسه يبني علاقاتٍ فوق استهلاكٍ غير محروس | — |

## 2026-08-12 — إتمام طبقة المعرفة: التبنّي أوّلاً، والعلاقة آخِراً

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| تقديم **التبنّي** على توحيد النَّسَب | توحيدُ النَّسَب يغيّر عقود خدماتٍ قائمة؛ وفعلُه قبل أن يستهلكه أحد يوسّع سطحاً لا قارئ له. والربطُ كشف بالتشغيل أيّ الحقول مطلوبةٌ حقّاً | `35fc67cc` |
| **انقسام** `maximum_safe_depth_mm_event` إلى مفتاحين | الرسم البيانيّ يُنتِج حدّاً أضيق يجمع قيد المعدّات؛ فنسبةُ ما يستهلكه المُجدوِل إلى قدرة الرشّ نَسَبٌ كاذب، ومفتاحٌ بمُنتِجَين هو المصدر الظلّ بعينه | `35fc67cc` |
| عقدٌ **لكلّ مهمّة** لا عقدٌ للمجال | العقد الموحَّد كان يحجب كلّ توصية لأنّ المُنسِّق لا يجلب مِلَفَّ منطقة الجذر — وهو ما لا يظهر إلّا ساعةَ الوصل | `35fc67cc` |
| `consumers` = القرّاء المباشرون وحدهم | القائمة تعني سطحَ الالتفاف؛ ومن يستهلك عبر العقد لا يمسّ الحقل فلا يلتفّ عليه. والعقد يسجّل التبعيّة | `35fc67cc` |
| `producer_digest_field` **مُعلَنٌ إلزاماً** | أوّل صياغةٍ افترضت `capability_digest` فأطلقت على مِلَفّ منطقة الجذر وبصمتُه `profile_digest`. بصمةٌ تُخمَّن ليست بصمة | `2ba96027` |
| المرساة الزمنيّة **شرطٌ لا زينة** | بلا `generated_at` يبقى بند الطزاجة في المُحلِّل معطَّلاً بصمت: كلّ عقدٍ يُعلِن `max_age_seconds` يحجب دائماً | `2ba96027` |
| تعريف «الحقيقة التشغيليّة» = ما له مفتاحٌ في السجلّ | حدُّ الاسترجاع يتّسع بالسجلّ ولا يحتاج قائمةً ثانية تَبيت وحدها | `rag_operational_boundary_guard.py` |
| مطابقةُ **احتواء** لا تساوٍ في حدّ الاسترجاع | الحالة الواقعيّة الخطيرة قالبُ سؤالٍ يذكر الحقيقة داخل جملة، لا سلسلةٌ تساوي الاسم. والتساوي جعل استثناء التوثيق كوداً ميّتاً | `rag_operational_boundary_guard.py` |
| تسجيل علاقةٍ **قائمة** لا اختراع أخرى | `REQUIRED_LINKS` تحكم فعلاً «أضعف حلقة» و`operational_eligible`؛ وتسجيلُ علاقاتٍ لا ينفّذها شيء يُنتِج رسماً بلا أثر | `knowledge_relation_registry.json` |
| ربطُ السلسلة المُسجَّلة بالثابت المُنفَّذ | هذا هو الفرق عن Ontology تقليديّة: ثلاثيّةٌ تُكتَب مرّةً وتَبيت بصمت مقابل سلسلةٍ يُحمِرّ انحرافُها | `knowledge_relation_registry_guard.py` |

## 2026-08-12 — معالجة الثلاثة الحاجبة لـ`real/cutover`

| القرار | السبب (rationale) | المصدر |
|---|---|---|
| رفعُ الحجر عن حزمة الـkillswitch | أمر المالك صراحةً بعد إبداء التحفّظ وإعادته — القرار قراره لا قراري | «عالج الثلاثة الحاجبة» |
| استشارة المفتاح **لكلّ جهاز** في التعويض | مفتاح صمّامٍ واحد يحجبه وحده ولا يُوقف تعويض البقيّة؛ واستشارةٌ واحدة للدفعة تخلط قرارين | `test_each_device_in_the_batch_is_consulted_separately` |
| `blocked` لا `failed` للمحجوب | الحجب قرارُ سلامة، وتسميتُه فشلاً تُغري بإعادة المحاولة | `test_a_blocked_compensation_is_recorded_as_blocked_not_failed` |
| `field_id` من **نفس** استعلام المُصرِّح | إعادة استعمال لا استعلام ثانٍ؛ والاستعلام قائم أصلاً لفحص الملكيّة | `_authorize_device_control` |
| قياس نطاق الـGUC بـAST لا بـregex | الاحتواء داخل معاملة سؤالٌ عن **البنية**، ولا يُجاب بمطابقة سطريّة | `tenant_guc_scope_guard.py` |
| الترسية على **وسائط الاستدعاء** | أوّل صيغة التقطت شرح الحارس نفسه مخالفةً — ملفٌّ يصف عيباً ليس ملفّاً يرتكبه | طفرة مستقلّة |
| **عدم** توحيد أسماء الـGUC آليّاً | التوحيد يكسر سياسات RLS التي تقرأ الاسم الآخر — تُجرَد ويبقى القرار بشريّاً | ٤ أسماء مرصودة |
| `_REVEALED_SCOPE_DEBT` منفصلاً عن الـallowlist | الأوّل يقول «عيبٌ قائم»، والثاني «صحيحٌ ولهذا السبب» — خلطُهما يُحوّل عطلاً إلى تبرير، وهو ما فعله المُصنِّف القديم | ٧ استعلامات مكشوفة |
| **عدم** إصلاح الـ٣٥ والـ٧ | قاعدة المالك: «يُسجَّل ويوقف الملفّ المعنيّ؛ لا يُصلَح ضمن الشريحة»؛ ومسارات لم تُقَس حيّاً | حدّ مُعلَن |

`runtime_verified: 0` · `production_certified: 0` · الحزمة الفيزيائيّة (٢٣ ملفّاً) محجوبة.

## 2026-08-12 (ج) — قرارات مراجعةِ main و#835 وإصلاح الترخيص الميّت

| القرار | السبب | الأثر |
|---|---|---|
| علاج العمى في **الكشف** لا بنزع الاستثناء | نزعُه وحده يجعل الحارس يتّهم `_compensate` بالإطلاق بلا مفتاح **وهي تستشيره** — تصحيحٌ يُنتِج كذباً معاكساً | `1ea13f72`+ |
| قبولُ **مستوىً واحد** من المَفصِل، وإعلانُ الحدّ باختبارين | تتبُّعُ عمقٍ عشوائيّ يقتضي رسمَ نداءٍ كاملاً؛ وحارسٌ يزعم ما لا يقيس أسوأ من حارسٍ يُعلِن حدّه | سلسلةٌ ومَفصِلٌ مستورَد يُرصدان `uncovered` |
| **عدم** سدّ «تستشير ولا تحجب» | خاصّيّةُ التصميم الأصليّ، ولم أقِس لها حادثة — وحارسٌ بلا عطلٍ مقيس يُضخّم العدد ولا يزيد تغطية | حدّ مكتوب |
| التكذيب على **الشجرة الحقيقيّة** لا بمعطيات مُركَّبة وحدها | الإنفاذ العكسيّ كان مُختبَراً بمعطيات ذات استدعاء مباشر، فمرّ أخضر وأخفق على أوّل رقعة حقيقيّة | طفرتان ⇒ ٢٩/١٧٧ |
| رفضُ تسمية «٣٩ إخفاقاً» أساساً في #835 | المقيس ٠ على main و٠ على رأسها؛ وتسميةُ فشلٍ بيئيّ أساساً تُرخّص لانحدارٍ حقيقيّ لاحقاً | ملاحظةٌ على المتن لا على الكود |
| **عدم** الالتزام في الشجرة الأصليّة رغم إلحاح الخطّاف | قِيست ثلاثاً: إمّا مطابقةٌ لـmain أو خلفها بـ٢٤٢٠ سطراً؛ والدفع يقتضي `--force` فوق عملي | لا فقد |

`runtime_verified: 0` · `production_certified: 0` · REAL/CUTOVER: BLOCKED باقٍ.
- **`f2202191` (بلا التزام جديد على المسار المحجوب) — أُرجِعت رقعة `A1`/`A2` (`M-01`/`M-02`) بعد تنفيذها، للمرّة الثانية في هذا المستودع.** السبب: `GATE-01-EXECUTION-CONTROL-SLICE-WITHHELD-01` حكمُ مالكٍ مُسجَّل (2026-08-09) يحمل `PHASE_0_EVIDENCE_FREEZE: NOT_PROVEN` و`PHASE_1_CODE_CHANGES: NOT_AUTHORIZED`، ونصُّه «لا تُدمَج حتّى تجميد evidence pack وقبولها **صراحةً** على SHA نهائيّ»؛ و`services/actuator-service/actuator_runtime.py` و`services/actuator-service/routers/commands.py` مُسمَّيان ضمن الـ٢٣ ملفّاً المحجوبة. أُرجِعت الملفّات الثلاثة (مع `scripts/ci/actuation_killswitch_coverage_guard.py`) إلى `f2202191` بايتاً — `git diff` عليها فارغ — والرقعة محفوظة خارج المستودع. **ولم يُفتَح الحجب من طرفي:** لا ملفّ في الشجرة يحمل `frozen_commit_sha` (الحزمة خارجها)، فادّعاء التجميد كان سيكون اصطناع دليل تشغيليّ. **واعتراضٌ مُسجَّل غير منفَّذ:** عقد `test_compensation_killswitch.py` يمنع إرسال العكس **المُهدِّئ** (`close`/`off`/`stop`) تحت المفتاح، وهو الاتّجاه الذي يريده الإيقاف نفسه؛ يُعرَض على المالك ولا يُغيَّر اجتهاداً.


## 2026-08-13 (ب) — قسمٌ سلوكيّ في سجلّ الطفرات، منفصلٌ عن قسم الحرّاس

- **القرار:** يُضاف إلى `guard_mutation_registry.json` قسمٌ `behavioural` مفاتيحه **مسارات مصادر إنتاج**، منفصلٌ عن `mutated` لا مدموجٌ فيه.
- **السبب:** القسمان يُكذِّبان شيئين مختلفين — `mutated` يسأل «هل يُطلِق هذا الحارس على عطلٍ مزروع فيه؟»، و`behavioural` يسأل «هل يمنع هذا المسار الأثر الفيزيائيّ فعلاً؟». ودمجُهما كان سيخلط جردَ الحرّاس بجرد المصادر ويُفسِد حساب `unmutated_debt` (الذي يُقاس على جرد `scripts/ci` وحده). والصرامة واحدة: سلسلةٌ فريدة في المصدر، و`expect` يسمّي اختباراً موجوداً — عبر `_spec_failures` المشتركة.
- **وقرارٌ ثانٍ:** `test` يجوز أن يُعلَن **على مستوى الطفرة** لا المواصفة. السبب مقيس: `actuator_runtime.py` تُقاس بجناحين — التعويض في `test_compensation_killswitch.py` والتصريح في `test_manual_command_killswitch_scope.py`. وإلزامُ جناحٍ واحد كان يدفع اختباراً إلى ملفٍّ لا يخصّه أو يُسقِط الطفرة؛ وكلاهما يُنقِص القياس لأجل شكل السجلّ.
- **وقرارٌ ثالث:** لا تُكتَب اختبارات جديدة حيث توجد أجنحةٌ سلوكيّة قائمة. المقيس أنّ أجنحة التعويض والمُصرِّح كانت تغطّي فعلاً، والناقص تسجيلُها وزرعُ العطل — فكتابةُ جناحٍ موازٍ كانت ستُضاعِف الصيانة وتُوهِم بتغطيةٍ جديدة. أُضيف جناحٌ للراوتر وحده لأنّه كان مقيساً نصّيّاً بإقرار وثيقته.
- **النطاق:** المساران هما بعينهما ما أذن به `GATE01-ADJ-2026-08-13-001` — لا توسيع. و`GATE-01` تبقى مغلقة، والتفويض `CONSUMED`، و`REAL/CUTOVER: BLOCKED`.
- **المرجع:** `docs/architecture/guard_mutation_registry.json` · `scripts/ci/guard_mutation_guard.py` · `tests_v9/test_actuation_killswitch_behaviour.py` · الفجوة `STATIC-GUARD-MEASURES-OCCURRENCE-NOT-EFFECT-01`.


## 2026-08-13 (ج) — الحمايةُ المتناسبة: بندٌ مشروط لا بندٌ دائم

- **القرار:** بندُ `require_code_owner_review` في `branch_protection_contract_guard` يُفرَض **حين تمسّ الـPR مسار التفويضات وحدها**، لا على كلّ دمج.
- **السبب:** الإغلاق الكامل للفجوة يحتاج إعدادَ مستودعٍ لا يملكه وكيل. وبندٌ دائم كان سيحجب **كلّ** دمجٍ في المستودع حتّى يُفعَّل — وحمايةٌ تُوقِف العمل كلّه تُطفَأ، فتُنتِج حمايةً صفراً. فالحجب يقع على **الفعل الذي يحتاج الحماية**: إصدارُ تفويضٍ لـGATE-01. وطفرةٌ مُسجَّلة تُكذِّب جعلَه دائماً، فالتناسب مقيسٌ لا نيّة.
- **وقرارٌ ثانٍ — القياس بالإشعال لا بالنصّ:** `guard_locale_survival_guard` **يُشغّل** كلّ حارس ولا يبحث عن `reconfigure` في مصدره. السبب مقيس: السطر قد يقع بعد أوّل طباعة فلا ينفع، وقد يغيب عن حارسٍ لا يطبع إلّا ASCII فلا يضرّ. وثمنُه ثمانون ثانية، ومقابلُه أنّ أخضره يعني ما يقوله.
- **وقرارٌ ثالث — فصلُ القلب عن العلامة في محارف الاتّجاه:** حظرٌ شامل يُكذَّب أوّل مرّة (٣٥٠ محرفاً مشروعاً)، وأساسٌ شامل يُرخّص الهجوم. فالقالبات تُحجَب مطلقاً والعلامات بأساسٍ يتقلّص — وطفرةٌ تُكذِّب كلّ فرع.
- **المرجع:** `scripts/ci/guard_locale_survival_guard.py` · `scripts/ci/bidi_control_char_guard.py` · `.github/CODEOWNERS` · `scripts/ci/branch_protection_contract_guard.py`.


## 2026-08-13 (د) — فصلُ `provenance_verified` عن `certification_accepted`

- **القرار:** سُلَّم الضمان لا يرتقي إلى L4/L5 إلّا بخلاصة تشغيلٍ ناجحة مُعلَنة ومربوطة بالالتزام المُختبَر — لا بحكم المصنوعات وحده.
- **السبب:** الشهادة تُثبِت **من قال ماذا وعن أيّ بايتات**، ولا تُثبِت أنّ اللقطة اجتازت البوّابة. وحزمةٌ صحيحة تشفيريّاً بالكامل خرجت من تشغيلٍ خلاصتُه `failure` — مقيسة لا مفترضة.
- **وقرارٌ ثانٍ — المفتاح معطَّل ومُعلَن لا مفروضٌ اليوم:** المُنتِج (وظيفةٌ داخل التشغيل) لا يملك خلاصة تشغيله. وفرضُ ما لا يُنتَج يُحمِّر `main` على غياب أداة لا على عطل. فالقاعدة تُكتَب وتُكذَّب الآن، وتُفرَض حين يوجد مُنتِجها — ويُسجَّل الدَّين في كلّ سجلّ تحقّق حتّى ذلك الحين.
- **المرجع:** `scripts/ci/sot_provenance_guard.py` · `docs/architecture/sot_provenance_policy.json` · الفجوة `ATTESTED-IS-NOT-CERTIFIED-01`.


## 2026-08-13 (هـ) — خلاصةُ التشغيل وثيقةٌ مستقلّة لا حقلٌ في البيان الموقَّع

- **القرار:** `execution_outcome` ملفٌّ منفصل يُسلَّم للحارس بـ`--execution-outcome`، والرابطُ بالبيان هو الالتزام المُختبَر.
- **السبب — وهو إلزامٌ لا تفضيل:** البيان من الموضوعات الموقَّعة، فتعديلُه بعد التوقيع يكسر التحقّق. أوّل تصميم لي وضع الحقل داخله، وكان غير قابل للتنفيذ.
- **وقرارٌ ثانٍ:** `--require-execution-outcome` راية على مستوى الاستدعاء لا مفتاح سياسة عالميّ — لأنّ الاستدعاء **داخل** CI لا يستطيع الشرط، والاستدعاء **بعده** يستطيعه. ومفتاحُ السياسة يبقى للقلب العالميّ متى صارت كلّ الاستدعاءات لاحقة.
- **المرجع:** `scripts/ci/run_outcome_guard.py` · `.github/workflows/certify-run.yml` · `scripts/ci/sot_provenance_guard.py`.
## 2026-08-13 (ب) — قرارات إغلاق دورة حياة تفويض GATE-01

| القرار | السبب | الأثر |
|---|---|---|
| ختمُ التفويض **إجراءٌ بشريّ**، والحارس يرصد التخلّف عنه فقط | حارسٌ يكتب `ISSUED`→`CONSUMED` أثناء CI يصير طرفاً في القرار الذي يحكم فيه؛ والقراءة وحدها تكفي للكشف | `stale_authorization_errors` نقيّة، ولا كتابة في `main()` |
| المُميِّز = «الـdiff لا يلمس المسارات المأذونة» لا تطابقُ البايتات | التطابق حاصلٌ **بالضرورة** أثناء الـPR المأذونة، فالبناء عليه وحده يتّهم الاستعمال المشروع | `test_an_authorization_in_flight_on_its_own_paths_is_not_flagged` |
| الاشتقاق من **الشجرة** لا سؤالُ GitHub «أمدموجةٌ الـPR؟» | عقد المستودع: حالة GitHub تُقاس في الوظيفة ولا تدخل أداةً؛ والبديل يعمل محلّيّاً بلا شبكة | الحارس يُشغَّل في أيّ بيئة |
| تشغيل الفحص **دائماً** لا عند مسّ مجمَّد | التفويض البائت لا يُكتشَف بالمسّ بل بمرور الزمن عليه؛ ربطُه بالمسّ يُبقيه صامتاً إلى أوان استعماله — وهو الأوان الذي وُجِد ليسبقه | طفرةٌ على الوصل نفسه |
| إعادة كتابة اختبارٍ كان يحرس العطل | `..._is_permitted_only_by_an_exact_authorization` يؤكّد أنّ المُنفَق يمنح PASS — الفجوة كانت مكتوبةً في اختبار لا شيفرة | `test_the_live_authorization_is_spent_and_no_longer_grants` |
| **عدم** إبطال التفويض تلقائيّاً عند رصد التخلّف | الإبطال قرار مالك؛ والحارس يقول «اختمه» ولا يختم نيابةً عنه | حدّ مُعلَن في الرسالة |

`runtime_verified: 0` · `production_certified: 0` · **GATE-01: CLOSED** · تفويضات حيّة: ٠.

## 2026-08-13 (ج) — قرارات `BRAIN-CLAIM-GUARD-CONFLATES-ADJUDICATION-WITH-GAP-01`

| القرار | السبب | الأثر |
|---|---|---|
| تحقّقُ التفويض في مجلَّده لا استثناؤه كالاستشارة | مصدر الاستشارة خارج الشجرة فيُضطَرّ للاستثناء؛ والتفويض مِلفٌّ هنا فيُقاس — والمبدأ «الذكر ادّعاء» يبقى قائماً | معرّف تفويضٍ ملفَّق يبقى ساقطاً |
| الشكل الكامل لا البادئة | `^GATE` كان سيبتلع `GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01` — نفس فخّ `startswith("CVE-")` | `test_the_adjudication_class_did_not_swallow_real_gap_ids` |
| إخراج الحارس من الدَّين عند تعديله | من يمسّ حارساً «لم تُقَس تغطيته» أولى الناس بقياسها — وإلّا نما الدَّين بالتعديل | ٣٢ حارساً / ٢٠٦ طفرة · الدَّين ١١٥ ⇐ ١١٤ |

## 2026-08-13 (د) — قرارات مراجعة #840

| القرار | السبب | الأثر |
|---|---|---|
| رفضُ `one_time: false` بدل استثنائه من فحص دورة الحياة | الوضع **غير منفَّذ** (لا عدّاد استعمالات ولا نطاق ولا سقف، ولم يقرأ الحقلَ سطرٌ قبل هذه الرقعة)؛ واستثناؤه يجعل حقلاً إعلانيّاً يُسكِت الفحص — بابَ تجاوزٍ ذاتيّ الخدمة يُعيد الفجوة | `test_a_reusable_authorization_is_refused_as_an_unimplemented_mode` + طفرة |
| التمييز بين **غياب** الحقل و**التصريح** بـfalse | الغياب هو الافتراض القائم (لمرّةٍ واحدة) فلا تُكسَر التفويضات القائمة؛ والتصريح ادّعاءُ وضعٍ لا وجود له ⇒ فشلٌ مغلق | `adj.get("one_time") is False` لا `not adj.get("one_time")` |
| نزعُ علامات الاتّجاه (RLM) من مصدر الحارس | محرفٌ غير مرئيّ في **نصٍّ يُطبَع في سجلّات CI** يُخفي ما يقرؤه الإنسان؛ نُزِعت من الرسالة الجديدة ومن سطرٍ سابق في نفس الملفّ ⇒ صفر في الملفّ | `[pr=…]` بدل `(PR …)` |

## 2026-08-13 (هـ) — قرارات تشديد مِعيار الحكم في آليّة الطفرات

| القرار | السبب | الأثر |
|---|---|---|
| القرار من `failing_tests(out)` لا من النصّ الخام | «سقط المُسمّى» هو العقد المعلَن، والبحث النصّيّ يقبل اسماً في رسالةٍ أو تتبُّع مكدّس | `_outcome` + مسار الحجب |
| تصحيح **الموضعين** لا `_outcome` وحده | مسار الحجب يحمل نسخةً ثانية من الحكم — دالّةٌ صحيحة لا تحكم خضرةٌ عن سؤالٍ لم يُطرَح | طفرتان مستقلّتان |
| الطفرة تُعيد الصيغة القديمة لا `if False:` | السؤال «أيّ مصدرٍ يقرأ» لا «أيفحص أم لا»؛ و`if False:` كانت ستقيس شيئاً آخر | `in observed` ⇐ `in out` |
| تشغيل `--run` **كاملاً** بعد التشديد | مِعيارٌ أشدّ قد يقلب حكم طفرةٍ قائمة — والادّعاء بلا قياس هو العطل نفسه | ٢٠٩/٢٠٩ خضراء |

`runtime_verified: 0` · `production_certified: 0` · **GATE-01: CLOSED** · ٣٢ حارساً / ٢٠٩ طفرة · الدَّين ١١٤.

## 2026-08-16 — ربط «latest» بيوم المشهد

| القرار | السبب | الأثر |
|---|---|---|
| **عدم** توسيع نافذة التاريخ التاريخيّ رغم توصية السجلّ | تواريخ الشريط اكتسابات حقيقيّة؛ التوسيع يعرض مشهد يومٍ آخر تحت التاريخ المختار — تلويثُ مصدر لا إصلاح | السجلّ صُحِّح بدل أن يُنفَّذ |
| الربط يفشل **مفتوحاً** لا مغلقاً | تحسينُ صدقٍ لا شرطُ صلاحيّة؛ الإغلاق يحوّل عطلاً في التسمية إلى بلاطة مفقودة | `except` ⇒ النافذة كما جاءت |
| الربط **بعد** فحص الكاش لا قبله | قبله نداءٌ شبكيّ على كلّ إصابة كاش | مرّة لكلّ ملء |
| `day_window` تُرفَع لا تُنسَخ | سلطتان على معنى «اليوم» تنحرفان بصمت | `raster_date_geo.day_window` |
| الاختبار في `tests_v9/` بلا `rasterio` | `services/raster-service/test_*.py` خارج `testpaths` ⇒ سُبات صامت | ١٢ حالة تعمل في البوّابة |
| `MAX_CLOUD_PCT` ثابتٌ واحد للبحث والمعالجة | سقفان مختلفان يربطان بيوم مشهدٍ ترفضه المعالجة ⇒ فراغٌ حيث كانت صورة | اختبار يقارن السقفين |

## 2026-08-16 (ب) — فصل سلطتَي الاختيار

| القرار | السبب | الأثر |
|---|---|---|
| `LATEST_ACCEPTABLE` لا تُنفَّذ بـ`rank_scenes` | ٠٫٥٠ سحاب مقابل ٠٫٢٠ حداثة ⇒ الأقدم الأنظف يهزم الأحدث؛ جوابٌ صحيح لسؤال آخر | منتقٍ مستقلّ |
| منتقٍ **واحد** للمسارين | إصلاح الحيّ وحده يُعيد التناقض من جهة الشريط الزمنيّ | `select_scene` في كليهما |
| الاستجواب من الأحدث إلى الأقدم | سقف الصفحات + ترتيب مزوّد غير موثَّق ⇒ الترقيم وحده لا يُثبِت «الأحدث» | `backward_probe_windows` |
| `SelectedScene` لا `tuple` | الـ`tuple` تفقد `scene_id` والغيوم ومصدرها عند الحدّ | إيصال قابل للنشر |
| قبول مجهول الغيوم | سياسة `_apply_cloud_filter` القائمة بقرار مالك؛ الرفض يُنشئ سلطة أهليّة ثانية | `cloud_source="unknown"` |
| رفض `mosaickingOrder` المجهول | المزوّد قد يتجاهله فيعود لافتراضه ⇒ دلالةٌ غير مطلوبة بلا إشارة | `ValueError` |
| تأجيل الترويسات وهويّة الكاش وإغلاق fail-open | أثرُها عرض/كلفة/توافريّة لا اختيارٌ خاطئ | مُعلَنة في السجلّ |

### 2026-08-18 — #870 (C2rem+C3) → `010c9627`، ودمج #869 (`08d135a3`)

| القرار | السبب | الأثر / الشاهد |
|---|---|---|
| حلّ التعارض بإعادة التوليد لا باليد | العشرة **كلّها مصنوعات مولَّدة**؛ الدمج اليدويّ لملفّ مشتقّ يُنتج نقطة ثبات بائتة | `77235a02` — ٧١ خطوة `--check` خضراء · ٥٥٣٤ بصمة |
| رفض الدمج القصريّ | القصر يتخطّى **بعينها** بوّابات انحراف المصنوعات — الحارس الوحيد لهذا الصنف؛ ولا يوفّر وقتاً (الكلفة في `Unit Tests`) | `010c9627` دُمج بالبوّابات كاملةً |
| أساس وحدات المنصّة 681→683 | وحدتا C3 مقصودتان لا انحرافاً | `c3_precision_execution_note` |
| استثناء راتشِت S5 واحد لا اثنين | الحارس رفض الثاني بإنفاذه العكسيّ — الاستثناء غير الضروريّ **يُرفَض** | `yield_map_processing` وحدها، `target_close_by: 2026-11-30` |
| تطبيع بصمة الإعادة | C3 وسّعت `PrescriptionZone` بحقلين اختياريّين ⇒ صفوف ما-قبل-C3 تُقرأ 409 كاذباً (مقيس) | إسقاط القيم الفارغة من الجهتين قبل الهضم |
| `canonical_field_state` بنصّ العقد | إرفاقُها مع `canonical=false` يناقض معامل الاستعلام ويُضخّم الحمولة | `if canonical or twin` |
| تطبيع الوحدات غير حسّاس للحالة | `KG_HA` كان يفلت من القاموس فيُخزَّن غير قانونيّ | `unit.lower()` قبل القاموس |
| لا تُسجَّل طفرةٌ لدَين لا يُكذَّب | طفرة بلا اختبار يحمرّ في **كلّ** بيئة تصير صمتاً لا تكذيباً (`STABLE_WRONG_TEST`) | يُعلَن دَيناً لا طفرةً |

### 2026-08-18 (ج) — تطبيق دلتا S5+C4+JAIS (`fc7965f4…`، قاعدة `010c9627` مطابقة)

| القرار | السبب | الأثر / الشاهد |
|---|---|---|
| تطبيق الدلتا كاملةً بعد التحقّق | `baseline_sha` مطابق حرفيّاً (التزاماً وشجرةً) + `PAYLOAD_SHA256SUMS.txt` تحقّق ذاتيّ + غياب الراوترين الحسّاسين من الحمولة | ١٤٠ ملفّاً: ٤١ إضافة، ٩٣ تعديل، ٦ حذف |
| وصل `s4_kg_consumer_freeze.py`/`s5_exec_01_edge_freeze.py` بـci.yml | مولّدان يدعمان `--check` بلا تصنيف ولا وصل — دَينٌ حقيقيّ لا استثناء مشروع | خطوتان جديدتان + إدخال في `_GENERATE_FLAG` |
| إكمال `shared/ai/provider_contract.py` بمدخلات vLLM | العقد القانونيّ الوحيد غائبٌ من الدلتا رغم أنّ الشريكين عُدِّلا — الحارس يفرض التطابق الثلاثيّ | `PROVIDER_ALIASES`+`CANONICAL_PROVIDERS`+`WIRE_FORMAT`+`ENV_VLLM_*`+`DEFAULT_CATALOG["vllm"]` |
| إصلاح اختبار v167 لا ارتداد `persistence.py` | اختبار جديد (`test_s5_exec_01_decision_record_immutable.py`) يفرض `DO UPDATE SET not in body` صراحةً — تصميمٌ متعمَّد لا خطأ | تحديث الاختبار القديم ليطابق نموذج الإلحاق غير القابل للتغيير |
| `measured_on` داخل `build()` لا خارجه | إلصاقه خارجاً كسر مطابقة `stored == generated` الذاتيّة — عطل ميكانيكيّ ذاتيّ | قيمة ثابتة حرفيّة `"010c9627…+delta"` |
| إصلاح `parents[2]` الهشّة بنمط المشي للأعلى | عطل حاوية حقيقيّ (٢٠٢٦-٠٧-١٢) يعود في خدمتين جديدتين — يُصلَح لا يُعاد إدخاله | مطابقاً لـ`indicators-service/main.py::_resolve_manifest` |
| حذف الستّ موصولات فعليّاً | تنفيذ تقاعد S5 المُقرَّر مسبقاً — أوّل انكماش حقيقيّ لا مقيسٌ فقط | `platform_domain_compute` 205→201 |
## 2026-08-18 — الحارس القائم يُسأل محليّاً (PREFLIGHT-DOES-NOT-ASK-ITS-OWN-GUARD)

| القرار | السبب | الأثر |
|---|---|---|
| `probe_leak_guard` يدخل `preflight.sh` **في الطيف السريع** لا الكامل | الطيف الذي يُشغَّل قبل الدفع هو `--fast`؛ بوّابة في طيفٍ لا يُشغَّل ليست مقيسة. Python صرف، أقلّ من ثانية، بلا خدمة | خطوة `٠ج` قبل الخروج المبكر |
| موضعها **بعد ٠ب مباشرةً** لا في نهاية القائمة | ٠ب تطبع «⚠ ملفّ غير متعقَّب» بلا تسميته؛ التفسير يجب أن يتلو التحذير لا أن يسبقه بعشر خطوات | التحذير ثمّ سببه وعلاجه |
| التحذير في ٠ب **لا** يُرقّى إلى إخفاق | ملفّ غير متعقَّب حالةٌ مشروعة يوميّاً (مسوّدة، سكربت محلّيّ)؛ ترقيتها تُدرِّب القارئ على التجاهل — والمطلوب إدانة **المِسبار** لا كلّ ما لم يُضَف | الحارس يُدين بالاسم، ٠ب تبقى تحذيراً |
| المدخل يُعلَن في `preflight_required.json` لا في السكربت | قائمة مدفونة في أداة تبيت بصمت — الصنف الذي أسقط `SENSITIVE=` والمحرّك الثاني لأثر القدرات | حذف الحارس = تقلّص تغطية مُسمّى |
| الأعداد المُعلَنة تُحرَّك مع التغيير لا بعده | «رقمٌ بائت أسوأ من غياب الرقم لأنّه يُقرَأ قياساً» (§٦ من الدليل نفسه، سطر 946) | ١٤→١٥ · ٧٠→٧١ · ١٣٩→١٣٨ في ثلاثة ملفّات |
| التكذيب ثلاثيّ لا واحد | «موجود» ليس «يُقاس في الطيف المُشغَّل»؛ اختبارٌ يقيس الوجود وحده يمرّ على نقل الخطوة خلف الخروج المبكر | نزع · نقل · حذف المدخل — كلٌّ أسقط الاختبار وحده |
| بنود التقرير البيئيّة **لا** تُعالَج في المستودع | صورة مبنيّة على SHA أقدم · سحب نموذج تضمين متعثّر · ترميز طرفيّة — لا شيء منها في الشجرة، وإصلاحٌ هنا يدّعي علاجاً لعطلٍ مكانه آخر | مُعلَنة في `log.md` بلا تغيير كود |

## 2026-08-19 — C5–C13 وبذّار Qdrant فوق 9d58b0dc · وتوافق PG15

**القرار:** تأسيسُ الفرع على `9d58b0dc` مع أخذ **الجديد وحده** من الحزم الواردة
(C8–C13 + بذّار Qdrant)، ورفضُ ١١٠ ملفّاً كانت سترتدّ فوق إصلاحاتٍ مُتحقَّقة.
**السبب:** القياس أثبت أنّ الحزم مبنيّة على شجرة تسبق مراجعتي — تُعيد `parents[2]`
الهشّة في خدمتين، وتُسقِط `measured_on` وإصلاحات الترميز وعقد المزوّد المكتمل بـvLLM.
**PR:** #872 · **SHA:** `f7c8dc50` ⇐ ثمّ إصلاح جولة `32205385706`.

**قرارٌ حوكميّ مُميَّز — لم أُصدِر لنفسي تفويضاً:** قطعُ كاتب `online_learning_updates`
في `api/phase_runtime_store.py` صحيحٌ ومطلوب، لكنّ الملفّ **مسارٌ مجمَّد** وGATE-01
حالتها `CLOSED`، والتفويض `GATE01-ADJ-2026-08-13-001` حالته `CONSUMED`. فرُدَّ التعديل
إلى نصّ `main` وأُزيلت حالته المقابلة، وسُجِّل القطع شريحةً مستقلّة تنتظر تفويضاً من
مالك القرار. **السبب:** إصدارُ الإذن الذي تشترطه البوّابة، بيد المحجوب بها، يُبطِلها.

**وتعارضُ حارسَين قِيس لا خُمِّن:** حذفي محرفَ RLM من هذا السجلّ لإرضاء
`bidi_control_char_guard` أنقصه ٣ بايتات، فأحمر `brain_append_only_guard`
(`JOURNAL_SHRANK`). والحلّ ليس استثناءً لأحدهما: هذا الإلحاق يُنمي الملفّ فوق
المفقود، وعددُ المحارف الخفيّة يبقى ٧ لأنّ النصّ الجديد بلا RLM.

## 2026-08-19 — `707ef54e` · التقارب الدلاليّ وهارنس CI

- **القرار:** دمجُ #874 ضغطاً بعد اخضرار الفحوص الخمسة عشر المطلوبة. **السبب:** المُشغّل القانونيّ للهجرات أغلق عطل ملكيّة المجرى الذي أنتج `applied 1/226` وانفجاراً ثانويّاً بـ57 فشلاً و23 خطأً كلّها أعراض؛ والعميل صار يُشتقّ من الصورة المسحوبة بدل رهانٍ على مرآة Ubuntu سقط خمس مرّات مقيسة.
- **القرار:** أخذُ حلّ #875 لـPlaywright وإسقاطُ حلّي. **السبب:** حلّهم يُبدّل مرآة APT قبل النوم بدالّة مشتركة ومعه ١٧٢ سطر اختبار؛ وحلّي إعادةٌ مسقوفة فقط. واختبارُهم يؤكّد غياب سطري المباشر، فإبقاء الاثنين عقدان متضادّان.
- **القرار:** خطوة `٣ج` في `preflight.sh` تزرع الطفرات محلّيّاً مقصورةً على ما مسّه التغيير. **السبب:** `preflight_required.json` كان يعدّ `guard_mutation_guard` مستوفىً بالاسم بينما المُشغَّل محلّيّاً نصفُه الساكن، والحاجب في CI هو `--run` — فمرّ زوجٌ أخضرُ كاذب من صنعي حتّى أسقطته الجولة `96216401333`.
- **القرار:** `PlainSerializer` بدل حذف `json_encoders`. **السبب:** الحذف يُغيّر شكل الإدامة من `+00:00` إلى `Z` بصمت على كلّ مخزن ذاكرةٍ قائم؛ والبديل قِيس مطابقاً بايتاً في الوضعين.

## 2026-08-20 — `GUARD-SCOPE-COMPLETENESS` مبدأً حاكماً (قبل أيّ تنفيذ من الخطّة الموحّدة)

- **القرار:** لا يُقبَل حارس **جديد أو معدَّل** إلّا بخمسة شهود: `universe_source` (مصدر اكتشاف مشترك لا قائمة يدويّة) · `discovered_paths` · `excluded_paths` بسببها · **شاهد تساوي المجموعات** (`discovered_set == git_tracked_expected_set`، لا عدّادات) · **شاهد طفرة** يُحتضَن في `guard_mutation_guard.py`.
- **السبب:** صنف `GUARD-SCOPE-SINGLE-FILE` تكرّر في هذا المستودع بأربع معالجات عرضيّة. والعدّاد يُخفيه: حارسٌ يرى ملفّاً واحداً ويقول «مرّ» يُقرأ تغطيةً كاملة. وتساوي المجموعات هو ما يجعل «ما لم يُرَ» ظاهراً؛ والعدّ لا يجعله.
- **النطاق:** راتشِت — **إلزاميّ على الجديد والمعدَّل، غير رجعيّ** على الـ٢١٨ القائمة. توسيعُه رجعيّاً يوقف العمل ولا يشتري صدقاً.
- **المصدر:** الخطّة الموحّدة النهائيّة، المرجع `258a5835`.

## 2026-08-20 — تصميم إغلاق الأسرار الافتراضيّة يُشتقّ من قياسٍ لا من قاعدة واحدة

- **القياس الحاكم:** `:?required` على خدمةٍ **خلف profile** يكسر `docker compose config` للمكدّس الافتراضيّ — الاستيفاء يسبق ترشيح الـprofiles. أُثبِت بمِسبار: خدمة `profiles: ["gpu"]` بمتغيّر `:?` ⇒ `rc=1` **مع تفعيل الـprofile وبدونه**.
- **القرار:** العلاج يختلف بحسب موضع الخدمة، لا قاعدة واحدة على الكلّ:
  - `APP_DB_PASSWORD` و`JOBS_DB_PASSWORD` — مستهلكوهما **دائمون** (١٩ خدمة عبر أربعة ملفّات) ⇒ `:?required`.
  - `ODOO_DB_PASSWORD` — مستهلكه الوحيد `profiles=['odoo']` ⇒ افتراضيٌّ **فارغ**، والإلزام ينتقل إلى طبقة تشغيل الـprofile.
  - `VLLM_API_KEY` — خدمةٌ خلف profile ومستهلكان **دائمان**؛ فرضُه يكسر كلّ مُشغِّل بلا vLLM ⇒ افتراضيٌّ **فارغ**.
- **السبب:** الغرض إزالةُ **سرٍّ منشور** من الشجرة، لا فرضُ إعدادٍ على مسارٍ لا يستعمله. والافتراضيّ الفارغ يُحقّق الأوّل بلا كسر الثاني — والفشل يبقى مغلقاً عند الاستعمال الفعليّ.
- **حدّ صدق:** الافتراضيّ الفارغ **أضعف** من `:?` — يُخفِق عند الإقلاع لا عند `config`. وهو مقايضةٌ مُعلَنة لا إغفال.


## 2026-08-20 — `SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01`: عقدٌ ثانٍ لا توسعةُ الأوّل

- **القرار:** فصلُ «خادمٌ لا يُقلِع بسرٍّ فارغ» عن «لا سرَّ افتراضيّ منشور» في حارسين وعقدين، ورفضُ توسعة `compose_no_default_secrets_guard` بنمط `.*API_KEY`.
- **السبب (تحكيمُ المالك، وأقبله):** النمطُ أوسع من الدليل. بعض متغيّرات `*_API_KEY` اعتمادُ عميلٍ اختياريّ لا مفتاحٌ يحمي خادماً، وجعلُها `:?` عالميّاً يكسر مكدّساتٍ تعمل بلا مزوّدٍ خارجيّ بحقّ. والأصحّ حراسةُ **موضعٍ له دلالة أمنيّة** مُسمّىً بالاسم.
- **والقيمةُ الحرفيّة هي البرهان على أنّ العقدين مختلفان:** `test_qdrant_key` سرٌّ منشور يُدينه الأوّل، ويُقلِع الخادمَ بالاستيثاق **مُفعَّلاً** فيُرضي الثاني بحقّ. فتغطيةُ الثانية باستثناءٍ داخل الأولى كانت ستخبّئ عقداً داخل عقد.
- **النطاق:** سجلٌّ صريح `docs/architecture/compose_auth_sinks.json` بمصرفٍ **مقيسٍ** واحد (`QDRANT__SERVICE__API_KEY`). التعميم إلى Redis/NATS/MQTT/MinIO يحتاج إثباتَ الدلالة نفسها لكلٍّ منها، لا تشابهَ أسماء.
- **والمقيسُ خاصّيّةٌ لا صيغة** (`GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`): أقلُّ ما تؤول إليه القيمة. فـ`${V?msg}` تُدان رغم حملها علامة استفهام، لأنّها تمرّر المضبوطَ فارغاً — مقيسٌ بـ`docker compose config`.
- **الأثر:** `docker-compose.unified.yml:409` ⇒ `:?` · حارسٌ جديد في `ci.yml` و`preflight.sh` (٤ﻫ) · ٢١ اختباراً منها خمسةُ مسابرَ حيّة · ٣ طفرات مُسجَّلة.
- **حدُّ صدق:** لم تُقلَع Qdrant ولم يُسبَر منفذُها. المقيس دلالةُ الاستيفاء وانحرافُ المكدّسات الأربعة، لا رفضٌ حيّ بـ401.
- **PR/SHA:** يُملأ عند النشر.

## 2026-08-20 — ما **لم** يُنفَّذ من توصيتي، وسببه

- **دمجُ `PYTEST-NONASSERTING-EXISTING-DEBT-01` مع `TESTS-PASS-WITHOUT-ASSERTING-01`: مؤجَّل.** الأساس القانونيّ يشير إلى الثاني (`"gap": "TESTS-PASS-WITHOUT-ASSERTING-01"`)، فهو المُرشَّح للهويّة القانونيّة والأوّل لقبٌ مهجور. لكنّ إعادة التسمية تحتاج **جردَ المُشيرين** أوّلاً؛ والكتابةَ فوق مراجع تاريخيّة تدميرٌ لا تصحيح.
- **أعدادُ جرد السجلّ (116/42/~70): لا تُتبنّى أساساً بعد.** خوارزميّتي عدّت كلّ عنوان `##` بمُعرِّفٍ وحدةً قانونيّة، والملفّ يحوي أقساماً تاريخيّة و«تفصيلاً أصليّاً» وألقاباً. فقد تكون خلطت الحاضر بالتاريخ. الشرط: تُحفَظ الخوارزميّة أداةً باختبارات، ويُحسَم `canonical_record` صراحةً، قبل بناء أيّ راتشِت عليها.
- **مفرداتُ الحالة:** الاتّجاه مُصدَّق والعلاج راتشِت لا إعادةَ كتابة: الصفوف الجديدة/المعدَّلة تلتزم مفرداتٍ محصورة ومصدراً ومُعرِّفاً، والقديمُ المخالف أساسٌ مُجمَّد يتقلّص ولا ينمو — فلسفةُ `assertion_presence_guard` نفسها.


## 2026-08-20 (ب) — تحكيمُ المالك على الشريحة، وثلاثةُ تصويبات عليّ

- **القرار:** تُعتمَد الصيغةُ المقبولة **واحدةً** لمصرف `REQUIRED_NONEMPTY` هي `${VAR:?…}`، وتُدان **القيمةُ الحرفيّة** ولو كانت غير فارغة.
- **وكنتُ مخطئاً:** مرّرتُ الحرفيّة بحجّة أنّ الخاصّيّة «لا تؤول إلى الخالي» تتحقّق فيها. والصواب أنّ «غير فارغ» شرطٌ **لازم لا كافٍ** لسرٍّ يحرس خادماً: `test_qdrant_key` تُقلِع الخدمة بالاستيثاق مُفعَّلاً وبمفتاحٍ **يعرفه كلّ قارئ للمستودع**. فحارسٌ يُبارِكها في مكدّسٍ إنتاجيّ يُبارِك سرّاً مكشوفاً.
- **والاستثناء لا يُعمَّم:** مقيَّدٌ بالملفّ **وبالخدمة**، بسببٍ ومالكٍ وتاريخِ انتهاء، ومشروطٌ بـ`non_production: true` — **ومرفوضٌ بنيويّاً** على المكدّسات الإنتاجيّة المُعلَنة في `production_stacks` مهما أعلن المدخلُ عن نفسه. التصنيفُ يقوله السجلّ لا المستفيدُ من الإعفاء.
- **واختفاءُ مصرفٍ مُسجَّل من السطح يحجب** ولا يُبلَّغ: حارسٌ لا يجد ما يفحص يبقى أخضر بلا معنى.
- **واسمُ العقد صُوِّب** إلى `SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01` كما حكم المالك.
- **واللقب `QDRANT-AUTH-EMPTY-SECRET-FAIL-OPEN-01` سُجِّل لقباً لا مدخلاً ثانياً** — نفس القاعدة التي أقرّها المالك لدَين التأكيدات: لا مُعرِّفان لدَينٍ واحد بلا جرد مُشيرين، ولا كتابةَ فوق مراجع تاريخيّة.

### وثلاثةُ أخطاءٍ في بنائي أمسكها المِرقاب لا أنا

1. **سمّيتُ اختباراً لا يسقط:** طفرةُ `?`⇒`:?` لا تُحمِّر اختبارَ الشجرة الحيّة — الشجرة نظيفةٌ من تلك الصيغة. صنّفها `STABLE_WRONG_TEST`.
2. **نجت طفرتان** لأنّ `min_expansion` صارت بعد إحكام القبول نموذجاً دلاليّاً موازياً **لا يقرّر شيئاً** — والقرارُ عند `_ACCEPTED` وحدها. فحُذفت: اشتقاقان لا يُبنى على أحدهما حكمٌ ينحرفان بلا أن يلاحظ أحد. وأُضيفت `scanned_files()` لتفصل «لم يجد» عن «لم ينظر»، وهما متطابقتان في الخضرة متناقضتان في المعنى.
3. **أدان اختباري تعليقي:** فحصتُ الملفّ كنصّاً فأدان التعليقَ الذي يقتبس الصيغة القديمة ليشرح ما أُصلِح — أي عقوبةٌ على التوثيق، وهو نمطٌ مُسجَّل هنا.

### وحدُّ صدقٍ بنيويّ على الطفرة E

طلبَ التحكيمُ طفرةً تُخرِج `docker-compose.unified.yml` من سطح الاكتشاف. و`guard_mutation_guard` يكتشف `*_guard.py` و`*_guard.sh` فقط (`GUARD_GLOBS`، مقيس) — و`compose_surface.py` وحدةٌ **مشتركة** لا حارس، فلا تقبل طفرةً مُسجَّلة. فنُفِّذت مكافئتُها **داخل** الحارس (`_scan_surface`)، ويحرس السطحَ نفسَه اختبارُ تساوي المجموعات + شاهدٌ مُسمّىً على الملفّ.


## 2026-08-20 (ج) — مراجعةُ Copilot على #881: ثقبٌ حقيقيّ في الخاصّيّة الحاجبة

- **رُفِعت مسألتان، وكلتاهما صحيحة، والأولى أخطر ممّا بدت:**
  - `unmeasured_sinks()` كانت تُقرّر «المصرف حيّ» بمطابقةِ اسمِه **نصّاً** داخل الملفّ (`name in text`)، بينما `findings()` تمرّ بـ`_ASSIGN` وتتخطّى التعليقات. فاختلف الجوابان عن السطر الواحد.
  - **والأثر مقيسٌ لا مُرجَّح:** ملفٌّ حُذفت منه الخدمة وبقي الاسم في تعليقٍ حرّ ⇒ `unmeasured_sinks() == []`. وسطرُ إسنادٍ مُعطَّلٌ بـ`#` ⇒ الشيء نفسه. أي أنّ الخاصّيّة التي أعلنتُها **حاجبةً في هذه الشريحة بالذات** تسقط صامتةً.
  - **وهو نفس صنف** ما حذفتُ لأجله `min_expansion` قبل ساعات: اشتقاقان للسؤال الواحد ينحرفان بلا أن يلاحظ أحد. وقعتُ فيه مرّتين في شريحةٍ واحدة.
- **العلاج:** `_sink_assignments()` — اشتقاقٌ واحد يستهلكه السؤالان («أهو حيّ؟» و«أهو منتهِك؟»)، فلا يمكن أن يتناقضا بنيويّاً. + اختبارٌ يقيس الحالتين، واختبارٌ يقيس **وحدة المصدر**، وطفرةٌ ثامنة تُعيد عدّ التعليق حياةً.
- **والثانية:** `_compose_available()` تُنفَّذ عند **جمع** الاختبارات بلا مهلة — عميلُ docker عالقاً كان سيُعلِّق الجمع كلَّه، وهو إخفاقٌ يُقرَأ «الجناح معطَّل» لا «الأداة غائبة». أُحيطت بمهلةٍ والتقاطِ خطأ؛ السلوك لا يتغيّر.
- **الدرس:** الحارسُ الذي يجيب سؤالين عن الشجرة نفسها بطريقتين سيتناقض — والمراجعة الخارجيّة أمسكت ما أمسكه مِرقابي في الحالة الأولى ولم يمسكه في الثانية، لأنّ الشجرة الحيّة لا تحوي المثال المضادّ.
## 2026-08-20 (ب) — سلطةُ الطزاجة إعادةُ الاشتقاق، والختمُ إسنادٌ لا شهادة

- **القرار:** `measured_on` يبقى **إشارةَ إسناد** غير حاجبة، وسلطةُ الطزاجة تبقى **إعادةَ اشتقاق** الحارس المالك من الشجرة الحاضرة ومقارنةَ ناتجه بالأساس المخزون. ولا يُضاف محرّكُ حقيقةٍ ثانٍ.
- **السبب:** إعادةُ الاشتقاق **أقوى** من بصمة المدخلات المقترحة — الأخيرة تلتقط تغيُّر المدخلات ولا تلتقط تغيُّر المولّد نفسه بمدخلاتٍ ثابتة. واشتراطُ `measured_on == HEAD` غيرُ قابلٍ للتحقيق داخل PR مع squash (الالتزام الناتج لا يوجد وقت القياس)، ويُحوّل كلّ PR إلى churn يُدرِّب القارئ على تجاهل الحارس.
- **النطاق:** المرفوض هو **دورُ** بصمةِ المدخلات سلطةً موازية — لا الإسنادُ المُعنوَن بالمحتوى في ذاته. بصمةٌ تُسجَّل إسناداً بجانب إعادةِ اشتقاقٍ تبقى هي الحاكمة مقبولةٌ متى أفادت.
- **الشاهد:** ستّة تأكيدات في `tests_v9/test_claim_base_guard.py`، منها زوجٌ دلاليّ A/B مُسجَّلُ الطفرتين في `docs/architecture/guard_mutation_registry.json` تحت `tenant_guc_scope_guard.py[2..3]` — مقتولتان بالزرع الفعليّ.
- **المصدر:** `44de9594` · جلسة `017Ee5NDNog8QCmQedcxMzW3`.

## 2026-08-20 (ج) — B1 تنقسم: التطبيع أُغلِق، والتكافؤ هو الحاجب

- **القرار:** `B1` تُصنَّف شريحتين مستقلّتين — `B1a` تطبيعُ درجات الدمج **مُغلَقة**، و`B1b` تكافؤُ دلالات المسار الكثيف **مفتوحة وهي الحاجب**. ولا تُعاد معايرةُ عتبات Jaccard ولا أوزانِ الدمج قبل إغلاق `B1b`.
- **السبب:** الشاهد Q4/NDVI — `dense_vs_sparse = 1.0` داخل المسار القانونيّ مع `direct_vs_rag_dense = 0.25`. تطابقُ الكثيف والمتناثر داخليّاً يمنع BM25 من أن يكون السبب الجذريّ لهذه الحالة بالبناء، لا بالترجيح.
- **ولمَ لا تُخفَّض العتبة:** خفضُ `min` من ٠٫٦ إلى ٠٫٢٥ و`mean` من ٠٫٨ إلى ٠٫٤٧ يُخضِر الإيصال لأنّ **معيار القبول نزل إلى مستوى النظام**، لا لأنّ النظام بلغ المعيار. وتكبيرُ الـcorpus قبل معرفة السبب يُخفي العطل إحصائيّاً. المعايرة تصير علميّةً **بعد** إثبات التكافؤ، بأحجام corpus متعدّدة وفترات ثقة، لا باختيار أرقامٍ تُمرِّر الجولة الحاليّة.
- **النطاق:** حكمُ `cutover-admission: FAILED` يبقى كما هو. و`.coveragerc` تبقى `B2` مستقلّة — تُغلَق بإعادة توليد بصمات الإصدار من الـsubject النهائيّ لا بتحرير digest يدويّاً. و`weather-signal-engine` يبقى finding خارج مسار RAG.
- **حدّ صدق مُعلَن:** قياسُ هذه الجولة **لم يجرِ في هذا الاستنساخ** ولا أملك التحقّق منه: لا daemon لـDocker ولا Ollama/Qdrant، والمِسبار المُوسَّع (`rag_hybrid_decomposition_probe.py`) و`_max_sparse` غير موجودين هنا، وsubject `4556dc4c4bae` غير قابل للحلّ. فالحالات مُسجَّلةٌ **نقلاً موثَّق المصدر** عن المالك، وما أضفتُه أنا **تشخيصٌ ساكن** من الشيفرة القائمة لا قياسٌ حيّ.
- **المصدر:** حكم المالك في هذه الجلسة · جلسة `017Ee5NDNog8QCmQedcxMzW3`.

## 2026-08-20 (د) — سلطةُ الطزاجة أساسٌ حتميّ، والالتزامُ خارج الحساب

- **القرار:** تُضاف `measurement_basis_digest` شرطاً **اقترانيّاً** إلى إعادة الاشتقاق، لا بديلاً عنها ولا سلطةً موازية. طازجٌ ⇔ تطابقَ الأساسُ **و** تطابقت النتيجة.
- **السبب:** إعادةُ الاشتقاق تُجيب عن النتيجة ولا تُجيب عن الأساس، فيبقى provenance قديم إلى الأبد بحجّة أنّ الناتج لم يتغيّر. والأساسُ ثلاثيّ لأنّ بصمةَ المدخلات وحدها تعمى عن تغيُّر منطق المولّد بمدخلاتٍ ثابتة.
- **النطاق:** طورٌ أوّل على `tenant_guc_scope_baseline.json` وحده. **لا بدائيّة عامّة** قبل إثبات تطابق العقود — و`claim_base_guard` لا يتقاسم الدلالة (يصنّف أختاماً، ولا يُنتِج قياساً يُعاد اشتقاقه). الحدُّ مفروضٌ باختبار لا بنيّة.
- **حدُّ صدق:** `PROVENANCE_STALE` يحجب. فتعديلُ مُدخَلٍ أصيل أو منطقِ المولّد يفرض إعادة توليد ولو ثبتت النتيجة — ضريبةٌ مُعلَنة، خُفِّضت بتطبيع AST (تعليقٌ أو docstring لا يُبيت شيئاً) ولم تُلغَ.
- **المصدر:** `d9b6116f` · مراجعةُ المالك «ACCEPT WITH REFINEMENTS» · جلسة `017Ee5NDNog8QCmQedcxMzW3`.


## 2026-08-21 — المعيارُ يُشتقّ ولا يُنتقى: «يكتبه» لا «يذكره»

- **القرار:** تصنيفُ المصنوعات في حلّ التعارض يُشتقّ من **عمليّات الكتابة** في المولّدات، لا من قائمةٍ منتقاة ولا من ورود المسار نصّاً.
- **السبب:** الصنف ارتدّ ثلاث مرّات، وفي كلّها بالآليّة نفسها — قائمةٌ تُغلِق المعلوم وتترك الصنف. والاشتقاق النصّيّ مقيسٌ ضارّاً (٢١٩ مقابل ٣١، وفي الفارق وثائقُ سياسةٍ يُتلِفها التصنيف الخاطئ).
- **والاشتقاق ساكن لا ديناميكيّ** — وهذا تصحيحٌ لتصميمي الأوّل: القياسُ الذي يُشغّل المكنسة يرث هشاشتها ويكسر نقطة ثباتها. ٢.٤ ثانية مقابل خمسَ عشرة دقيقة.
- **الأثر:** أداة + بيان مُصنَّف `measured` + وصلٌ في `ci.yml` و`preflight` (٤و) + ١٥ شاهداً.

## 2026-08-21 — قاعدةٌ تشغيليّة جديدة بعد ستّة ارتدادات

- **القديمة:** انسخ المرفقات إلى المِصنَع فور وصولها.
- **ونُقِضت اليوم:** الارتدادُ الخامس أباد **المِصنَع نفسه** ومعه دلتا `D06-C1` المُنقَذة، ودليلَ الرفع الأصليّ معاً.
- **الجديدة: ما لم يُدفَع إلى البعيد لم يُحفَظ.** يُلتزَم ويُدفَع عند كلّ وحدةٍ ذات معنى — «نقطة حفظ» — لا عند اكتمال الشريحة.
- **ومُثبَتةٌ بالتجربة في الجلسة نفسها:** الارتدادُ السادس أعاد الشجرة إلى `f87cbfb5` بعد الدفع بدقائق، و`git fetch` أعاد `29f60157` كاملاً. ما دُفِع نجا، وما لم يُدفَع ضاع مرّتين.
## 2026-08-21 — D09: انحرافُ المجموعة حالةُ خدمة، والتصفيةُ على مستوى الصفّ تُرفَع

- **القرار (نصُّ المالك):** D09 يرفع تصفيةَ الأهليّة على مستوى الصفّ من الاسترجاع الكثيف والمتفرّق. انحرافُ المجموعة **حالةُ جاهزيّةِ خدمة**، لا شرطُ تصفيةٍ لكلّ نتيجة. `canonical_storage_shape()` تبقى سياسةً حتميّة؛ و`noncanonical_serving_points` قياسٌ ودليل؛ وD09-M يقدّم هويّةَ مجموعةٍ مركّبة؛ ومسارُ القبول في `/readyz` والاسترجاع يفشل مغلقاً حين تُخالِف المجموعةُ المقيسةُ العقد.
- **السبب:** حذفُ الصفّ يُنتِج `200` بنتائجَ ناقصة لا يعرف المستهلكُ نقصَها — إجابةٌ مبتورة تُقرَأ كاملة. وفي مسار RAG هذا جوابٌ واثقٌ مبنيٌّ على شاهدٍ غائب، وهو الوضعُ الذي بُنيت المجموعةُ كلُّها لمنعه. فإمّا الخدمةُ جاهزةٌ فتُخدَم كلُّ الصفوف، وإمّا غيرُ جاهزةٍ فيُمنَع المسارُ كلُّه.
- **ولمَ الهويّةُ مركّبة لا عدد:** `point_count` وحده يمرّ على **استبدالِ المحتوى كلِّه** بعددٍ ومُعرِّفاتٍ ثابتة. فالهويّة `point_count` + `id_set_digest` + `content_digest`، والتخريبُ المُلزَم «نفسُ العدد ونفسُ المُعرِّفات ومحتوًى مبدَّل» يُحمِّر `test_same_count_same_ids_but_altered_content_still_drifts`.
- **ولمَ الحكمُ دالّةٌ نقيّة:** كي يُكذَّب بالسلوك لا بالنصّ. أوّلُ صياغةٍ فحصت مصدرَ المسار فمرّت على التعطيل الصريح `if False and …` — النصُّ يبقى قائماً بعد تعطيله (`TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`).
- **النطاق — وما لا يُفعَل:** D10–D12 **لا تُعدَّل** لتوقيعها بـD09 ولا لجعلها تعتمد على رموزه. ولا تُحذَف نقاط Qdrant قبل snapshot وتصنيفٍ وإيصالِ هجرة، ولا provenance مُلفَّق. ولا تُعاد معايرةُ عتبات Jaccard.
- **حدُّ صدق:** لا Qdrant حيّة ولا إيصالُ جرد في هذا الاستنساخ. السلطةُ لم تتحرّك (`EVIDENCE_REQUIRED` · `capable=False`)، وD09-M/E مقيسان على تقاريرَ مُختلَقة لا على مجموعةٍ حقيقيّة. الإيصالُ الحيّ يبقى بوّابةَ D09-M/E وD10/D11/D12.
- **المصدر:** حكمُ المالك في هذه الجلسة · الأساس `a1f5da7f` · جلسة `017Ee5NDNog8QCmQedcxMzW3`.

## 2026-08-21 (ب) — التكرارُ يُكشَف عند المحلّل، والنطاق بلا استثناء

- **القرار:** كشفُ المفاتيح المكرَّرة يقع عند `object_pairs_hook` لا بمسحٍ معجميٍّ للنصّ الخام، ونطاقُه كلُّ ملفّ `.json` متعقَّب بلا قائمة استثناءات وبلا أساسٍ مُجمَّد.
- **السبب (١) — لمَ لا مسحٌ نصّيّ:** الخاصّيّةُ المطلوبة «ما رآه المحلّل مرّتين»، والهُوك يقولها بالضبط. والمسحُ النصّيّ يرى `"dup": 1` داخل قيمةٍ نصّيّة مفتاحاً فيُدين وثيقةً سليمة — `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`. والمرفوضُ هو `json.load` **الافتراضيّ** الذي يطوي التكرار، لا وحدةُ `json`. والبديلُ مُكذَّبٌ باختبارٍ محفوظ (`test_a_key_shaped_string_value_is_not_a_duplicate`).
- **السبب (٢) — لمَ بلا استثناء:** القياسُ سبق الاختيار — ٢٣٣ ملفّاً، صفرُ تكرار. ومفتاحٌ مكرَّر لا حالةَ استعمالٍ مشروعةً له في وثيقة سياسة، فالاستثناءُ ثقبٌ لا مرونة. وهذا يفارق `compose_auth_sink_guard` بحقّ: هناك كانت للنمط استعمالاتٌ شرعيّة فلزم سجلٌّ صريح.
- **النطاق — وما لا يُفعَل:** لا تُمَسّ دلالاتُ سجلّ الطفرات ولا صيغتُه ولا قارئُوه. والحارسُ يحرس التكرارَ وحده: مفتاحٌ **مفقود** أو قيمةٌ خاطئة تمرّ منه بحقّ.
- **وحدُّ الشريحة:** مستقلّةٌ عن D09 قطعاً — `7fecea3d` باقٍ كما هو، ولا سطرَ من شيفرته مُسّ.
- **المصدر:** حكمُ المالك في هذه الجلسة · جلسة `017Ee5NDNog8QCmQedcxMzW3`.


## 2026-08-21 — محلّيّةُ العقد: العميل يُثبِت اعتمادَه لا يرثه بالصدفة

- **القرار:** يُوسَّع `SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01` بعقدِ عملاء (`AUTHENTICATED-QDRANT-CLIENT-CREDENTIAL-MUST-BE-NONEMPTY-01`) داخل **السجلّ نفسه** — لا سجلٌّ موازٍ.
- **السبب:** إسنادُ العميل العاري كان يعمل لأنّ مصرف الخادم في الملفّ نفسه يُلزِم المتغيّر. وهذا اعتمادٌ على **مجاورةٍ في ملفّ**، لا على عقد. ونقلُ الخادم أو استخراجُ الخدمة يُسقِطه صامتاً.
- **وشكلُ `:?` وحده ليس ملكيّةً للسرّ:** `${WRONG_SECRET:?x}` يُثبِت «غير فارغ» ولا يُثبِت «هو السرّ المعنيّ». فصار القرارُ في دالّةٍ واحدة تُطابِق `source_env` المُعلَن.
- **والاكتشاف يسبق السجلّ:** الحارس يقرأ YAML لمكدّسات الإنتاج ويجد أيّ خدمةٍ تستعمل متغيّراً مُسجَّلاً — فلا يصير «حارسَ ما يعرفه».
- **الحزمة:** رقعةٌ مُعادُ إرساؤها على `f8b49ac` من المالك، طُبِّقت نظيفةً وقِيست قبلها وبعدها (٤ إسنادات عارية ⇒ صفر · ٥ روابط مُعلَنة).


## 2026-08-21 (ب) — استثناءٌ سقط سببُه فلم يُراجَع، وأباده ارتدادٌ فأُصلِح

- **ما حدث:** سُجِّلت `generated_write_targets.py` استثناءً في `generated_sweep_unmapped_generators.json` بحجّةٍ **بنيويّة صحيحة وقتها**: `--generate` عندها كان يُشغّل المكنسة، فوصلُها بها استدعاءٌ دائريّ.
- **ثمّ سقطت الحجّة ولم أُراجع التسجيل:** حين تحوّل الاشتقاق إلى الساكن (٢.٤ث، بلا تشغيل شيء) لم تعد الدائريّة قائمة — والاستثناء بقي.
- **وأباده ارتدادُ حاوية**، فطرحت المكنسة السؤال من جديد ووُصِلت الأداة بـ`_GENERATE_FLAG` كما ينبغي.
- **والدرس أعمّ من الحادثة:** الاستثناءُ يُراجَع حين يتغيّر ما بُنِي عليه، لا حين يشتكي أحد. وهذا بالضبط ما يفرضه `stale_exceptions()` على استثناءات Compose — ولم يكن مفروضاً هنا. صنفٌ يستحقّ التسمية: **إعفاءٌ يعيش بعد موت سببه**.
## 2026-08-22 — شرطُ D12 يُبنى قبله، وسلطةُ الإسقاط واحدة

- **القرار:** لا يُنزَل مخطِّطُ D12 قبل أن يُنتِج جردُ D08 `explicit_logical_chunk_id` و`logical_identity_source`. والشريحتان مفصولتان: `D12-PRE` إصلاحُ عقدِ D08، وD12 بناءُ المخطِّط.
- **السبب:** بدون الحقلين يكون المخطِّطُ شيفرةً ميتة — تمرّ اختباراتُه على تجهيزاتٍ مُختلَقة وينهار على أوّل إيصالٍ حقيقيّ. وإنزالُه هكذا هو «أخضرُ عن سؤالٍ لم يُطرَح» بعينه.
- **وقرارٌ ثانٍ — سلطةٌ واحدة للإسقاط:** `canonical_storage_point_id()` في `production_qdrant.py` يستوردها كلُّ من يحتاجها. أربعُ نسخٍ لصيغةٍ واحدة تنحرف، والانحرافُ يظهر أوّلَ ما يظهر في هجرةٍ تكتب فوق الخطأ.
- **والباذرُ استثناءٌ مقيسٌ لا إهمال:** خدمةٌ محاويَة لا ترى `core.rag` وقتَ التشغيل، ففرضُ الاستيراد يكسر حاويتَها. يُترَك الاقترانُ ويُفرَض التطابقُ بعقدٍ يقرأ صيغتَه من مصدرها.
- **وقرارٌ ثالث — الحارسُ لا يُثبِّت اسمَ الاحتجاز:** الثابتُ «لا تُرقَّى هويّتُه ولا يُهاجَر»، لا «يُحتجَز بهذا الاسم». وحارسٌ يُحمِّر الصوابَ يُدرِّب قارئَه على تخطّيه.
- **حدُّ صدق:** لم تُنتَج خطّةٌ حقيقيّة ولا أُنشئ إيصالٌ حيّ. والسلطةُ لا تتحرّك بهذه الشريحة.
- **المصدر:** قياسُ هذه الجلسة · الأساس `f8b49acb` · جلسة `017Ee5NDNog8QCmQedcxMzW3`.

## 2026-08-22 (ج) — الإيصال الحيّ أداةٌ واحدة بربطٍ إلزاميّ، والحكمُ للدالّة القانونيّة

- **القرار:** سلسلةُ دليل D09 الحيّ تُجمَع بأداةٍ واحدة (`scripts/architecture/d09_live_evidence_receipt.py`) تستورد أداةَ جرد D08 ولا تنسخها، وتحسب هويّةَ D09-M من صفوف القراءة نفسها التي بُني منها إيصالُ الجرد.
- **السبب:** قياسان منفصلان (جردٌ ثم هويّة بقراءةٍ ثانية) يفتحان نافذةَ سباقٍ تجعل «M1==M2» ادّعاءً لا قياساً؛ والنسخُ يصنع سلطةً ثانية تنحرف — وهو عينُ ما أُصلِح في D12 (أربعُ نسخ لصيغةٍ واحدة).
- **وقرارٌ ثانٍ — الربط شرطُ كتابة:** لا يُكتَب إيصالٌ أصلاً بلا SHA وشجرة وبصمةِ مصنوعةِ نشرٍ `sha256:` صالحة. «لا دليلَ مُصطنَع» تشمل «لا إيصالَ بلا مَربِط» — إيصالٌ سائبٌ يُنسَب لاحقاً لأيّ شجرة.
- **وقرارٌ ثالث — لا حكمَ جاهزيّةٍ ثانٍ:** D09-E في الإيصال هو ناتجُ `readiness_problems` القانونيّة على التقرير المقيس حيّاً؛ الأداةُ لا تملك رأياً خاصّاً بها.
- **حدُّ صدق:** الأداةُ لم تُشغَّل على بيئةٍ حيّة بعد — اختباراتُها التسعة تكذيبُ منطقها النقيّ لا دليلاً تشغيليّاً. والسلطةُ لا تتحرّك بهذه الشريحة.
- **المصدر:** `scripts/architecture/d09_live_evidence_receipt.py` · `tests_v9/test_d09_live_evidence_receipt.py` · الشجرة `dcf136d7` · جلسة `017Ee5NDNog8QCmQedcxMzW3`.
## 2026-08-22 (ج) — الالتفافُ يُسمّى التفافاً، والاتّحادُ يُفضَّل على الانتقاء

- **القرار:** لا يُضاف `edited` إلى `types` في `capability-governance.yml` الآن، ويُسجَّل الصنفُ `open` بدل إغلاقه بالالتفاف.
- **السبب:** إضافةُ `edited` تُعيد تشغيل ٥٨ فحصاً عند كلّ تحرير متنٍ ولو مطبعيّاً — كلفةٌ **لم تُقَس**؛ والبديلُ الأضيق (قراءةُ المتن حيّاً عبر الـAPI) يحتاج تصميماً لا رايةً. وإغلاقُ الفجوة بإعادةِ فتح الطلب كان سيُسجّل التفافاً بوصفه إصلاحاً.
- **وقرارٌ ثانٍ — تعارضُ وثيقة السياسة يُحَلّ بالاتّحاد:** `guard_mutation_registry.json` حُلَّ بجمع مدخلَي #887 ومدخلِ #888 ومفاتيحِ السياسة الثلاثة، لا بانتقاء جانب.
- **السبب:** قِيس أنّ أخذَ جانب main وحده يمحو `$scope_ar` و`$what_was_missing_ar` و`$why_ar` صامتاً — حذفها الفرعُ من رأس القسم ولم تُضَف إلّا داخل الكتلة المتعارضة. فالانتقاءُ هنا إتلافٌ لا اختيار.
- **حدُّ صدق:** الصنفُ الجديد **بلا حارسٍ وبلا طفرةٍ مُكذَّبة** — حادثةٌ موثَّقةٌ لا تغطيةٌ مفروضة.
- **المصدر:** قياسُ هذه الجلسة · #887 (`97040471171` فاشلة · `97043697680` ناجحة) · #888 (`fb9a5299`) · main `dcf136d7`.

## 2026-08-23 — البيانُ يُحَلّ قبل مستهلكه، والحدُّ يُعلَن حين يعجز القياس

- **القرار:** عند تعارضٍ يشمل `generated_write_targets.json` نفسَه، يُحَلّ **البيانُ أوّلاً** ثمّ يُعاد تشغيل المُصنِّف — لا يُقبَل تصنيفُه قبل ذلك.
- **السبب:** مقيسٌ بالتفريق على #889 — بالبيان المتعارض وقف عند ٣ ملفّات، وبحلّه وحدَه انحصر الوقوفُ في وثيقة السياسة. فالثلاثةُ لم تكن مصادر، بل كان المُصنِّفُ أعمى.
- **وقرارٌ ثانٍ — لا يُسجَّل الصنف `fixed` بعلاجٍ لم يُكتَب:** سُجِّل `open` مع علاجٍ مُقترَحٍ مسمّى (أن يقول المُصنِّفُ «حُلَّ بياني أوّلاً» بدل التدهور المجهول)، لأنّ ما جرى في #889 التفافُ ترتيبٍ لا إصلاحُ أداة.
- **وقرارٌ ثالث — يُعلَن ما لم يُقَس:** `preflight --fast` تعذّر إكمالُه لانهيار بيئة الحاوية، فكُتِب في متن #889 وفي السجلّ أنّ `٢د` و`٢و` **لم تُقاسا محلّيّاً وCI هي الشاهد** — بدل الاكتفاء بالبوّابات التي مرّت.
- **ولم يُكرَّر عملُ جلسةٍ أخرى:** `GATE-READS-A-FROZEN-EVENT-PAYLOAD-NOT-THE-LIVE-BODY-01` وُجِد `closed` سلفاً بـ#907 — البديلُ الأضيق الذي سُمّي في قرار 2026-08-22 (ج) ورُفِض ارتجالُه، نُفِّذ بتصميمٍ واختبارات. فلم يُحرَّر الصفّ.
- **المصدر:** قياسُ هذه الجلسة · #889 (`b979190`) · #907 (`43840e9`) · main `2bf8814`.

## 2026-08-24 — حارسٌ يطلب شيفرةً فتُكتَب، لا صياغةً تتفاداه

- **القرار:** حين حجب `brain_state_transition_guard` تغييراً دماغيّاً صرفاً، كُتِبت الشيفرةُ الناقصة بدل إعادة صياغة النثر لتفادي اللفظ المُطلِق.
- **السبب:** الحارسُ يمنع «إغلاقاً في الدماغ وحدَه»، وكان في الصفّ علاجٌ مُسمًّى **لم يُنفَّذ**. فإعادةُ الصياغة تُمرِّر البوّابةَ وتُبقي الفجوة؛ وكتابةُ العلاج تُرضي البوّابةَ **لأنّها صادقة**. والالتفافُ هنا كان سيُسجَّل إصلاحاً وهو ليس به.
- **وقرارٌ ثانٍ — الإبانةُ لا تُغيّر السلوك:** `_manifest_is_conflicted()` يُضيف رسالةً ولا يمسّ القرار («مصدر» تبقى «قف»).
- **السبب:** العطلُ كان عطلَ إبانةٍ لا صحّة — التدهورُ آمنٌ بالتصميم ومُكذَّبٌ باختبارٍ قائم. فتوسيعُ الصلاحيّة علاجٌ لِما ليس مريضاً.
- **وقرارٌ ثالث — المرساةُ مسارٌ مُطبَّع لا `substring`:** ومُثبَّتٌ بطفرة. لأنّ رسالةً تقول «حُلَّ بياني» عن ملفٍّ ليس بياننا **تكذب على قارئها**، وذلك أسوأ من الصمت الذي جاءت تُصلحه.
- **حدُّ صدق:** `fixed` لا `verified` — لم تُختبَر الرسالةُ على تعارضٍ حيٍّ يقرؤها مُشغِّل. و`pytest` معطَّلٌ في الحاوية فالتأكيداتُ شُغِّلت باستيرادٍ مباشر.
- **المصدر:** قياسُ هذه الجلسة · main `b3c532a` · `guard_mutation_registry.json` (٤ طفرات للأداة).

## 2026-08-24 (ج) — لا يُختلَق اختبارٌ لفرعٍ لا يُبلَغ، ويُحرَس البرهانُ بدله

- **القرار:** سطرُ `prefix mismatch` بقي بلا تكذيبٍ مُسجَّل، ولم يُكتَب له اختبارٌ يُوهِم بتغطيته.
- **السبب:** مُبرهَنٌ بالجداء الكامل (٩×٩ = ٨١ مِسباراً، صفرُ موضعٍ حرّ) أنّه غيرُ قابل للبلوغ ما دام المخطَّطُ يُثبِّت (المرحلة ⇄ التسلسل). واختبارٌ يمرّ عن فرعٍ لا يُبلَغ يُسجَّل تغطيةً وهو صمت.
- **وقرارٌ ثانٍ — يُحرَس البرهانُ لا الفرع:** كُتِب اختبارٌ يحمرّ إن ارتخى المخطَّطُ عن تثبيت الاقتران، فيُعلَم أنّ الفرعَ عاد حيّاً ويلزمه تكذيبٌ خاصّ.
- **السبب:** البرهانُ شرطٌ خارجيّ قد يسقط بتغييرٍ في ملفٍّ آخر، وسقوطُه صامتاً يُحوِّل «مُبرهَنٌ لا يُبلَغ» إلى «ثغرةٌ بلا حارس».
- **وقرارٌ ثالث — لم يُحذَف الفرعُ الميت:** يبقى دفاعاً في العمق؛ حذفُه اليوم يفتح ثغرةً غداً إن ارتخى المخطَّط.
- **حدُّ صدق:** C6 الحيُّ غيرُ مُدَّعى (يلزمه استنساخُ Git حقيقيّ وخدماتٌ حيّة) — كما أعلن بيانُ الرقعة بصدق، وأُبقِي على إعلانه.
- **المصدر:** قياسُ هذه الجلسة · main `a771197` · `guard_mutation_registry.json` (٥ طفرات للمُتحقِّق).

## 2026-08-24 (د) — وحدةٌ بلا مستهلكٍ تُقبَل بقيدٍ زمنيّ، لا بإعفاء عدّ

- **القرار:** `api/irrigation_decision_evidence_chain.py` سُجِّلت في `platform_python_module_baseline.json` (679 ⇐ 680) **وفي استثناءات `platform_shrink_ratchet.json`** بهويّة المسار وسببٍ وتاريخِ إغلاق `2026-12-31`.
- **السبب:** الحاجبان مختلفان جذريّاً — العدديُّ يقرأ الأساس، والهُويّاتيُّ لا يقرؤه إطلاقاً (`new_identity = BLOCK_UNLESS_EXPLICIT_EXCEPTION` · `count_only_waivers_forbidden = true`). فرفعُ العدد وحدَه كان سيُبقي C13 حمراء.
- **وقرارٌ ثانٍ — لم تُسجَّل على أرضيّة «مستهلكٍ إنتاجيّ»:** المستورِدُ الوحيد ملفُّ اختبارها، مقيساً بمسحٍ كامل للشجرة. وأرضيّةُ الأساس المُعلَنة (`ci10_knowledge_layer_note`) تشترط مستهلكاً حيّاً — فادّعاؤها كان كذباً متاحاً، ورُفِض. القبولُ مقيَّدٌ زمنيّاً على سابقة `c3_precision_execution_note`، بشرط إغلاقٍ مسمّى: مستهلكٌ حيٌّ في مسار أدلّة C6 أو انتقالٌ إلى الخدمة المالكة.
- **وقرارٌ ثالث — لم يُرفَع حارسُ البلوغ إلى حاجبٍ فوراً:** ١٣٩ وحدةً موروثة بلا جذرٍ تنفيذيّ ⇒ الحجبُ الفوريّ يُوقِف الشجرة كلّها. سُجِّل الصنفُ `open` بعلاجٍ مُقترَحٍ متناسب: راتشِتٌ على الموروث لا يصعد.
- **حدُّ صدق:** التسجيلُ **لم يُسكِت حارساً** — قِيس بالتعطيل: `platform_module_reachability_guard` أخضرُ قبله وبعده. وما كشفه أنّ الأرضيّةَ المُعلَنة نثراً لا يفرضها حارسٌ حاجب أصلاً.
- **المصدر:** قياسُ هذه الجلسة · main `9953bc5` · #916 · `platform_shrink_ratchet.json` (استثناءٌ ثانٍ) · `platform_python_module_baseline.json` (`irr_corr1_evidence_chain_verifier_note`).

## 2026-08-25 (ز) — التغطية لا تُنزع قبل أن يحجب البديل: تسلسلٌ خماسيّ لا رباعيّ

- **القرار:** تُفعَّل حزم المكنسة الخمس في CI **بلا نزع** المكنسة الكاملة من *Unit Tests* — ازدواجٌ متعمَّد لدورةٍ واحدة. main `786e5d03` (#924)، فوق `ab0d67c3` (#923).
- **السبب:** بين بناء الآلة وضبط الـRuleset تُفتَح **نافذةُ صمت**: من ينزع المكنسة قبل أن تصير أسماءُ الحزم فحوصاً مطلوبة يترك ٣٢٠ طفرةً تُبلِّغ ولا تحجب. الازدواجُ ثمنٌ مقبول لدورة؛ نافذةُ الصمت ليست كذلك.
- **وقرارٌ ثانٍ — الأسماء حرفيّةٌ في `include` لا مُشتقّةٌ من تعبير:** الـRuleset يُطابِق الاسم حرفيّاً، واسمٌ يُبنى وقت التشغيل لا يُطابَق فيُعلَّق كلّ PR أبداً. **وقِيس فعلاً** على `7fadf14e`: الخمسة ظهرت كما كُتِبت.
- **وقرارٌ ثالث — حارس الاتّحاد في كلّ حزمة وقبل الزرع لا في واحدة وبعده:** حزمةٌ لا تُشغَّل أصلاً لا تفحص شيئاً، والفحصُ الواقع في أختها لا يشهد لها.
- **والاقترانُ مفروضٌ بآليّة لا بانضباط:** `test_the_sweep_stays_in_unit_tests_until_the_ruleset_is_set` ثنائيّ الاتّجاه — اسمُ حزمةٍ واحد في العقد يوجِب الخمسة ويوجِب النزع؛ وغيابُ الأسماء يوجِب البقاء. فلا نزعَ قبل إنفاذ ولا إنفاذَ جزئيّ.
- **وقرارٌ رابع — لم تُقحَم `SERVICE-MAIN-NAME-COLLISION-REMEDY-UNADOPTED-01` في الشريحة:** عطلٌ حقيقيّ مقيس (١ يستعمل العلاج مقابل ١٦) لكنّه **كامنٌ لا حاجب**، وخلطُه بشريحة التقسيم كان يُعمّي مراجعتها. سُجِّل `open` بشرطِ قياسٍ يسبق ترحيله.
- **حدُّ صدق:** المقيس ٥:٠٤ للأثقل مقابل ٣٤:٢٧ لـ*Unit Tests* — لكنّ الرقم يشمل إعداداً يتكرّر خمساً، والتوازن الزمنيّ ١٫٣٥× لا ١٫٠٦× المُصمَّمة، و*Unit Tests* نفسها أبطأ ستّ دقائق من أساس #920 **بسببٍ غير مُدّعى**. المكسبُ الصافي لا يُعرَف قبل الخطوة ⑤.
- **المصدر:** #923 (`ab0d67c3`) · #924 (`786e5d03`) · جولة CI على `7fadf14e` · `.github/workflows/ci.yml` (`mutation-sweep`) · `tests_v9/test_ci_pipeline_settings.py`.

## 2026-08-25 (ح) — ترتيبُ الدمج قرارُ المالك، وكلفتُه المقيسة تشغيلةٌ ضائعة

- **القرار:** دُمِج #928 (W2) قبل #927 بأمر المالك، خلافاً لترتيبٍ رجّحتُه. main `37561b8c` ثمّ `18d5ef4f`.
- **السبب المُعلَن لترجيحي العكس:** تشغيلةُ #927 الجارية كانت **الشاهد على إصلاح انحدار MFA**؛ ودمجُ الآخر يوجِب إعادةَ أساسٍ تُتلِفها. وضياعُ تشغيلةٍ حتميّ في الترتيبين، فالسؤال أيّهما نضحّي به: شاهدُ إصلاحِ عطلٍ أم شاهدُ ميزةٍ لم تُخفِق قطّ.
- **وما وقع فعلاً:** أُتلِفت الشهادة (`Unit Tests` = `cancelled` على `47e5f596`)، وأُعيد القياس على `8ff58dba` فنجح — ٥٩ فحصاً، ٥٨ ناجحة وواحد متخطّى. الكلفةُ ~٣٥ دقيقة، لا صحّة.
- **وقرارٌ ثانٍ — لم يُدمَج #927 على الإشعار:** وصل `check_suite.completed` يقول «لا شيء يُخفِق» وهو يستثني الملغاة بنصّه. فرُفِض شاهداً، وجُرِدت الوظائف على الرأس الحيّ بدله.
- **حدُّ صدق:** الترتيبُ المُختار **لم يُنتِج خطأً** — أُعيد القياس كاملاً قبل الدمج. الكلفةُ زمنٌ لا مخاطرة، والقرارُ للمالك بحقّ.
- **المصدر:** #927 · #928 · تشغيلات `32840092421` (ملغاة) و`32841607576` (ناجحة).

## 2026-08-25 (ط) — الشريحةُ تبقى في حدود الأمر: P1 وحدها، وP3 يُبلَّغ ولا يُصلَح

- **القرار:** أُصلِحت `Weather P1` وحدها (أربعةُ مواضع + حارسٌ ثلاثيّ الفروع)، و`P3` (`operation_tile_data` 500) رُئي ولم يُمَسّ. فرع `weather-p1-cache-tuple-01` فوق main `293765a8`.
- **السبب:** المالك رتّب ستّ خطوات وسمّى الثالثة «إصلاح/اختبار Weather P1». وإصلاحُ عطلٍ ثانٍ في الشريحة نفسها يُعمّي مراجعتها ويخلط تكذيبَين، والمكسبُ ساعةٌ والكلفةُ وضوحُ الحكم.
- **وقرارٌ ثانٍ — لم يُضَف تراجعٌ إلى المُخبّأ البائت عند فشل الجلب:** `_cached_sample` (`:289`) يفعلها، والأربعةُ لا. وإضافتُها كانت ستُحسِّن الصمود، لكنّها **تغييرُ سلوكٍ** يحتاج شاهدَه الخاصّ — و`503` هي ما كان يقصده الكاتب. أُبقيت كما هي وسُمّي الحدُّ صراحةً بدل أن يُهرَّب تحسينٌ في ثوب إصلاح.
- **وقرارٌ ثالث — الحارسُ ثلاثيُّ الفروع لا فرعٌ واحد:** فرعُ «200 على مخبّأ بارد» وحده يترك طفرتَين حيّتَين. والفرعُ الثالث (البائت يُجدَّد) هو الوحيد الذي يقتل `if series is None` — وهي أقربُ طفرةٍ إلى العطل الأصليّ وأخطرُها لأنّها **صامتة** لا صاخبة: تُقدِّم بياناتٍ قديمةً بجواب `200`.
- **وقرارٌ رابع — لم يُسجَّل شيءٌ في `guard_mutation_registry.json`:** مفاتيحُه سكربتاتُ `scripts/ci/*.py` حصراً (٥١ مفتاحاً، كلُّها كذلك)، وحارسي اختبارُ `pytest` في خدمة. فالتسجيلُ كان سيُقحِم نوعاً لا يعرفه المُشغِّل. التكذيبُ مُسجَّلٌ في رسالة الإيداع وسجلّ الفجوات بدله.
- **حدُّ صدق:** أثرُ الإصلاح مقيسٌ بـ`TestClient` لا بخدمةٍ مرفوعة. و٦ مساراتٍ من ٢٧ تبقى بلا شاهد — مُسجَّلةً `open` لا مُغلَقة.
- **المصدر:** main `293765a8` · `services/weather-service/weather_runtime.py` · `services/weather-service/tests/test_crop_stress_endpoints.py` · مراجعةُ المالك للطقس (P1–P15).
## 2026-08-25 (ي) — التصفيرُ يُزال من المُطبِّع كلّه، والحرارةُ وحدها

- **القرار (للمالك):** إزالةُ التصفير في `normalize_daily` **كلّه** — لا في مسار الأرشيف وحده — بنطاقٍ محصور في `temp_max_c`/`temp_min_c`. فرع `h1-missing-temperature-not-zero` فوق main `293765a8`.
- **السبب المُعلَن:** الكذبةُ واحدة في المسارَين؛ وقصرُ الإصلاح على الأرشيف يُخلِّد نصفَ العطل في التوقّع **بقرار** — وهو ما لا يُبرَّر.
- **وحدُّ النطاق ليس تردّداً:** `precipitation_mm = 0` له قراءةٌ معقولة («لا مطر») والرياح كذلك؛ فتصفيرُهما تقريبٌ مُعلَن لا كذبة، ويبقى قيدُه صادقاً في `_DAILY_ZERO_COERCED_FIELDS`. أمّا `0.0°C` فقراءةٌ فيزيائيّة مشروعة — لا سبيل لتمييزها من الغياب بعد التصفير.
- **وقرارٌ ثانٍ — القيدُ المُعلَن ضاق مع الإصلاح:** إبقاءُ الحرارتين في `_DAILY_ZERO_COERCED_FIELDS` كان سيُبقي الغلافَ يُعلن تصفيراً لم يعد يقع. والقيدُ الكاذب أسوأ من غيابه: يُقرأ **عذراً** فيُبرِّر تجاهلَ قيمةٍ صحيحة.
- **وقرارٌ ثالث — المُنتِج الثاني سُجِّل ولم يُضَمّ:** `connectors/openmeteo.py` يحمل الكذبة نفسها مفروضةً بالنوع (`temp_max_c: float`) وبخمسة مستهلكين. ضمُّه كان يُبدّل حجم الشريحة ويخلط تكذيبَين — نفس المبدأ الذي أبقى P3 خارج P1. سُجِّل `open` بنطاق انفجارٍ مقيس.
- **وقرارٌ رابع — عرضُ التغطية لم يركب مع H1** (حكم المالك): دمجُ بوّابة صحّةٍ بميزة عرضٍ يُعمّي المراجعة. الترتيب: H1 ← H2/H3 ← شريحةُ عرض التغطية.
- **حدُّ صدق:** الحالة **PARTIAL** لا إغلاق. و«لا مستهلكَ انكسر» مقيسٌ على ثمانية فحصتُها بالقراءة، لا على جناحٍ يُغطّيها كلَّها.
- **المصدر:** `sahool-brain/gaps/registry.md` (`WEATHER-NORMALIZER-ZERO-COERCION` تحديث 2026-08-25) · مراجعةُ المالك للطقس · وثيقةُ بحث إغلاق الفجوات (G1).

## 2026-08-25 (ك) — عمرُ المخبّأ يُعَدّ على الخادم لا بساعةٍ تُشارَك

- **القرار:** `TTL(key)` مصدراً للعمر على مسار Redis، لا epoch. فرع `p9-cache-age-server-side` فوق main `aa26c2ab`.
- **السبب:** كلاهما يُصلِح المشاركة، لكنّ `TTL` **يُلغي مسألة الساعات من أصلها** — لا ساعةَ تُكتب ولا تُقارَن ولا تُزامَن؛ العدُّ كلُّه داخل Redis. وepoch يبقيها قائمةً ويُحيلها إلى انضباط NTP بين المُضيفات. ورجّحته وثيقةُ البحث للسبب نفسه.
- **وقرارٌ ثانٍ — `None` لا `0` عند تعذّر العدّ:** الرجوعُ إلى صفرٍ عند فشل `TTL` كان سيُعيد إنتاج العطل بالضبط في الحالة التي وُضِع الإصلاحُ لأجلها. و«لا أعرف» جوابٌ مشروع؛ «طازجةٌ تماماً» ادّعاء.
- **وقرارٌ ثالث — أُسقِط `max(age, TTL_S)`:** كان تخفيفاً لعرَضٍ لا علاجاً لسبب — يرفع رقماً بلا معنى إلى حدٍّ معقول المظهر. وإبقاؤه فوق عدٍّ صحيح كان سيُخفي أخطاءَ العدّ المستقبليّة كما أخفى هذه.
- **وقرارٌ رابع — مسارُ الذاكرة لم يُمَسّ:** التعميمُ «monotonic خطأ» غلط؛ الخطأ **مشاركتُها**. و`_CACHE` داخل العمليّة الواحدة. وحُرِس ذلك باختبارٍ يقتل تصفيرَه، لئلّا يقرأ لاحقٌ الإصلاحَ أوسعَ ممّا هو.
- **حدُّ صدق:** لا خادمَ Redis حيّاً شهد — الاختبارُ الحيّ مشروطٌ بمتغيّر بيئة غير مضبوط في CI. والأثرُ الزمنيّ لنداء `TTL` الإضافيّ **غير مقيس**، وهو بندٌ في سلسلة القياس الزمنيّ التي رتّبها المالك بعد التغطية.
- **المصدر:** مراجعةُ المالك (P9) · وثيقةُ بحث إغلاق الفجوات (G3) · PEP 418 · `cache.py`.

## 2026-08-25 (ل) — الثقةُ تُقاس بحدٍّ أدنى، والمقامُ يُحمَل ولا يُشتقّ

- **القرار:** حدُّ Wilson الأدنى (z=1.645، أحاديّ الطرف عند 95%) أساساً لثقة إشارتَي الصقيع والحرارة. فرع `p4-confidence-wilson-lower-bound` فوق main `cf44cfe1`.
- **السبب:** النسبةُ الخام لا تملك ما تُفرّق به بين 1/1 و24/24. وWald ينهار عند `p̂ = 1` (طولُ فترته صفر ⇒ يقينٌ كامل من أيّ عيّنة)، وWilson يبقى صالحاً عند الأطراف. والإبلاغُ **بالحدّ الأدنى** لا بالتقدير النقطيّ يجعل الرقم دعوى يمكن الدفاع عنها لا أفضلَ حالةٍ ممكنة.
- **وقرارٌ ثانٍ — المقامُ صار مخصوصاً لكلّ حدث، لا محمولاً فحسب.** حملُ `hours_evaluated` مقيساً أصلحَ الاختراع ولم يُصلِح **الوحدة**: الحضورُ ليس فرصةً. فصار لكلّ حدثٍ مقامُه (`frost_evaluable_hours`/`heat_evaluable_hours`)، وWilson فوقه. **والقاعدة:** Wilson لا يُصلِح مقاماً خاطئاً.
- **وقرارٌ ثالث — المقامُ صار محمولاً لا مُشتقّاً.** `build_signal_records` كان يخترعه `max(1, heat, frost)` فيُساويه بالبسط. وWilson فوق مقامٍ مُخترَع تجميلٌ لا إصلاح — يجعل الرقمَ أقلَّ سوءاً في المظهر ويُبقيه بلا أساس. فحُمِل `hours_evaluated` مقيساً في سجلّ التراكب: سطرٌ واحد، بلا هجرة، لأنّ الإدراج يقرأ بالاسم عموداً عموداً.
- **وقرارٌ ثالث — المتناقض يُرَدّ ولا يُقَصّ:** `successes > trials` عدٌّ مستحيل. وقصُّه إلى 1.0 يُترجِم التناقضَ إلى **أقوى** جملةِ ثقة ممكنة — وهو أسوأُ ما يمكن فعله بمدخلٍ فاسد.
- **وقرارٌ رابع — حارسُ اللادليل يشمل الإشارات كلَّها لا الساعيّتَين:** صفرُ ساعاتٍ مُقيَّمة كان يُطلِق `trafficability_poor` بثقة 1.0. وقصرُ الحارس على الصقيع والحرارة كان سيُبقي أسوأ حالةٍ قائمة — «ثقةٌ كاملة من لا شيء» — لأنّ نطاق الأمر ذُكِر فيهما. فالمبدأُ واحد: بلا دليلٍ لا ادّعاء.
- **وقرارٌ خامس — `spray`/`disease`/`trafficability` لم تُمَسّ:** ثقتُها الدرجةُ نفسُها (خلطُ المقدار بالثقة)، وهو صنفٌ آخر؛ وعدّاداتُها غيرُ قابلة للاسترداد من كسرٍ مُقرَّب. تصحيحُها يحتاج حملَ بسطِها كما حُمِل المقام — شريحةٌ أخرى، مُسجَّلة لا مُنفَّذة.
- **حدُّ صدق:** اختبارٌ قائم كان يُثبِّت العطل (`test_confidence_clamped`) واستُبدِل بنقيضه. والتبديلُ جزءٌ من الإصلاح: حارسٌ يحرس كذبةً أسوأ من غياب حارس.
- **المصدر:** مراجعةُ المالك (P4) · وثيقةُ بحث إغلاق الفجوات (G5: NIST/SEMATECH · Wilson) · `core/weather_signals.py` · `core/weather_overlay_pipeline.py`.

## 2026-08-25 (ن) — التغطيةُ تُعرَض قياساً، والعتبةُ تبقى مفتوحة

- **القرار:** عرضُ التغطية على نقطة الأرشيف **بلا عتبةٍ حاجبة**، وتسجيلُ `D5` فجوةً `open`. #935 (`f969da63`) فوق main `c7207e4a`.
- **السبب — بصياغة المالك وهي أدقُّ من صياغتي:** «هناك فرق بين **بيان غير معاير** و**حاجب قرار**». أنا قلتُ إنّ العتبة حكمٌ بلا مرجع؛ وهو بيّن **لماذا لا يُنقذها وسمُ `uncalibrated`**: `collision_confidence = medium` يصف حالةَ معرفتنا، و`coverage < 0.5 ⇒ امنع validated` يصف ما يُسمح به — والوسمُ يعتذر عن الأوّل ولا يُرخّص الثاني، والمزجُ بينهما كذبةٌ بنيويّة.
- **وسببٌ ثانٍ عمليّ — عدمُ التماثل:** إضافةُ عتبةٍ فوق قياسٍ معروض تغييرٌ إضافيّ؛ ونزعُ عتبةٍ صار المستهلكون يقرؤونها كسرُ عقد. فتركُها هو الخيارُ الوحيد القابل للنقض بلا ضرر. وقد مضيتُ به **قبل** وصول ردّ المالك ثمّ أعلنتُه صراحةً — لأنّ تعطيلَ الشريحة على سؤالٍ إجابتُه المحافِظة معروفة ليس حذراً.
- **وقرارٌ ثالث — لا مفردةَ جودةٍ ثانية:** استُعملت `degraded_incomplete_coverage` نفسُها التي يستعملها `gdd_view`، ونفسُ المفاتيح ونفسُ `_expected_days_inclusive`. مفردةٌ ثانية لنفس المعنى تُجبِر كلَّ مستهلكٍ على معرفة **أيّ** منتَجٍ أجابه قبل أن يفهم الجواب.
- **وقرارٌ رابع — بلا تصريحٍ بالمطلوب لا تُختلَق مقارنة:** المطلوبُ لا يُخمَّن من السلسلة نفسها، وإلّا قارنّاها بذاتها فخرجت كاملةً دوماً. وهذا يحفظ التوافقَ للخلف لكلّ مُستدعٍ لا يُمرّر المدى.
- **المصدر:** ردُّ المالك على خيار (أ) · وثيقةُ بحث إغلاق الفجوات (D5: «لا حدّ رسميّ خاصّ بفجوات تراكم GDD — فراغٌ موثّق») · `canonical_weather_state.py` · `canonical_daily_weather_series.py:178-190`.

## 2026-08-25 (س) — الشهادةُ الخارجيّة لا تُقبَل على مظهرها، والفكرةُ تُفصَل عن شيفرتها

- **القرار:** رفضُ وثائق `Semantic Weather Contract` الثلاث (v2 · v2.1 · v2.1.1) بكاملها، وتسجيلُ ثلاثِ أفكارٍ منها فجواتٍ `open` تُبنى عندنا بشهادةٍ وطفرات. فرع `brain-d5-and-external-artifact-lessons`.
- **السبب — مقيسٌ لا مقروء:** v2 أخطأ **مساراته التسعة عشر كلَّها**، وشيفرتُه ترفع `NameError` عند الاستيراد، ومنطقُه يُعلن يوماً ينقصه `temp_max_c` أنّه `VALIDATED` — أي يكسر الثابتَ الذي تُعلِنه وثيقتُه نفسُها. v2.1 صحّح ثلاثةً من ثمانية وأبقى المنطقَ حرفاً بحرف، وأضاف خطأَ أبعادٍ يُنتِج `coverage = 2.0` (بسطٌ يعدّ **متغيّرات** ومقامٌ يعدّ **أيّاماً**) — وهو خطأُ P4 نفسُه. v2.1.1 أضاف هَنَكاً لا يُطبَّق وأعاد تسمية الوسم وأبقى المخالفة.
- **والقاعدةُ التي أخرجها التتابع:** في كلّ دورةٍ عولِج **ما سمّيتُه أنا** ولا ما تفعله الشيفرة. فالمسافةُ بين الوثيقة والشيفرة لم تتقلّص في أيّ دورة — تقلّص الغلافُ وحده. **ولذلك رُفِضت دورةٌ رابعة.**
- **وقرارٌ ثانٍ — الفكرةُ تُفصَل عن شيفرتها:** ثلاثُ أفكارٍ فيها حقيقيّة (تصنيفُ الغياب · `ERA5T ≠ ERA5-final` · شكلُ سجلّ العتبات)، فسُجِّلت فجواتٍ بمصادرَ من شجرتنا لا من الوثيقة. رفضُ الشيفرة لا يستلزم رفضَ ما فيها من صواب.
- **وقرارٌ ثالث — لا رفعَ إلى وجهةٍ خارجيّة:** عُرِض رفعُ الشجرة كاملةً أصلَ إصدار. رُفِض: فعلٌ خارجيٌّ يصعب التراجعُ عنه، وخارجُ نطاق التفويض (شرائحُ داخل المستودع، لا نشرٌ). ويحتاج إذناً صريحاً وتحقّقاً من رؤية المستودع قبله.
- **المصدر:** `git apply --check` (`corrupt patch at line 12` · `patch does not apply` مع `--recount -C1`) · تنفيذُ `from_legacy_dict` معزولاً · `sha256sum` على ٤٤ أرشيفاً · `open_meteo.py:297` · `weather_signals.py:20,22,37`.

## 2026-08-26 (ع) — W4 تُوسِّع بطاقةً قائمة، ولا ترفع بوّابةَ ظهورها

- **القرار:** عرضُ `critical_window` و`critical_window_collisions` داخل `SeasonEvidenceCard` القائمة، لا في بطاقةٍ جديدة. #937 (`2a40271f`) فوق main `49174521`.
- **السبب:** البطاقةُ تُعرّف نفسَها في ترويستها بأنّها تعرض الحقيقة الموحّدة **«كقراءة واحدة»**. وبطاقةٌ ثانية لجزءٍ من المنتَج نفسِه تُنشئ موضعَين للحقيقة الواحدة، فيُجبَر المستهلكُ على معرفة **أيّ** بطاقةٍ أجابته قبل أن يفهم الجواب — وهو ما رفضه كاتبُ W1 بعبارته «تعريفان للحرج أسوأ من غياب الإسقاط».
- **وقرارٌ ثانٍ — العتبةُ تُعرَض بمصدرها وحالة معايرتها:** الخلفيّةُ تحمل `threshold_source` و`calibration: "uncalibrated"`، فيُعرضان لا يُطويان. رقمٌ يحجب قراراً بلا أن يقول من أين جاء هو نفسُه ما تستأصله `D5-COVERAGE-CUTOFF-IS-A-POLICY-WITHOUT-A-REFERENCE-01`. وطيُّه في الواجهة كان سيُحوّل عتبةً غيرَ مُعايَرة إلى حكمٍ يبدو مُعايَراً.
- **وقرارٌ ثالث — «لا يُقاس ولا يُنفى» مفردةٌ مستقلّة:** `insufficient_context` لا تُطوى في `clear`. غيابُ التنبّؤ اليوميّ ليس سلامة، وطيُّهما كان سيجعل المزارعَ يقرأ صمتَ القياس اطمئناناً — وهو الصنفُ الذي أُغلِق في #935.
- **وقرارٌ رابع — بوّابةُ الظهور لم تُرفَع:** البطاقةُ خلف `fieldMode === 'expert' && expertMode` (`MapHub.tsx:2065`). فW4 تُنجِز **العبورَ إلى الواجهة** لا **الإظهارَ للمزارع**. متى تظهر بطاقةٌ قرارُ منتَجٍ لا قرارُ تنفيذ، ورفعُها بلا أمرٍ توسيعٌ للشريحة يُعمّي مراجعتها.
- **حدُّ صدق:** الشاهدُ `@testing-library` لا متصفّحٌ حقيقيّ، والحالةُ `fixed` لا أكثر. وأربعةُ مفاتيحَ باقيةٌ خارج العقد رُئيت ولم تُمَسّ.
- **المصدر:** ترتيبُ المالك (W4) · `hot.md:843` · W1 (`06c7f9fe`) وW2 (`37561b8c`) · `core/gdd_phenology.py:200-225` · `core/season_stage_risk.py:208-320`.

## 2026-08-26 (ف) — النفيُ يحتاج مرجعاً مُنتَجاً، لا مقارنةً متاحة

- **القرار:** سحبُ حكمي على رسالة الأرشيف، وإلحاقُ إبطالٍ صريح بالمُدخَل الذي حمله في #936. فرع `brain-w4-and-the-refutation-that-fell`.
- **السبب:** أنتجتُ الأرشيفَ بنفسي فسقط شاهدان من ثلاثة. **٦٠٧٤** هو ما يطبعه `unzip -l` على `git archive` لهذا المستودع (٥٦٩٦ ملفّاً + ٣٧٨ مجلّداً)، و**١٧٫١ ميغابايت** حجمُ الأرشيف لا ٦١٢ (تلك شجرةُ عملٍ بـ`node_modules`). فقارنتُ عدَّ مُدخلاتِ أرشيفٍ بـ`git ls-files`، وأرشيفاً بشجرةِ عمل.
- **ولماذا لا يكفي الشاهدُ الباقي:** «لا ملفَّ بذلك الحجم أو البصمة بين ٤٤ أرشيفاً» يُثبِت أنّي لم أُنتِج ذلك الملفّ، لا أنّه غيرُ موجود — وأرشيفٌ بأداةٍ أخرى أو ضغطٍ مختلف يختلف حجمُه وبصمتُه شرعاً.
- **القاعدة التي تُستخلَص:** قبل نفيِ رقمٍ، أنتِج المرجعَ الذي يُقارَن به **بنفس الأداة** التي أنتجت الرقمَ المدَّعى. ونفيٌ بلا مرجعٍ مُنتَجٍ دعوى لا قياس.
- **وقرارٌ ثانٍ — الإبطالُ إلحاقاً لا تعديلاً:** قاعدةُ الدماغ append-only، فلم يُحرَّر السطرُ الخاطئ؛ أُلحِق به سطرُ إبطالٍ يُحيل إلى مُدخَلٍ جديد يحمل القياس. **وسجلٌّ يحمل خطأً موسوماً أصدقُ من سجلٍّ نظيفٍ أُعيدت كتابتُه.**
- **وقرارٌ ثالث — ما لا يُسحَب:** أحكامي على وثائق `Semantic Weather Contract` الثلاث تبقى، لأنّها أُثبِتت **بالتنفيذ** لا بالمقارنة. والتصحيحُ يُصيب ما بُني على مقارنةٍ خاطئة ولا يبتلع ما بُني على تشغيل.
- **المصدر:** `git archive` على `49174521` · `unzip -l` · `sha256sum` · `git ls-files` · و`LESSON-FABRICATED-EVIDENCE-MIMICS-THE-SHAPE-OF-PROOF-01` في #936.

## 2026-08-27 — لا تُسجَّل فجوةٌ لم تُقَس، ولو جاءت من المالك

- **القرار:** من اثنتي عشرة فجوةَ طقسٍ واردةً في مراجعة المالك، سُجِّلت **تسع**؛ ورُدَّت **P10** و**نصفُ P8**، وتُرِكت **P13** بلا تسجيل.
- **السبب:** قاعدةُ السجلّ «لا فجوة بلا مصدر + حالة» تعني مصدراً **مقيساً** لا مذكوراً. وتسجيلُ فجوةٍ منقوضة أسوأُ من تركها: يُنفِق عليها وقتَ إصلاحٍ ويُدرِّب قارئَ السجلّ على الشكّ في صفوفه. وP10 مقيسةٌ بالنقض: `state_id` يُسلسِل قيمَ المشاهدة في بصمته.
- **وقرارٌ ثانٍ — الآليّةُ تُقاس لا تُنقَل:** ثلاثُ دعاوى صحّت نتيجتُها (P3 · P7 · P5) وخانتها آليّتُها. وسُجِّلت كلُّها **بآليّتها المقيسة لا الموصوفة**، لأنّ العلاجَ يتبع الآليّةَ لا النتيجة: حراسةُ مفتاحٍ لا تُصلِح `None`، وإسقاطُ سقفٍ يختلف عن تكميمه.
- **وقرارٌ ثالث — P2 صُحِّح في العميل لا في الخدمة:** تغييرُ مسار الخدمة كان يكسر أيَّ مستهلكٍ آخر يناديه بالاسم القانونيّ، والقفزةُ المُصلَحة داخليّة؛ ومسارُ المنصّة العامّ يبقى كما هو.
- **وقرارٌ رابع — العلاجُ في `operation_suitability` لا في موضع النداء:** آليّةُ الفشل المغلق قائمةٌ بعده بخطوة، والسطرُ الواحد في المدخل يغطّي الأفعالَ الخمسة.
- **حدُّ صدق:** الفجواتُ التسع **مُسجَّلةٌ لا مُصلَحة** — سبعٌ `open` بعلاجاتٍ مُقترَحةٍ موصوفة، واثنتان `fixed` بحارسَيهما المُكذَّبَين.
- **المصدر:** قياسُ هذه الجلسة · main `a97e347` · مراجعةُ الطقس الواردة من المالك.

## 2026-08-27 (ب) — الاحتياطُ الذي نجا من طفرته يُحذَف، لا يُسجَّل

- **القرار ①: يُحذَف الاحتياطُ الذي نجت طفرتُه، ولا تُسجَّل طفرةٌ بديلةٌ تُجمِّله.** سجّلتُ في `no_manual_backup_files_guard` طفرةً تُسقِط عزلَ اسم الملفّ (`rsplit("/", 1)[-1]`) وتوقّعتُ احمراراً — فنجت. **والسبب:** كلُّ بدائل النمط مرساةٌ بـ`$`، ونهايةُ المسار هي نهايةُ الاسم. فالعزلُ لم يكن يمنع شيئاً. **والبديلُ المرفوض** أن أُبقيه وأصوغ اختباراً يُحمِّرها بحالةٍ مُصطنَعة — فتُسجَّل «تغطية» على خاصّيّةٍ لا تُحرَس. **احتياطٌ لا يمنع شيئاً أسوأُ من غيابه: يُقرَأ ضماناً ويُعَدّ تغطية.** حُذِف، والخاصّيّةُ باقيةٌ مفروضةً بآليّتها الحقيقيّة (المِرساة).
- **القرار ②: قائمةُ الإعفاء تحمل سقفاً نازلاً، والسقفُ يفشل في الاتّجاهين.** المقيس: عشرةُ مداخلَ في `composite_residuals_pending_p4` كلُّها «pending P4» منذ الكنس الأوّل، ولا شيءَ يحمرّ لو بقيت سنة. **وإعفاءٌ بلا سقفٍ نازل ليس ديناً مؤجَّلاً بل شطبٌ صامت.** و`<= ceiling` وحدَه لا يكفي: إغلاقُ مُعفًى بلا خفضِ السقف يترك مقعداً شاغراً يعود إليه مخالفٌ صامتاً. فالشرطُ **مساواة**.
- **القرار ③: يُصحَّح الحارسُ بدل صياغةِ النثر للالتفاف عليه.** كشفُ `test_p3_5_weather_direct_wiring_final_sweep` كان نصّيّاً، فتعليقي الذي يشرح هجرَ الموصّل أبقى الملفَّ «مخالفاً» — أي أنّ توثيقَ الإصلاح يُبطِله. **البديلُ الأرخص** إعادةُ صياغة تعليقي ليتفادى السلسلة؛ ورُفِض: يُخفي أنّ الحارسَ يقرأ نثراً، ويُبقي `from api.connectors import openmeteo` (صفرُ مطابقات، مقيس) و`fetch_bundle` مُفلِتَين. صار الكشفُ بـ`ast`.
- **القرار ④: يُحفَظ قسرُ المطر المفقودِ إلى صفرٍ في `irrigation-advice`، ويُسجَّل فجوةً.** تغييرُه يُحوِّل ردّاً قائماً إلى ٥٠٣ أو يُوسِّع عقدَ `irrigation_advice` — وكلاهما قرارُ منتَج لا أثرٌ جانبيٌّ مشروعٌ لنقلِ واجهة. **وإصلاحٌ صادقٌ يكسر مستهلكاً صامتاً يُبدِّل عطلاً بعطل.** سُجِّل `IRRIGATION-READS-MISSING-RAIN-AS-NO-RAIN-01` ووُثِّق في موضعه بالكود.
- **القرار ⑤: يُسجَّل صنفُ «العقدِ المختبَرِ طرفَين متفرّقين» `open` لا `fixed`.** الحوادثُ الثلاثُ مُغلَقةٌ بثلاثة شهودِ قفزة، **والصنفُ لا**: لا شيءَ يُلزِم عقداً جديداً بشاهد. والحارسُ يلزمه جردُ العقود العابرة أوّلاً — وحارسٌ بلا جردٍ يُعلِن تغطيةً لا يملكها (`MUT-REGISTRY-STRANDED-SPECS-01`).
- **حدُّ صدق:** القياسُ المحلّيُّ لا يشهد للطفرات في هذه الحاوية — `cryptography` تنهار فتُسقِط `conftest`، وتُبلَّغ كلُّ طفرةٍ فشلاً واحداً بلا اسمِ اختبار (`RUNNER-CRASH-READS-AS-A-TEST-FAILURE-…-01`). كُذِّبت الخمسُ يدويّاً بـ`--noconftest`، والشاهدُ الحاجبُ هو CI.
- **المصدر:** فرع `claude/weather-p6-p15` فوق main `e01b57ac`.

## 2026-08-27 (ج) — الحارسُ يُشتقّ نطاقَه، والاختبارُ يحتاج شاهداً موجباً

- **استدراكُ بصمة:** شريحةُ P6/P15 دُمِجت في **`7c118b54`** (#951). مدخلُ 2026-08-27 (ب) أعلاه كُتِب قبل الدمج فحمل الأساسَ لا البصمة — **لا يحمل PR بصمةَ نفسِه**، والاستدراكُ في الشريحة التالية هو الشكلُ الوحيد الممكن.
- **القرار ①: نطاقُ الحارس يُشتقّ من الشجرة، لا يُكتَب.** العملاءُ يُعرَّفون بحملهم عنوانَ خدمةٍ داخليّة (`http://sahool-<اسم>-service`)، ومنه تُشتقّ الخدمةُ الهدف. **والقياسُ حسم البديل:** جردي اليدويّ عدّ أربعةَ عملاء، والاشتقاقُ وجد ثمانية. فقائمةٌ مكتوبةٌ كانت ستحرس النصفَ وتُعلِن الكلّ — وهو **أسوأُ من لا حارس**، لأنّ خضرتَها تُقرأ تغطيةً.
- **القرار ②: يُقابَل قارئان، ولا يُوثَق بقارئٍ واحد.** ثلاثةُ ثقوبٍ في المستخرِج، **ولا واحدٌ منها ظهر بقراءةٍ واحدة**؛ كلُّها ظهرت بفارقِ عددٍ بين `ast` وتعبيرٍ نمطيّ مستقلّ. **قارئٌ واحدٌ لا يُكذِّب نفسَه**، والصفرُ الذي يُنتِجه يُقرأ عقداً نظيفاً وهو عمًى. المقابلةُ مُثبَّتةٌ في الاختبار لئلّا تُفقَد، وباتّجاهٍ أحاديّ (البنيويُّ يرى كلَّ ما يراه النصّيّ وزيادة) كي لا تمنع توسيعَه.
- **القرار ③: تأكيدُ الغياب يحتاج شاهدَ حضور — ويُصلَح الاختبارُ لا يُحذَف الكود.** طفرةٌ تُطفئ كشفَ العمى **نجت**، لأنّ شاهدَها كان «القائمةُ فارغةٌ على شجرةٍ سليمة» — وهي تبقى فارغةً إن عُطِّل الكشف. أُخرِج التصنيفُ دالّةً نقيّةً تُقاس بمُدخَلٍ مُصطنَع. **والفرقُ عن قرار أمس (حذفِ احتياطٍ نجت طفرتُه) فرقُ موضعِ العطل:** هناك كان الكودُ بلا أثرٍ فحُذِف، وهنا الآليّةُ حقيقيّةٌ والشاهدُ ناقصٌ فأُصلِح الشاهد. **والطفرةُ الناجية تشخيصٌ لا حكم** — تقول «شيءٌ هنا لا يُقاس»، ولا تقول أيَّ الطرفين يُصلَح.
- **حدُّ صدق:** صفرُ انحرافٍ في العقود الثمانية اليوم. فالحارسُ يمنع القادمَ ولا يُصلِح قائماً، **وخضرتُه ليست إنجازاً**.
- **المصدر:** فرع `claude/cross-service-hop-witness` فوق main `7c118b54`.

## 2026-08-27 (د) — يُقاس البلاغ، ويُسحَب المكرّر ولو كان أصحّ ما بنيتُ اليوم

- **القرار ①: التشخيصُ والإطارُ يُفصَلان في الحكم.** بلاغُ M-01…M-06 صحيحُ التشخيص بالسطر، وإطارُ تنفيذه ساقطٌ كلُّه. **وردٌّ يقبل الكلَّ أو يرفض الكلَّ يُضيّع النصفَ الصحيح.** فقُبِل التشخيصُ ورُفِض الإطارُ بأدلّته.
- **القرار ②: لا أدفع عملَ جلسةٍ أخرى ولا أُعيد إنتاجه بلا أمر.**
- **القرار ③ — وهو الأثقل: يُسحَب حارسي المكرّر كاملاً.** بنيتُ `declared_writer_ownership_guard` ثمّ تبيّن أنّ #952 يحمل `db_writer_ownership_guard`، أوسعَ (٧٥ مخالفةً على عشر خدمات مقابل ٥٤ على واحدة) وأصحّ (يُعفي خمسةَ جسورٍ موثَّقة لا يعرفها حارسي). **حارسان يقيسان الخاصّيّةَ نفسَها بأساسَين منفصلين ينحرفان ويتعارضان — وذلك أسوأُ من غياب أحدهما.** والبديلُ المرفوض: إبقاؤهما بحُجّة أنّ عملي مقيسٌ ومُكذَّب؛ وجودةُ الشيء لا تُبرّر ازدواجَه.
- **القرار ④: يُجرَد القائمُ قبل البناء لا بعده.** الخطأُ لم يكن في الحارس بل في ترتيبي: بنيتُ فوق سطحٍ لم أجرده، بعد أن قِستُ التكرارَ مع #950 بساعات. **قاعدةٌ تُطبَّق على النفس كما تُطبَّق على الغير: قبل بناء حارسٍ لصنفٍ، اجرد PRs المفتوحة والحرّاسَ القائمة على الخاصّيّة نفسِها.**
- **وما نجا من القياس بقي نافعاً:** تنفيذان مستقلّان اشتقّا الجداولَ الأربعةَ والخمسين نفسَها بصفر فرق — **تصديقٌ متبادَلٌ للرقم** يرفع الثقةَ فيه ولو أسقط أحدَ التنفيذين.
- **حدُّ صدق:** لم أقِس بقيّةَ #952 (بطاقةَ التحكيم · اكتشافَ `SKIP LOCKED` بلا معاملة) قياساً مستقلّاً — قِستُ تقاطعَه مع عملي وسَعتَه. فحكمي «أوسعُ وأصحّ» مبنيٌّ على ذلك وحدَه.
- **المصدر:** قياسُ هذه الجلسة على `7c118b54` · #952 (`m03-ownership-truth`) · بلاغُ الجلسة المحلّيّة.
- **حدُّ صدق:** لم أقِس بقيّةَ #952 (بطاقةَ التحكيم · اكتشافَ `SKIP LOCKED` بلا معاملة) قياساً مستقلّاً — قِستُ تقاطعَه مع عملي وسَعتَه. فحكمي «أوسعُ وأصحّ» مبنيٌّ على ذلك وحدَه.
- **المصدر:** قياسُ هذه الجلسة على `7c118b54` · #952 (`m03-ownership-truth`) · بلاغُ الجلسة المحلّيّة.

## 2026-08-28 (ب) — تفويضٌ مقيَّد لا فتحُ بوّابة: اختار المالكُ الأضيقَ بعد أن رأى نصَّ السياسة

- **القرار ① — الأداةُ اختيرت بعد تصحيحِ معلومةٍ ناقصة، لا قبله.** عُرِضت أوّلاً أربعةُ خيارات فاختار المالكُ «انقل GATE-01 إلى OPEN». ثمّ فُتِح الملفُّ فظهر فيه نصّان لم يكونا أمامه: `why_open_is_not_a_pr_exception_ar` ينهى عن **هذا الانتقال بعينه ولهذا السبب بعينه** («لا transition من CLOSED إلى OPEN لمجرّد أنّ رقعةً تحتاج لمسَ ملفّ»)، ودلالةُ `OPEN` أنّها **إقرارُ اكتمالِ المرحلة ٠** لا إذنُ رقعة — والمقيس `runtime_verified=0`. فأُعيد العرضُ بالنصّين، فاختار المالكُ التفويضَ المقيَّد. **والقاعدة: معلومةٌ ماديّةٌ ظهرت بعد القرار تُعرَض، ولا يُنفَّذ قرارٌ بُني على نقصها.**
- **القرار ②: الإصدارُ فعلُ المالك، والحارسُ لا يُوقِّع.** قُرِئ `_authorization_errors` كاملاً: **لا تحقّقَ تشفيريّاً من توقيع** — يُفحَص المخطَّطُ والحالةُ والأساسُ والمسارات والبصمة. فكتابةُ السجلّ **هي** الإصدار، والبوّابةُ تقوم على انضباط من يكتبه لا على مفتاح. ولذلك لم يُكتَب بمبادرةٍ منّي، وكُتِب بأمرٍ صريح.
- **القرار ③: التفويضُ يُكذَّب قبل أن يُقبَل.** خمسُ حالات: سليمٌ ⇒ 0 · بايتٌ مُغيَّر في مأذون ⇒ 1 · مسارٌ مجمَّدٌ ثالث ⇒ 1 · `CONSUMED` بدل `ISSUED` ⇒ 1 · استُعيد ⇒ 0. **والخامسةُ ليست زينة:** بدونها لا يُعرَف أنّ الثلاثةَ سقطت لأسبابها لا لأنّي كسرتُ شيئاً.
- **القرار ④: يُعلَن حدُّ الأداة لا يُستَر.** الهجرةُ `v228_worker_claim_lease.sql` **ليست في المأذون** — لأنّ `frozen_paths` تُسمّي الملفَّ نفسَه باسمٍ آخر فلا يلتقطه الحارس، ولأنّ `blobs` تُبنى من `frozen_paths` وحدَها فإدراجُ غيرِ مجمَّدٍ يُفشِل التفويض. سُجِّل في `$scope_limit_measured_ar`: **الثغرةُ في الحارس لا في السجلّ.**
- **دَينٌ لازمٌ بعد الدمج:** لا شيء يُحوِّل `ISSUED` إلى `CONSUMED` آليّاً. فبعد دمج #954 يجب الختمُ بـ`merge_sha`، وإلّا أحمرّ `stale_authorization_errors` على `main` — وهي `GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01`.
- **حدُّ صدق:** التفويضُ يأذن بالمسّ ولا يشهد بالصحّة، والبوّابةُ تبقى `CLOSED` بعد استهلاكه. ولم تُقَس المرحلةُ ٠ ولم يُدَّعَ اكتمالها.
- **المصدر:** `docs/architecture/gates/adjudications/GATE01-ADJ-2026-08-28-001.json` · داخل #954 نفسِها (`claim-lease-tx`) فوق main `90df6145`.
- **وخطأٌ في التغليف أمسكته اختباراتُ المستودع:** وضعتُ التفويضَ أوّلاً في شريحةٍ مستقلّة فوق `main`، فسقط `test_the_live_authorization_matches_the_tree_it_authorises`: تفويضٌ `ISSUED` يجب أن تُطابِق بايتاتُه **الشجرةَ التي يعيش فيها**، وشجرةُ `main` لا تحمل الرقعةَ بعد. فموضعُه داخل الـPR التي يأذن لها — وهو ما يقوله سجلُّ 2026-08-13 حرفيّاً: «مِلَفُّ التفويض نفسه يُلتزَم بعد الرقعة». نُقِل، ولم يُضعَّف الاختبار.

## 2026-08-28 (ج) — الاختبارُ يُصلَح لأنّه يقيس اللقطة، لا لأنّه يمنع تفويضي

- **القرار ① (المالك): لا يُفتح GATE-01، ولا يُعدَّل الحارس، ولا تُحذَف الآليّة.** ويُفحَص التأكيدُ ذو `set()` المُصمَتة بسؤالٍ واحد: **أيَّ ثابتٍ سياسيٍّ يُمثّل؟** فإن كان جوابُه «الشجرةُ بعد #837 لا تحمل `ISSUED`» فهو تثبيتُ حالةٍ لا ثابت.
- **والجواب قِيس لا خُمِّن:** `ISSUED ⇒ بايتاتٌ حاضرة` (اختبارٌ) و`بايتاتٌ حاضرة ⇒ يُرصَد` (اختبارٌ آخر) ⇒ `ISSUED` مستحيلة. والحارسُ بريء: بالمسّ الحقيقيّ صفرُ أخطاء.
- **القرار ②: يُنزَع الضلعُ المعطوب وحدَه ويُستبدَل، لا يُضعَّف الاختبار.** بقيت أضلاعُ الاختبار الثلاثة (لا يمنح · يحجب · يذكر CONSUMED)، ونُزِع التأكيدُ الرابع وحدَه، وأُضيف اختبارُ علاقةٍ كامل. **والفرقُ عن «تعديل اختبارٍ ليمرّ تغييري» فرقُ اتّجاهِ الحجّة:** لو كان التأكيدُ يقيس ثابتاً لَوَجَب سحبُ التفويض؛ قِيس فتبيّن أنّه يقيس تاريخاً.
- **القرار ③: تُتجنَّب الدائريّة صراحةً.** التوقّعُ من `gate01_policy.json` وإعلانِ السجلّ، والواقعُ من `git hash-object` — ثلاثةُ مصادر. ولو كُتِب `expected = discover_actual_tree()` لمرّ على أيّ شجرة، وهو تحصيلُ حاصلٍ يُقرأ حراسة.
- **القرار ④: تُسجَّل الطفراتُ الدائمةُ وحدَها.** أربعٌ على السجلّ المختوم (لا يتغيّر)، واثنتان تخصّان `ISSUED` تُرِكتا يدويّتين لأنّ التفويضَ الحيَّ يُختَم بعد الدمج فتبيت مرساتُهما — وهو `STABLE_WRONG_TEST` الذي يحذّر منه `CLAUDE.md`. **والتسجيلُ الذي يبيت أسوأُ من غيابه.**
- **حدُّ صدق:** القاعدةُ المستخلَصة موضعُها IFOTS، **ولا وجود لتلك الوثيقة في الشجرة** — فسُجِّلت في الدماغ ولم يُدَّعَ تعديلُها. والتفويضُ لم يُدمَج بعد، والبوّابةُ تبقى `CLOSED`.
- **المصدر:** `tests_v9/test_gate01_frozen_path_guard.py` · `docs/architecture/guard_mutation_registry.json` · داخل #954 (`claim-lease-tx`) فوق main `90df6145`.

## 2026-08-28 (د) — الشيفرةُ تمرّ والحوكمةُ تقف: NO-GO حتّى مراجعةٍ مستقلّة

- **حكمُ المالك على #954 (رأس `9f16ae8a`):** **الكود GO · الحوكمة NO-GO** حتّى تتحقّق مراجعةُ مالكِ كودٍ **من طرفٍ مستقلّ**. والمسارُ المُقرَّر: مالكُ كودٍ ثانٍ للمسار ⇐ `Require review from Code Owners = ON` مع `Enforcement = Active` ⇐ مراجعةٌ من غير صاحب الـPR ⇐ دمج ⇐ **ثمّ** ختمُ `GATE01-ADJ-2026-08-28-001` بـ`CONSUMED` و`merge_sha`. وGATE-01 تبقى `CLOSED` في كلّ ذلك.
- **وأربعةُ أبوابٍ أُغلِقت بالنصّ لا بالسكوت:** لا مصادقةَ من حساب صاحب الـPR · لا `bypass` للـruleset · لا إعادةُ `@kafaat` مالكاً ثانياً · لا تعديلَ للتفويض للالتفاف على المراجعة. **وكلُّها كانت ممكنةً تقنيّاً** — والمنعُ حكمٌ لا عجز.
- **القرار ①: الحاجزُ الأخيرُ ليس عطلاً، فلا يُعامَل معاملةَ العطل.** `branch_protection_contract_guard` يُخرِج `✗` واحدةً فقط (`require_code_owner_review = [False]`)؛ فالبندان العامّان (PR مطلوبة · حلُّ المحادثات) **محقَّقان سلفاً**، والناقصُ إعدادٌ واحد. وتشخيصُه صحيح: `approved_by: "owner"` حقلٌ نصّيٌّ في ملفٍّ داخل الـPR نفسِها، ولا يُثبِت منشأً.
- **القرار ②: يُقاس تاريخُ الحارس قبل أن يُروى.** كتبتُ في تعليق الـPR أنّ البند «بقي خامداً لأنّ أحداً لم يمسّ المسار»، ثمّ أوحى تعليقٌ في الـworkflow أنّ السبب اشتقاقٌ فارغ (`no merge base` تحت عمق ١). فرجعتُ إلى التاريخ: ذلك العطلُ أُصلِح في **#844 يوم 2026-08-14**، فالاشتقاق يعمل منذ أسبوعين (`— المسارات المشتقّة: 56 —`). **فروايتي الأولى كانت صحيحة، وكِدتُ أستبدلها بأخرى خاطئة اعتماداً على قراءةِ تعليقٍ يصف تاريخاً لا حاضراً.** والقاعدة: تعليقٌ في الشيفرة يصف عطلاً **لا يقول متى أُصلِح** — يُسأل التاريخُ لا النصّ.
- **حدُّ صدق:** لم يُدمَج شيء، ولم تُفعَّل قاعدةٌ، ولا مراجعةَ مُقدَّمة على #954 حتّى الآن. والتفويضُ يبقى `ISSUED` غيرَ مختوم — وهو الوضعُ الصحيح ما دامت الرقعةُ لم تهبط.
- **المصدر:** #954 عند `9f16ae8a` · حكمُ المالك 2026-08-28 · [تعليق الحاجب](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/954#issuecomment-5454402794).

## 2026-08-27 (هـ) — تُحسَب الإحصاءاتُ داخل المجموعة، ولا يُؤخَذ الثباتُ شاهداً وحدَه

- **القرار ①: نطاقُ الإحصاء هو المجموعةُ المرئيّة لا المُرشَّحة.** `{tenant_id, __global__}` — نفسُ ما يرشّح عليه البحثُ الكثيف. **والسبب:** حصرُه بالمُرشَّح كان سيجعل `idf` دالّةً في مرشِّح الاستعلام نفسِه، فتتبدّل ندرةُ المصطلح بتبدّل سؤالٍ واحد — عطلٌ أوسعُ من المُغلَق. **والمرفوض:** هجرةُ المخزَن؛ العلاجُ عند القراءة يشفي الصفّ لحظةَ تحليله.
- **القرار ②: `score` يطلب `tenant_id` صراحةً ولا يفترضه.** **والسبب:** «مستأجِرُ الوثيقة» افتراضٌ يبدو مقبولاً ويكون خاطئاً — وثيقةُ المرجع العامّ تُقاس داخل مجموعة **السائل**. وافتراضٌ صامتٌ يُعيد العطلَ من بابٍ آخر بلا أن يُحمِّر شيئاً.
- **القرار ③: المجاميعُ العالميّة تُشتقّ ولا تُمسَك.** **والسبب:** «لا انحرافَ بالبناء» أقوى من «اختبارٌ يفحص الانحراف» — ونسختانِ تُحدَّثان بيدَين تنحرفان صامتتَين. وبقيتا معروضتَين للجرد التشخيصيّ، **ولم تعودا مُدخَلاً في الترتيب**.
- **القرار ④ — وهو الأهمّ منهجيّاً: لا يُقبَل تأكيدُ ثباتٍ بلا شاهدِ حركة.** «الدرجةُ لم تتحرّك» يبقى صادقاً لو صارت `score` تُعيد صفراً أبداً. **والسبب:** هو `assertion_presence_guard` بعينه في طبقةٍ أخرى — تأكيدُ غيابٍ يقيس سكونَ العيّنة لا عملَ الآليّة، وقد أمسكه المراجعُ الآليّ عليّ في #953 فطُبِّق هنا **قبل** أن يُمسَك.
- **القرار ⑤: تُوجَّه الطفرةُ غيرُ القابلة للقتل ولا يُحدَّث اسمُها.** `"present": False` صارت بعد الإغلاق تُعطي الاختبارَ ما يؤكّده. **والسبب:** `MUT-REGISTRY-STRANDED-SPECS-01` — تحديثُ `expect` كان سيُسجّل تغطيةً لا تملكها. **ثاني مرّةٍ في يومين**، وقد صارت نمطاً مُتوقَّعاً لا مفاجأة: **إغلاقُ عطلٍ يُبطِل الطفرةَ التي كانت تحرسه، فتُوجَّه إلى نصفِ النزاهة الآخر — الإنذارِ الكاذب.**
- **حدُّ صدق:** الزرعُ الآليّ لم يُشغَّل هنا — `--run` يموت على `pyo3` في `cryptography`، **والمُسجَّلات الستُّ السابقة على الملفّ نفسِه تسقط بالعطل عينِه**، فهو بيئيٌّ لا منطقيّ. التكذيبُ يدويٌّ بـ`--noconftest`، **وCI هي الشاهد** لا هذا الاستنساخ.
- **المصدر:** فرع `claude/rag-bm25-corpus-scope` فوق main `157a9cb4` · [`guard_mutation_registry.json`](../../docs/architecture/guard_mutation_registry.json) (`behavioural` · `production_qdrant.py[6..8]` · `rag_corpus_admissibility_probe.py[1]`).

## 2026-08-30 — يُعاد القياسُ لأنّ الاسمَ كذب، لا لأنّ شيئاً احمرّ

- **القرار ①: مرساةٌ صار اسمُها كاذباً تُعاد وإن لم تُحمِّر بوّابة.** `MEASURED_SLOWEST_MINUTES = 34.7` والأبطأُ المقيسُ ٣٧٫٢٣. **والسبب:** الشجرةُ خضراءُ بكلّ بوّاباتها، والثابتُ مع ذلك يصف كوناً لم يعد قائماً ويُقرَأ عقداً حيّاً — وهو صنفُ العطل الذي يطارده هذا المستودع نفسُه. **والانتظارُ حتّى يحمرّ يعني الاكتشافَ بعد حرقِ تسعين دقيقة.**
- **القرار ②: لا يُدَّعى وقوعُ الشرط الذي لم يقع.** كان الملفُّ يقول «إن قاربت جولةٌ الستّين ثانيةً فالمرساةُ بائتة» — **ولم تقاربْ**. **والسبب:** أسهلُ تبريرٍ متاحٍ كان استدعاءَ ذلك الشرط، وهو ادّعاءُ حادثةٍ لم تقع لشرعنةِ فعلٍ صحيح. السببُ الحقيقيُّ أضعفُ صوتاً وأصدق: **الاسمُ كذب.**
- **القرار ③: تُشتقّ العلامةُ بالصيغة القائمة ولا تُبدَّل الكلفةُ المتحفّظة.** ٥٥٢ ⇒ ٥٧٤ بالصيغة نفسِها والكلفة نفسِها (٠٫٧٧٥د). **والسبب:** ستُّ جولاتٍ في يومٍ واحد أظهرت تشتُّتاً **عند العدد الثابت نفسِه ٦٫٠٤ دقيقة** — من رتبة الفرق بين الأعداد. فهي **لا تقيس كلفةً حدّيّة**، واستبدالُ المتحفّظة بـ«مشتقّةٍ من الواقع» كان سيبني رقماً على تشتُّتٍ لا على أثر.
- **القرار ④: تُسمّى العلامةُ بما هي.** ارتفعت والجولةُ أبطأ. **والسبب:** الصيغةُ تقيس من النقطة المقيسة، وعلاجُ بلوغِها يُحرِّكها هي نفسَها — **فهي مِشعَلُ إعادةِ قياسٍ لا سقفٌ على النموّ**. وتركُها تُقرَأ سقفاً كان يجعل ارتفاعَها اليومَ يبدو تلييناً للبوّابة.
- **القرار ⑤: يُضاف حدُّ انجرافٍ مشتقٌّ لا رقمٌ ثالثٌ يُكتَب بيد.** `RE_MEASURE_DRIFT_CEILING` = نصفُ الهامش ⇒ ٥٤٠. **والسبب:** البياتُ الصامت هو العطلُ المقيس (٤٨١ ⇒ ٥٠٩ بلا حمرة)، والعلامةُ وحدَها تنطق متأخّرةً بعلاجٍ أغلى. **والاشتقاقُ لا الكتابةُ** لأنّ رقماً ثالثاً ينحرف عن الرقمين اللذين يُفترَض أن يقع بينهما.
- **القرار ⑥: كلُّ تأكيدٍ على الغياب يُقرَن بشاهدِ حضور — والمرّةُ الأولى التي يُوجَد فيها الثقبُ قائماً لا مُستبَقاً.** السقفانِ يمرّان أخضرين والمقياسُ منهار: ٥٠٩ ⇒ ٣٣٨ بإعادة تسمية قسم. **والسبب:** `assertion_presence_guard` نفسُه، مُطبَّقاً ثلاثَ مرّاتٍ استباقاً في عنقود RAG، وهنا **مقيسٌ بالتكذيب على شجرةٍ قائمة**.
- **القرار ⑦: يُصرَّح بالاستثناء البنيويّ ولا يُترَك صمتاً.** لا طفرةَ مُسجَّلةً للشاهد الموجب: مُكذِّبُه الوحيدُ تعديلُ `guard_mutation_registry.json`، **وهو مُدخَلُ عدّاءِ الطفرات ذاتِه**. **والسبب:** «غيرُ مُسجَّل» بلا تعليلٍ يُقرَأ تهاوناً؛ والتكذيبُ وقع يدويّاً ومُدوَّنٌ بأرقامه.
- **القرار ⑧: يُصحَّح دَينٌ مُعلَنٌ كان نصُّه أضعفَ من القياس.** «اسمٌ لن يُمَسّ» (تنبّؤ) ⇒ «**صفرُ التزام على كلّ المراجع**» (قياس)، مقابل ٧٦ لنظيره القائم. **والسبب:** صياغةٌ أضعفُ من الدليل تُضعِف الحجّةَ التي تقوم عليها فجوةٌ مفتوحة.
- **حدُّ صدق:** الحدُّ الجديد يقيس بياتَ **الاقتران** لا بياتَ **الزمن** — جولةٌ تبطؤ بلا نموِّ سجلٍّ تمرّ خضراء، والقياسُ الزمنيُّ يبقى فعلاً بشريّاً دوريّاً. **والزرعُ الآليّ لم يُشغَّل:** `--run` يموت على `pyo3` في `cryptography`، **وقد أُثبِت أنّه بيئيّ بإعادة التشغيل على شجرةٍ نظيفة (`git stash`) فسقط بالعطل عينِه**. التكذيبُ يدويٌّ بـ`--noconftest`، **وCI هي الشاهد**.
- **المصدر:** فرع `claude/mut-sweep-anchor-remeasure` فوق main `5112a613` · [`test_mutation_sweep_headroom.py`](../../tests_v9/test_mutation_sweep_headroom.py) · جولات CI ٣٣٢٥٩٦٥١٢٠٩ → ٣٣٢٦٩٠٤٦٤٣٧.

## 2026-08-29 — يُحرَس الصنفُ ولا يُوحَّد الاسم، ويُسحَب تحفّظٌ سقط بالقياس

- **القرار ①: يُحرَس الاتّساعُ ولا يُنفَّذ التوحيد.** **والسبب:** توحيدُ الاسم يمسّ ثلاثَ عائلاتِ سياسات، **وشكلُ الخطأ فيه صامتٌ لا حاجب** — صفرُ صفوفٍ بلا شكوى. فهجرةٌ كهذه قرارُ ترتيبٍ وقياسٍ للمالك، بينما منعُ الاسم الرابع رخيصٌ وفوريٌّ ولا يحتاج إذناً.
- **القرار ②: نطاقُ الحارس يُشتقّ من الاسم لا من قائمة** (`app.*tenant*`). **والسبب:** قائمةٌ مكتوبة تبيت — اسمٌ رابع لا يدخلها، فيبقى الحارسُ أخضرَ عن سؤالٍ لم يعد يطرحه.
- **القرار ③: يُستبعَد `app.current_role` و`app.current_user_id` بالاشتقاق.** **والسبب:** انحرافُهما عطلُ تفويضٍ لا عطلُ عزل — إدخالُهما كان يُوسِّع الادّعاءَ فوق الدليل المقيس.
- **القرار ④ — وهو الأهمّ منهجيّاً: كلُّ كاشفٍ يُقاس بالإيجاب.** كلُّ تأكيدٍ على شجرةٍ سليمة هنا تأكيدُ **غياب** يبقى صادقاً لو عُطِّل الكشفُ رأساً. **والسبب:** `assertion_presence_guard` بعينه في طبقةٍ أخرى — أمسكه مراجعٌ آليّ عليّ في #953، فطُبِّق هنا **قبل** أن يُمسَك، بأربعة شهودٍ موجبةٍ على تقاريرَ مُصطنَعة.
- **القرار ⑤: يُسحَب تحفّظٌ سقط بالقياس.** ادّعيتُ فشلاً مفتوحاً في `WITH CHECK` فوجدتُه **اختياراً معلَناً بنصّ كاتبه**. **والسبب:** الحكمُ يتبع القياس؛ وتركُ ادّعاءٍ منقوضٍ قائماً يُفسِد كلَّ ما بعده. **والقاعدة: يُقرأ تعليلُ الكاتب قبل أن يُصنَّف اختيارُه عطلاً.**
- **حدُّ صدق:** الحارسُ يمنع **اتّساعَ** الانحراف ولا يُصلِح القائم. **خضرتُه تعني «لم يتّسع» لا «وُحِّد»** — والفجوةُ تبقى `open`.
- **المصدر:** فرع `claude/tenant-guc-convergence` فوق main `99000487` · [`guard_mutation_registry.json`](../../docs/architecture/guard_mutation_registry.json) (`tenant_guc_name_convergence_guard.py[0..2]`).
## 2026-08-28 — يُقاس المفتاحُ قبل أن يُبنى عليه، والفرضيّةُ تُكذَّب قبل أن تُكتَب

- **القرار ①: لا يُدمَج رأسٌ لم تُقَس عليه البوّابات.** أُخِّر دمجُ #956 حتّى أنهت *Unit Tests* على `04026b7d` (٥٩ فحصاً). **والخُضرةُ المحلّيّة لا تُغني** — سقطت `pytest-contracts` و*Unit Tests* في هذه الجلسة بعد خُضرةٍ محلّيّة، مرّتين. (#956 ⇒ `90df6145`)
- **القرار ②: لا يُدمَج ما تحجبه بوّابةُ حوكمة ولو أُذِن بالدمج.** أمرُ «قوم بالدمج» نُفِّذ على #957 و#956 ولم يُنفَّذ على #954: `GATE-01` يحجبه، **ودمجُه تجاوزُ البوّابة لا استعمالُ الإذن**. والإذنُ في الدمج ليس إذناً في رفع التجميد.
- **القرار ③: تُكذَّب الفرضيّةُ قبل أن تُكتَب في وثيقةِ تحكيم.** بنيتُ أنّ إعادةَ التنفيذ تُولّد `execution_id` جديداً فيسقط منعُ التكرار — **فقرأتُ الاشتقاق فسقطت الفرضيّة** (`execution_id` حتميٌّ من `{rec, gate, commands}`، والبوّابةُ بلا ساعة). ولو كُتِبت لكانت ادّعاءً في بطاقةٍ تُبنى عليها قرارات. والمسارُ الذي بقي بعد التكذيب **أضيقُ وأصدق**: السياسةُ تدخل عبر `max_authorized_effect`.
- **القرار ④: يُسجَّل ما يُغيّر كلفةَ توصيةٍ قائمة، ولا يُعاد الحكمُ فيها.** القياسُ يُظهِر أنّ أ‑٢ تُسقِط آخِرَ موضعٍ يُطبَّق فيه الثابتُ الملزِم. **فسُجِّل الثمنُ ولم تُبدَّل التوصية** — تصحيحُ كلفةِ خيارٍ قياس، واختيارُ الخيار حوكمة.
- **حدُّ صدق:** لا هجرةَ ولا شيفرةَ تنفيذيّة في هذه الشريحة — وثيقةٌ وسجلٌّ فقط. والعلاجان كلاهما محجوبٌ: العمودُ خلف `GATE-01`، وفصلُ الهويّتين عقدٌ لا قياس.
- **المصدر:** `90df6145` · #956 · #957 · فرع `claude/m03-envelope-identity`.

## 2026-08-30 (و) — لا يُعمَل على صفٍّ يقول `open` قبل أن يُقاس المصدر

- **القرار ①: يُقاس المصدرُ قبل العمل على صفٍّ يقول `open`.** فُتِحت صفوفٌ للعمل فسقط اثنان بالقياس **قبل** أن يُكتَب سطرُ إصلاحٍ واحد. **والسبب:** العملُ على صفٍّ بائتٍ يُنتِج «إصلاحاً» لشيءٍ مُصلَح — ضجيجٌ يُقرأ إنجازاً، ويُخفي أنّ الجهدَ لم يمسّ عطلاً. (`7508702a` · `bba61eea` · `673bc161`)
- **القرار ②: الصفُّ البائتُ عطلٌ يُسجَّل لا سهوٌ يُصحَّح صامتاً.** كُتِب في خانة الحالة **كيف** سقط كلُّ صفّ ومتى ومن أيّ التزام — لا `fixed` مجرّدة. **والسبب:** «متى صار الصفُّ كاذباً» هو الدليلُ الذي يمنع تكرارَه؛ و`fixed` بلا إسنادٍ تُنتِج سجلّاً يُوثَق به بلا سببٍ للثقة — وهو الصنفُ الذي يحرسه السجلُّ أصلاً.
- **القرار ③: يُبنى الحارسُ على الاحتواء لا التساوي حين يكون للخطأ اتّجاه.** القيدُ الأضيقُ من الواقع يكذب على المستهلك؛ والأوسعُ يصف تصفيراً لم يقع وله حارسُه القائم. **والسبب:** حارسُ التساوي هنا كان سيمنع مُزوّداً ثانياً من توسيع القائمة **بحقّ** — وحارسٌ يُحمِّر الصوابَ يُدرِّب قارئَه على تخطّيه.
- **القرار ④: لا يُكتَب حارسٌ قبل قياس أنّه يُجمَع في CI.** `testpaths = tests_v9` كان سيُسقِط الاختبارَ الجديد صامتاً لولا وظيفةٌ مستقلّةٌ قِيست في `ci.yml:996-999`. **والسبب:** حارسٌ لا يُشغَّل أسوأُ من لا حارس — يُقرأ تغطيةً وهو غياب.
- **حدُّ صدق:** التصفيرُ اليوميُّ **لم يُزَل** ولا يُدَّعى زوالُه — قرارٌ مُعلَنٌ بتعليله، والمُغيَّرُ ربطُ إعلانِه بما يبلغ المستهلك. ولا سلطةَ تحرّكت: `runtime_verified=0` · `production_certified=0` · `capable=false`.
- **المصدر:** فرع `claude/project-exploration-dtjw3p` فوق `399614e4` · [`open_meteo.py`](../../services/weather-service/open_meteo.py) (`_DAILY_ZERO_COERCED_FIELD_MAP`) · `test_missing_temperature_is_not_zero.py::test_the_published_caveat_names_every_field_the_edge_actually_coerces`.

## 2026-08-31 — الصفُّ يقول أين نُظِر، لا أين العطل

- **القرار ①: يُقاس الصنفُ لا الموضعُ الذي يسمّيه الصفّ.** صفُّ المطر كان صادقاً في ملفّه ومُصلَحاً فيه، والصنفُ حيٌّ في ثلاثة أسطحٍ أخرى. **والسبب:** الصفُّ يسجّل **أين نُظِر** لا **أين العطل**؛ فإغلاقُه بقراءة ملفِّه وحدَه يُنتِج «مُغلَقة» فوق عطلٍ حيّ — وهو أسوأ من صفٍّ مفتوح.
- **القرار ②: يُوسَّع الإعلانُ مع الإنفاذ في الشريحة نفسِها.** لمّا صار المطرُ يُبوِّب محرّكَ الريّ، وُسِّعت `required_inputs`. **والسبب:** إعلانٌ أضيقُ من الإنفاذ هو عينُ العطل الذي تُغلقه الشريحة — فكنتُ سأُنشئ من صنفه وأنا أُغلقه.
- **القرار ③: يُفوَّض الحكمُ ولا يُنسَخ.** الموجِّهُ الذي كان يحمل الحكمَ صار يستخرج ويُفوِّض إلى سياسةٍ واحدة على `list[float | None]`. **والسبب:** ثلاثةُ أحكامٍ لحقيقةٍ واحدة تنحرف، والانحرافُ هنا يعني جواباً مختلفاً للمزارع بحسب أيّ مسارٍ سأل.
- **القرار ④: يُفرَّق بين الفشل المغلق والصمت بحسب ما يطلبه المستدعي.** المسارُ الطالبُ لتقديرٍ يفشل مغلقاً (503)؛ ومسارُ التنبيهات **يصمت** لأنّ عقدَه يحمل الغياب أصلاً. **والسبب:** 503 في محرّك تنبيهات يُسقِط تنبيهاتٍ صحيحةً لا علاقة لها بالمطر — وحارسٌ يُحمِّر الصوابَ يُدرَّب على تخطّيه.
- **حدُّ صدق:** طفرتان نجتا أوّلاً **بخطأٍ في شهادتي**: قياسُ الدالّة المساعِدة بدل موضع البناء، وقياسُ العقد بتمرير `None` صراحةً حيث لا يفرض بايثون التصنيف وقتَ التشغيل. **والقاعدة المستخلَصة: تُقاس المواضعُ والافتراضاتُ، لا الأشكالُ والتوقيعات.** ولا سلطةَ تحرّكت: `runtime_verified=0` · `production_certified=0` · `capable=false`.
- **المصدر:** فرع `claude/project-exploration-dtjw3p` فوق `fe4c7744` · [`weather_advice.py`](../../services/sahool-platform/api/weather_advice.py) (`complete_rain_total`) · `tests/test_missing_rain_is_not_no_rain.py`.

## 2026-09-01 (ب) — عند تناقض إعلانين، يُبقى الحارسُ لا يُزال

- **القرار ①: يُتحقَّق من دعوى المُدقِّق قبل تنفيذ توصيته.** أُعيد إنتاجُ تزييف الشهادة في رملٍ معزول قبل أن أكتب سطرَ إصلاح. **والسبب:** توصيةٌ تُنفَّذ على دعوى غيرِ مُكذَّبة هي نفسُ العطل الذي يصفه التقرير — ثقةٌ بلا سند. وقد صحّ كلُّ ما ادّعاه، **وصحّ أكثرُ ممّا ادّعى** في موضعٍ واحد: «السبب» كلمةٌ في اسم الحالة لا حقلٌ يُقرأ.
- **القرار ②: الإعفاءُ يُجدَّد ولا يُصنَّف دائماً حين يتناقض السجلّ.** المالكُ عرض الخيارين والشرطُ «إن لم يكن له UI مطلوب». **والسبب:** حقولُ التصنيف والنصُّ يتنازعان، والتصنيفُ الدائم **يُزيل حارساً** بناءً على الجهة المتنازَعة بينما التجديدُ يُبقيه. **والقاعدة: عند تناقض إعلانين، يُؤخَذ الفعلُ الذي يُبقي الحارس** — فالخطأُ في اتّجاه الإبقاء قابلٌ للنقض، وفي اتّجاه الإزالة صامت.
- **القرار ③: لا يُخترَع تاريخ.** الأفقُ مُحاذًى لشقيقٍ قائمٍ في الملفّ نفسِه (نفس المالك، نفس سلسلة WX-11.x). **والسبب:** رقمٌ من عندي يُقرأ حكماً وليس لي فيه سلطة؛ والمحاذاةُ تُبقي القرارَ للمالك ظاهراً.
- **القرار ④: يُسجَّل P0 بشاهده ولا يُصلَح في شريحةٍ عن موضوعٍ آخر.** الشريحةُ الجارية عن المطر، وضمُّ إصلاح بوّابة الاعتماد إليها يخلط تكذيبين. **والسبب:** الشريحةُ المختلطة تُخفي أيَّ الأدلّة يسند أيَّ دعوى.
- **حدُّ صدق:** التزييفُ **ما يزال ممكناً** بعد هذه الشريحة — لم يُغلَق، سُجِّل. وحالةُ الحكم تبقى `verdict: blocked` · `static_ready: false` · `production_certified: false`، وهي **الحقيقةُ لا عطلٌ يُصلَح**.
- **المصدر:** فرع `claude/project-exploration-dtjw3p` · `config/endpoint_ui_coverage_waivers.json` · صفّ `PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01`.

## 2026-09-01 (ج) — لا تُتبنّى روايةٌ عن عملٍ دون قياس، ولا يُدفَع ما لا يُملَك

- **القرار ①: يُقاس ما يُنسَب إليّ قبل أن أستجيب له.** وردت رسالةٌ تصف أفعالاً وفرعين، فتحقّقتُ: الفرعان على البعيد والتزاماهما مجهولان محلّيّاً، وشجرتي نظيفة. **والسبب:** تبنّي روايةٍ صحيحةٍ عن جلسةٍ أخرى يُنتِج نسبةَ عملٍ ليس لي — وهو العطلُ الذي حذّر منه كاتبُها؛ فتكرارُه في الاتّجاه المعاكس ليس أهون.
- **القرار ②: لا يُدَّعى فعلٌ على ما ليس في الحاوية.** حزمةُ الأدلّة غيرُ موجودة، فقلتُ ذلك ولم أعِد بدفعها. **والسبب:** وعدٌ بحفظ أدلّةٍ لا أراها هو أسوأُ من الصمت — يُطمئن مالكَها فيتركها تضيع.
- **القرار ③: يُسنَد القياسُ الحيُّ بقياسٍ ساكنٍ في المصدر، لا يُعاد نقلُه.** ثلاثةُ بنودٍ أُكِّدت من الشجرة بشواهدَ بالسطر. **والسبب:** الحيُّ يقول **ماذا حدث**، والساكنُ يقول **لماذا** — وبلا الثاني يبقى العلاجُ تخميناً. وأحدُها خرج **أحدَّ** من وصفه الأصليّ: `status` لم يكن عموداً منحرفاً بل عموداً لم يوجد.
- **القرار ④: يُسجَّل ما لا أملك تنفيذَه ولا يُنفَّذ نصفُه.** مصادقةُ NATS **تزويدٌ** لا شيفرة (اعتمادات في ٧ مواضع + كتلةُ صلاحيّات مواضيع). **والسبب:** إضافةُ كتلةٍ بلا اعتماداتٍ حقيقيّة تُوقِف المكدّس أو تُنتِج أماناً صوريّاً؛ وكلاهما أسوأ من غيابٍ مُعلَن.
- **حدُّ صدق:** لم يُغلَق شيءٌ في هذه الشريحة — **ثلاثةُ صفوفٍ سُجِّلت بشواهدها وحسب**. والحكمُ يبقى NO-GO كما قرّره المالك.
- **المصدر:** فرع `claude/project-exploration-dtjw3p` · `nats/nats.conf` · `migrations/v68_execution_ledger.sql`.
## 2026-09-02 — حالة التشغيل تُقرأ وقت الاستعمال وGUC المعاملة لا يعيش خارجها

- **القرار ①:** المتغيّر الذي تعيد lifespan ربطه لا يُستورَد بالاسم في موجّه؛ يُقرأ من الوحدة المالكة وقت الاستعمال. السبب: `from module import value` يلتقط مرجعاً لا يتحدّث عند `module.value = replacement`.
- **القرار ②:** `set_config(..., true)` وسائر استعلامات المستأجر عملية واحدة داخل transaction. السبب: نطاق `true` محلي للمعاملة وasyncpg auto-commit ينهيه قبل الاستعلام التالي إن نُفّذا منفصلين.
- **القرار ③:** إضافة جداول runtime الغائبة هجرة أمامية لا تعديل لهجرة v9 التاريخية، وتسبق v206 النهائي. السبب: البيئات التي طبّقت v9 لن تعيد تطبيقه بوصفه تغييراً جديداً، وv206 يجب أن يبقى آخر حارس RLS.
- **حد الصدق:** هذه قرارات شيفرة مُختبرة محلياً وليست اعتماداً حياً؛ outbox يبقى opt-in ويحتاج قياس staging.

## 2026-09-01 (د) — الشاهدُ الحيُّ يُصدَّق في ما قاس لا في ما سمّى

- **القرار ①: يُصحَّح صفّي كما يُصحَّح صفُّ غيري، وبنفس الصراحة.** سجّلتُ فجوةً بموضوعٍ خاطئ ودعوى أثرٍ باطلة، فكُتِب الخطآن **في نصّ الصفّ نفسِه** لا في هامش. **والسبب:** صفٌّ يُصحَّح صامتاً يُعلِّم قارئَه أنّ السجلَّ يُنقَّح لا يُراكِم — وحينها لا يُوثَق بأيّ صفٍّ فيه.
- **القرار ②: يُقاس ما يُنقَل قبل البناء عليه.** أخذتُ `actuator.command` من تقريرٍ حيٍّ منقولٍ ولم أقِسه. **والسبب:** التقريرُ الحيُّ سلطةٌ على **ما وقع**، لا على **كيف سُمّي**؛ وخلطُ الاثنين أنتج دعوى أثرٍ فيزيائيٍّ لا يسندها المصدر — وهو بعينه ما أعيبه على الصفوف البائتة.
- **القرار ③: يُخفَّض ادّعاءُ الخطورة عند سقوطه، ولا يُخفَّض تصنيفُ الفجوة معه.** الأثرُ الفيزيائيُّ سقط، والصفُّ بقي `open` بسببين مقيسين. **والسبب:** «لا يُستَغَلّ اليوم» ليس «مُغلَق» — وسيطٌ مفتوحٌ يرثه أوّلُ مشتركٍ يُضاف.
- **حدُّ صدق:** لم يُقَس شيءٌ حيّاً هنا — كلُّ ما فوق قراءةُ مصدرٍ وإعداد. وMQTT مُصادَقٌ **في الإعداد**؛ لم أُشغّل وسيطاً ولم أُجرّب اتّصالاً مجهولاً به.
- **المصدر:** `nats/nats.conf` · `phase_runtime_workers.py:507` · `actuator_runtime.py:584,1086` · `mosquitto.conf`.

## 2026-09-02 — لا تُخترَع دالّةٌ غائبةٌ لتُرضي مُناديها

- **القرار:** `main.tenant_connection_for(tenant_id)` — التي ينادِيها `internal_service.py` في موضعَين وهي **غيرُ معرَّفةٍ في `main.py` أصلاً** — **لم تُنشَأ**. بدلاً منها صُرِّحت هويّةُ الخدمة كائنَ مستخدِمٍ كامل السمات (`_ServiceUser` بمستأجِرٍ صريح وفاعلٍ مُميَّزٍ في التدقيق ودور `UserRole.VIEWER`) ومُرِّرت إلى `tenant_connection` القائمة.
- **السبب — مقيسٌ لا مفترَض:** `tenant_connection` تضبط ثلاثةَ GUCات (`app.current_tenant` · `app.current_user_id` · `app.current_role`)، و**٢٨ موضعاً في `migrations/*.sql` يقرأ الأخيرَين**. فدالّةٌ تضبط المستأجِرَ وحدَه (النمطُ القائم `_apply_tenant_guc`) كانت ستُنشئ **سياقَ RLS ثانياً أضعفَ** يحمل اسماً يوحي بالتكافؤ — أي الصنفَ نفسَه الذي أغلقناه اليوم في حكم الاعتماد وفي سياسة المطر: **تعريفان لحقيقةٍ واحدة يتّفقان اليوم وينحرفان غداً**. وإنشاؤها كان سيُثبِّت العطلَ بدل كشفه: الاسمُ يصير صحيحاً والدلالةُ تبقى ناقصة.
- **وشاهدٌ يقطع الشكّ:** الصنفُ المحلّيُّ `_ServiceUser` الذي كان في `internal_service.py` **بلا `role` أصلاً** — فحتّى لو وُجِدت `tenant_connection_for` لَسقط تمريرُه إلى أيّ مسارٍ يقرأ الدور. العطلُ كان في الهويّة لا في الدالّة.
- **حدُّ صدق:** `VIEWER` أدنى صلاحيّةٍ مُعرَّفة، واختيارُها قرارٌ محافظ: مسارُ الحدث يكتب عبر outbox داخل معاملةٍ مُنطّقةٍ بالمستأجِر، ولم يُقَس حيّاً أنّ سياساتِ RLS تقبله بهذا الدور. لو ردّت سياسةٌ الكتابةَ فالفشلُ **مغلقٌ ومرئيّ**، لا صامت.
- **المصدر:** `services/sahool-platform/api/routers/internal_service.py` · `services/sahool-platform/api/main.py:619` (`tenant_connection`) · `services/sahool-platform/api/main.py:645` (`_apply_tenant_guc`) · `scripts/ci/tenant_connection_call_shape_guard.py` · فرع `claude/project-exploration-dtjw3p` فوق `9b1f630b`.

## 2026-09-03 — لا يُختَم حاجبٌ من وظيفةٍ تقيس غيرَه، ويُعلَن الغيابُ بدل ختمِه

- **القرار:** لم تُبعَث أدلّةٌ لـ`P-CERT-3` و`P-CERT-4` و`GUARDS` رغم أنّ ذلك كان يجعل `production-certification-blockers.yml` قادرةً على بلوغ `production_certified=true` لأوّل مرّة. أُبعِثت اثنتان فقط (`P-CERT-1` بشاهدٍ جديدٍ من واجهة Actions، و`P-CERT-2` من قياسٍ قائم)، وسُجِّلت الثلاثُ الباقيةُ `no_honest_producer` بأسبابها في عقدٍ يفرضه حارس.
- **السبب — مقيسٌ لا مفترَض:** اسمُ الوظيفة ليس قياسَها. `P-CERT-3` تحجب على السرّ `WEATHER_REDIS_INTEGRATION_URL` و**سكربتُها يتجاهله تجاهلاً تامّاً**، يرفع `test-redis` من `docker-compose.test.yml` ويُثبِّت `redis://:test_redis_pass@127.0.0.1:6380/0` في سطره الأخير — فالسرُّ يحكم *هل تعمل الخطوة* لا *ما الذي اختُبِر*، وحقلُ `readyz_cache_backend` الذي يشترطه الحارس لا يُقاس في المسار أصلاً. و`P-CERT-4` تفحص اتّساقَ عقد الحافّة، و`edge_models.required.json` يقول لكلّ نموذجٍ `packaged_in_repository=false` و`operator_must_provision=true`، وافتراضا compose هما `EDGE_READINESS_MODE=partial` و`EDGE_PRODUCTION_REQUIRED=false` — أي أنّ الحقلَين المشترطَين قيمتُهما في CI هي **قيمةُ عدم التزويد** لا شاهدٌ عليه. و`guard_results_summary.json` لا يكتبه شيءٌ في المستودع كلِّه.
- **ولمَ لا يكفي أن يُترَك الأمرُ صامتاً:** الصمتُ هو ما جعل خمسةَ حواجزَ `pending` تُقرأ عجزاً في القياس بينما سببُها غيابُ الإنتاج. فالإعلانُ **بسببٍ مقيس** يُبقي الحقيقةَ مرئيّةً لمن يأتي، والحارسُ يرفض انبعاثاً لحاجبٍ مُعلَنٍ هكذا فلا يبقى الإعلانُ نصّاً يُخالِفه العمل.
- **والثمنُ مُعلَن ومقبول:** المنصّةُ تبقى `production_certified=false` بعد هذه الشريحة، وهي بالضبط ما كانت عليه قبلها. المكسبُ أنّ سببَ ذلك صار ثلاثةَ مُنتِجين غائبين مُسمَّين بأسبابهم وعلاجاتهم، لا «لا شيء يُنتِج شيئاً».
- **حدُّ صدق:** التوقيعُ الشهاديّ (`actions/attest` بهويّة Sigstore) يربط بايتاتِ الحزمة بهويّةِ الـworkflow — ولا يشهد أنّ الحقولَ داخلها تصف تشغيلاً حقيقيّاً. تلك تقع على شرطِ بلوغ خطوة الانبعاث بعد خطوة القياس، وعلى صدقِ المُنتِج نفسِه. ولم تُشغَّل الـworkflow في هذه الشريحة (`workflow_dispatch`): كلُّ المقيس ساكنٌ ومحلّيّ.
- **المصدر:** `.github/workflows/production-certification-blockers.yml` · `docs/architecture/certification_evidence_producers.json` · `scripts/ci/certification_evidence_producer_guard.py` · `scripts/ci/emit_certification_evidence.py` · `scripts/ci/collect_full_branch_ci_evidence.py` · `services/edge-inference/models_manifest/edge_models.required.json` · `scripts/ci/run_weather_redis_integration.sh` · فرع `claude/project-exploration-dtjw3p` فوق `ee0bdfc6`.

## 2026-09-05 — تُوَرَّث زياداتُ #979 بالقاعدة، ولا تُقرَّر بإقرارٍ نثريّ

- **القرار:** ستُّ ثلاثيّاتِ الحجب التي أضافتها #979 أُدرِجت في `legacy_blocking` على `d3471e39` — **ولم تُكتَب لها إقراراتٌ** بالخصائص الأربع، رغم أنّ ذلك كان ممكناً شكلاً وكان يُظهِر الآليّةَ أقوى.
- **السبب — مقيسٌ لا مفترَض:** حقلُ `mutation` كان يقبل نثراً، و**لا واحدةَ من الستّ لها طفرةٌ مسجَّلة** (قِيس: صفرٌ من ستّ). فكتابةُ إقراراتٍ لها كانت ستملأ الحقولَ الأربعةَ بجملٍ صحيحةِ الشكل تسمّي تكذيباً لا وجودَ له — أي **تصنيعُ مُدخَلِ البوّابة بدل استيفائه**، وهو بالحرف الصنفُ الذي بُنيت هذه الآليّةُ لمنعه. والتوريثُ يقول الحقيقةَ: `legacy_blocking` **مُتوارَثٌ لا مُثبَت**.
- **وخطُّ التجميدُ قاعدةٌ لا اختيار:** قاعدةُ الطلبِ الذي يُنزِل الآليّة، تسري على كلّ داخلٍ بالتساوي. ولقطةٌ تُختار **بعد** رؤية أيِّ الزيادات ستُبلَّغ ليست قاعدة.
- **وإفصاحٌ يلزم لأنّه ضدّ مصلحتي:** كاتبُ الستّ هو كاتبُ الآليّة، فالتوريثُ **إعفاءٌ للنفس**. ما يجعله مقبولاً أنّه بالقاعدة لا بالاستثناء، وأنّ الإدراجَ لا يشهد لها بشيء، وأنّ غيابَ التكذيب عنها **مُعلَنٌ بالرقم** لا مطويّ.
- **الثمنُ المُعلَن:** الدَّينُ غيرُ المُكذَّب ارتفع ٢١٩ ⇒ **٢٢٢**. والتجميدُ يمنع النموَّ **بعد** خطّه، ولا يُقلّم ما قبله ولا يُخفّفه.
- **المصدر:** `docs/architecture/blocking_surface_baseline.json` · `docs/architecture/blocking_surface_additions.json` · `scripts/ci/guard_mutation_guard.py::addition_violations` · `tests_v9/test_blocking_surface_freeze.py` · فرع `claude/blocking-surface-freeze @ b2c261a0` فوق `d3471e39`.

## 2026-09-05 — لا يُستعار زمنٌ من جولةٍ ليُقرَن بعددٍ من أخرى

- **القرار:** لمّا حمرّ حدُّ انجراف المكنسة، **لم يُنقَل الحدُّ** ولم يُبقَ الزمنُ الأبطأ تاريخيّاً (٣٧٫٢٣د) مقروناً بالعدد الجاري (٥٤٠). قُرِئ توقيتٌ حيٌّ من CI وقُرِن **بعددِ جولتِه هو**: (٢٩٫٨٥د · ٥٤٠).
- **السبب:** الزوجُ يصف كوناً واحداً. وقرنُ زمنٍ من جولةٍ بعددٍ من أخرى يصنع زوجاً **لم يُرصَد قطّ** — رقمٌ يبدو محافظاً وهو **مُختلَق**، وذاك أسوأُ من رقمٍ متفائلٍ مرصود لأنّه يُورِّث ثقةً بلا مصدر. وهو الصنفُ نفسُه الذي أُغلِق مرّتين في هذه الجلسة: لقطةٌ تصف كوناً غيرَ القائم.
- **والثمنُ مقبولٌ ومُعلَن:** الأخذُ بالمرصود **خفض** المرساةَ فوسّع الهامشَ المشتقّ (العلامة ٥٧٤ ⇒ ٦١٧). ولم يُعوَّض ذلك بتشديدٍ يدويٍّ في الصيغة أو الكلفة: **تليينُ حدٍّ بقياسٍ خيرٌ من تشديدِه بتقدير**، والسقفُ الذي يحرس السلامة فعلاً (تسعون دقيقة) لم يتحرّك.
- **حدُّ صدق:** المقيسُ **بديلٌ** (عددُ الطفرات) لا زمن. وجولةٌ تبطؤ بلا نموِّ سجلٍّ — لتبدُّل عدّاءٍ أو نموِّ اختباراتٍ خارج المكنسة — تمرّ من هنا خضراء؛ والقياسُ الزمنيُّ يبقى فعلاً دوريّاً لا يفرضه ملفّ.
- **المصدر:** `tests_v9/test_mutation_sweep_headroom.py` · run 33970429290 · job 101317844845 · فرع `claude/blocking-surface-freeze @ b2c261a0` فوق `d3471e39`.

## 2026-09-05 — التقاعدُ يُنطَق ولا يُمنَع، والمراجعةُ البشريّةُ لا تُفرَض من شريحةٍ تقنيّة

- **القرار ①:** جُعِل نزعُ حاجبٍ من سطح الحجب **مُبلَّغاً عنه** (اتّجاهٌ رابع) ولم يُجعَل **ممنوعاً**، ولم يُطلَب له تكذيبٌ ولا شاهدٌ موجب.
- **السبب — مقيسٌ لا مفترَض:** النزعُ كان صامتاً بالكامل (٣٠١ ⇒ ٣٠٠ و`blocking_surface_ok`)، **وعلاجُ الشكوى الوحيدة — إعادةُ توليد الكتالوج — هو ما يمحو الدليل**. ومنعُ النزع كان سيجعل التجميدَ يفرض بقاءَ كلّ حاجبٍ أبداً فيُعاقِب التضييقَ المشروع ويُدرِّب الناسَ على الالتفاف؛ والمطلوبُ أن يُقال **لماذا**، لا أن يُمنَع الفعل.
- **وشاهدٌ يقطع الشكّ:** `test_a_declared_retirement_passes` — بدونه يصير الفحصُ يرفض كلَّ تقاعد، وذاك منعٌ لا نطق.
- **القرار ②:** **لم يُضَف** `/.github/workflows/` إلى `CODEOWNERS` رغم أنّ القياس كشف أنّ المسارَ بلا مالك، ورغم أنّ ذلك كان سيبدو تشديداً حميداً.
- **السبب:** التكلفةُ **بشريّة لا تقنيّة**. المؤلّفُ عادةً `@kafaat` وGitHub تمنع اعتمادَ المؤلّف لطلبه، فيصير كلُّ تعديلِ workflow معلَّقاً على شخصٍ واحد — وهو الصنفُ الذي يشرحه `CODEOWNERS` نفسُه: «مالكٌ واحدٌ قفلٌ لا حراسة». وفرضُ اعتماديّةٍ على توفّرِ إنسانٍ بعينه قرارٌ تنظيميٌّ للمالك، لا يُتَّخذ داخل شريحةٍ تقنيّة ولو كان الاتّجاهُ صحيحاً.
- **وبديلٌ أخصُّ نُفِّذ بدلاً منه:** الاتّجاهُ الرابع يحرس **الفعلَ الخطر** (زوالُ الحجب) بقياسٍ داخل المستودع، لا بوكيلٍ عنه (لمسُ ملفّ workflow). وهو نفسُ منطق `CODEOWNERS` القائم: الحجبُ على الفعل الذي يحتاج الحماية لا على كلّ دمج.
- **حدُّ صدق:** الاتّجاهُ الرابع **إرشاديّ** (يُعيد `0`)، ولا يمسك تعديلاً يُبقي الاستدعاءَ ويُفرِغه من أثره. والفجوةُ التنظيميّة تبقى `open` بانتظار حكم المالك.
- **المصدر:** `scripts/ci/guard_mutation_guard.py` · `docs/architecture/blocking_surface_baseline.json` (`retired`) · `tests_v9/test_blocking_surface_freeze.py` · فرع `claude/blocking-surface-retirement` فوق `a3124ccf`.
## 2026-09-05 (ب) — مالكٌ لمسار الـworkflows بأمر المالك، ودفاعٌ يُحذَف لأنّه لا يُكذَّب

- **القرار ①:** أُضيف `/.github/workflows/` إلى `CODEOWNERS`. وكنتُ قد رجّحتُ **تأجيله** وسجّلتُ ذلك قراراً؛ **فأمر المالكُ صراحةً بتنفيذه**، وهذا هو المُنفَّذ. القرارُ السابق يبقى في السجلّ بسببه، ولا يُمحى — تغيّر الحكمُ بقرار من يملكه لا بانقلابٍ في التقدير.
- **السبب المقيس:** #982 مسّت `.github/workflows/capability-governance.yml` وانتقلت من `blocked` إلى `clean` **بلا اعتمادٍ يُضاف**؛ ومن يملك تعديلَ الـworkflow يملك نزعَ أيّ حارسٍ منها.
- **والثمنُ مُعلَنٌ ومقبول:** المؤلّفُ عادةً `@kafaat`، وGitHub تمنع اعتمادَ المؤلّف لطلبه — فكلُّ تعديلِ workflow صار معلَّقاً على `@haithmgarallah-ye`. وهذا يُقارِب «مالكٌ واحدٌ قفلٌ لا حراسة»، والفارقُ أنّ المالكَين اثنان فالقفلُ يُفتَح بأيّهما لم يكن المؤلّف.
- **القرار ②:** حُذِف فرعُ «لا كتلة `parameters` مفهومة» من `stale_review_violations` بدل توسيع اختبارٍ ليقتله.
- **السبب:** أثبتت المكنسةُ أنّه **غيرُ بالغ**؛ و«اختبارٌ يُكتَب ليقتل فرعاً لا يُبلَغ» يشتري خضرةً بلا حراسة ويُضخِّم ما يبدو محروساً. والحذفُ يُبقي المقياسَ صادقاً.
- **حدُّ صدق:** البندُ الثالث يقيس **الإعدادَ النافذ** لا سلوكَ GitHub؛ وإسقاطُ الاعتماد عند الدفع يبقى فعلَ المنصّة لا فعلَ هذا المستودع.
- **المصدر:** `scripts/ci/branch_protection_contract_guard.py` · `.github/CODEOWNERS` · `tests_v9/test_branch_protection_contract_guard.py` · فرع `claude/codeowners-workflows-and-stale-reviews` فوق `a3124ccf`.

## 2026-09-05 — رفضُ الطلب ليس عطلَ مزوّد، والزمنُ يُحَلّ بطابعه لا بموضعه

- **القرار ①:** فُصِل حسابُ قاطع Open-Meteo إلى ثلاث فئات — `provider` (شبكة/مهلة/5xx ⇒ يُحسَب) · `access` (401/403/429 ⇒ حالةٌ مستقلّة تُرى) · `request` (بقيّة 4xx ⇒ يُسجَّل ولا يُحسَب) — **لا** إلى قاعدة «4xx لا يُحسَب مطلقاً».
- **السبب:** رفضُ معرّفِ نموذجٍ يقول شيئاً عن طلبنا لا عن توافر المزوّد؛ لكنّ الحصّةَ والاعتمادَ يقولان شيئاً عن إعدادنا ويستحقّان أن يُريا كتدهورٍ منفصل لا أن يختفيا في «طلبٌ سيّئ». والقاعدةُ العمياء كانت ستُخفيهما. **نوعُ الاستثناء للمتّصلين لم يتغيّر** — الفصلُ في الحساب وحدَه.
- **القرار ②:** `+Nh` يُحَلّ بمرساة `current.time` وطابعٍ مطابق؛ ولا مطابقَ ⇒ **الأقربُ مُعلَناً** (`policy=nearest` · `delta_hours` · قيدٌ مسمّى) لا رفضاً ولا استبدالاً صامتاً؛ ولا مرساةَ ⇒ **لا قيمة**.
- **السبب:** الرفضُ التامّ كان سيُفرِغ البلاطةَ لنموذجٍ خطوتُه ٦ ساعات عند كلّ ساعةٍ بينيّة، والاستبدالُ الصامت هو العطلُ نفسُه. والإعلانُ يترك القرارَ للمستهلك بمعلومةٍ كاملة. **وأُسقِط احتياطُ «أقربِ قيمةٍ غيرِ فارغة»** في الموصِّل لأنّه استبدالٌ صامتٌ على مستوى القيمة — `None` أصدق، وهو عقدُ المنصّة القائم.
- **القرار ③:** نسختان من `resolve_hourly_index` و`classify_upstream_error` في خدمتين، **لا حزمةٌ مشتركة**.
- **السبب:** `weather-service` و`sahool-platform` صورتان منفصلتان بلا حزمةٍ بينهما اليوم، وإنشاءُ واحدةٍ لأجل دالّتين توسيعُ نطاقٍ يفوق الشريحة. **والتطابقُ يُقاس لا يُفترَض**: `test_the_two_services_resolve_identically` يُشغِّل النسختين على المدخلات نفسها.
- **حدُّ صدق:** حالةُ `ecmwf_ifs04` الحيّة **NOT_MEASURED** (الوكيلُ حجب المزوّد)؛ العلاجُ صحيحٌ سواءٌ أُجيب المعرّفُ القديم أم رُفِض. وعتباتُ القاطع (٣ · ٥) لم تُمَسّ.
- **المصدر:** `docs/architecture/weather_model_catalogue.json` · `services/weather-service/open_meteo.py` · `services/sahool-platform/api/connectors/openmeteo.py` · `tests_v9/test_weather_model_identity.py` · فرع `claude/claude-md-docs-p6qqir` فوق `9876bd92`.

## 2026-09-05 — البصمةُ تُفعِّل عند الاستدلال، والجدولُ يُحذَف لا يُخفى

- **القرار ①:** بوّابةُ هويّة المصنوعة تُطبَّق **في نقطتي الاستدلال** (`_require_approved_model` ⇒ 503) لا في `/capabilities` و`/readyz` وحدَهما.
- **السبب:** الكاشفُ والمُقدِّر يحمّلان ONNX **بالمسار**؛ فبوّابةٌ على التقرير وحدَه تترك ملفّاً أعلنت القدرةُ أنّه غيرُ فعّال **يُستدلّ به** فعلاً. الرقعةُ والحزمةُ الواردتان وقفتا عند التقرير.
- **القرار ②:** جدولُ «الإجراء» في `PEST_DB` **حُذِف** من المصدر، لا أُبقي مع تصفير الحقل.
- **السبب:** جدولٌ بأسماء مبيدات لا يقرؤه أحد بياناتٌ ميّتة تعود بنسخةٍ ولصق؛ وحارسٌ يطابق نصّاً هشّ. الاختبارُ يقيس **شكلَ كشفٍ منتَج** من رأسٍ تركيبيّ وغيابَ الأسماء من المصدر.
- **القرار ③:** المنطقُ الصرف في `model_artifact_gate.py` **بلا FastAPI**.
- **السبب:** لا وظيفةَ CI تُشغّل `services/edge-inference/tests`، و`python-multipart` ليست في `requirements-test` فاستيرادُ `main.py` يسقط في جناح الوحدة. الفصلُ يجعل الحكمَ يبلغ بوّابةَ الدمج بدل أن يعيش في جناحٍ لا يعمل — ولم تُضَف وظيفةُ CI لأنّ توسيعَ السطح قرارٌ منفصل.
- **حدُّ صدق:** البصمةُ هويّةٌ لا صلاحيّة؛ الرخصةُ والتصنيفُ والمعايرةُ NOT_PROVISIONED. وجودُ `MODELS_BASE` على GitHub لم يُقَس.
- **المصدر:** `services/edge-inference/model_artifact_gate.py` · `tests_v9/test_edge_model_artifact_integrity.py` · فرع `claude/claude-md-docs-p6qqir` فوق `ad4ac5cc`.

## 2026-09-06 — الوحدةُ تُعلَن لا تُخمَّن، والحسّاسُ يُقارَن ولا يحكم

- **القرار ①:** `%` العارية تُصنَّف `undeclared` وتبقى القراءةُ قائمةً — لا تُرفَض ولا تُفسَّر.
- **السبب:** الرفضُ كان سيُسكِت مسارَ الإلحاح والتنبيهات لكلّ الحسّاسات الحاليّة (الكاتبُ يخزّن `%` للجميع)، والتفسيرُ تخمينٌ. الحقيقةُ تُنشَر ويقرّر كلُّ مستهلكٍ ما يفعل بها: التوأمُ لا يحوّلها، والإلحاحُ يفسّرها كما كان **ويكتب افتراضَه**.
- **القرار ②:** لا تعديلَ في `soil-service` (جانب الكاتب) في هذه الشريحة.
- **السبب:** إعلانُ `vwc_pct` في المُنتِج ادّعاءٌ عمّا تُخرِجه الحسّاسات، وهو غيرُ مقيس. يُقاس أوّلاً (جهازٌ واحد، قراءةٌ واحدة، ورقةُ بياناته) ثمّ يُعلَن — قرارُ المالك.
- **القرار ③:** الطزاجةُ إعلانٌ في `device_registry` (ساعةٌ إبلاغاً، أربعُ ساعاتٍ سقفاً) لا رقمٌ في الوصلة.
- **السبب:** درسُ WEATHER-HEARTBEAT-01: الطزاجةُ تُربَط بإيقاع المُنتِج. لا حقلَ إيقاعٍ في المخطّط، فالإعلانُ يحلّ محلّه إلى أن يُقاس، وموضعُه حيث يُوصَف الجهاز لا حيث يُستهلَك.
- **حدُّ صدق:** الراوتر لم يُختبَر بقاعدة؛ `alert_rules._low_moisture` ما يزال بلا وحدة.
- **المصدر:** `services/sahool-platform/api/water_twin_seed.py` · `soil_telemetry.py` · `tests_v9/test_soil_moisture_unit_identity.py` · فرع `claude/claude-md-docs-p6qqir` فوق `ad4ac5cc`.
- **تصحيحُ القرار ②:** جانبُ الكاتب **مُسَّ** بعد كلّ شيء — لكن بغير ما رُفِض: لم يُعلَن `vwc_pct` عن الحسّاسات، بل فُتِح للمُنتِج أن **يُعلن هو** (`units=`) ويبقى الافتراضيُّ `%` غيرَ مُعلَن. الفرقُ أنّ الإعلانَ صار ممكناً بلا ادّعاءٍ عمّا لم يُقَس.
- **القرار ④ (بعد المراجعة المضادّة):** الطزاجةُ **إثباتٌ إيجابيّ**: `fresh` فقط بعمرٍ وسقفٍ محدودين والسقفُ موجب والعمرُ ضمن النافذة؛ ما عداه لا يهيّئ ولا يُقارَن. وسياسةُ المستقبل مُعلَنة: انحرافٌ حتّى ٣٠٠ ثانية طازج، أبعدُ منه `future`.
- **السبب:** `not stale` جعل غيابَ العمر والسقف وNaN والطوابعَ المستقبليّة كلَّها «طازجة» — والراوترُ يمرّر `None` للسقف حين يغيب نوعُ الجهاز، فالمسارُ حقيقيّ لا نظريّ. الإثباتُ الإيجابيّ هو الشكلُ الوحيد الذي لا يجعل الحارسَ أعمى عمّا لم يُقَس.
- **القرار ⑤:** `bool` يُرفَض في **موضعين**: القارئ (القراءات القائمة) والابتلاع (القادمة) — لا على العقد العامّ كلِّه، لأنّ خصائصَ أخرى قد تقبل `bool` عمداً.
- **مُلاحَظٌ لا مُقرَّر:** `brain_duplicate_gap_identity_guard.py` يرى التكرارَ (مقيس على سجلّ `a7d64adf`) لكنّه موصولٌ في `no-report-only-change.yml` وحدَه؛ ضمُّه إلى `preflight.sh` قرارٌ على سطح الحجب المُجمَّد، سُجِّل فجوةً `open` ولم يُنفَّذ هنا.
- **القرار ⑥ (المراجعة التكميليّة):** حارسُ «الرطوبة قياسٌ» يعيش في **العقد** `SoilObservation` لا في بابٍ من أبواب الابتلاع، ويُدرَج بخاصّيّته في `MEASUREMENT_ONLY_PROPERTIES`.
- **السبب:** ثلاثةُ أبوابٍ تبني الكائنَ نفسَه؛ حارسٌ عند بابٍ واحد يترك بابين. والعقدُ هو الحدُّ الوحيد الذي **لا يمكن** أن يُبنى الكائنُ بدونه. و`bool` يبقى مشروعاً لخصائصَ أخرى — التشديدُ على الخاصّيّة لا النوع.
- **القرار ⑦:** أهليّةُ التهيئة من الحسّاس وحدَه = `quality_status == accepted` — سياسةٌ صريحة؛ `suspect`/`uncalibrated` شاهدٌ مرئيّ يُقارَن ولا يهيّئ؛ الغيابُ لا يؤهّل.
- **السبب:** الوحدةُ الصحيحة والطابعُ الحديث لا يُثبِتان جودةَ القياس؛ والكاتبُ نفسُه يُصنّف حسّاسَه غيرَ المعتمد `uncalibrated` — فاستعمالُه بذرةً يُبطل تصنيفَ كاتبه.
- **القرار ⑧ (المراجعة المستقلّة على `703607bf`):** غيابُ إعلان الجودة من حسّاسٍ لخاصّيّة قياس يُحسَم **في العقد** إلى `uncalibrated`، لا يُرفَض ولا يُترَك `accepted`.
- **السبب:** الرفضُ كان سيُعطّل باباً يعمل اليوم لمصادرَ لا تعرف حقلَ الجودة؛ و`accepted` ادّعاءٌ عمّا لم يُعلَن. و`uncalibrated` هو ما يقوله البابُ المجمِّع عن الحالة نفسها — فالحسمُ يوحّد دلالةَ الغياب بين الأبواب بلا قاعدة معايرةٍ جديدة. النطاقُ مضيَّق بقصد: `LABORATORY` والخصائصُ غيرُ القياسيّة كما كانت، لأنّ تغييرَ افتراضاتها قرارٌ آخر لم يُتَّخذ.
- **القرار ⑨ («قوم بتنفيذ الكل» بعد المراجعة المستقلّة):** حارسُ التكرار يُضمّ إلى `preflight.sh --fast` **بذاته** (خطوة `٦د`) لا بكاشفٍ موازٍ ولا بworkflow جديد، ويُدرَج في `preflight_required.json`.
- **السبب:** الحارسُ رأى التكرارَ على `a7d64adf` ولم يُسأل محلّيّاً — الفجوةُ في الوصل لا في الكشف. وشروطُ الإغلاق الثلاثة (صفٌّ مكرَّر يُحمِّر · الغيابُ تقلّصُ تغطيةٍ لا تخطٍّ · النظيفُ يمرّ) تُقاس على **الشيفرة المشحونة** باستخراج `require_file`/`run` وسطرِ الاستدعاء من السكربت نفسه، لأنّ نسخةً في الاختبار تعود خضراء بعد انحراف الأصل.
- **حدُّ صدق:** أخضرُ `--fast` ما يزال «ما قِيس مرّ» — الخطوةُ تضيف سؤالاً واحداً إلى الطبقة ولا تجعلها CI. وقياسُ جهاز الرطوبة الفيزيائيّ عملٌ ميدانيّ خارج هذه البيئة.
- **المصدر:** `scripts/ci/preflight.sh` (٦د) · `docs/architecture/preflight_required.json` · `tests_v9/test_local_preflight_contract.py` · فرع `claude/claude-md-docs-p6qqir` فوق `f9350d79`.
