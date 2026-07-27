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
| `058bd81` | **استثناء `services/decision-service/*` من مقياس تغطية الوحدة عبر `.coveragerc` جذر — إصلاح نطاق لا تخفيض أرضيّة.** السبب: decision-service مُختبَر بـPostgres حقيقيّ في وظيفة CI مخصّصة، غير قابل لـ`-m unit`؛ أسطره الصفريّة في مقام `--cov=services` عاقبت النسبة مع كلّ زيادة (انهارت دون ٤٠٪). الأرضيّة تبقى ٤٠٪؛ بوّابة المنصّة (‏.coveragerc خاصّة) لم تُمَسّ. لا كود غير مُختبَر يُخفى. |

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
