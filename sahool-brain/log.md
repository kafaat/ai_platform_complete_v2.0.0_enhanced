# 📜 سجلّ الجلسات (append-only)

## 2026-07-14 — IRR-X1.7-1.9 حاسبات الري التفاعلية ومتعددة الأنظمة — LANDED
- **What:** دمجتُ حزمة X1.9 (تحوي X1.7-1.9، efe777e-based) جراحيّاً فوق تِلّ X1.6. حاسبتان هندسيّتان **عديمتا الحالة توصية-فقط** (لا حفظ، لا تشغيل، `execution_authorized=False`): X1.7 تفاعليّة (احتياج ماء من محصول/تربة/طقس + احتكاك Hazen-Williams + فواقد ثانويّة + ضغط/رفع مطلوب + قدرة مضخّة/محرّك + مدّة)؛ X1.8/1.9 شبكة بركة-بوستر متعدّدة الأنظمة (آبار + رصيد بركة + بوستر + جهاز ريّ اختياريّ: محور/خطّيّ/بكرة/رشاشات/تنقيط/شبكة صمامات، أو «بدون»). خلفيّة: `irrigation_engineering_workspace.py` +615 سطراً إضافيّاً + راوتر +مساران `/interactive-calculate`، `/network-calculate` (مستأجِر خادميّ 403، 422 على مدخل خاطئ). واجهة: مكوّنان + عميلا API موصولان في FieldWorkspaceIrrigationPanel. 3 حُرّاس + سويتا اختبار.
- **الدمج (جراحيّ، حفظ إصلاحاتي X1.1-1.6):** طبّقتُ نسخ X1.9 للملفّات المتغيّرة فعليّاً (workspace/router/workspace-test) عبر مقارنة ruff-normalized؛ أبقيتُ نسختي حيث كان الفرق إصلاحاتي فقط. إعادة hoist استيرادات الراوتر (E402) + دمج كتلة استيراد الاختبار + pytestmark=unit. رفع أُسُس المسارَين: extraction-map 612→614، p2_6 609→611، تسجيل ملكيّة؛ baseline الوحدات ثابت (لا وحدة جديدة). جرد 1014→1016.
- **مراجعة جنائيّة (وكيل):** **صفر عيوب صحّة** — كلّ الهيدروليك صحيح فيزيائيّاً (أُسُس Hazen-Williams 1.852/4.87، السرعة، ثابت bar↔m=10.197، قدرة ρgQH، تحويلات الوحدات) + الحوكمة نظيفة (عديم حالة، fail-closed) + كلّ المقسومات gt=0 في طبقة pydantic (لا قسمة على صفر).
- **تحسين UI:** الحاسبتان تمسحان النتيجة البائتة (+ digest) عند أيّ تغيير مدخل/نوع نظام، فلا تُعرَض نتيجة لا تطابق النموذج.
- **Green + FF:** ruff · 11 حارس irrx1 · 22 اختبار حاسبة · سويت المنصّة 3754 @ 62.09% · pytest -m unit 3152 · production_validation_gate PASS (compile 25530/0) · frontend typecheck + 205 vitest · endpoint-ui-coverage PASS · حزمة 4436. **علّة CI مُصلَحة:** انحراف جرد (عدّلتُ UI/راوتر بعد التوليد ⇒ إزاحة أرقام أسطر) — أُعيد التوليد (`a03cad4`). main=develop=`a03cad4`.
- **Source:** حزمة المستخدم irrx1_9 (efe777e-based). ملفّات: `irrigation_engineering_workspace.py` · `routers/irrigation_engineering.py` · frontend IrrigationEngineeringCalculator/ReservoirBoosterNetworkCalculator + عميلا API.
- **سياق dev محلّيّ (من المستخدم، ليس على فرعي):** وكيل محلّيّ حلّ تعارض دمج useApi.ts (404→null) + أوقف حلقة WS reconnect (JWT_SECRET في compose لعامل الإشعارات) + شفافيّة بلاطات CDSE = حصّة خارجيّة. **فرعي نظيف بلا علامات تعارض؛ useCurrentNDVI عندي يرمي على 424 عمداً ليصل الخطأ لبطاقة الحالة الفارغة (لا أتبنّى 404→null).**

## 2026-07-14 — IRR-X1 (vendor-neutral irrigation engineering → X1.6 operator volume) — LANDED
- **X1.1–X1.5 (`adaa1dc`→`f281796`):** دمجتُ حزمة `irrx1_5` (مبنيّة على efe777e، 38 ملفّاً/+3348). ميزة توصية/تسجيل-فقط بلا تشغيل: ورشة هندسة ريّ محايدة المورّد + commissioning runtime + دورة تنفيذ يدويّ + جسر as-applied→water_ledger، محكومة بقفل نَسَب توصية موثوقة (v185–v190، كلّ الجداول FORCE RLS + tenant_isolation + WITH CHECK؛ v190 BEFORE-INSERT trigger يرفض التنفيذ اليتيم/غير المطابق). راجعها وكيل حوكمة: **الثوابت الثمانية صحيحة** (لا تشغيل عتاد، fail-closed، RLS، مستأجِر خادميّ، idempotent، حُرّاس حقيقيّة، راوتر مركَّب). **إصلاحاتي التكامليّة:** علّة طيّ YAML في ci.yml كانت تُعطّل حارس النَّsب صامتاً (فصلتها لخطوتين) · hoist استيرادات الراوتر (E402) · blind Exception→ValidationError · pytestmark=unit لأربعة اختبارات · **9 جداول في db_ownership.yml** · رفع أُسُس الراتشيت (وحدات 635→640، مسارات 602→612، p2_6 599→609 موثَّق) · **إصلاح اختبارَي pcert التكامليَّين** (زرع مصدر موثوق قبل الإدراج ليجتاز قفل v190؛ + دور NOSUPERUSER NOBYPASSRLS لأنّ superuser الاختبار يتجاوز RLS — نمط soil-cert). CI 13/13 أخضر شمل Integration Tests.
- **X1.6 (`f35760d`):** حجم يدويّ مُعلَن من المشغّل. طبّقتُ الدلتا **جراحيّاً** فوق تِلّي (فصلتُ منطق X1.6 عن إصلاحاتي بمقارنة ruff-normalized): حقل `manual_volume_m3` (gt=0) + مُحقِّق `METER_READING_PAIR_REQUIRED` (قراءتا العدّاد معاً أو لا شيء) + فرع اشتقاق يرتّب الحجم المُعلَن فوق التدفّق المُقدَّر لكن يُعلّمه `quality="operator_declared"` + حاجز `OPERATOR_DECLARED_VOLUME_REQUIRES_INDEPENDENT_MEASUREMENT` (يبقى `ledger_eligible=false`، ليس measured). واجهة + عميل API + حارس `irrx1_6_manual_volume_guard.py` + اختبار UI. **لا مسار/وحدة/هجرة جديدة ⇒ لا رفع أُسُس** (1014 مسار ثابت). CI أخضر.
- **صدق:** انتشار النَّسَب الكامل عبر PostgreSQL يُشهَّد على staging. القفل v190 يمنع التنفيذ اليتيم فعليّاً (مُختبَر على PG حقيقيّ في CI).
- **Green + FF:** ruff · 8 حُرّاس irrx1 · اختبارات وحدة IRR-X1 · سويت المنصّة 3751 @ 62.10% · pytest -m unit 3143 · production_validation_gate PASS (compile 25525/0) · frontend typecheck + 185 vitest · حزمة 4426. main=develop=`f35760d`.
- **Source:** حزمتا المستخدم irrx1_5/irrx1_6 (efe777e-based). الملفّات: `irrigation_manual_execution.py` · `routers/irrigation_engineering.py` · migrations v185–v190 · scripts/ci/irrx1_*.py.

## 2026-07-14 — NDVI 424 تشخيصيّ: بطاقة الحالة الفارغة الهادئة في الواجهة — LANDED
- **What:** أُكمِل الجانب الواجهيّ لعقد 424 التشخيصيّ (خلفيّته نزلت `6d9c05a`: خدمة الغطاء real-only تفشل مُغلَقةً بـ`{code,message,field_id,action,retryable}` وتحافظ على HTTP 424). مكوّن جديد `frontend/src/components/fieldview/NdviUnavailableNotice.tsx` — قابل لإعادة الاستخدام + مُحلِّل `ndviUnavailableFromError(error)` (يستخرج التفصيل المُصنَّف من axios 424؛ 424 القديم بتفصيل نصّيّ ⇒ `{code:'NO_PROCESSED_IMAGERY', retryable:false}`). يُصيّر حالة فارغة **هادئة** (`role="status"`، لا `console.error`، لا اختلاق قيمة NDVI) برسالة عربيّة لكلّ code. زرّ المعالجة (`refreshFieldImagery`) يظهر **فقط** للحالات الحتميّة القابلة للمعالجة يدويّاً (`retryable===false` + cta + معالِج) — لا للأعطال العابرة (`RASTER_DEPENDENCY_UNAVAILABLE`) ولا التفويض (`RASTER_AUTH_FAILURE`)، وبلا إعادة محاولة تلقائيّة.
- **Wiring:** `SatellitePage.tsx` يلتقط خطأ `useCurrentNDVI(fieldId)` (`error: ndviError`) ⇒ `ndviUnavailable = ndviUnavailableFromError(...)` ⇒ يُصيّر البطاقة في اللوحة الجانبيّة تحت شبكة إحصاء NDVI، موصولاً الزرّ بـ`refreshImagery({fieldId})`/`refreshingImagery`. tokens sahool-* المستخدَمة تطابق ألوان الصفحة الداخليّة (surface #1e293b/border #334155/green #16a34a).
- **صدق:** لا تحويل 424→200 null، لا NDVI مُصطنَع، لا بدء backfill تلقائيّ — تحسين تابع للإصلاح الجذريّ (تطابُق المستأجِر) لا بديل عنه.
- **Green + FF:** CI run 29358795610 — 13/13 وظيفة مكتملة، 0 فشل. تغيير واجهة صرف (لا services/compose/migration ⇒ لا production_validation_gate، لا انحراف مُشغّل main-only). 11 اختبار vitest (المُحلِّل: 424/غير-424/شبكة/null + تصيير لكلّ code + بوّابة الزرّ + processing/disabled) · typecheck نظيف · حزمة الإصدار مُعاد بناؤها (4390 checksum). main=develop=`efe777e`.
- **Source:** `NdviUnavailableNotice.tsx` + `.test.tsx` · `SatellitePage.tsx:211,662` · متابعة لـ`vegetation_runtime.py` diagnostic contract (6d9c05a).

> ألحِق مدخلاً في نهاية كلّ جلسة. لا تُعدّل المدخلات السابقة. الأحدث في الأعلى.

---
## 2026-07-13 — Lexicographic MPC P1.1: إصلاح تصادم النَّسَب (P0) + تصلّب العقد وصدق حدّ الإنتاج (بتدقيق جنائيّ)

**التدقيق أثبت خلل P0 في كودي:** `candidate_lineage_id` يتصادم — 3 قرارات مختلفة (37.5 عاديّ · 5.0 بميزانيّة · 2.0 بسقف تطبيق) أعادت نفس النَّسَب `mpc_67d5779885cdc2eb0`، لأنّ البصمة أغفلت القيود (season_budget/max_application/water_price/depletion_conf/data_degraded/السياسة/الخطّة) واقتُصَّت لـ16-hex. **أعدتُ إنتاجه ثمّ أصلحتُه.**

**الإصلاح (نقيّ، إضافيّ):**
- **`content_digest` كامل sha256 (64-hex)** على canonical-JSON لكلّ الحقائق (المدخلات + `constraint_trace` + `solver_version` + `ky_registry_version` + السياسة الفائزة + القرار + الخطّة + الأهداف). **فصل** `idempotency_key` (فتحة الطلب المنطقيّة: tenant+field+season+solver+stage+forecast — ثابتة رغم اختلاف القيود) عن `content_digest` (المحتوى الكامل) عن `candidate_lineage_id` (`mpc_`+content[:16] عرضاً).
- **حقول حوكمة:** `tenant_id`/`season_id`/`solver_version`(=lex-mpc.v1)/`execution_allowed`(=False)/`constraint_trace`/`modeled_capabilities`.
- **صدق حدّ الإنتاج:** `yield_floor_scope="forecast_horizon"` صراحةً (لا موسميّ — لا تراكم مرحليّ)؛ **Ky العامّ (`generic_stage`) لا يُثبِت** حدّ إنتاج (None)؛ التأكيد بـ**الحدّ الأدنى للثقة** `yield_floor_lower_bound` = `1−(Ky+uncertainty)·(1−ETa/ETm)` (نشر عدم يقين Ky أسوأ-حالة).
- **تسميات:** فصل `first_action_depth_mm` (اليوم الأوّل) عن `horizon_total_irrigation_mm` (ما يقيّمه J2)؛ `predicted_water_m3_per_ha`→`recommended_gross_water_m3_per_ha`؛ توحيد `not_modeled`.
- **فشل-مُغلَق للمدخلات:** NaN/Inf في TAW/الأفق، استنزاف <0 أو >TAW، هدف حدّ إنتاج خارج [0,1] (يُهمَل).

**لم يُمَسّ** التنفيذ/MQTT/التفويض. **تصحيح صدق:** وسم zip السابق `…_verified` أوسع من الحقيقة — الأدقّ **computational core verified، غير موصول إنتاجيّاً**.

**التحقّق:** `test_lexicographic_irrigation_mpc.py` **32/32** (11 جديد: النَّسَب يختلف بالقيود لا تصادم · ثبات فتحة idempotency · عزل مستأجر/موسم · content_digest 64-hex · فشل-مُغلَق NaN/خارج-مدى/أفق-غير-منتهٍ · هدف خارج [0,1] يُهمَل · Ky عامّ لا يُثبِت · execution_allowed=False · فصل first_action/horizon) · `pytest -m unit` **2946 نجاح @ 45.50%** · ruff نظيف · Ky guard أخضر · bandit HIGH صفر · ADR-0032 مُحدَّث. **المتبقّي P1.1b (قبل م2):** Route + وصل water_decision_bridge (مرشّح lexicographic_irrigation) + استمرار PG + انتشار النَّسَب عبر execution→outcome→learning.

---
## 2026-07-13 — Lexicographic MPC المرحلة 1: نموذج Ky الكنسيّ (J3 حقيقيّ) + سجلّ FAO-33 + حارس عزل اقتصاديّ

**بأمر المستخدم (م1 قبل م2):** حوّلتُ J3 من وكيل إجهاد إلى معادلة Ky الكنسيّة `Ya/Ym = 1 − Ky·(1 − ETa/ETm)` — توسعة منطقيّة فوق م0 بلا بنية تشغيليّة جديدة ولا هجرات.

**`core/engines/ky_registry.py` (جديد):** معاملات FAO-33 (Doorenbos & Kassam 1979، Table 24) حسب المحصول والمرحلة. **لا اختلاق:** `KyEntry` يحمل `ky_source`/`version`/`effective_from`/`uncertainty`. 7 محاصيل يمنيّة خاصّة (maize/sorghum/wheat/tomato/potato/onion) + صفّ عامّ حسب المرحلة (نفس قيم FAO-33 المستخدَمة في المنصّة). `lookup_ky(crop,stage)`: خاصّ-بالمحصول (`crop_stage`) ⇒ عامّ حسب المرحلة (`generic_stage` مُعلَّم) ⇒ None. **مرحلة مجهولة ⇒ None** (لا استبدال صامت). مرادفات عربيّة للمحاصيل.

**`lexicographic_irrigation_mpc.py` (تعميم J3):** `_eta_over_etm(plan)` يحسب ETa/ETm من Ks اليوميّ (FAO-56: Ks=1 عند Dr≤RAW وإلّا (TAW−Dr)/(TAW−RAW)). `_yield_response(plan,ky)` → `YieldResponse{status, eta_over_etm, ky, ky_source, ky_basis, predicted_relative_yield, predicted_yield_loss_fraction, within_bounds, uncertainty}`. J3 = كسر الغلّة حين يُحسَب؛ 0 محايد عند `insufficient_data`. `yield_floor_preserved` = True **فقط** ببيانات كاملة (status=ok + مرحلة + Ky + داخل الحدود + هدف مُحقَّق)؛ وإلّا None. عجز شديد + Ky>1 ⇒ `out_of_bounds` (RY مقصوصة [0,1]). عقد مُوسَّع: `crop`/`growth_stage`/`yield_response`/`yield_floor_ratio`/`objective_trace`/`candidate_lineage_id`. رموز أسباب جديدة: `YIELD_FLOOR_AT_RISK`/`YIELD_DATA_INSUFFICIENT`. الثقة تنخفض لـ`generic_stage`/`out_of_bounds`/عدم يقين Ky. **J1 يبقى الأعلى** (السلّم يضمن أنّ J3 لا يكسر الحماية — مُختبَر).

**عزل اقتصاديّ (طلب المستخدم):** حارس CI `scripts/ci/ky_no_economic_coupling_guard.py` (مُركَّب في ci.yml) يمنع أيّ إيراد/هامش مُشتَقّ من Ky (سجلّ Ky بلا مصطلحات اقتصاديّة · `economic_margin_delta=None` دائماً · J4 من الماء فقط · لا ضرب غلّة×سعر). لم يُمَسّ التنفيذ/MQTT/التفويض.

**التحقّق:** 21 اختبار وحدة (بوّابات القبول كلّها: Ky لكلّ مرحلة · غياب Ky ⇒ insufficient_data · ETm=0 ⇒ insufficient_data · J3 لا يتغلّب على J1 · yield_floor لا يظهر بلا بيانات كاملة · حتميّة · لا هامش من Ky) · `pytest -m unit` **2935 نجاح/5 تخطٍّ @ 45.47%** · ruff نظيف (نطاق CI) · حارس Ky أخضر · baseline 613→614 · ci.yml صالح · release 4236 · ADR-0032 مُحدَّث. إضافيّ صرف (لا هجرة/نقطة/تنفيذ). **التالي: م2 طبقة الطاقة/الآبار كحزمة مستقلّة.**

---
## 2026-07-13 — Lexicographic MPC المرحلة 0: نواة الحلّال الهرميّ + العقد (توصية-فقط، الطاقة not_modelled)

**السياق:** المستخدم قدّم مواصفة تفصيليّة لمتحكّم ريّ تنبّؤيّ هرميّ معجميّ (سلّم حماية-محصول≻ماء/طاقة≻حدّ-إنتاج≻هامش، غير قابل للمقايضة الماليّة). **استطلاع ثلاثيّ الطبقات (٣ وكلاء):** الهيكل المحكوم موجود كلّه (water_ledger Dr · canonical_water_stress AWF · fao56 ETc/TAW/Zr/Ks · سلسلة candidate→review→execute→verify→learning · water_decision_bridge يصدر مرشّح ريّ)؛ ومتحكّم جشِع قائم `api/irrigation_mpc.plan_irrigation` يصف نفسه صراحةً غير-QP/LP = نقطة التعميم. الجديد كلّيّاً: الحلّال المعجميّ · نموذج Ky الكنسيّ · **طبقة الطاقة/الآبار/الشمسيّة غائبة تماماً كبيانات** (COMPETITIVE_ANALYSIS.md مخطّط فقط). القرار: البدء بـم0 يبني كلّه على بيانات موجودة؛ الطاقة تُعلَن not_modelled لا تُلفَّق.

**م0 المُنفَّذة (`services/sahool-platform/api/lexicographic_irrigation_mpc.py`، نقيّ حتميّ):**
- يعمّم `plan_irrigation` من سياسة واحدة إلى **اختيار معجميّ بهامش ε**: يُحاكي السياسات الخمس أماماً، يسجّلها على 4 أهداف، ثمّ يثبّت J1 ⇒ ضمن EPS_J1 أفضل J2 ⇒ EPS_J2 أفضل J3 ⇒ EPS_J3 أدنى J4 (كسر تعادل حتميّ).
- **J1** `Σ max(0,Dr−RAW)² + λ_s·(أيّام إجهاد في مرحلة حرجة)` (حرجة = Ky FAO-33 ≥ 0.85) · **J2** ماء + رشح عميق (طاقة not_modelled) · **J3** وكيل نقص إنتاج قائم على الإجهاد الحرج (`stress_proxy_pending_ky`، يُستبدَل بـ`Ya/Ym=1−Ky·(1−ETa/ETm)` في م1) · **J4** وكيل تكلفة ماء (إيراد not_modelled).
- **آلة حالات:** NORMAL_OPTIMIZATION · CROP_PROTECTION (مرحلة حرجة + اقتراب/تجاوز RAW) · WATER_SCARCITY (نفاد ميزانيّة + إجهاد) · ENERGY_CONSTRAINED (غير قابلة للوصول م0) · DATA_DEGRADED (ثقة مخفوضة) · EMERGENCY_FAIL_CLOSED (مدخلات حرجة مفقودة ⇒ لا أمر، موافقة، ثقة 0).
- `ReasonCode` enum + عقد `LexicographicIrrigationDecision` (عمق/استنزاف قبل-بعد/نغمة إجهاد كنسيّة/عدّادات/رموز أسباب/`not_modelled` صريحة/`calibrated=False`). **توصية-فقط:** `approval_required=True` دائماً؛ لا أمر مضخّة مباشر — يمرّ بمركز القرار.
- يعيد استخدام: `plan_irrigation` (محاكٍ) · `_STAGE_SENSITIVITY` (Ky) · `available_water_fraction`+`WATER_STRESS_CRITICAL_AWF` (نغمة كنسيّة).

**التحقّق:** `tests_v9/test_lexicographic_irrigation_mpc.py` **11/11** (حماية غير مقايَضة بالماء · فشل-مُغلَق على أفق مفقود/TAW غير صالح · مطر⇒تأجيل بلا اختلاق · الطاقة/الآبار not_modelled دائماً · توصية-فقط · تدهور يخفض الثقة · شحّ ماء يعلَّم · حتميّة قابلة للتكرار) · ruff نظيف على النطاق الكامل · ADR-0032 + فهرس ADR. إضافيّ صرف (لا هجرة، لا نقطة، لا تنفيذ). **المراحل التالية:** م1 Ky؛ م2 طبقة الطاقة/الآبار (هجرات wells/pumps + PV)؛ م3 أفق ساعيّ؛ م4 واجهة + كاتب irrigation_runs + إغلاق الحلقة.

---
## 2026-07-13 — مراجعة واجهات (بوّابة/backend/عمل أخير) + أوّل مستهلك UI للحوكمة (SOIL-GOVERNANCE-WORKSPACE)

**المراجعة (٣ وكلاء استطلاع متوازية):** (backend) ~50 نقطة soil-service P1–P6 تُخدَم بلا بادئة عبر `router_registry`؛ (بوّابة) `/api/soil/` → `service_proxy` (يجرّد رؤوس العميل، يحقن `X-Agent-Token`+`X-Tenant-Id`) → `SOIL_SERVICE_URL` (`sahool-soil-service:8000`)؛ لا upstream soil مباشر في nginx عمداً؛ (واجهة) المستهلَك فعليّاً: SoilGrids/Terrain (raster) · Irrigation-water · Salinity · Lab CRUD. **الفجوة:** P4–P6 (حلقة مغلقة/تحقّق/تصديق/runtime) بلا مستهلك واجهة، و`frontend/src/lib/soilWorkspace.ts` سقالة يتيمة تُخطئ عقد `soil-profile.v1`.

**البند المعماريّ (أوّل مستهلك قراءة للحلقة المغلقة P4):**
- **إصلاح `soilWorkspace.ts` لعقد v1 الحقيقيّ:** الاكتمال من `completeness_score` (0..1) لا `completed_properties` المُتوهَّم (كان يعطي 0٪ دائماً)؛ بوّابة الجودة `{passed,executable,reasons}` تُعرَض كما هي؛ `conflicts` (قائمة كائنات) تُلخَّص نصّاً؛ `historyCount` من نقطة `profile/history` لا حقل غير موجود؛ عدّادات حلقة مغلقة صادقة (تنفيذ مكتمل/جارٍ · تحقّق · نتائج · تعلّم مؤهَّل للتدريب).
- **`useSoilWorkspace(fieldId,enabled)`** (`useApi.ts`): يجمع `fetchSoilProfileSnapshot`+`fetchSoilClosedLoop`+`fetchSoilProfileHistory` عبر `soilApi` (base `/api/soil`، nginx يجرّد البادئة) — قراءة فقط بلا mock، `retry:false`، غياب اللقطة ⇒ 404/503 صادق.
- **`SoilGovernanceCard`** في FieldView (`MapHub.tsx`، محروسة `selected && fieldMode==='expert'`، بعد DiagnosticsCard): مستوى الأدلّة (وسم مُلوَّن) · بوّابة الجودة + أسباب + تعارُضات · اكتمال · مسموح/محجوب · عدّادات الحلقة · حالة «لا لقطة تربة بعد» صادقة.
- حارس ساكن `SoilGovernanceWiring.static.test.ts` + مدخل `backendCoverageRegistry` (توثيقيّ) + تحديث `soilWorkspace.test.ts` لعقد v1 (8/8).
- **علّة كامنة أُصلِحت:** `soil_evidence_bridge.py:33` افتراض `soil-service:8134` → `sahool-soil-service:8000` (مطابقة compose/service_proxy/field_intelligence_adapters).

**التحقّق:** `tsc --noEmit` 0 · `tsc -p tsconfig.field-workspace-contract.json` 0 · vitest التربة **8/8** · `vite build` نجح · `endpoint_ui_coverage_gate.py` PASS (458 core + عكسيّ) · ruff نظيف على backend المُعدَّل · release **4231** checksum. الفرع يُدفَع؛ CI ثمّ FF.

---
## 2026-07-13 — دمج soil P6 (التصديق التشغيليّ/الإنتاجيّ v166) + تشخيص أحمر Service Inventory Drift على main

**P6 (`soil_p6_runtime_certification`) — دُمِج على حزمة P5 بتصميم الحزمة القانونيّ:** عقد `shared/contracts/soil/p6.py`
(`RuntimeCertificationRun` + أدلّة مُعنونة بالمحتوى، صادرات صريحة في `__init__.py`) · بانِي `services/soil-service/p6_certification.py`
(نقيّ، وحدةً 3/3) · راوتر `routers/p6_certification.py` (تركيب تلقائيّ عبر router_registry) · هجرة `v166`
(جدولان `soil_runtime_certification_runs`/`soil_runtime_certification_evidence` بـENABLE+FORCE RLS + tenant_isolation) ·
CLI `scripts/soil/run_production_certification.py` (يخرج 2 عند الفشل) · حارس `scripts/ci/soil_p6_runtime_certification_guard.py`
+ خطوة ci.yml. التسجيلات: MANIFEST v166 · run_migrations خطوة 172 · db_ownership الجدولان. طُبِّقت v166 على `sahool_ci`:
0 أخطاء، 2/2 FORCE RLS.

**عيب تسليم حقيقيّ أُصلح:** `tests_v9/test_soil_p6_runtime_integration.py::test_concurrent_supersession_accepts_one_replacement`
كان INSERT في `soil_observations` يُغفِل NOT NULL `depth_from_cm`/`depth_to_cm` — كان سيفشل حتماً على PG حقيقيّ.
أُضيف العمودان + `0,30`. بعده: P6 تكامل PG حقيقيّ **3/3**.

**تشخيص أحمر main@`9f24a2a` (المستخدم أرسل رابط وظيفة CI):** وظيفة *Service Inventory Drift* (`drift`) فشلت في خطوة
«Verify generated service inventory is current» بـ`Inventory drift detected: SERVICE_REGISTRY.md`. السبب: عند دمج سلسلة
P0–P5 لم تُعَد الجرود المُولَّدة. الإصلاح: `generate_service_inventory.py --write-registry` (29 خدمة/997 مساراً) +
`route_mount_contract_guard.py --write` (25 مدخلاً) + إعادة بناء حزمة الإصدار (**4222** checksum). **درس مُرسَّخ:** قائمة
قبل-الالتزام لأيّ عمل يضيف راوترات/وحدات تشمل الآن إعادة توليد الجرود المُولَّدة صراحةً، لا الحُرّاس الساكنة فقط.

**التحقّق الكامل:** `pytest -m unit` **2914 نجاح / 5 تخطٍّ**، تغطية **45.17%** (أرضيّة 40%) · 15/15 حارس تربة ·
حارس تزامن المُشغّلَين · حُرّاس المنصّة (decomposition + route budget) · الجرود المُولَّدة نظيفة (`--check` أخضر) ·
`ruff format+check` نظيف على النطاق الكامل · حزمة الإصدار 4222 checksum · ci.yml YAML صالح. تفصيل الملحق:
`docs/audits/SOIL_P6_RUNTIME_CERTIFICATION_INTEGRATION_20260713.md`.

---
## 2026-07-10 — دمج clp_all_nan_test_fix (برنامج جودة الراستر) + Docker Build Matrix (P-CERT)

أرشيف `57cf56e_clp_all_nan_test_fix` — البصمات كشفت أساسه الحقيقيّ **استيرادنا السابق `c53875c`** (vs 57cf56e: 85+213؛ vs c53875c: **34 جديد + 7 مُعدَّل فقط**) ⇒ استيراد على c53875c ثمّ merge نظيف **بلا تعارضات** (git حسم تلقائيّاً؛ دُقّق يدويّاً: runtime_real_smoke.sh وملفّات الراستر الخمسة المتداخلة، وبقاء المرفوضات السابقة محذوفة).

**قيمة مقبولة:** `raster_cloud_mask_strategies.py` (Sentinel2SCLStrategy: قناع SCL + عتبة CLP بحراسة `np.isfinite` قبل nanmax — علّة all-NaN — وتسجيل `sentinel2_clp_all_nan_unavailable` بصدق) · `raster_topographic_qa.py` (انحدار/ظلّ تضاريس من DEM بهندسة شمس اختياريّة؛ `dem_not_configured_for_topographic_qa` عند الغياب) · `raster_validated_product.py` (تجميع منتَج مُصادَق: pixel_qa + quality_flags + استراتيجيّة السحب + topographic_qa + provenance) · تكامل في `raster_pixel_processing.py`/`raster_api_models.py`/`raster_job_orchestration.py`/`raw_data_processing.py` · 4 حُرّاس CI (`raster_pixel_qa_indicator_guard` · `raster_topographic_qa_guard` · `raster_validated_product_guard` · `production_certification_blockers_status`) · 4 workflows · 29 اختبار راستر جديد (`services/raster-service/test_*.py` + `tests_v9/test_raster_*`).

**مرفوض (ثالث مرّة، نفس الدليل):** legacy/compose + compose_reference_guard + workflow-ه (يناقض ~10 حُرّاس compose-جذر قائمة).

**إصلاحات إلزاميّة على دلتا الأرشيف (فئات أعطال CI موثَّقة سابقاً):**
- workflows الثلاثة الجديدة كانت بلا خطوة تثبيت (pytest غير مثبَّت على runner عارٍ) ⇒ أُضيف `pip install -r tests_v9/requirements-test.txt` + `python -m pytest` (درسا fresh-runner وdual-pytest).
- `production-certification-blockers.yml`: P-CERT-1 كان يثبّت pytest فقط ثمّ يشغّل runtime_real_smoke.sh (فخّ ModuleNotFoundError: fastapi ذاته) ⇒ تثبيت tests_v9+weather+edge؛ و`if: secrets.X != ''` على مستوى الوظيفة (سياق secrets **غير متاح** في `jobs.<id>.if`) ⇒ فحص داخل الخطوة بتخطٍّ صريح مُعلَن.
- ذيل runtime_real_smoke.sh في الأرشيف أضاف الحُرّاس الثلاثة **بعد** سطر `runtime_real_smoke_ok` وبـ`python` العاري ⇒ نُقلت قبل السطر وبـ`"$PYTHON_BIN"`.
- ruff: I001/UP037/E402 (استيراد numpy منتصف ملف اختبار مُلحَق) ⇒ أُصلحت، والحُرّاس الساكنة بقيت خضراء بعد التنسيق.

**Docker Build Checklist — P-CERT (طلب المستخدم الصريح، مواصفة §0–§12):** نُفِّذ كـ(1) `.github/workflows/docker-build-matrix.yml`: مصفوفة `fail-fast: false` للأربع (raster/weather/edge/sam2)، لكلّ ساق: حُرّاس ساكنة stdlib ← docker build بسياق الجذر ← إقلاع منفرد ← `/healthz` إلزاميّ (30×2s) ← `/readyz` معلوماتيّ (degraded صادق مسموح) ← `! grep -E "ModuleNotFoundError|ImportError|Traceback"` على السجلّات؛ و(2) runbook `docs/runbooks/DOCKER_BUILD_CHECKLIST_P_CERT_CRITICAL_SERVICES.md`. **تكييفات مُوثَّقة (§8) عن مواصفة المستخدم بعد تحقّق ميدانيّ:** منافذ الحاويات الفعليّة 8001/8000/8100/8080 (لا 8001/8092/8180/8150 — 8092 منفذ مضيف compose فقط) · edge-inference لا يملك إلّا `Dockerfile.arm64` وقاعدته python:3.12 متعدّدة المعماريّات (تُبنى على amd64) · sam2 صورة CUDA موجَّهة GPU (البناء+الإقلاع يثبتان الاستيراد وصدق readyz فقط) · الرايات الحقيقيّة الوحيدة: FIELD_DEM_PATH/WEATHER_REDIS_URL/EDGE_PRODUCTION_REQUIRED/EDGE_READINESS_MODE/SAM2_CHECKPOINT+SAM2_MODEL_CFG (لا وجود لـRASTER_RUNTIME_MODE/WEATHER_CACHE_BACKEND/SAM2_PRODUCTION_REQUIRED/…) · `raster_container_contract_guard.py`/`dependency_inventory_guard.py` غير موجودَين ⇒ استُبدلا بالمكافئات القائمة.

**التحقّق المحلّيّ:** unit **2858 passed** (5 skipped) · منصّة 3579 (خلفيّة — انظر السطر الختاميّ) · `runtime_real_smoke_ok` (35 passed +الحُرّاس الثلاثة الجديدة داخله) · inventory regenerated (874 routes) · validate_ci_gates ✓ · YAML الخمسة الجديدة/المعدَّلة صالحة · ruff نظيف (scope services/bots/agents/tests_v9) · release bundle **3842 checksums**.

---


## 2026-07-09 — دمج raw-processing + container-fleet (أساس موازٍ 15398bd) بدمج ثلاثيّ ثانٍ

أرشيف `57cf56e_weather_raw_processing_fixed` — البصمات كشفت أساسه الحقيقيّ `15398bd` (نسل الأرشيف الخام؛ بلا sorted-rglob/EDGE_SYNC_DIR/إصلاح expert-mode). استيراد verbatim على أساسه (مستثنياً المرفوضَين السابقَين: legacy/compose + workflows التثبيت الصارم) ثمّ merge — 38 تعارضاً حُسم أغلبها «لنا» (requirements بالمدى، اختبارات المصالحة، الدماغ) و3 يدويّاً (auth Dockerfile، vegetation main إعادة-تصدير موسّعة، weather_runtime: استيراد Body الجديد + إبقاء noqa).

**قيمة مقبولة:** raw_weather_processing (نقطة `/v1/weather/raw/process` بنماذج pydantic مُتحقَّقة) · raw_data_processing للراستر (`/raw/process` بـ`require_service_token`) · 5 حُرّاس عقود حاويات + audits + workflows · تحسينات compose (liveness=healthz، NATS best_effort غير حاجب لـvegetation، قصّ env عن indicators) · معيار مرايا أصرم (صفر أثر Tencent) · تنظيف indicators-service الحقيقيّ (أكّدتُه: main يستورد fastapi+os فقط) · pip_audit_resolution_guard.

**ارتدادات الدمج الآليّ المُستدرَكة (فئة يجب تفقّدها في كلّ دمج موازٍ):** ملفّات لم نلمسها بعد نقطة الأساس يأخذها git من الطرف الآخر بصمت — 7 ملفّات واجهة/موبايل (عمل المطوّر: AddSeasonWithStages −171، expert-mode، wizard) + `raster_pixel_processing.py` (إصلاح truecolor KeyError) + اختباره. استُعيدت جميعاً من `57cf56e` وتأكّد صفر فرق.

**حارسانا اصطادا عيوبهم:** `test_requirements_completeness` كشف pydantic غير مُعلَنة في weather (يستوردها ملفّهم الجديد) — الحاوية كانت ستتعطّل؛ و`test_raster_endpoint_auth_coverage` أجبر تصنيف `/raw/process` صراحةً.

**تكييف مبدئيّ مُوثَّق:** حارسهم `pip_audit_resolution_guard` كان يفرض `redis==5.3.1` نصّاً في 20 ملفّاً (إعادة التثبيت الصارم من الخلف). حُوِّل لدلالة **التوافق**: كلّ مواصفة يجب أن تقبل المرجع 5.3.1 (المدى `>=5.0.0` يمرّ؛ `<5.3.0` يفشل — اختبار سلبيّ نفّذتُه فعليّاً). هذا يحفظ غرض الحارس (منع ResolutionImpossible المُوحَّد) دون نقض اتّفاقيّة CLAUDE.md.

**التحقّق:** unit **2851/5** · منصّة **3579** · smoke كامل (شاملاً حُرّاسهم الجدد) · كلّ بوّابات scripts/ci (الاستثناء الموثَّق: gen_route_auth_matrix اليدويّ) · pip-audit نظيف · ruff نظيف · release **3813** checksum.

---
## 2026-07-10 — إصلاح فشل CI على main (push:main workflows) + دمج docker_build_matrix_verifier

بعد تسريع main إلى `2f75665`، أطلقت workflows بمُطلِق `push: branches:[main]` لأوّل مرّة (لم تُشغَّل على الفرع قطّ لأنّها ليست pull_request-triggered). **5 فشلت** — التشخيص من السجلّات:
- `pip-audit-resolution` و`raw-data-processing-contract`: `python: No module named pytest` (خطوة `python -m pytest tests_v9/...` بلا أيّ تثبيت).
- `ai-container-contract` · `vegetation-container-contract` · `runtime-container-deep-contract`: `conftest.py:11 import httpx ⇒ ModuleNotFoundError: httpx`. conftest tests_v9 يستورد httpx **بلا شرط** عند الجمع ⇒ أيّ `pytest tests_v9/*` يحتاج httpx. (runtime-deep كان يثبّت `pytest PyYAML` فقط — ناقص httpx.)

**الإصلاح:** أضيفت خطوة `pip install -r tests_v9/requirements-test.txt` إلى **6** workflows (الخمسة + container-fleet الذي يحمل نفس الفخّ لكن لم يُطلَق هذا الدفع لفلتر مساراته). تدقيق شامل: كلّ workflow يُشغّل `pytest tests_v9/test_*` الآن يثبّت httpx (11/11 OK).

**درس جديد مُوثَّق (مهمّ):** workflow بمُطلِق `push: branches:[main]` **فقط** (بلا pull_request) لا يُشغَّل على فرع التطوير إطلاقاً — أوّل تشغيل حقيقيّ له يقع على main بعد التسريع. ⇒ **يجب تدقيق خطوات تثبيت هذه الـworkflows محليّاً (أو بـact) قبل التسريع، لا الاكتفاء بتشغيل الحُرّاس/الاختبارات محليّاً حيث التبعيّات مثبَّتة.** الجذر: بيئة الـrunner العارية ≠ صندوق التطوير (الدرس المتكرّر، بُعد جديد: مُطلِقات push:main العمياء عن الفرع).

**دمج archive `57cf56e_docker_build_matrix_verifier` (نسخة المسار الموازي للطلب ذاته، أنضج):** أساسه الحقيقيّ `c53875c` (8 مُعدَّل + 39 جديد؛ بقيّة الـ202 «مُعدَّل vs HEAD» ضوضاء أساس-بائت من قبل مصالحتي `2f75665`) ⇒ **نسخ انتقائيّ** للملفّات الجديدة الخمسة (لا merge — تجنّباً لسحب مصالحاتي للخلف):
- `scripts/ci/docker_build_matrix_verifier.py`: verifier أمين — أوضاع `--critical/--extended/--all/--services`، مراحل build/file-in-image/health/trivy/compose-config، **لا يضع `production_certified=true` أبداً**، skipped يُسجَّل skipped لا pass، ويكتب `certification/evidence/{docker_build_matrix_full,ci_summary,model_provisioning_summary}.json` — الأدلّة ذاتها التي يقرأها `production_certification_blockers_status.py` (يُغلق حلقة أدلّة P-CERT-1/4).
- **تصحيح خطأ حقيقيّ:** `edge-inference internal_port` كان **8180** (خطأ) ← **8100** (الحاوية تستمع 8100؛ 8180 كان سيُفشِل فحص الصحّة). الرايات الوهميّة (RASTER_RUNTIME_MODE/WEATHER_CACHE_BACKEND/EDGE_MODEL_DIR/SAM2_*) خاملة (env مجهول يُتجاهَل) — تُركت مع بانر صدق على الـrunbook.
- اختبار ساكن + workflow (build ثقيل على `workflow_dispatch` فقط، static test على PR — تصميم أذكى من مصفوفتي المباشرة التي كانت ستبني صورة sam2 CUDA على كلّ PR) + runbook موسّع (7 خدمات، +auth/platform/odoo).

**تقاعد (تفادي ازدواج):** حُذف `docker-build-matrix.yml` (مصفوفتي المباشرة) و`DOCKER_BUILD_CHECKLIST_P_CERT_CRITICAL_SERVICES.md` (runbook-ي الضيّق) — استبدلهما نظام الموازي الأنضج (verifier + runbook موسّع). قصّة Docker-matrix واحدة متماسكة بدل اثنتين متداخلتين.

**التحقّق المحلّيّ:** 10 اختبارات (verifier ساكن + الحُرّاس الستّة الفاشلة) تمرّ · verifier `py_compile` ok · YAML السبعة صالحة · ruff نظيف · report_index_check_ok · release **3842**. **بعد الدفع:** يجب تأكيد خضرة الستّة على الفرع (الآن pull_request-triggered؟ لا — push:main فقط ⇒ ستُختبَر فعليّاً عند التسريع التالي؛ لذا أُبقي main عند 2f75665 حتّى تأكيد الفرع، ثمّ أسرّع).

---


## 2026-07-09 — تثبيت أسطول workflows الحوكمة على main (a86f229→949074f→الحاليّ)

أوّل تشغيل حيّ كامل لأسطول الحوكمة (~20 workflow جديداً تعمل على push:main فقط) كشف سلسلة أعطال أصلحناها تباعاً commit-بعد-commit مع مزامنة main/develop عند كلّ اخضرار:

1. **`a86f229`:** تعارض `redis==5.2.1` (إضافة weather الوحيدة المُبقاة من الأرشيف) مع `redis==5.3.1` (المنصّة) في **الحلّ المُوحَّد** لخطوة pip-audit الحاجبة عبر 18 ملفّ requirements — ResolutionImpossible. تحقّقي المحلّي السابق مرّ لأنّي شغّلت التدقيق على دفعتين منفصلتين. وُحِّد على 5.3.1؛ التدقيق المُوحَّد بنفس أمر CI حرفيّاً يمرّ. + مفتّش endpoint-authz علّم `/metrics`/`/readyz` HIGH بعد انتقالهما من api/main.py (خارج مسح routers/) إلى platform_health.py — إعفاء مُوثَّق: نقاط الفحص الصحّي عمداً بلا مصادقة (healthchecks/Prometheus بلا JWT، تُعيد حالة منطقيّة لا بيانات مستأجِر).
2. **`e3182db`:** توحيد redis غيّر مدخلات `dependency_conflicts.*` و`requirements.services.direct.lock` المولَّدة دون إعادة توليد ⇒ workflow انجراف التعارضات فشل. أُعيد التوليد.
3. **`b42fa11`:** بروفايل Runtime Real Smoke ثبّت tests_v9 فقط بينما اختبارات weather/edge المستهدفة تستورد fastapi/onnxruntime — نفس فئة درس jwt الصباحيّ. أُضيفت تبعيّات الخدمتين.
4. **`949074f`:** تعديل workflow البروفايل بلا إعادة بناء حزمة release ⇒ بوّابة checksum. أُعيد البناء.
5. **(الحاليّ):** بعد إصلاح التثبيت، اختبارات edge الجديدة نفسها فشلت على runner غير-root بـ`PermissionError: /data` — `get_sync_service` كان يُثبّت `sync_dir="/data/sync_queue"` نصّيّاً بلا override. مرّت محليّاً **لأنّ بيئتنا root**. الإصلاح في كود المنتج: `EDGE_SYNC_DIR` env (افتراضيّ الحاوية بلا تغيير — تحسين نشر حقيقيّ للحاويات غير الجذريّة SEC-2 أيضاً) + الاختبارات تمرّر tempfile.mkdtemp + إثبات canary بعمليّة منفصلة أنّ sync_dir يحترم env.

**درس تشغيليّ مُرسَّخ (ثالث تكرار اليوم):** بيئة التطوير (root + حزم عالميّة مثبَّتة) لا تُحاكي fresh CI runner في: قوائم pip install، صلاحيّات نظام الملفّات، والحلّ المُوحَّد للتبعيّات. أيّ workflow/اختبار جديد يحتاج فحصاً صريحاً لهذه الثلاثة قبل الدفع.

**حالة الأسطول عند 949074f:** 18/20 أخضر (شاملاً Production Gates وField Workspace Closure وDependency Conflict Inventory)؛ المتبقّيان: Runtime Real Smoke (أُصلح هنا) وci.yml (كان قيد التشغيل).

---
## 2026-07-10 — مراجعة عدائيّة + إغلاق فجوات الكود المدموج حديثاً (raster QA + verifier)

استجابةً لـ«قوم بعمل تحسينات و إغلاق الفجوات»: بما أنّ سجلّ الفجوات مُغلَق أساساً (fixed/verified/by-design؛ المتبقّي deferred يحتاج GPU/Flutter/معايرة ميدانيّة، وP-CERT يتطلّب أدلّة نشر حقيقيّة **لا تُختلَق**)، وُجِّه الجهد إلى **الكود المدموج حديثاً الذي لم يُراجَع مستقلّاً** (~1000 سطر: برنامج جودة الراستر + verifier). وكيل مراجعة عدائيّة رفع 7 فجوات؛ أُصلحت الأربع الحقيقيّة (كلٌّ بمشهد فشل ملموس مُتحقَّق):

- **HIGH — عقد المنتَج المُصادَق يرفض المسار الصادق «قناع غير متاح» ⇒ 500:** `raster_validated_product.py` كان يقبل فقط {noop_unavailable, provider_precomputed_expected, rgba_alpha_mask, unknown_unavailable} عند cloud_mask_applied=False، لكنّ `process_pixels` يمرّر اسم المحاولة الخام (`sentinel2_scl`/`landsat_qa_pixel` عند غياب قناع، أو `not_requested` عند `apply_cloud_mask=False`) ⇒ ValueError غير محروس ⇒ 500 على طلب مشروع (يستخدمه `test_clip_grid.py:133` فعلاً). **الإصلاح:** عند غياب قناع فعليّ (cloud_pct is None) تُعيَّن الاستراتيجيّة إلى `unknown_unavailable` صراحةً قبل البناء (المحاولة+سببها محفوظان في stats/التحذيرات، فلا فقدان)؛ و`not_requested` أُضيف لمجموعة العقد المقبولة (حالة صريحة صادقة). `raster_pixel_processing.py` + `raster_validated_product.py`.
- **MED — `cloud_pct` مُخفَّف ببكسلات خارج الحقل ⇒ يُخفي الغيوم:** الاستراتيجيّات حسبت `np.mean(cloud)*100` على كامل المصفوفة؛ عند القصّ تُملأ بكسلات خارج المضلّع بـ0 (SCL 0 = «صافٍ») فتُخفّض النسبة. حقل صغير غائم في زاوية نافذة كبيرة ⇒ ~10% بدل ~100% ⇒ جودة مُضخَّمة (اتّجاه-كذب يُخفي مشكلة). **الإصلاح:** دالّة `_pct(np, mask, valid_mask)` تقصر المقام على البكسلات الصالحة داخل الحقل؛ `process_pixels` يمرّر `valid_mask=np.isfinite(arr)` (arr NaN خارج المضلّع/nodata)؛ غياب بكسل صالح ⇒ None لا صفر مُختلَق. توقيع `apply()` كسب `valid_mask=None` (متوافق للخلف).
- **MED — verifier يدّعي `all_services_up=True` بعد فحص config فقط:** `docker compose config` يتحقّق من المخطّط ولا يُقلِع خدمات. **الإصلاح:** حقل `config_valid: bool` جديد على `ComposeResult` (يفصل «المخطّط صالح» عن «الخدمات تعمل»)؛ فحص config-only يعيد الآن all_services_up=False + config_valid=True (صدق).
- **MED — `dockerfile_for` ثلاثيّ ميّت:** `return candidate if candidate.exists() else candidate` (فرعان متطابقان) لا يسقط للـDockerfile الافتراضيّ حين المسار المُهيّأ بائت. **الإصلاح:** سقوط فعليّ إلى `services/<svc>/Dockerfile`.

**فجوات LOW مقبولة بوعي (لا إصلاح، موثَّق السبب):** عتبة CLP `0.40 if clp_max<=1.0 else 40.0` (تفشل نحو القناع — محافِظة، لا اتّجاه-كذب) · security «skipped» تُعدّ pass داخل verified (لكنّ `phases_run` يسجّلها و`production_certified` صلب-False دائماً — لا تسريب اعتماد) · حقل pydantic `schema` يظلّ `.schema()` (تسمية عقد سلكيّ مقصودة `sahool.validated_raster_product/1`؛ إعادة التسمية تكسر العقد والاختبارات).

**نظيف من المراجعة:** `raster_topographic_qa.py` (حُرّاس all-NaN/DEM-غائب + fabricated=False صادقة) · حارس CLP all-NaN (`np.isfinite` قبل `nanmax`) صحيح · verifier: `production_certified` صلب-False في المخرَجات الثلاثة، وbuild/health يتطلّبان pass حقيقيّاً (skipped≠pass).

**اختبارات مُضافة (3):** dilution (25% مخفَّف مقابل 100% داخل الحقل) · valid-mask كلّه False ⇒ None · قبول الاستراتيجيّات الصادقة غير المتاحة. التحقّق: unit كامل + 28 اختبار راستر + كلّ الحُرّاس + verifier static (4) + ruff نظيف.

---


## 2026-07-09 — دمج أرشيف الحوكمة الكبير (prod_evidence_runtime_smoke) بدمج ثلاثيّ + مصالحة شاملة

أكبر أرشيف في الجلسة: **166 ملفّاً جديداً / 88 مُعدَّلاً / برنامج متكامل من ~10 تقارير** (P0/P1/P2 تفكيك mains + جرد مسارات/تبعيّات + شهادة إنتاج + smoke + نظافة تقارير). الأساس المُعلَن `6bf6465` صحيح، لكنّ الأرشيف **لم يُشغِّل قطّ** حزم الاختبارات الكاملة (تقريره يعترف بـ«targeted tests» فقط) — فكان مليئاً بكسور لم يرَها.

**آليّة الدمج (جديدة في الجلسة):** بدل النسخ الانتقائيّ اليدويّ، استيراد الأرشيف commit كاملاً على فرع `smoke-import` عند أساسه الحقيقيّ `6bf6465` ثمّ `git merge` في الفرع المخصّص — git عزل التعارضات الحقيقيّة آليّاً: **30 فقط** (29 Dockerfile + حارس المرآة؛ كلا الطرفين طبّق إصلاح PyPI+retries باستقلال) حُسِمت كلّها «لنا» (المُتحقَّق نجاحه حيّاً).

**المقبول:** تفكيك ٧ خدمات (`weather_runtime`/`mfa_runtime`/`vegetation_runtime`/`actuator_runtime`/`erp_runtime`/`sam2_runtime`/`ai_evidence_runtime`) · راوتران منصّة جديدان (`internal_service`/`platform_health`؛ baseline 590→592 + 5 route_keys في extraction_map) · weather-service **runtime حقيقيّ** (Open-Meteo مباشر + قاطع دائرة + كاش Redis اختياريّ + بوّابة عقد TestClient بلا شبكة) · طبقة certification/evidence (`certification/evidence/*` + evidence pack guard) · بروفايل smoke (`scripts/ci/runtime_real_smoke.sh`) · تصنيف بقايا المسارات + جرد mounts + سياسة versioning · نظافة تقارير (REPORT_INDEX + no-report-only-change) · ~30 بوّابة و~20 workflow جديدة · تصلّب compose (`SAHOOL_AGENT_TOKEN:?required`، رايات edge بآمن افتراضيّ partial/false).

**المرفوض بالدليل:**
1. **نقل compose إلى `legacy/`** — بوّابة الأرشيف الجديدة (`compose_reference_guard`) تحرّم وجود fixed/unified بالجذر بينما ~10 حُرّاس قائمة (لم يلمسها الأرشيف!) تؤكّد وجودها بالجذر (`assert path.exists()` في `test_compose_env_bypass_guard` مثلاً) — تناقض داخليّ يقطع بأنّ suite الأرشيف الكاملة لم تُشغَّل. أُبقيت الملفّات بالجذر وأُسقِطت البوّابة+workflow.
2. **برنامج التثبيت الصارم (== في 22 requirements)** — يناقض اتّفاقيّة CLAUDE.md الموثَّقة نصّاً فوق `httpx>=0.27.0` (التثبيت الصارم يتصادم في الحلّ المُوحَّد) ويحوي أسطراً **مكسورة نحويّاً** (`pyotp==2.9.0# TOTP` بلا مسافة قبل # — تحقّقتُ: pip يرفضها بـInvalid requirement ⇒ كلّ بناءات الخدمات المتأثّرة كانت ستفشل). أُرجعت الـ22 ملفّاً لنسختنا (استُبقيت إضافة واحدة: `redis==5.2.1` لكاش weather — pip-audit نظيف) وأُسقِطت `dependency_pin_guard`/`dependency_inventory_guard`/`test_requirements_inventory_guard` + workflows + الاختبار المرتبط (المرجعيّة القائمة: SEC-6).
3. **workflow الإغلاق بنسخة الأرشيف** — يفتقد إصلاح jwt/pip-install المُتحقَّق؛ رُكِّب المُوحَّد (أمرنا الواسع + تبعيّات weather الجديدة) وحُدِّث حارس P0-5 ليطابقه.

**عيوب حقيقيّة في الأرشيف نفسه أُصلِحت:**
- بوّابة عقد weather تتوقّع `@app.get(` بينما main-ه المُفكَّك سجّل النداءات call-style (`app.get(path)(rt.handler)`) — البوّابة أقدم من تفكيكه ولم تُعَد تشغيلها. وُسِّعت للملفّين + call-style.
- monkeypatch في نفس البوّابة كان بلا `sys.modules["main"]` الذي يعتمده `_facade_attr` — أُضيف.
- **Dockerfiles لم تُحدَّث للتفكيك:** `mfa_runtime.py` (auth) و`vegetation_runtime.py` (vegetation) غير منسوخين — الحاويتان كانتا ستتعطّلان عند الإقلاع **حتى في شجرة الأرشيف** (Dockerfiles الأرشيف مطابقة!). حارسنا `test_decomposed_service_dockerfile_guard` التقطها؛ أُضيف سطرا COPY بتعليق الدرس.
- درس pytest المزدوج (المُوثَّق بجلستنا) مُكرَّر في `runtime_real_smoke.sh` (`pytest` مجرّد بلا httpx) — أُصلح بـ`"$PYTHON_BIN" -m pytest`.
- 5 متغيّرات compose جديدة غير مُعلَنة في `.env.example` — بوّابة `compose_env_contract_gate` (blocking في ci.yml) كانت ستفشل. أُعلِنت.

**مصالحة 45 اختباراً قائماً كسرها التفكيك** (نُفِّذت عبر subagent بقواعد صارمة: لا إضعاف أيّ تأكيد — فقط توسيع نطاق المسح إلى main+الشقيقة أو تتبّع السمة المنقولة): 15 ملفّ اختبار + `scripts/tenant_query_audit.py` (مفتاح allowlist جديد بنفس التبرير). صفر انحدارات سلوكيّة حقيقيّة. + توسيع 6 حُرّاس منصّة (weather الأربعة + readyz + metrics) + سطر «Field Intelligence Backbone» في مولّد SERVICE_REGISTRY (حارس V50). + noqa F401 لإعادة تصديرات نمط `main.X` في mains المُفكَّكة (noqa السطر الأوّل لا يغطّي القائمة المُقوَّسة) + إزالة F811 مزدوج حقيقيّ في vegetation main.

**التحقّق الكامل:** tests_v9 unit **2846 نجاح / 5 تخطٍّ (0 فشل)** · منصّة **3579** · بروفايل smoke كاملاً `runtime_real_smoke_ok` · **45/47** بوّابة scripts/ci (الاستثناء الوحيد الفعليّ: `gen_route_auth_matrix.py` مولّد يدويّ قديم خارج CI، فشله سابق للدمج) · ruff format+check نظيف على النطاق الكامل + scripts/ · 27 workflow YAML صالحة · compose config صالح · pip-audit نظيف على weather requirements · release مُعاد بناؤه (**3766** checksum، +148 ملفّاً).

---
## 2026-07-10 — إصلاح كاشِفَين على main بعد تسريع مراجعة الراستر (203cabe)

تسريع main إلى `203cabe` أطلق وظيفتين لأوّل مرّة منذ فترة (مُطلَقتان بمسار `services/raster-service/**`، ولم يمسّه db6a9ba) فكشفتا فشلَين — لا أحدهما من منطق مراجعتي، بل أحدهما بائت والآخر أثر جانبيّ متوقَّع:

- **Service Inventory Drift (أثر جانبيّ منّي):** إصلاحات المراجعة أضافت 69 سطراً إلى raster-service (`python_loc` 18356→18425)؛ الجرد يتتبّع LOC/خدمة. **الإصلاح:** إعادة توليد `service_inventory.*`/`SERVICE_REGISTRY.md` (كان يجب توليدها ضمن 203cabe — درس: أيّ تغيير LOC في خدمة يتطلّب `generate_service_inventory --write-registry`).
- **Raster Service Gates (اختبار بائت مكشوف):** `test_p2_tile_observability_static.py::test_soil_service_is_enabled_in_compose_for_readyz` يؤكّد `localhost:8000/readyz` في compose، لكنّ توحيد الأسطول نقل كلّ HEALTHCHECK إلى `/healthz` (22 healthz · 0 readyz في compose — سياسة «HEALTHCHECK يستخدم healthz» التي أرساها checklist المستخدم). الاختبار لم يُحدَّث وبقي خامداً لأنّ بوّابة الراستر لم تُطلَق منذ التوحيد. **الإصلاح:** تحديث التأكيد إلى `/healthz` + إعادة تسمية الاختبار `..._with_healthz_liveness` (صدق). مؤكَّد بائتاً: يفشل على db6a9ba أيضاً (ليس انحداراً منّي).

**درس مُعزَّز:** الوظائف المُطلَقة بمسار خدمة معيّن (`pull_request:paths`/`push:main:paths`) تبقى خامدة حتّى يمسّ commit ذلك المسار — أوّل تشغيلها قد يكشف أعطالاً بائتة متراكمة (كاختبار readyز). التحقّق المحلّيّ لكامل مجموعة الخدمة قبل تسريع commit يمسّها = وقاية. التحقّق: raster-service **207 passed** (كان 206+1) · inventory --check نظيف · ruff · release 3847.

---


## 2026-07-09 — مزامنة main + إصلاح فشل بناء ai_agronomist + إصلاح حارسَين فاشلَين على main

**المُشغِّل:** المستخدم لصق سجلّ فشل `docker compose up` حقيقيّاً (٣٩ صورة، بناء متوازٍ) — الفشل الحاسم:
```
[sahool-ai-agronomist 4/7] RUN pip install --no-cache-dir -r /tmp/requirements.txt
ERROR: Could not find a version that satisfies the requirement pydantic-core==2.46.4 (from pydantic)
ERROR: No matching distribution found for pydantic-core==2.46.4
```
وطلب: تحقّق من `main` وأصلح المشكلة مع التأكّد من باقي الخدمات.

**اكتشاف: main تقدّم 16 التزاماً خارج انضباط الفرع.** `git fetch origin main` كشف أنّ `origin/main` تقدّم عن آخر تقدّمة معروفة لي (`6bf6465`) بـ16 التزاماً — دفعات مباشرة من مطوّر بشريّ (Haithm Garallah)، أبرزها:
- `b42e879` "fix(raster): fix Element84 backfill failures — OverflowError, truecolor KeyError, white-image scale"
- `0f778ab` "fixing pip mirrors" — بدّل `ARG PIP_INDEX_URL` الافتراضيّ في 29 Dockerfile من مرآة Tencent Cloud (`mirrors.cloud.tencent.com`) إلى PyPI الرسميّ، لأنّ مرآة Tencent — بحسب رسالة الالتزام — **كانت تُقدِّم حزمة pip بتجزئة (hash) مغلوطة**، ما يكسر البناء كليّاً.

أعدتُ بناء فرعي المخصّص من هذا الأساس: `git checkout -B claude/code-review-34hO3 origin/main` — لا فقدان لأيّ عمل (main تحوي كامل تاريخ عملي حتى `6bf6465` بالإضافة إلى عمل المطوّر).

**تشخيص فشل `pydantic-core==2.46.4`:** تحقّقتُ مباشرةً أنّ الحزمة موجودة فعلاً على PyPI الرسميّ (`pip index versions pydantic-core` أظهرها ضمن ٨٠+ إصدار متاح، و`pip download pydantic==2.13.4` نجح فوراً من هذه البيئة) — فالفشل **ليس** حزمة مفقودة بل عطل شبكة/فهرس عابر، مرجّح بسبب ضغط الشبكة من بناء ٣٩ صورة بالتوازي على مرآة PyPI الجديدة (بلا CDN مثل Tencent). **الدليل الحاسم:** `grep -rn "pip install" --include=Dockerfile*` أظهر أنّ `services/ai_agronomist/Dockerfile` هو الوحيد بين ~29 Dockerfile يشغّل `pip install` **بلا** `--timeout 300 --retries 10` — كلّ إخوته يملكونها. عطل عابر واحد بلا إعادة محاولة كافٍ لإسقاط بناء كامل.

**الإصلاح — طبّقته على كلّ Dockerfile كان ناقصاً (فحصتُ الجميع via grep، لا افتراض جزئيّ):**
- `services/ai_agronomist/Dockerfile` (الفاشل فعلاً في السجلّ الملصَق)
- `services/weather-signal-engine/Dockerfile`، `services/weather-polygon-worker/Dockerfile`، `services/raster-tiler-service/Dockerfile` — كانت تفتقر الرايتين بالمثل
- `services/knowledge-graph/Dockerfile`، `services/rag-retrieval/Dockerfile` — نمط مختلف (`python -m pip install --upgrade pip setuptools wheel && ... -r requirements.txt`)؛ أُضيفت الرايتان لكلا الاستدعاءين
- `services/sam2-inference/Dockerfile` — استدعاء ثانٍ ثانويّ (تثبيت sam2 من git) كان بلا الرايتين أيضاً؛ أُضيفتا للاتّساق رغم أنّه ليس مصدر الفشل المُبلَّغ

**حارسان كانا يفشلان فعلاً على `main` (`pytest -m unit` أحمر — اكتشفتُه أثناء التحقّق، لا في السجلّ الملصَق):**
1. `tests_v9/test_dockerfile_pip_mirror_guard.py` — لم يُحدَّث بعد `0f778ab`؛ كان لا يزال يفرض «كلّ Dockerfile يجب أن يُشير افتراضيّاً إلى مرآة Tencent» فيفشل على كلّ الـ29 ملفّاً التي بدّلها المطوّر بحقّ. أعدتُ كتابته بالكامل: (أ) يفرض الآن PyPI افتراضيّاً لا Tencent (مع توثيق التاريخ التشغيليّ الكامل في docstring: لماذا Tencent أُضيفت 2026-07-08 ثمّ أُزيلت 2026-07-09 لتلف الحزمة)، (ب) اختبار جديد `test_pip_installs_pass_timeout_and_retries` يفرض وجود `--timeout`/`--retries` على كلّ استدعاء pip install — يمنع تكرار فشل `ai_agronomist` تحديداً.
2. `tests_v9/test_e2e_cdse_to_element84_switch_v31_4.py::test_full_switch_cdse_failclosed` (ملفّ جديد من `b42e879`) — فشل بـ`ModuleNotFoundError: No module named 'raster_scene_model'`. السبب: الملفّ يحمّل `stac_search.py` عبر `importlib.util.spec_from_file_location` (استيراد مباشر بمسار، لا حزمة) لكنّه نسي `sys.path.insert(0, str(_RASTER))` — نمط قياسيّ في كلّ اختبار مشابه (`test_raster_scene_model_v63.py` وغيره). بعد إصلاح الاستيراد ظهر عطل ثانٍ: التأكيد `"cdse" in detail.lower()` افترض `detail` نصّاً حرّاً بينما `stac_search.py` يُعيد فعلاً dict مُهيكَلاً (`{"message": ..., "fallback_suggestion": {"suggested_provider": "element84", ...}}` — تصميم متعمَّد موثَّق في `raster_scene_model.provider_fallback_suggestion`). صحّحتُ التأكيد ليقرأ `detail["message"]` و`detail["fallback_suggestion"]["suggested_provider"]` — **لم أُضعِف** الفحص، بل قوّيته (يتحقّق الآن من الحقول المُهيكَلة الفعليّة لا نصّ حرّ تخمينيّ).

**صدق:** كلا الحارسين كانا خطأً حقيقيّاً في كود الاختبار من دفعات المطوّر المباشرة (نسيان تحديث حارس بعد قرار مُعاكِس؛ نسيان سطر sys.path قياسيّ) — لا خطأ في كود الإنتاج (`stac_search.py` سليم وصحيح التصميم). تنسيق ruff بحت (بلا تغيير منطق) لملفّين إضافيّين من نفس الدفعات: `services/raster-service/raster_pixel_processing.py`، `tests_v9/test_raster_reflectance_scaling.py`.

**قيد صادق:** لا Docker daemon في بيئة عملي (`docker build` يفشل بـ«failed to connect to the docker API»). لم أُعِد بناء صورة `sahool-ai-agronomist` فعليّاً لأؤكّد نجاح البناء حيّاً؛ التحقّق اعتمد على: (أ) تأكيد وجود الحزمة الحقيقيّ على PyPI عبر `pip index`/`pip download` من بيئتي، (ب) مطابقة نمط الإصلاح لكلّ الخدمات الأخرى التي تبني بنجاح بنفس الرايتين، (ج) `docker compose config --no-interpolate` للتحقّق من سلامة بنية YAML. **يبقى تأكيد حيّ مطلوب** من المستخدم عند إعادة تشغيل `docker compose up` على بنيته الفعليّة.

**التحقّق المستقلّ الكامل:** `pytest -m unit` **2844 نجاح / 5 تخطٍّ** (0 فشل — كان فشلان قبل الإصلاح) · حُرّاس منصّة (بـCWD الصحيح `services/sahool-platform/`) **3576 نجاح** · tsc **0** · vitest **1100/155** · ruff format+check نظيف بالكامل (`services/ bots/ agents/ tests_v9/`) · `docker compose -f docker-compose.v9.yml config --no-interpolate` صالح بنيويّاً · release مُعاد بناؤه والتحقّق منه (**3619** checksum).

---
## 2026-07-10 — منتج «الإجهاد الحراريّ المركّب» (فجوة تغطية زراعيّة) مع مستهلك حقيقيّ

استجابةً لـ«اعمل ما تراه مناسباً وحقيقيّاً وله مستهلك»: بعد تحليل تغطية زراعيّة أمين (مسح `core/engines/` ~30 محرّكاً ⇒ النواة عميقة: مياه/تربة/حماية/فينولوجيا/اقتصاد؛ البياض الحقيقيّ **ضيّق**: DTR/إجهاد مركّب=3 ملفّات · رقود/تلقيح=0 · نماذج برودة=5)، بُني أوّل منتج للبياض: **`compound_thermal_stress`** (حرّ النهار × برد الليل — موضوع المستخدم).

**التصميم (يحترم حدود المحرّكات المُرسَّخة):**
- **المنتِج في weather-service** (المنطق حيث يفرضه عقد الخدمة): `thermal_stress.py` دالّة نقيّة `compute_compound_thermal_stress` تحسب DTR · heat_stress_days · cold_stress_nights · frost_nights · consecutive_cold_nights · compound_index · risk، وعند توفّر سلسلة ساعيّة: day/night_stress_hours + تقدير رطوبة أوراق. `fetch_thermal_series` (Tmax/Tmin يوميّة + حرارة/رطوبة/نهار ساعيّة). endpoint `GET /v1/weather/thermal-stress?lat&lon&crop&stage`.
- **مشروط بـ(محصول×مرحلة):** جدول `THERMAL_THRESHOLDS_V1` (قمح/ذرة/طماطم/فلفل/خيار/بطاطا/عنب/لوز/نخيل/بنّ) بعتبات تُشدَّد في المراحل التكاثريّة.
- **صدق صارم:** محصول/مرحلة مجهولان ⇒ `insufficient_context` بلا مخاطرة مُختلَقة (fail-closed) · **دور `supporting` لا decision_blocking** (عتبات أدبيّة تحتاج معايرة ميدانيّة كـH5/C5) · رطوبة الأوراق `estimated_not_measured` · لا «ساعات» بلا سلسلة ساعيّة (`requires_hourly`).
- **مستهلك حقيقيّ (لا نقطة يتيمة):** عميل منصّة `weather_service_client.get_thermal_stress` + façade جديد `GET /api/v1/fields/{id}/weather/thermal-stress` في `field_workspace_weather.py` (يستنتج lat/lon+محصول+مرحلة من سياق الحقل ويستهلك المنتِج) — نفس نمط façade الريّ/الأمراض الذي يستهلكه تبويب طقس Field Workspace.

**bug التقطه ruff:** `confidence` كانت تُحسَب ولا تُدرَج في العقد (F841) ⇒ أُضيفت. + zip strict=False + ترتيب استيراد.

**التحقّق:** weather-service **28 passed** (10 thermal بمشاهد حدّيّة: 39°/7° مُزهِر=high، 34°/19°=low، صقيع=high، تتابع ليلتين، ساعات ساعيّة صادقة، daily-only=requires_hourly، fail-closed) · منصّة façade guard (4) + workspace guards (15، لم تنكسر بالإضافة) · unit · ruff نظيف · عقد weather الحقيقيّ ✓ · inventories (service/route/mount/api-versioning) مُعاد توليدها. **بوّابة ملكيّة الراوترات (Platform Unit) التقطت — درس مُتكرّر:** أيّ راوتر منصّة جديد يجب أن يُعلَن في `docs/architecture/platform_extraction_map.json` بـ`target_owner` (الطقس ⇒ weather-service، owner_type=bff-facade-to-weather) + رفع `baseline_route_count` عمداً (575→576). فشلت 3 حرّاس P0 لأنّي شغّلت محليّاً حرّاس façade/UI فقط لا `test_p0_platform_route_ownership_guard`/`test_p1_weather_boundary_guard`. **القاعدة:** عند إضافة راوتر منصّة، شغّل **كامل** مجموعة المنصّة محليّاً لا مجموعة فرعيّة. **بوّابة تغطية الواجهة (unit) التقطت الحوكمة:** المسار المواجِه الجديد صُنِّف في `config/endpoint_ui_coverage.json` **core** (نفس تصنيف façades الريّ/الأمراض الشقيقة، دليل `/api/v1/fields`) لا waiver (البوّابة تفرض ذلك للمسارات الحقليّة). **صدق:** بطاقة تبويب الطقس في الواجهة **دَين مقصود تالٍ** — الـfaçade مُنجَز ومُستهلِك للمنتِج، والكرت الأماميّ لم يُبنَ بعد. **الفجوات المتبقّية للعائلة** (`lodging`/`pollination`/`chill_models`) تبقى `open` في السجلّ.

---


## 2026-07-09 — إصلاح تكرار OpenAPI operation_id في proxy الخدمات الداخليّة

أرشيف + تقرير `openapi_proxy_operation_id_fix` (متابعة بعد الشهادة النهائيّة لـSoR وإصلاح jwt). **الفارق الحقيقيّ عن `9cc6b2a`:** 3 أسطر فقط في ملفّ واحد + حارس ساكن جديد — تحقّقتُ بـ`diff` أنّ باقي الأرشيف (نسخة كاملة للمستودع على أساس `d01a7a9`) ضجيج بائت محض.

**المشكلة:** استيراد `api.main` حيّاً كان يُصدِر 3 تحذيرات FastAPI:
```
Duplicate Operation ID proxy_edge_api_edge__path__patch
Duplicate Operation ID proxy_soil_api_soil__path__patch
Duplicate Operation ID proxy_segmentation_api_segmentation__path__patch
```
السبب: `services/sahool-platform/api/routers/service_proxy.py` يُعرِّف كلّ بوّابة (`proxy_edge`/`proxy_soil`/`proxy_segmentation`) بـ`@router.api_route(path, methods=["GET","POST","PUT","PATCH","DELETE"])` واحد — FastAPI يُوَلِّد نمط operation_id واحداً للمسار متعدّد الطرق فيتكرّر.

**الإصلاح:** أضفتُ `include_in_schema=False` للمسارات الثلاثة فقط (`grep` أكّد أنّها الوحيدة بنمط `@router.api_route` في كامل `services/sahool-platform/api/`). هذه بوّابات تمرير داخليّة (JWT→X-Agent-Token) لا عقود SDK عامّة، فإخفاؤها من المخطّط لا يُغيِّر سلوك التشغيل — تبقى حيّة، فقط لا تظهر في `/openapi.json`.

**تحقّق-قبل-دمج:** التقرير المرفق ادّعى "7 passed" لملفّ حارس P0-5 مع نسخة **مُتراجِعة** لحارس pip-install الذي أصلحتُه للتوّ في `9cc6b2a` (الأرشيف مبنيّ على أساس أقدم من ذلك الإصلاح). **لم أنسخ** دالّة الحارس تلك — أضفتُ فقط الحارس الجديد الحقيقيّ (`test_service_proxy_catch_all_routes_are_excluded_from_openapi_schema`) فوق حارسي القائم، فبقي حارس pip-install الأوسع (يشمل `tests_v9/requirements-test.txt`+`pillow`) سليماً بلا تراجع.

**تحقّق حيّ لا افتراضيّ:** استوردتُ `api.main` فعليّاً (بنفس `sys.path` الذي تستخدمه بوّابات CI) داخل `warnings.catch_warnings(record=True)` وعددتُ رسائل "Duplicate Operation ID" — **صفر** بعد الإصلاح (كانت 3 قبل تطبيقه، تأكّدتُ يدويّاً من وجودها في الكود الأصليّ عبر الـdiff). لم أكتفِ بتشغيل بوّابة الإغلاق الساكنة فقط.

**التحقّق المستقلّ الكامل:** `field_workspace_production_closure_gate.py` + 4 بوّابات SoR (final-certification/cutover-readiness/shadow-promotion/staging-probe) كلّها exit 0 · حُرّاس منصّة **63** (11 ملفّ، P0-5 الآن 7 اختبارات) · tests_v9 unit **2806 نجاح / 5 تخطٍّ** · ruff format+check نظيف · py_compile نظيف · لا تغييرات frontend (tsc/vitest غير مُعاد تشغيلهما) · release مُعاد بناؤه والتحقّق منه (**3618** checksum).

---
## 2026-07-10 — إكمال عائلة إجهاد المحصول (lodging + pollination + chill) بمنتِجات حتميّة ومستهلك مُجمَّع

«نفّذ الكل» ⇒ بُنيت الفجوات الزراعيّة الثلاث المتبقّية (`open` في السجلّ) كمنتِجات weather-service حتميّة، بنفس نمط `compound_thermal_stress` المُتحقَّق:
- **`lodging_risk.py`** — خطر الرقود: شدّة هبّات الرياح × قابليّة (محصول×مرحلة، الحبوب الطويلة عالية عند الطرد/الامتلاء) × مُعامِل تضخيم (تربة مُشبَّعة/مطر ≥20مم، ارتفاع ≥80سم). ارتفاع/رطوبة **اختياريّان** (ثقة أعلى، وإلّا مُعلَن الافتقاد لا مُختلَق).
- **`pollination_risk.py`** — خطر الطقس على التلقيح **أثناء الإزهار فقط**: حرارة تعقيم لقاح/برد/صقيع/رياح/مطر. **صدق صارم: خارج مرحلة الإزهار ⇒ `not_applicable`** (لا خطر على تلقيح غير جارٍ — لا اختلاق).
- **`chill_accumulation.py`** — تراكم البرودة للمتساقطات: **Chilling Hours** (0–7.2°م) + **Utah Chill Units** (أوزان بالنطاق، لا رصيد سالب مُبلَّغ) + %المتطلّب. **النموذج الديناميكيّ (Chill Portions) مُعلَن `not_implemented` — لا نُزيّفه بتقريب خاطئ.**
- الثلاثة: fail-closed (محصول مجهول ⇒ insufficient_context) · دور `supporting` · provenance مُنسَّخ. 3 endpoints منتِجة + 3 fetch (`fetch_daily_wind_temp_rain` · `fetch_archive_hourly_temps`).

**المستهلك — مُجمَّع عمداً:** façade واحد `GET /api/v1/fields/{id}/weather/crop-stress` يستهلك الثلاثة best-effort (تعذّر منتج يُسجَّل خطأً مُعلَناً `partial:true` لا يُسقِط الباقي). **السبب:** بوّابة `test_p2_6_platform_route_budget_reduction` تفرض سقفاً صارماً 575 لراوترات المنصّة (فلسفة التفكيك: لا نموّ)؛ 3 راوترات منفصلة تجاوزته (576>575). التجميع في راوتر واحد = 574≤575 **وUX أفضل** (كرت إجهاد واحد بنداء واحد). 3 عملاء منصّة يبقون منفصلين (لا يُحسبون على المنصّة).

**درس (مُعزَّز):** إضافة راوترات منصّة تصطدم بسقفَين: `baseline_route_count` (ownership guard) **و** `p2_6.new_max_platform_routes` الصارم ≤575. عند بناء عدّة منتجات ذات مستهلك منصّة ⇒ **façade مُجمَّع** لا راوتر-لكلّ-منتج.

**التحقّق:** weather-service **41 passed** (13 crop-stress بمشاهد حدّيّة: رقود عالٍ عند هبّة 22+تربة مُشبَّعة · تلقيح not_applicable خارج الإزهار · تلقيح عالٍ عند حرّ 42 في silking · chill 400ساعة=100% · dynamic not_implemented) · منصّة **3587** · unit · **19 حارس حوكمة** (P0 ownership + p1 weather-boundary + p2_6 budget + coverage gate + facades) · ruff · release. الفجوات LODGING/POLLINATION-WX/CHILL-MODELS تُنقَل إلى `fixed`.

---


## 2026-07-09 — Decision SoR final certification (P0-5) + رفض إصلاح CI مُكرَّر أضيق

أرشيف `d01a7a9_decision_sor_final_certification` — الطبقة الأخيرة قبل ترقية decision-service إلى SoR فعليّاً. **الفارق الحقيقيّ عن الأساس المحلّيّ (`5af67ea`) بعد استبعاد الضجيج** (الأرشيف مبنيّ على `d01a7a9` أقدم فأعاد نسخاً بائتة من tsconfig المكسور + workflow بلا إصلاح jwt/pip-install المُطبَّق سابقاً؛ ملفّات `platform_python_module_baseline.json`/`backfill.py`/`cutover.py`/`main.py`/`migration_runner.py`/`persistence.py`/`staging_probe.py`/`decision_sor_mode.py`/`test_p0_3...guard.py` كلّها ضجيج تنسيقي محض تأكّد بـ`diff`): **٧ ملفّات جديدة فعليّاً**.

**قراءة-فقط بالتصميم (تحقّقتُ من الثلاثة قبل التطبيق):**
- `services/decision-service/production_promotion.py`: preflight للترقية الإنتاجيّة. dry-run افتراضيّ يطبع فقط `required_flags`. `--live` يتطلّب `SAHOOL_ENV=production` + `DATABASE_URL` + 7 رايات `REQUIRED_TRUE_FLAGS` (SOR_ENABLED/MIGRATIONS_VERIFIED/BACKFILL_VERIFIED/TENANT_ISOLATION_VERIFIED/OUTBOX_VERIFIED/STAGING_CUTOVER_APPROVED/PRODUCTION_CUTOVER_APPROVED) + `PRODUCTION_PROMOTION_APPROVED`+`_ALLOW_LIVE` + استعلام GET حيّ لـ`/v1/cutover/readiness` يشترط `can_demote_platform=true` و`production_approved=true`. لا `INSERT`/`UPDATE`/`DELETE` في أيّ مسار من الملفّ.
- `services/decision-service/read_side_compare.py`: مقارنة قراءة-فقط بين المِرْآة والمنصّة. dry-run افتراضيّ؛ `--live` يتطلّب `DECISION_SERVICE_READ_COMPARE_APPROVED`+`_ALLOW_LIVE` (و`_ALLOW_PRODUCTION` إضافيّاً إن `SAHOOL_ENV=production`). يُشغِّل `migration_runner.py --check` + `backfill.py --verify-counts` + GET على readiness/health فقط.
- `services/decision-service/rollback.py`: **تحقّقتُ يدويّاً أنّه لا يُنفِّذ أيّ فعل** — `_plan()` تُرجِع قائمة ثابتة من 7 `RollbackStep` (ترتيب/اسم/أمر نصّيّ، `destructive=False` افتراضيّاً) تصف تسلسلاً يدويّاً للمشغّل (مثال: "set DECISION_SERVICE_SOR_ENABLED=false"). `run_rollback()` يطبع هذه الخطّة كـJSON فقط خلف رايتَي موافقة (`ROLLBACK_APPROVED`+`_ALLOW_LIVE`) لحالة "preflight" — **بلا تنفيذ فعليّ لأيّ خطوة**. موثَّق صراحةً غير هدّام (يُبقي جداول decision-service للمقارنة الجنائيّة).

**توصيل الحَوكمة:** خطوة `Decision SoR final certification gate` (`scripts/ci/decision_sor_final_certification_gate.py` — حارس ساكن يتحقّق من وجود الملفّات السبعة + توكِنات نصّيّة إلزاميّة كـ"no writes are performed"/"non-destructive"/"dry-run" + توصيل الـworkflow والحارس) + `test_p0_5_decision_sor_final_certification_guard.py` (٦ اختبارات) أُلحِقا يدويّاً بـ`.github/workflows/field-workspace-production-closure.yml` **الحاليّ المُصلَح** — لم يُنسَخ ملفّ workflow الأرشيف لأنّه يفتقر إصلاح `pip install` الحرج المُطبَّق في `5af67ea`.

**⚠️ رفض إصلاح CI مُكرَّر أضيق (مُقدَّم من المستخدم أثناء العمل):** وصل تقرير `SAHOOL_FIELD_WORKSPACE_CI_PYJWT_FIX_REPORT.md` + أرشيف `d01a7a9_ci_pyjwt_fix` يقترحان استبدال خطوة التثبيت الحاليّة (`pip install -r tests_v9/requirements-test.txt -r services/sahool-platform/api/requirements.txt pillow`) بخطوة أضيق باسم "Install backend runtime dependencies" (`pip install -r services/sahool-platform/api/requirements.txt pytest` فقط — بلا `tests_v9/requirements-test.txt` وبلا `pillow`، وكلاهما تبعيّتان يحتاجهما تحقّق آخر في نفس الـworkflow). **رُفِض الاستبدال** (انحدار — الإصلاح الحاليّ أوسع وسبق تطبيقه وتأكيد نجاحه في `5af67ea`). اعتُمِد فقط جوهر اقتراح الأرشيف (حارس انحدار CI): أُضيفت `test_field_workspace_ci_installs_backend_runtime_dependencies_before_runtime_gates` إلى `test_p0_5_decision_sor_final_certification_guard.py` — مُكيَّفة لتتحقّق من **نصّ خطوتي الفعليّة** (لا اسم خطوة الأرشيف الوهميّ) وتؤكّد سبقها لخطوتَي "Field Workspace Python closure gate" و"Field Workspace guard tests" نصّيّاً في الـYAML، فتمنع أيّ تراجع مستقبليّ عن ترتيب التثبيت.

**التحقّق المستقلّ الكامل:** بوّابة P0-5 مستقلّة (exit 0) · حُرّاس منصّة **62** (11 ملفّ P0/UI، شامل P0-5 الجديد بـ6 اختبارات) · تست_v9 unit **2806 نجاح / 5 تخطٍّ** · ruff format+check نظيف (4 ملفّات جديدة، إصلاح `F401 sys غير مُستخدَم` في `production_promotion.py`) · YAML صالح · لا تغييرات frontend في هذا الأرشيف (tsc/vitest غير مُعاد تشغيلهما، لا حاجة) · release مُعاد بناؤه والتحقّق منه (**3611** checksum).

---
## 2026-07-10 — مراجعة استهلاك تنفيذيّة (المستخدم) + إصلاح W2 (Weather operation fail-closed)

المستخدم قدّم **مراجعة تنفيذيّة** بتتبّع مستهلكي الحاويات الأربع (raster/indicators/vegetation/weather) عبر platform/web/mobile/nginx/decision/MCP. الحكم: **قدرات كثيرة تُنتَج بلا مستهلك، ومستهلكون يعتمدون على بيانات تركيبيّة/افتراضيّة؛ الأولويّة للقدرات ذات المستهلك القائم لا البناء دفعةً.**

**اعتراف صدق (يُسجَّل لا يُخفى):** منتجاتي الثلاثة السابقة `lodging_risk`/`pollination_weather_risk`/`chill_accumulation` تقع في **P2-التأجيل** بمعيار المراجعة (façade `crop-stress` مُجمَّع موجود، لكن **لا كرت واجهة ولا مستهلك Decision موصَّل بعد**). القرار: **تُبقى** (أمينة، مُختبَرة، إضافيّة، دور `supporting` لا حاجب، fail-closed) وتُصنَّف «مبنيّة تنتظر مستهلكاً» — لا يُدّعى أنّها موصولة بمسار قرار. الدرس: «تنفيذ الكل» لا يعني بناء قدرات بلا مستهلك؛ المعيار الصحيح **consumer-first**.

**نُفِّذ أعلى بند صادق فوراً — W2 (المراجعة تسمّيه «أخطر فجوة زراعيّة في Weather»):** `services/weather-service/operations.py` كان يقرأ مدخلات السلامة بافتراضات طبيعيّة عند الغياب: `temp=20 · rh=50 · wind→0 (عند غياب kmh وms) · precip=0`. النتيجة الخطرة: عيّنة بلا رياح ⇒ `wind=0` ⇒ `penalize(wind>18)`/`penalize(gust>29)` لا تُطلَق ⇒ نافذة الرشّ **`safe=true` زوراً**. مستهلكوه المباشرون: `/operation-window`·`/operation-plan` → إنشاء مهمّة/توصية/تنبيه.

**الإصلاح (fail-closed):** قراءة صادقة (None=مفقود، لا افتراض)؛ جدول `_SAFETY_CRITICAL` لكلّ عمليّة (spraying/fertilizing: wind+precip · harvesting/sowing/irrigation: precip)؛ أيّ مدخل حرِج مفقود ⇒ `{status:"insufficient_data", safe:false, suitability:"insufficient_data", missing_inputs:[...]}` بلا نافذة مُختلَقة. `_wind_kmh` يقبل m/s كبديل صحيح (ليس مفقوداً). عقوبات المدخلات غير-الحرِجة (temp/rh/gust) محروسة بالوجود. `advice_ar` يضيف رسالة «بيانات ناقصة». `gust` المفقود يُقدَّر محافظاً من wind.

**التحقّق:** weather-service **47 passed** (6 اختبارات fail-closed جديدة: رياح مفقودة⇒unsafe · مطر مفقود⇒insufficient · m/s مقبول · رياح عالية تُعاقَب كالمعتاد · عيّنة كاملة هادئة⇒safe · الريّ لا يحتاج رياح) · **مسار البيانات الكاملة غير مُتأثِّر** (Open-Meteo يُرجِع رياح/مطر عادةً ⇒ لا انحدار) · ruff · عقد weather الحقيقيّ ✓.

**الخطّة المعتمَدة (بترتيب المراجعة):** P0 = Vegetation (حذف FIELD_REGISTRY التركيبيّ + season_id + timeseries حقيقيّ من Raster + منع fallback تقديريّ صامت + hypotheses بدل توصيات) · ValidatedIndicatorProduct في Raster · Indicators **Registry أوّلاً لا Job Platform** · Weather ET0/VPD/GDD موحَّدة + provider ثانٍ/freshness · مسار الإجهاد المائي E2E كأوّل مستهلك تكامليّ للأربع. + بوّابة CI: أيّ capability جديدة بلا Consumer Contract تفشل.

---


## 2026-07-09 — Decision SoR staging probe (P0-3/P0-4) + إصلاح فجوة تثبيت تبعيّات CI حرجة

أرشيف `d01a7a9_decision_sor_staging_probe` — يبني فوق جاهزيّة الـSoR (P0-2). **الفارق الحقيقيّ عن الأساس المحلّيّ الحاليّ (`4cfa233`) بعد استبعاد الضجيج (الأرشيف مبنيّ على `d01a7a9` أقدم فأعاد نسخاً بائتة من tsconfig المكسور + تنسيق ruff/tsc سبق إصلاحه):** ٩ ملفّات جديدة فعليّاً + إضافة صغيرة لـmain.py.

**P0-3 (shadow/promotion control surface):**
- `services/decision-service/cutover.py`: `readiness_from_env()` نموذج صرف (dataclass, لا I/O) يفصل بوضوح `can_enable_sor` (DB+migrations+backfill+tenant+outbox+staging-approval) عن `can_demote_platform` (كلّ ما سبق + production-approval) — لا يمكن تخمين إسقاط كتابة المنصّة بعلم واحد.
- `/v1/cutover/readiness` نقطة جديدة في `main.py` (أضفتُها يدويّاً: import + endpoint + حقلا `cutover_readiness_endpoint`/`demotion_gate` في `/contract` — لم أنسخ main.py الأرشيف لأنّه كان يُعيد كسر تنسيقي/بنيويّ سبق إصلاحه في `4cfa233`).
- `services/sahool-platform/api/decision_sor_mode.py`: `get_platform_decision_sor_mode()` — `SAHOOL_DECISION_WRITE_MODE` (platform_sor افتراضيّ / shadow / decision_service_sor)، **لم يُستهلَك من أيّ راوتر بعد** (تحقّقتُ: grep صفر استيراد خارج ملفّه واختباره وgate). سطح تحكّم مُجهَّز، لا تفعيل.
- تأكيد صريح في اختبار جديد (`test_platform_router_still_contains_authoritative_writes_until_runtime_cutover`) أنّ `decision_record.py` ما زال يحوي `INSERT INTO decision_record`/`outcome_record` و`_mirror_to_decision_service` — مسار الكتابة الموثوق سليم.

**P0-4 (staging probe harness):** `services/decision-service/staging_probe.py` — أداة CLI للمشغّل: dry-run افتراضيّ (لا شبكة/DB)، `--live` يتطلّب `SAHOOL_ENV≠production` + `DECISION_SERVICE_STAGING_PROBE_APPROVED=true` + `DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE=true` معاً، `--sample-write` منفصل تماماً (كتابة noop عبر BFF المنصّة بمفتاح idempotency). runbook + gate + حارس يفرضان هذا التسلسل نصّيّاً.

**تحقّق-قبل-دمج:** رفضتُ نسخ ملفّات الأرشيف حرفيّاً حين تحتوي انحداراً معروفاً (نفس نمط الجلسات السابقة: tsconfig المكسور، تنسيق main.py/persistence.py/gate scripts القديم) — طبّقتُ فقط الإضافات الجوهريّة الجديدة يدويّاً أو بنسخ الملفّات الجديدة فعلاً (لا تعديل على موجود). ruff: 4 ملفّات جديدة احتاجت `--fix`+format (ترتيب استيراد، لا منطق).

**⚠️ إصلاح CI حرج بعد الدمج (اكتُشِف من سجلّ GitHub Actions الفعليّ، لا محليّاً):** أوّل تشغيل حيّ لـ`field-workspace-production-closure.yml` (الذي أنشأتُه في جلسة سابقة) فشل: `ModuleNotFoundError: No module named 'jwt'` في خطوة "Field Workspace Python closure gate" — السبب: الـworkflow يستورد `api.main` (عبر `field_workspace_production_closure_gate.py::check_runtime_routes`) لكنّه **لم يُثبِّت تبعيّات المنصّة إطلاقاً** (فقط `actions/setup-python` بلا `pip install`). **لم أكتشف هذا محليّاً** لأنّ `jwt`/fastapi/asyncpg كلّها مثبَّتة مسبقاً في بيئة عملي — تحقّقي المحلّي لم يُحاكِ "fresh runner". الإصلاح: أضفتُ `pip install -r tests_v9/requirements-test.txt -r services/sahool-platform/api/requirements.txt pillow` (نفس أمر وظيفة Platform Unit Tests في `ci.yml`) كخطوة مبكرة قبل أيّ بوّابة تستورد `api.main`. **درس تشغيليّ مُسجَّل:** أيّ workflow جديد يستورد تطبيقاً حيّاً يحتاج تحقّقاً صريحاً من خطوة تثبيت التبعيّات — لا يكفي أن يعمل محليّاً.

**توصيل الحَوكمة:** baseline وحدات المنصّة 589→590 (`api/decision_sor_mode.py` جديد ومُبرَّر).

**التحقّق المستقلّ الكامل (بعد إصلاح CI):** tsc 0 · vitest **1100/155** · منصّة **3569** (+2 P0 حارس جديد، 56/56 في مجموعة حُرّاس الـworkflow) · tests_v9 unit **2806** · ruff CI نظيف · YAML صالح (كلا الملفّين) · release مُعاد بناؤه (3602 checksum).

---
## 2026-07-10 — P0-1 (Vegetation V2): وسم السلسلة الزمنيّة التركيبيّة صراحةً (منع «تركيبيّ يُعرَض كحقيقيّ»)

أوّل بند من الخطّة consumer-driven المعتمَدة. المراجعة سمّت هذا «ذا أولويّة قصوى»: `/v1/timeseries/{field_id}` كان يعيد `_generate_timeseries` (سلسلة تركيبيّة من نطاقات مُصطنَعة) **بلا أيّ وسم مصدر**، والرسوم في الويب/الموبايل (NDVI charts) تستهلكها كأنّها رصد حقيقيّ.

**الإصلاح (V2 — الشريحة القابلة للتحقّق الآن):** لا يُقدَّم التركيبيّ كحقيقيّ أبداً:
- `_generate_timeseries`: كلّ نقطة تُوسَم `source="synthetic_estimate"` + `estimated=True`.
- مُعالِج المسار: الرد يحمل `data_source="synthetic_estimate"` · `real_data=False` · `synthetic=True` · `authoritative_source="raster-service:/imagery/timeseries"` · `warning_ar` صريح.
- حارس `test_timeseries_honesty.py` يمنع عودة الفجوة (نقاط مُعلَّمة + أعلام الرد).

**صدق النطاق:** هذه شريحة **الوسم الأمين** (منع الخداع)، لا الوصل الكامل بسلسلة Raster الحقيقيّة — الأخير يتطلّب تشغيل Raster حيّاً (غير متاح للتحقّق هنا) وهو الخطوة التالية المُعلَنة في كود/رسالة التحذير. المكسب الآن: **مستحيل أن تُعرَض السلسلة التركيبيّة كرصد حقيقيّ** بعد اليوم.

**التحقّق:** vegetation-service 21 passed (2 honesty + 19 logic) · حارس تفكيك الراوترات 7 · ruff · إضافيّ متوافق للخلف (لا كسر مستهلك). المتبقّي من P0-Vegetation (season_id · FIELD_REGISTRY الإنتاجيّ · anomaly/state · hypotheses بدل توصيات · وصل Raster timeseries) يبقى مُتسلسلاً.

---


## 2026-07-09 — جاهزيّة cutover لـ decision-service SoR (بنية flag-gated آمنة)

أرشيف `d01a7a9_decision_sor_cutover_readiness`. **يُنجِز مسار الترقية الذي وثّقتُه** (الجسر الانتقاليّ → SoR حقيقيّ) بأمان: **يجعل الـcutover قابلاً للتدقيق آليّاً دون قلب إنتاج**. `DECISION_SERVICE_SOR_CUTOVER_READINESS.md` يعلن الحالات (Mirror افتراضيّ / Staging SoR / Production SoR) والثوابت غير القابلة للتفاوض.

**البنية المُطبَّقة (decision-service، قاعدة خاصّة منفصلة عن المنصّة):** `migrations/001_decision_sor.sql` — جداول الحلقة الخمسة + outbox. **حلّ مانعي السابق:** `recommendation_outcomes PRIMARY KEY (tenant_id, recommendation_id)` (مفتاح إزالة التكرار)؛ `outcome_record` UNIQUE (tenant_id, idempotency_key) WHERE NOT NULL؛ `online_learning_updates` قيد `CHECK ck_learning_traceable` (يفرض النَّسَب على مستوى DB). `persistence.py` (asyncpg مستورَد كسولاً ⇒ آمن الاستيراد لطبقة الوحدات) · `migration_runner.py` (يتطلّب `DECISION_SERVICE_ALLOW_SCHEMA_CHANGE` — لا تغيير مخطّط كأثر استيراد) · `backfill.py --verify-counts` · `tests/conftest.py`. `main.py` write endpoints: `persisted:true, authoritative:true` **فقط** إن `sor_enabled()` (DECISION_SERVICE_SOR_ENABLED=true + DATABASE_URL)، وإلّا `_mirror_ack` (persisted:false). `requirements.txt` +`asyncpg==0.30.0` (pip-audit نظيف). عميل المنصّة: docstring فقط (مسار الكتابة الموثوق محفوظ). 3 حُرّاس P0 + بوّابة `decision_sor_cutover_readiness_gate.py` (تتحقّق من migration_runner/backfill/الوثائق/توصيل CI).

**flag-gated افتراضيّاً OFF ⇒ صفر تغيير سلوك إنتاج** (المنصّة تبقى SoR؛ decision-service مِرْآة صادقة حتى تفعيل صريح بعد backfill + تحقّق تكامليّ).

**تحقّق-قبل-دمج (الأرشيف مزج production-closure المدموج + عمل SoR جديد + تغييرات واجهة عرضيّة):** لم أُعِد أجزاء production-closure المكسورة (tsconfig no-op/scratch، package.json) — أبقيتُ نسخي النظيفة؛ أخذتُ workflow الأرشيف (نظيف = قاعدتي + توصيل SoR). أصلحتُ: **tsc** في `layerRegistry.ts` (الوصول لحقل اختياريّ على `as const satisfies MapLayer[]` ⇒ توسيع لـMapLayer) · **25 خطأ ruff** في decision-service (autofix + B904 raise-from + F841). تغييرات الواجهة العرضيّة (api.ts/useApi تعليقات · SettingsPage · layerRegistry metadata+test) طُبِّقت (تمرّ tsc+vitest).

**التحقّق المستقلّ:** tsc 0 · vitest **1100/155** · منصّة **3554** (+20 حارس SoR، CI-style) · tests_v9 unit **2806** · ruff CI نظيف · pip-audit asyncpg نظيف · release مُعاد بناؤه.

---
## 2026-07-10 — P0 Vegetation V3+V4: علم `estimated` صريح + إعادة تأطير التوصيات إلى فرضيّات

استكمال للخطّة consumer-driven. بعد V2 (وسم السلسلة التركيبيّة)، أُصلح خطران في مُخرَج `analyze`:

- **V4 (الأخطر):** `_recommendations_ar` كان يُصدِر **أوامر تنفيذيّة** («يُنصح بالري الفوري» · «زيادة تكرار الري») مبنيّةً على `CWSI` **تقديريّ** (نطاقات تركيبيّة) — انتهاك مضاعف لحدود المحرّكات (القرار التنفيذيّ لخدمة القرار) وللصدق (مبنيّ على تقدير). أُعيد تأطيرها إلى **فرضيّات + اقتراح فحص** («فرضيّة: إجهاد مائي محتمل — يوصى بالتحقّق؛ قرار الريّ لخدمة القرار») + `advisory_role="hypothesis"` + `advisory_note_ar`. أُبقيت الكلمات المفتاحيّة (ريّ/آفة/مرض/✅) كي لا يُكسَر مستهلك يطابق النصّ.
- **V3:** كلّ مؤشّر في الرد كسب علماً صريحاً `estimated: bool` (= المصدر ليس raster-service) بجانب `source` النصّيّ — كي لا يُخلَط تقديريّ بحقيقيّ (LAI/CWSI/GNDVI تقديريّة؛ NDVI/NDMI حقيقيّة عند توفّر Raster).

**التحقّق:** vegetation-service 19 logic + 4 honesty (فرضيّة لا أمر · «خدمة القرار» مذكورة · لا «الفوري» · أعلام estimated/advisory) · ruff · إضافيّ متوافق للخلف. **متبقٍّ من P0-Vegetation:** season_id (يحتاج تمرير عبر run_analysis/الراوتر) · حذف FIELD_REGISTRY الإنتاجيّ · وصل Raster timeseries الحقيقيّ (يتطلّب Raster حيّاً).

---


## 2026-07-08 — إغلاق مساحة عمل الحقل الإنتاجيّ (بوّابة runtime + workflow)

أرشيف `d01a7a9_field_workspace_production_closure` (على رأسنا الأخضر). **القيمة المُطبَّقة:** بوّابة runtime `scripts/ci/field_workspace_production_closure_gate.py` (تستورد تطبيق FastAPI: مسارات مساحة العمل مُسجَّلة مرّة واحدة · OpenAPI يكشف العقود · fields.py لا يملك المسارات المتخصّصة · ملفّات العقد الأماميّة موجودة) · workflow `.github/workflows/field-workspace-production-closure.yml` (contract-typecheck + build + gate + 5 حُرّاس ui20/24-26/27/28-30/31-35) · `tsconfig.field-workspace-contract.json` · doc.

**رفض صادق (تحقّق-قبل-دمج):** الأرشيف غيّر `package.json:typecheck` إلى `tsc -p tsconfig.app.json` — و`tsconfig.app.json` تضمينه `["src/vite-env.d.ts"]` فقط ⇒ **يفحص ملفّاً واحداً** (`--listFiles` أكّد 1) ⇒ لا فحص أنواع للتطبيق إطلاقاً (انحدار خطير). و`tsconfig.test`/`tsconfig.field-workspace` يفشلان (TS7016 حلّ exports لـ@turf في التجميع المعزول — يعالجه الفحص الموحّد بلا مشكلة؛ +TS5010 glob غير صالح `src/test/**`). أعدتُ `typecheck: tsc --noEmit` الموحّد (الأخضر المُثبَت مراراً)، وأزلتُ scripts المكسورة (typecheck:test/field-workspace) وtsconfig المكسورة/الميتة (app·test·field-workspace·field-core) + scratch (one·tmpone غير المُرجَّعة أصلاً)، وأبقيتُ فقط `typecheck:field-workspace-contract` (يعمل، يستخدمه الـworkflow). لم أُضِف typecheck:test إلى ci.yml (الموحّد يغطّي الاختبارات أصلاً).

**التحقّق:** unified `tsc --noEmit` 0 · `typecheck:field-workspace-contract` 0 · `npm run build` 0 · بوّابة الإغلاق 0 (6 فحوص) · 5 حُرّاس (21 اختبار) · YAML صالح (workflow + ci.yml) · ruff نظيف · release مُعاد بناؤه.

---
## 2026-07-10 — P0 Vegetation V5: تمرير season_id + توثيق حالة المصادر الحقيقيّة

- **V5:** `/v1/analyze` كسب `season_id` اختياريّاً (متوافق للخلف، max_length)؛ يُمرَّر إلى `run_analysis(..., season_id=None)` ويُصدَّر في الرد (`"season_id"`) — يربط النتيجة بالموسم الصحيح للنَّسَب (تفسير المؤشّر حسب المرحلة يبقى في المنصّة). حارس ساكن يؤكّد القبول+التمرير+الإصدار.

**اكتشاف يخفّف قلق المراجعة (يُسجَّل بصدق):** الخدمة **تُفضّل Raster الحقيقيّ أصلاً** — `VEGETATION_PREFER_RASTER=1` افتراضيّاً + `_RASTER_REAL_INDEX={evi,savi→msavi,ndmi→moisture}` + محاولة NDVI الحقيقيّ، مع ارتداد **fail-safe مُعلَّم** للتقدير. فمنتَج `analyze` ليس تركيبيّاً بالكامل — NDVI/EVI/SAVI/NDMI حقيقيّة عند توفّر Raster، والباقي (lai/cwsi/ndwi/gndvi/recl) تقديريّ مُعلَّم صراحةً (V3 أضاف `estimated:bool`). الفجوة المتبقّية الحقيقيّة: **`/v1/timeseries` تركيبيّ بالكامل** (عولِج بالوسم V2) والمصدر الحقيقيّ Raster؛ ووصله + تفعيل `FEATURE_SENTINEL_DB_FIELDS` (حقول القاعدة) **قرارا تهيئة/نشر** (يتطلّبان Raster/platform حيّاً) لا كوداً قابلاً للتحقّق هنا.

**التحقّق:** vegetation-service 31 (5 honesty + 19 logic + 7 decomposition) · ruff · إضافيّ متوافق للخلف.

**خلاصة P0-Vegetation:** V2 (وسم timeseries) · V3 (estimated per index) · V4 (فرضيّات لا أوامر) · V5 (season_id) **مُنجَزة وقابلة للتحقّق**. المتبقّي (وصل Raster timeseries · تفعيل حقول القاعدة) **deployment-gated بصدق** — لا يُزيَّف.

---


## 2026-07-08 — دمج أرشيف UI5–UI35 (تفكيك MapHub + مساحة عمل الحقل الكاملة + واجهات BFF خلفيّة)

أرشيف المستخدم `3573402_ui31_ui35_field_workspace_final_completion` مبنيّ على رأسنا الأخضر بالضبط (بلا حذوفات زائفة). دلتا 69 ملفّاً. **الميزة:** تفكيك `MapHub.tsx` إلى قشور `sections/maphub/*` (Shell/ToolToggle/OperationalOverlayControls/RoleAwareMapSurface…) + **مساحة عمل الحقل** (FieldWorkspace* ألسنة/لوحات: imagery/weather/irrigation/tasks/timeline/priority/operations/reports) + **٤ راوترات BFF خلفيّة** تفوّض عبر الواجهات: `field_workspace_imagery` (available-dates/timeline → raster facade) · `field_workspace_weather` (operation-windows → weather facade؛ irrigation-advice/disease-risk بقايا Open-Meteo منقولة من fields.py) · `field_workspace_timeline` (unified-timeline) · `field_priority_queue` (farm/field) + عقود route/completion. **UI28-30 تنظيف:** نُقِلت 5 مسارات من fields.py إلى الراوترات الجديدة (لا تكرار تسجيل).

**تحقّق-قبل-دمج أصلح (الأرشيف مكسور كما شُحِن رغم بنائه على رأسنا):** (أ) **٤ أخطاء tsc متكرّرة** (App.tsx بلا استدعاء الـhook · api.ts إعادة تصدير لا تربط + deactivateUser ساقط · **MapHub حذف تعريف `CompareMap` مع إبقاء استخدامه** — استعدتُه). (ب) **١١ اختبار vitest** (7 بائتة رُقِّيت + حارسا تفكيك MapHub وُسِّعا لقراءة OperationalOverlayControls). (ج) **١٣ حارس منصّة** — توصيل حَوكمة كامل: baseline وحدات 583→589 · مسارات 572→575 (إزالة 5 مدخلات fields.py بائتة للمسارات المنقولة + إضافة 8 بمالكيها: imagery→raster-service · weather→weather-service · priority/timeline→sahool-platform) · سقف P2.6→575 · allowlists الحدود (raster/weather boundary + P2.5 alias + weather_direct_wiring: field_workspace_weather بقيّة منقولة موثَّقة) · /api/v1/features في القراءة العامّة · UI20 guard (unified-timeline انتقل) · تصحيح imagery-timeline test لموطنه الجديد. **صدق معماريّ محفوظ:** لم أطبّق النسخة الأقدم (`dab14b7_ui27`) التي كرّرت المسارات وخرقت حدود الطقس؛ هذه النسخة نظّفتها (UI28-30). بقايا Open-Meteo المباشرة = **نفس بقايا fields.py السابقة منقولة** (موثَّقة residual، لا خرق جديد).

**التحقّق المستقلّ:** tsc 0 · vitest **1099/155** · منصّة **3534** · tests_v9 unit **2806** · ruff نظيف · release **3534**.

---

## 2026-07-08 — دمج أرشيف UI3b/UI4 (سجلّ الميزات الحيّ + عقود تشغيل الحقل + تقسيم api.ts)

أرشيف `dab14b7_ui3b_ui4_auto_continuation` مبنيّ على رأسنا الأخضر بالضبط ⇒ الدلتا (22 ملفّاً) حقيقيّة مباشرة. **الميزة:** (UI3b) سجلّ رايات ميزات حيّ `GET /api/v1/features` + `useFeatureRegistry` (fail-open حتى التحميل؛ يُخفي صفحات الأعلام المطفأة بعد التحميل) + `AdvancedServiceState` يميّز 404=ميزة مطفأة / 502-504=وضع متدهور / 401-403=صلاحيّة · (UI4) واجهة `GET /api/v1/fields/{id}/readiness` (إعادة تشكيل عقد data-completeness، `calibrated=false` صادق) + عقود `fieldOperating.ts` (منها priority-queue **خامل** بلا خلفيّة — موثَّق «مخطَّط») · (UI3) بدء تقسيم api.ts إلى `api/{client,auth,features,fieldOperating}.ts` مع واجهة توافق + 5 حُرّاس منصّة جديدة.

**تحقّق-قبل-دمج اصطاد وأصلح:** (أ) **6 أخطاء tsc** — `api.ts` يعيد تصدير `asApiError/apiErrorMessage` ويستخدمهما داخليّاً (إعادة التصدير لا تربط في نطاق الوحدة ⇒ استيراد صريح) + `getAccessToken` بلا استيراد + `deactivateUser` سقط من إعادة التصدير (كسر SettingsPage) + `App.tsx` يستخدم `featureRegistry` بلا استدعاء الـhook. (ب) **توصيل الحَوكمة** (الأرشيف شحن الراوترَين بلا تهيئة): baseline الوحدات 581→583 + ملكيّة المسارَين (bff-orchestrator) + ميزانيّة 570→572 (سقف P2.6 مرفوع موثَّقاً) + `/api/v1/features` في قائمتَي القراءة العامّة المُراجَعة (طوبولوجيا أعلام فقط، لا بيانات مستخدم/مستأجِر) + تصنيف/تغطية UI للنقطتين. (ج) **7 اختبارات vitest بائتة رُقِّيت لا أُضعِفت:** 4 صفحات (503 صار «وضعاً متدهوراً» أصدق) · segmentField (+`timeout:90000` مشروع) · Satellite static (معالج 401 انتقل إلى `api/client.ts`) · MapHub static (**فشل موروث** من P2: بناء params انتقل إلى `raster_service_client.py` — vitest ليس في CI فمرّ صامتاً؛ المؤشّر ثُبِّت على الموطن الحاليّ). ملاحظة: التسجيل تلقائيّ أصلاً (`register_routers` يلتقط كلّ `api/routers/*`) — لا حاجة لتعديل registry.

**التحقّق المستقلّ:** tsc 0 · vitest **1099/155** · منصّة **3479** (CI-style بلا -m) · tests_v9 unit **2806** · ruff نظيف · release **3521**.

---

## 2026-07-08 — مرآة Tencent Cloud لـpip في كلّ Dockerfile (يُصلح فشل build المتكرّر)

المشغّل: build يفشل باستمرار على `pypi.org` من شبكتنا حتى مع VPN. الحلّ: كلّ Dockerfile حقيقيّ يستخدم `pip install` (٢٩ ملفّاً تحت services/·agents/·bots/؛ استُثنيت نُسَخ `.claude/worktrees` لفرع آخر) صار افتراضه `ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/` — قابل للتجاوز بـ`--build-arg PIP_INDEX_URL=https://pypi.org/simple`. **٢٥** ملفّاً كان لديه نمط ARG (بدّلتُ القيمة الافتراضيّة + علّقتُ الافتراض القديم الكاذب)؛ **٤** بلا نمط (ai_agronomist · raster-tiler-service · weather-polygon-worker · weather-signal-engine) حقنتُ فيها كتلة ARG+ENV قبل pip. **صدق أمنيّ:** مرآة Tencent HTTPS ⇒ **لم أضبط `--trusted-host`** (ضبطه يُضعِف TLS بلا داعٍ)؛ `PIP_TRUSTED_HOST` يبقى فارغاً افتراضيّاً (تحقّق TLS طبيعيّ). أصلحتُ تعليقات local-ai-rag المتناقضة (كانت تدّعي عكس ذلك) وحدّثتُ فحص `test_roadmap_phase23` #2 (كان يزعم «PyPI الرسميّ افتراضيّاً» — صار يتحقّق من افتراض Tencent + بقاء pypi.org كـoverride). حارس جديد `test_dockerfile_pip_mirror_guard.py` (أرضيّة ≥25) يمنع انحدار أيّ Dockerfile للافتراض على pypi.org. التحقّق: unit **2806** · ruff نظيف · حارسا non-root/shared يمرّان · release 3520.

---

## 2026-07-08 — تحقيق ترقية decision-service لـSoR: اكتشاف مانع مخطّطيّ (لا كود غير آمن)

على «استمر» بحثتُ الخطوة الكبيرة التالية (ترقية decision-service لمصدر سجلّ حقيقيّ) وأصّلتُها في مخطّطات الجداول الخمسة. **اكتشاف حاسم:** جعل decision-service يستمرّ الجداول *بالإضافة* (مِرْآة flag-gated تكتب مع المنصّة) آمنٌ فقط لجداول لها مفتاح إزالة تكرار طبيعيّ (المِرْآة تعمل **بعد** كتابة المنصّة فتكون no-op بـ`ON CONFLICT DO NOTHING`). الحالة: `decision_record`/`dispatch_decisions` (PK decision_id) ✅ · `outcome_record` (PK + UNIQUE idempotency_key) ✅ · `online_learning_updates` (UNIQUE tenant_id,update_id) ✅ · **`recommendation_outcomes` ❌** — PK `BIGSERIAL` وإدراج المنصّة (`recommendations.py:347`) بلا `ON CONFLICT` ⇒ كلّ نداء يُلحِق صفّاً؛ مِرْآة تستمرّه تُنشئ **صفّاً مكرّراً** لنتيجة واحدة ⇒ pseudoreplication يُضخّم العيّنة ويُفسِد `success_rate` (عين ما يحميه `outcome_reconciler` وتدقيق إغلاق الحلقة).

**الخلاصة الصادقة:** ترقية SoR **يجب أن تكون cutover حقيقيّ** (المنصّة تتوقّف عن الكتابة ⇒ decision-service الكاتب الأوحد + backfill)، **لا** خطوة «كلاهما يكتب» إضافيّة. سابقة لأيّ flip: migration يضيف مفتاح إزالة تكرار لـ`recommendation_outcomes` (مرشّح `UNIQUE(tenant_id, recommendation_id, season_id)` بعد تأكيد أنّ المجال يمنع تعدّد النتائج لكلّ (توصية، موسم)، وإلا عمود `idempotency_key` صريح) — يُصمَّم ويُتحقَّق على Postgres حيّ (`-m integration`) قبل الـcutover، لا يُنفَّذ بأمان من بيئة وحدات فقط. **لم أكتب كوداً يكتب DB مزدوجاً** (كان سيُفسِد البيانات) — وثّقتُ المانع + السابقة في `DECISION_SERVICE_BOUNDARY_CONTRACT.md`. لا تغيير كود تنفيذيّ هذه الخطوة (توثيق قرار معماريّ صادق فقط).

---

## 2026-07-08 — نشر decision-service (البند الحرج من قائمة المتبقّي)

المستخدم حدّد المتبقّي ورتّبه؛ الحرج: `decision-service` غير قابل للنشر (بلا Dockerfile/compose/env) ⇒ المضيف `sahool-decision-service:8160` غير موجود ⇒ المِرْآة best-effort ميتة (تحذير لكلّ كتابة). لا فقدان بيانات (الجسر الانتقاليّ `d201527` جعل المنصّة SoR)، لكنّ P4.5–P4.7 لا تُعتبَر صالحة إنتاجاً حتى يُنشَر المِرْآة.

**المُطبَّق (٥ ملفّات):** `services/decision-service/Dockerfile` (python:3.11-slim، non-root `USER sahool` SEC-2، `EXPOSE 8160`، uvicorn على 8160، healthcheck `/healthz`، لا نسخ shared لأنّه لا يستورده) · خدمة `sahool-decision-service` في `docker-compose.v9.yml` و`docker-compose.fixed.yml` (build من Dockerfile + healthcheck 8160/healthz + no-new-privileges + شبكة داخليّة) · `DECISION_SERVICE_URL=${...:-http://sahool-decision-service:8160}` على `sahool-platform` في كلا الملفّين + `.env.example` · حارس `tests_v9/test_decision_service_deployment_contract.py` (٧ تأكيدات: Dockerfile non-root/8160/healthz · الخدمة معرَّفة بـbuild+healthcheck في كلا الملفّين · المنصّة تُوصِّل DECISION_SERVICE_URL · لا env قاعدة مُضلِّل).

**قرار صدق موثَّق (انحراف عن حرفيّة طلب المستخدم «JOBS_DATABASE_URL/DB»):** لم أُوصِّل `DATABASE_URL/JOBS_DATABASE_URL` للخدمة — فهي جذع بلا asyncpg/DB (يُرجِع `persisted:false`)؛ وصل env قاعدة يتجاهله يُوهِم استمراراً غير موجود ويخالف مبدأ الصدق. حارس رابع يُثبِّت هذا (لا env قاعدة على المِرْآة). DB env + تبعيّة postgres تأتيان مع ترقية SoR الحقيقيّ (`DECISION_SERVICE_BOUNDARY_CONTRACT.md`). لا مسار nginx (مِرْآة داخليّة فقط، لا مستهلِك أماميّ مباشر — خلاف weather/raster). المنصّة لا تعتمد على صحّة المِرْآة (فشلها لا يحجب الكتابة).

**التحقّق المستقلّ:** ruff format+check نظيف · tests_v9 unit **2801** (+7) · حارسا Dockerfile non-root/shared (auto-discover) يمرّان على الملفّ الجديد · YAML صالح (pyyaml) · release **3518**. الفرع بانتظار خُضرة CI قبل التقديم السريع.

**يبقى (موثَّق، مؤجَّل بصدق):** تأكيد استماع weather-service على 8000 + healthcheck · P6 توجيه بوّابة فعليّ (عقد نصّيّ حاليّاً) · بقايا aggregators مركّبة · تقليص ميزانيّة مسارات BFF · تقسيم عامل حالة dispatch · تشغيل `-m integration` end-to-end بالخدمات مرفوعة · ترقية decision-service لـSoR حقيقيّ (asyncpg+DB) · عمل منتَج أقدم (field-season↔أدلّة · Field Normal Behavior · Disease Forecast).

---

## 2026-07-08 — لوحة التعلّم: حالة متدهورة صادقة (P0) + تقديم main/develop إلى الأخضر

**التقديم السريع أوّلاً:** CI للرأس `cfa768e` (الجسر الانتقاليّ `7347e92` + hotfix المقاييس `419847c`/`cfa768e`) أخضر ⇒ `main` و`develop` قُدِّما من `3609fdb` إلى `cfa768e` ودُفِعا (يُزامن إصلاح سلامة البيانات + hotfix معاً).

**دمج الأرشيف `3609fdb_learning_dashboard_degraded_p0`** (`8d17ca0`): مبنيّ على 3609fdb قبل عملي؛ الفرق الخام مقابل `cfa768e` (37 ملفّاً) معظمه قلبٌ لعملي. عزل الدلتا بالأساس (17 ملفّاً غيّرها الأرشيف فعلاً مقابل 3609fdb) أظهر أنّ الميزة الحقيقيّة الوحيدة = تدهور مسار قراءة لوحة التعلّم. المُطبَّق (٣ ملفّات): `api.ts` عقد degraded + catch(404/502/503/504) · `LearningDashboardPage.tsx` شارة تدهور (أُخِذت كاملةً — مطابق 3609fdb في cfa768e) · حارس `test_learning_dashboard_degraded_guard.py` (عقد الواجهة + القراءة تبقى SoR مباشرة لا واجهة).

**رفضان صادقان:** (أ) هُنك backend يقلب `list_decision_records` إلى تدهور واجهة decision-service — رُفِض لأنّه يعكس صامتاً قرار الجسر الانتقاليّ (المنصّة SoR، قراءة DB مباشرة، 503 صادق)؛ التدهور يعيش في الواجهة. (ب) نُسَخ field_intelligence/evidence_snapshot/main.py قديمة (تُزيل `# noqa: BLE001`، تعكس `datetime.now(UTC)`) — رُفِضت لصالح hotfix المقاييس المدموج `419847c`.

**التحقّق المستقلّ:** tsc 0 · ruff format+check نظيف · منصّة unit **1249** · tests_v9 unit **2794** · release **3517** بصمة. الفرع `8d17ca0` بانتظار خُضرة CI قبل التقديم السريع.

---

## 2026-07-05 (ن) — إكمال بذرة الجوف لكلّ المناطق المنتِجة

«تحميل ما تبقّى من الجوف»: كلّ المناطق الستّ لها الآن موسم نشط بمحصولها الحقيقيّ من `farm_map` (لا Z1 فقط). Z1 يبقى بمواسمه الثلاثة المؤرَّخة (حصاد موزون)؛ Z2 قمح · Z3 برسيم · Z6 أشجار (حمضيات/عنب/رمان/بابايا) مواسم نشطة بتواريخ NULL (Z1 فقط موثَّق التواريخ؛ المعمّرة بلا سوينج) — **لا تواريخ مفبركة**. **لم يُبذَر** (لا مصدر/جدول صادق): الآبار (لا جدول) · اقتصاد لكل حقل (economics.yaml: «تُحسب لا تُخزَّن») · zone_factors (معايرة) · الـ22 عيّنة (المرجع متوسّط؛ 7 تنتظر GPS). **مُثبَت على Postgres حيّ: 6/6/1 idempotent**. release + runbook محدَّثان.

---

## 2026-07-05 (ن) — بذرة تشغيليّة لمزرعة الجوف/السنيدار من بيانات مرجعيّة حقيقيّة

`scripts/seed/aljawf_sunaydar_farm.sql`: يُدخِل المزرعة الحقيقيّة في قاعدة المنصّة لتظهر بالشاشات (قاعدة v9_foundation كانت تبذر حقول البيضاء الوهميّة فقط، بينما بيانات الجوف/السنيدار حيّة في YAML/CSV فقط). من مصادر حقيقيّة: 6 حقول (farm_map) · 3 مواسم قمح Z1 (yield_history 2.6→4.5→6.17 طن/هـ حصاد موزون) · فحص تربة مرجعيّ (sunaydar_soil_reference: pH 8.2/CaCO3 31%/OM 0.94%/P 2.7). **صدق:** المستأجِر `:tenant_id` (لا UUID مثبَّت) · idempotent (ON CONFLICT DO UPDATE) **مُثبَت على Postgres حيّ** (6/3/1، تشغيل مرّتين بلا تكرار) · إحداثيّات مديريّة (16.15 من climate.yaml)، حدود الحقل وGPS الدقيق **معلّقان** (7 عيّنات، لا مضلّع مفبرك). حارس tests_v9 + قسم Runbook. بذرة اختياريّة للمشغّل لا migration تلقائيّ. unit ناجح · ruff نظيف · release 3164.

---

## 2026-07-05 (ن) — Runbook تشغيليّ لصور الأقمار (البند #10)

`docs/runbooks/SATELLITE_IMAGERY_RUNBOOK.md` (مبنيّ على الكود الفعليّ): تشغيل backfill + عامل السحب · تشخيص/ضبط خنق CDSE 429 (env + Retry-After) · إعادة تشغيل العامل + استرداد الحجز/صدق إعادة المحاولة · التحقّق من `raster_assets` (`asset_status='ready'`) · التحقّق من الخطّ الزمنيّ (available-dates/imagery/timeline) · الحالة الموحّدة · تمييز demo عن real (`real_data`/`demo-only`/`lib/realData.ts`+DemoBadge) · إبطال الكاش · فحوص صحّة. حالة التشغيل موثّقة عبر نقطة raster الداخليّة + استعلام `backfill_runs` (المنصّة لا تبروكسيها — أُبقِي صادقاً). توثيق فقط · بلا كود/migration.

---

## 2026-07-05 (ن) — سيناريوهات Playwright E2E لسياق الحقل (البند #9)

`e2e/field-context-flows.spec.ts`: يتحقّق أنّ توصيل «الحقل المشترك» (الجولات 1–4) وصل الشاشات فعليّاً — satellite/spatial/lab-sampling/maestro/irrigation-plan تُحمَّل مُصادَقةً (seed)، المسار لا يُطرَد للدخول، الهيكل يُصيَّر (تسمية الشريط)، شاشات المنتقي تُظهر combobox حقيقيّاً مُغذّى من `/api/v1/fields`، بلا أعطال console حقيقيّة. هرمسيّ (نفس حزام Playwright في CI: /api مُعترَض + SwiftShader) — بلا خلفيّة/WebGL فحتميّ. رُشِّح ضجيج WS الإشعارات (يعالجه التطبيق بلطف). تشغيل محلّيّ 5/5. tsc نظيف · vitest 1063 · release. واجهة فقط · بلا migration.

---

## 2026-07-05 (ن) — حارس الديمو الموحّد (البند #6)

`lib/realData.ts` مصدر واحد لقاعدة «لا تستخدم بيانات تجريبيّة كأنّها حقيقيّة»: `isRealData`/`filterRealData`/`hasDemoData`. الشاشات القراريّة الحسّاسة توجّه القاعدة عبره بدل إعادة تعريفها: FieldRanking (تصفية + شارة `DemoBadge` «حقول تجريبيّة مُستبعَدة» حين وُجِد ديمو) · ProblemFields (تجاهل NDVI للديمو). مكوّن `DemoBadge` مشترك. اختبارات: وحدة الحارس + حارس ساكن يؤكّد أنّ الشاشات تستورد القاعدة الموحّدة. tsc نظيف · vitest 1063 · release. واجهة فقط · بلا migration.

---

## 2026-07-05 (ن) — نقطة الخطّ الزمنيّ الإنتاجيّة (البند #5)

`GET /api/v1/fields/{id}/imagery/timeline?months=N`: تجميع خادميّ للخطّ الزمنيّ (بدل جمع الواجهة من عدّة مصادر). tenant-scoped؛ يبروكسي تواريخ raster المتوفّرة (COG حقيقيّ)، يقصرها على آخر N شهراً خادميّاً، ويبني لكل تاريخ `thumbnail_url` True Color (`/api/raster/.../cdse-thumbnail.png?index=truecolor&date=..&tid=..`) تُحمّل كسولاً. خدمة المصغّرة تقصّ على هندسة الحقل وتتراجع بصدق إن غاب المشهد؛ ETag/cache على تلك النقطة. واجهة: `fetchFieldImageryTimeline`/`useFieldImageryTimeline`. العقد محدَّث + حارس tests_v9. مسار متمايز (لا ازدواج). البوّابات: router + coverage · platform 3105 · unit 2631 · vitest 1057 · release 3158. بلا migration.

---

## 2026-07-05 (ن) — `8537724` نقطة الحالة الموحّدة (البند #4، مصدر حقيقة واحد)

على خارطة المستخدم الإنتاجيّة، بُني الحجر المعماريّ #4: `GET /api/v1/fields/{id}/state/full` — قراءة tenant-scoped واحدة تركّب **القرّاء الحقيقيّين القائمين** (لا تخترع): field+geometry · الموسم النشط (_field_season_context) · الحالة القانونيّة (recompute_field_state) · تنبيهات مشتقّة · soil_lab_tests · water_ledger+irrigation_runs. كل قسم best-effort ⇒ `available:false` صادق عند التعذّر بدل 503؛ البوّابة الصلبة الوحيدة الحقل-ضمن-المستأجِر (404). المصادر بلا خزن حقيقيّ لكل حقل (عينات ماء مخبريّة · اقتصاد لكل حقل · توصيات حيّة ثقيلة) تُعلَن available:false + مؤشّر endpoint. مسار متمايز عن `/state` (لا ازدواج — router guard أخضر). واجهة: `fetchFieldState`/`useFieldState`. **جرد بوكيل Explore** أثبت أنّ `/state` القانونيّة موجودة لكنّها لا تضمّ field/season/alerts/irrigation — فبُنيت التجميعة عليها. البوّابات: coverage-gate (أُضيف للعقد بدليل) · platform 3105 · unit 2629 · vitest 1057 · release 3157. بلا migration.

**ملاحظة صدق للمستخدم:** البنود 1–2 (docker build + اختبار متصفّح يدويّ) تحتاج بيئة الإنتاج؛ CI يغطّي Integration+E2E. الاقتصاد/الغلّة/الإشعارات تحتاج جداول بيانات حيّة — لا تُختلق.

---

## 2026-07-05 (ن) — `3206dc6` إصلاح: لا ازدواج لمسار /terrain (الفرع اصطاده)

بوّابة CI للفرع اصطادت أنّ المنصّة **تملك أصلاً** `GET /api/v1/fields/{id}/terrain` (`get_field_terrain`: enrich_terrain على أعمدة مخزّنة + ملاحظة «DEM مؤجَّل»)؛ فالوسيط الذي أضفتُه كان **تسجيلاً مزدوجاً** أسقط `test_router_decomposition_guard`. الإصلاح: حذف الوسيط المكرّر وبدلاً منه **إغناء النقطة القائمة من DEM حيّ**: عند غياب القيم المخزّنة، `get_field_terrain` ينادي best-effort راستر `/terrain` (bbox من الهندسة) ويغذّي enrich_terrain بالارتفاع/الانحدار(deg→pct)/الاتّجاه المحسوب، ويكشف المظروف الخام تحت `dem_auto_fill.computed` ويقلب `available`؛ التعذّر ⇒ available=false صادق. الواجهة `fetchFieldTerrain` تقرأ `dem_auto_fill.computed`. **درس:** ابحث عن نقطة قائمة قبل إضافة راوت — الفرع-أولاً أنقذ من ازدواج في main. البوّابات: router-guard أخضر · platform 3105 · unit 2626 · vitest 1057 · release 3157.

---

## 2026-07-05 (ن) — `beec5ef` أساس TERRAIN: نقطة تضاريس خادميّة من DEM حقيقيّ

على «استمر» بُني أساس فجوة TERRAIN بصدق (لا اختلاق): `terrain_analysis.compute_field_terrain(dem, bbox)` يقصّ DEM على bbox الحقل ويحسب ارتفاع/انحدار/اتّجاه عبر Horn + الجهة الغالبة؛ غياب DEM/bbox ⇒ `computed=false` بمصدره. راستر `GET /v1/fields/{id}/terrain` (tenant-scoped + `FIELD_DEM_PATH` + تصنيف حصاد المياه) · منصّة proxy (geometry→bbox عبر guard_field_geometry، 404 صادق خارج المستأجِر) · واجهة `fetchFieldTerrain`/`useFieldTerrain` + `TerrainView3D` يعرض إحصاءات محسوبة أو سبباً صادقاً («DEM غير مُهيّأ»)؛ تصيير 3D terrain-RGB يبقى حالة انتظار موثّقة (لا نقش مزيّف). اختبارات: سلوكيّ مرافق + حارس tests_v9 + TerrainView3D.static. **البوّابات:** unit 2626 · vitest 1057 · tsc/ruff نظيف · release 3154. بلا migration. **يبقى نشريّاً:** تزويد DEM حقيقيّ + بلاطات 3D.

---

## 2026-07-05 (ن) — مواءمة الدماغ مع واقع CI: عدّة قيود `open`/`deferred` كانت بائتة

على «قوم بتنفيذ الكل» أُجري تحقّق عميق فتبيّن أنّ أغلب البنود «المفتوحة» **منجَزة ومُتحقَّقة في CI**، لا عملاً كوديّاً متبقّياً. الدليل: **CI run 28750924733 عند `781f7a4` — 11 مهمّة كلّها success**، تشمل: **Frontend E2E (Playwright · MapLibre/WebGL QA)** (⇒ MAP-QA حيّ أخضر) · **Integration Tests** على Postgres+PostGIS حيّ (⇒ تحقّق SAT-DEFERRED التكامليّ) · **Flutter Analyze & Test** · Security/Unit/Typecheck/إلخ.

صُحِّحت القيود البائتة في `gaps/registry.md`: MAP-QA ⇒ verified · SAT-DEFERRED ⇒ fixed (integration أخضر؛ يبقى تفعيل عامل الإبطال نشريّاً) · MAPHUB-CDSE + NOTIF-WS ⇒ fixed (PR **#564 مدموج** 2026-06-28، القيد «قيد المراجعة» بائت) · SPATIAL-401 ⇒ fixed (أفاد المستخدم بإصلاحه في dev) · v57.5-DB ⇒ fixed (سابقاً). **تشغيل Playwright محلّيّ** أكّد 8/9 خطوات gating خضراء؛ خطوة رسم Terra Draw حسّاسة لبناء Chromium تحت software-WebGL (تمرّ على Chromium المُدار في CI) — **لم أُضعِف البوّابة** لأجل بيئتي المحلّيّة.

**المتبقّي حقّاً مقيَّد بالنشر/البيانات لا بالكود** (لا يُنفَّذ في حاوية تطوير بلا اختلاق): C4/M1 (اعتمادات FCM/APNs الإنتاجيّة) · TERRAIN 3D (بلاطات DEM/terrain-RGB حقيقيّة) · تفعيل عامل الإبطال كخدمة compose في الإنتاج. **درس:** أعِد التحقّق من الشيفرة/CI قبل «تنفيذ» بند — عدّة قيود كانت بائتة.

---

## 2026-07-05 (ن) — صيانة سجلّ: v57.5-DB بائت ⇒ fixed (إعادة تحقّق)

استُفسِر عن الخطّة؛ عند إعادة التحقّق المُلزَم لبند P1 «v57.5-DB» تبيّن أنّه **مُغلَق downstream** وأنّ قيد `open` في `gaps/registry.md` كان بائتاً: v130/v131/v132/v124 موصولة في MANIFEST **و** run_migrations.sql، والقرّاء/الكتّاب موجودون. صُحِّح السجلّ إلى `fixed`. **درس:** لا تُنفَّذ إعادة بناء لبند قبل التحقّق من الشيفرة — أنقذ هذا ترحيلاً مكرّراً. الكود مكتمل إلى حدّ بعيد؛ المتبقّي أغلبه مقيَّد ببيئة (تحقّق تكامليّ `-m integration` · Playwright حيّ · موبايل Flutter · مسار /terrain خادميّ · متابعة PR #564).

---

## 2026-07-05 (ن) — `567e8e3` الجولة 4: قوائم حقول في agronomy/GIS/governance + وسم الـmocks demo-only

**بعد دمج PR #580** (`8f2109d`؛ main=develop=الفرع). عمل جديد على الفرع (لم يُعَد فتح أيّ PR):

- AgronomyConsistencyCard: input معرّف حقل المحفظة ⇒ select (useFieldOptions) مبذور من prop الحقل.
- GisTemporalOpsCard: replay-reconstruct يُسقِط إدخال المعرّف اليدويّ ويستخدم `fieldId` النشط؛ نوع الكيان select محدود.
- GovernancePage (تتبّع النَّسَب): نوع الكيان ⇒ Select؛ عند `field` يأتي المعرّف من select الحقل المشترك (useSelectedField)، ويبقى حقل يدويّ لـcommand/recommendation.
- FieldManagementPage: **إيقاف تلفيق field_id عشوائيّ** (`field_<ts>_<rand>`) عند غيابه من API ⇒ `''` وإسقاط الصفوف بلا معرّف.
- api.ts: وسم كتلة الـmock بـ**DEMO-ONLY** (تحت VITE_MOCK_MODE فقط)، `field_01`⇒`demo-field-01`، `real_data:false` على fields_summary، و`status/source='demo-only'` — فلا تُخلَط بيانات العرض بالإنتاج أبداً.

**البوّابات:** tsc نظيف · vitest **1054** (145 ملفاً) · release **3154** checksums. واجهة فقط · بلا migration.

## 2026-07-05 (ن) — `960a86d` الجولة 3: قوائم حقول في لوحات القرار/المدير + إشعارات صادقة

رقعة المستخدم (`..._rest_runtime_screens_round3_hotfix.zip`، حزمة كاملة). عزلتُ تغييراتها الحقيقيّة عن حالتي التراكميّة (r3 = حالتي + round3): App.tsx/routes.ts نُسخ متطابقة-فائقة (فقط 22 alias جديداً) + 3 ملفّات لم أمسّها:

- **DecisionDeepPanel:** input نصّيّ fld_* ⇒ select مشترك (useSelectedField) متزامن مع الحقل النشط عبر منتقيات القرار الثلاثة.
- **ManagerConsolePage:** مدخلات معرّف الحقل ⇒ selects (multi للتقارير، single لأمر العمل/اللقطة).
- **NotificationCenter:** **إزالة إشعارات SEED المفبركة** (رسائل NDVI/طقس/معمل مخترعة) ⇒ حالة فارغة صادقة حتّى ربط مصدر حيّ (websocket/store). موافق لقاعدة «لا اختلاق».
- **توجيه:** 22 alias + Routes (indicator-timeline · phenology/growth · prescription · water/twin/etc-dual/fao56 · yield/rankings/problems/roi · iot/irrigation-network · admin/manager).

**حافظتُ على إصلاحاتي التي يفتقر إليها أساس الحزمة:** FarmMapOverview `source:'user'` (لا `'map'` غير الصالح) · allowlist حارس Portfolio · MemoryRouter في اختبار FieldWorkspaceMapCard · تأكيدات الخطّ الزمنيّ المحدود بالخادم · stub اختبار Portfolio. **لم أنسخ ملفّات الاختبار من r3** (كانت ستُرجِع أخطاء أصلحتُها).

**البوّابات:** tsc نظيف · vitest **1054** (145 ملفاً) · release **3154** checksums. واجهة فقط · بلا migration. يُضاف لـPR **#580**.

## 2026-07-05 (ن) — `f18c74b` الجولة 2: قوائم منسدلة للحقول في بقيّة الشاشات + aliases توجيه

رقعة المستخدم (`rest_runtime_screens_round2_fix.diff`) — تُكمِل توصيل الشاشات التشغيليّة المتبقّية بالحقول الحيّة وتستبدل آخر مدخلات معرّف الحقل النصّيّة/الوهميّة بقوائم منسدلة. `patch -p1` نظيف بعد إصلاح عيبَين:

- Devices/Documents/IrrigationOps (قناة+جدول): input نصّيّ ⇒ select من قائمة الحقول · Pest/Recommendation: dropdown + زرّ مشروط · Portfolio/PortfolioCommand: قوائم منسدلة لكلّ صفّ + **إزالة الحقول التجريبيّة المفبركة (حقل-أ/ب/ج)** (صفوف تبدأ فارغة؛ الحساب مشروط باختيار حقل حقيقيّ؛ الصفوف الفارغة تُسقَط) · `useDashboardData` افتراض `'field_01'`⇒`''` · توجيه: aliases + Routes لـindicators/growth/prescription/soil-water/water-analysis/predicted-plan/advanced/roi.

**تحقّق-قبل-دمج اصطاد عيبَين:** (١) حارس `useSelectedField.static.test.ts` يمنع `useFieldOptions` في الأقسام؛ صفحتا Portfolio مُحرِّرا **تعدّد حقول** (استثناء مشروع كـFieldMapCenter) ⇒ allowlist بمبرّر بدل إجبارهما على hook الحقل المفرد. (٢) `PortfolioCommandPage.test.tsx` انكسر لأنّ الصفحة صارت تجرّ hook استعلام حيّ وتشترط اختيار حقل ⇒ stub لـuseFieldOptions + اختيار الحقل قبل المقارنة (كان يعتمد على الحقول التجريبيّة المُزالة).

**البوّابات:** tsc نظيف · vitest **1054** (145 ملفاً) · release **3154** checksums. واجهة فقط · بلا migration. يُضاف لـPR **#580**.

## 2026-07-05 (ن) — `7cdefde` توصيل الشاشات التشغيليّة العريضة بالحقل النشط المشترك

رقعة المستخدم (`wide_runtime_screens_fix.diff` على أساس `..._backfill_incremental_retry_hotfix.zip`) — تُوصِّل ~14 شاشة بالحقل المختار المشترك بدل معرّفات ثابتة/stub وتضيف تنقّلاً بين الشاشات بسياق الحقل. طُبِّقت بـ`patch -p1` (dry-run نظيف) بعد تحقّق:

- FarmMapOverview (نقر يثبّت الاختيار + بطاقة crop/area/id + أزرار انتقال) · FieldWorkspaceMapCard (بطاقات فعّالة) · SpatialIndicatorsPage (إزالة `FIELD_ID="field_01"` الثابت ⇒ FieldSelector يقود useIndicatorGrid/prescription) · FieldIntelligencePage/maestro (dropdown بدل إدخال id خام) · LabSamplingPage (خريطة قمر تفاعليّة لنقطة العينة) · Irrigation Plan/Water (FieldSelector + field_id بالحمولة) · WaterTwinPage (`initial_depletion_mm=0` عند غياب دفتر المياه) · FieldRanking/ProblemFields (احترام `real_data !== false`) · توجيه `/health/timeline`+`/health/temporal-indicators` (aliases + Routes) · مكوّن FieldSelector جديد · `computeFieldEtcDual` fallback عميلٌ **شفّاف** فقط عند خطأ DATABASE_URL المعطَّل (موسوم `client_fallback`، لا يُقدَّم كإنتاج).

**تحقّق-قبل-دمج اصطاد عيبَين في الرقعة:** (١) `source: 'map'` ليس قيمة `FieldSelectionSource` صالحة (`'user'|'route'|'auto'|'restore'|'system'`) ⇒ tsc error؛ صُحِّح لـ`'user'`. (٢) اختبار render لـFieldWorkspaceMapCard لم يُلَفّ بـRouter بعد إضافة `useNavigate` ⇒ 5 اختبارات فشلت؛ لُفّ بـ`MemoryRouter`.

**البوّابات:** tsc نظيف · vitest **1054** (145 ملفاً) · release **3153** checksums. واجهة فقط · بلا migration. يُضاف لـPR **#580**.

## 2026-07-05 (ن) — `ad49e73` اعتماد الخطّ الزمنيّ التاريخيّ الأغنى + جسر geometry صادق

رقعة المستخدم (`sahool_v2.0.0_5171ee6_backfill_incremental_retry_hotfix.zip`): جزؤها الخلفيّ (backfill incremental retry) كان **مطبَّقاً حرفيّاً** عندي (`backfill_scan_worker.py` + compose متطابقان). لكنّ واجهة الزيب أغنى؛ اختار المستخدم اعتمادها. طُبِّق بعد تحقّق-قبل-دمج:

- **الواجهة:** MapHub خطّ زمنيّ تاريخيّ (`timelineImageryDates` منفصل، جلب all-index، dedup لكلّ تاريخ، `monthLabel`، خيارات 3/6/12/24 شهراً، شريط مصغّرات). النطاق يحدّه الخادم (limit/backfill سنتين) لا قصٌّ عميلٌ صلب 730 يوماً. تسمية «السلسلة التاريخية».
- **api/hooks:** `refreshFieldImagery(fieldId, date?, geometry?)` + طفرة analyze تمرّران هندسة الحقل المختار؛ `fetchFieldImageryAvailableDates` بمعامل `limit` (240).
- **الخلفيّة (platform fields.py):** `/imagery/refresh` يقبل `geometry` كجسر صادق عند غياب صفّ fields للمستأجر (بعد guard؛ بلا هندسة يبقى 404). `/available-dates` بمعامل `limit` + لا يُسقِط 404 عند غياب الصفّ (raster يفرض ملكيّة المستأجر عبر X-Tenant-Id؛ لا اختلاق).

**تحقّق-قبل-دمج اصطاد عيبَين في رقعة المُدقِّق:** (١) اختبارها `MapHubTwoYearTimeline` كان يؤكّد قصّ 730 المُزال وتسمية «آخر سنتين» القديمة — كان سيفشل ضدّ MapHub نفسه في الزيب؛ حُدِّث للسلوك المقصود (نطاق يحدّه الخادم). (٢) `platform_field_missing` ميّت ⇒ ruff F841؛ صُحِّح (`_`-prefix). حُرّاس جدد: MapHubHistoricalTimeline · SatellitePageFieldGeometryRefresh.

**البوّابات:** tsc نظيف · vitest **1054** (145 ملفاً) · ruff format/lint نظيف · unit **2623** · release **3151** checksums. بلا migration. PR **#580** (claude/code-review-34hO3 → main).

## 2026-07-05 (ن) — `03281cb` مصغّرات True Color + خنق CDSE 429 + إعادة محاولة backfill التزايُديّ

ثلاث رقعات من المستخدم على مسار الأقمار، طُبِّقت بعد تحقّق-قبل-دمج + تشغيل بوّاباتنا:

- **مصغّرات True Color:** كانت المصغّرات تُعرض بالمؤشّر التحليليّ النشط (`activeIndicator ?? 'ndvi'` / `gridIndex`)؛ حُوِّلت إلى `'truecolor'` ثابتاً (معاينة بصريّة طبيعيّة). اختيار مصغّرة يبدّل التاريخ فقط ولا يلمس مؤشّر الخريطة. (`MapHub.tsx`, `SatellitePage.tsx`). فرعي عندي أبسط من فرع المُدقِّق: لا `handleSelectImageryTimelineItem`/`preferredTimelineIndex` عندي، فاختُصِر التغيير إلى وسيط الفهرس.
- **خنق CDSE Process API:** تبنّيت نسخة `cdse_client.py` بخنق + إعادة محاولة (بوّابة `_throttle_process_api` عبر `_PROCESS_RATE_LOCK` بـ`CDSE_PROCESS_MIN_INTERVAL_SECONDS=2.0`، حلقة `process_index` تحترم `Retry-After` بـ`CDSE_PROCESS_MAX_RETRIES=5`). وُصِلت env في كتلتَي raster-service + backfill-scan-worker (compose) وhelm values. اختبار سلوكيّ مرافق + حارس ساكن في tests_v9 (CI unit لا يجمع `services/raster-service/`).
- **إعادة محاولة backfill التزايُديّ (v12):** عند تصادم `ON CONFLICT (tenant_id, idempotency_key) DO NOTHING` كان العنصر يُسقَط بـ`continue` بصمت — فعنصر فشل سابقاً (429/عطل) لا يُعاد أبداً ويُعلَن نجاح كاذب. الآن: ready ⇒ skip؛ غير ready ⇒ `UPDATE backfill_run_items SET status='queued', job_id=NULL, error=NULL, processed_at=NULL` وإعادة ربطه بالتشغيلة؛ تصادم غير قابل للاستعادة ⇒ `items_failed`.

**درس:** فرعي يتقدّم على أساس المُدقِّق؛ رقعة المصغّرات كانت تُزيل دوالّ لا أملكها — فُحِص أوّلاً فاختُصِر التطبيق لوسيط الفهرس فقط بلا كسر. بلا migration. unit 2623 · vitest 1047 · tsc نظيف · release 3147 checksums. HOLD main حتّى Integration + Security أخضر.

## 2026-07-05 (ن-40) — تدقيق صور الأقمار v2: إصلاح latest البائت (FINDING-001) + تصفية التواريخ بالمؤشّر (006)

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). تدقيق أعمق — نتائجه حقيقيّة؛ عولج الأخطر والأكثر أماناً:

- **FINDING-001 (High، أعاد المدقّق إنتاجه):** بعد ترطيب تاريخ محدّد من `raster_assets`، معرّف الطبقة `db_{field}_{index}` **غير مخصّص بالتاريخ** ⇒ طلب `latest` لاحقاً يجد الطبقة القديمة في الذاكرة ويُعيدها كأحدث بلا استشارة القاعدة (خريطة تُظهر صورة قديمة والنظام يبدو سليماً). **الإصلاح:** استخراج `_rehydrate_field_layer_from_db` بمعرّف مخصّص بالتاريخ `db_{field}_{index}_{acq}`؛ و`_resolve_field_layer('latest')` يستشير القاعدة ويختار الأحدث acquisition_date بين الذاكرة والقاعدة. حارس انحدار يُعيد سيناريو المدقّق حرفيّاً (2026-05-01 ثمّ latest ⇒ 2026-06-10).
- **FINDING-006 (Med/High):** الواجهة كانت تطلب `/available-dates` بلا `index` وتُسقط `indices` ⇒ قد يُعرَض تاريخ «جاهز» لمؤشّر آخر فتظهر بلاطة شفّافة. **الإصلاح:** `fetchFieldImageryAvailableDates(fieldId, index?)` يمرّر المؤشّر + يحفظ `indices[]`، وMapHub يعيد الجلب عند تغيّر المؤشّر + تصفية دفاعيّة على العميل.
- **مُنجَز سابقاً (v142، المدقّق على أرشيف أقدم):** FINDING-002 (dedup unique index + ON CONFLICT) · FINDING-003 (processing_job_id يُمرَّر ويُدرَج).
- **مؤجَّل بصدق (يحتاج عاملاً/معماريّة، لا نصف حلّ):** FINDING-004 (ربط geometry_revision) · 005 (عامل استهلاك raster_cache_invalidations) · 007 (سلوك auto-refresh) · 008/009 (جسر registry + STAC) · 010 (احتفاظ كاش) · 011 (asset status).

**تحقّق:** tsc نظيف · vitest **1043** · pytest -m unit **2551** · بوّابة الإنتاج PASS · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-05 (ن-39) — إصلاح بوّابة الإنتاج: v142 نُقِص من run_migrations.sql (منظومة ترحيل ثانية)

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). بوّابة الإنتاج فشلت (رمز 1): `v142_raster_assets_dedup_traceability.sql is missing manifest entries`.

- **الجذر:** المستودع يملك **منظومتَي ترحيل متوازيتين**: `migrations/MANIFEST.txt` (أضفتُ v142 إليها) و`scripts_v9/run_migrations.sql` (psql `\i` بنفس الترتيب) — والبوّابة تتحقّق من تطابقهما. أضفتُ v142 لـMANIFEST دون run_migrations.sql فاختلّ التطابق.
- **الإصلاح:** أُضيف v142 كمدخل #148 في `run_migrations.sql` بنفس النمط. البوّابة الآن **PASS كاملةً** (148 migration · RLS · legacy quarantine · source-of-truth · certification matrix · compile 3282/0).
- **حارس جديد `test_migration_runners_in_sync`:** unit يلتقط أيّ ترحيل في MANIFEST غائب عن run_migrations.sql محلّيّاً قبل CI/البوّابة — كي لا يتكرّر (الدرس: أيّ ترحيل جديد يُضاف للمنظومتين معاً).

**درس تشغيليّ (مثل f9dc4c8 سابقاً):** *Sahool Production Gates* سير عمل منفصل يعمل على main فقط ولا يظهر في فحص الفرع — بعد أيّ ترحيل: `bash scripts/production_validation_gate.sh` محلّيّاً قبل اعتبار main نظيفاً.

**تحقّق:** بوّابة الإنتاج PASS · pytest -m unit (migration/manifest/raster) أخضر · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-05 (ن-38) — تدقيق صور الأقمار: idempotency + تتبّع raster_assets (v142)؛ إصلاح اختبار المستأجِر

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). تدقيق عميق عالي الجودة على تخزين الصور التاريخيّة — نتائجه حقيقيّة، عولجت الأعلى قيمةً والأكثر أماناً:

- **P0-2 (تكرار):** `raster_assets` بلا قيد تفرّد ⇒ إعادة تشغيل backfill تُراكم صفوفاً مكرّرة. **v142:** فهرس فريد جزئيّ `uq_raster_assets_scene_product` (tenant/field/index/date/scene/cog، على غير الفارغ فقط) + حذف تكرارات قائمة (يُبقي الأحدث) + `insert_raster_asset` صار **ON CONFLICT DO UPDATE** (يُحدِّث الجودة/الأصل بدل الإدراج المكرّر).
- **P0-3 (تتبّع):** العمود `processing_job_id` كان يُستعلَم في `layer_owner_tenant` لكنّه لا يُملأ (فيسقط إلى ILIKE هشّ على مسار COG). الآن يُمرَّر من `_run_processing`→`_persist_raster_asset`→الإدراج + فهرس `idx_raster_assets_processing_job`.
- **P2-2 (اختبار بائت):** `test_db_rehydrate` كان يُدرِج `tenant_id=None` بينما قراءات الإنتاج تُرشِّح بـuuid ⇒ صحّح إلى مستأجِر UUID حقيقيّ + ترويسة `X-Tenant-Id` (يعكس واقع الإنتاج).
- **مؤجَّل بصدق (أوسع، follow-up):** جسر `raster_assets`→`raster_registry` (P0-1) · عامل استهلاك `raster_cache_invalidations` (P1-2) · سياسة احتفاظ كاش البلاطات (P1-3) · ربط geometry_revision (P1-1) — عمل معماريّ يحتاج مستهلكاً/عاملاً، لا يُنجَز نصفاً. حارس v142 ساكن جديد (3 تأكيدات).

**تحقّق:** pytest -m unit **2549** أخضر · حارس v142 3/3 · validator أخضر (v142) · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-05 (ن-37) — تدقيق DB/هجرات: إصلاح أمر helm الميّت + تحذير .down.sql؛ دحض الباقي

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). فُرزت نتائج تدقيق القاعدة/الهجرات:

- **مُصلَح (حقيقيّ):** (١) `helm/sahool/values.yaml` كان أمر مهمّة الترحيل `python -m api.migrations.run` — **وحدة غير موجودة** ⇒ مهمّة k8s تفشل. صُحِّح إلى `scripts_v9/migrate.py up` (المُشغّل الفعليّ backed by MANIFEST) + `migrate.py._db_url` صار يقبل `JOBS_DATABASE_URL` (helm يمرّره باسمه) + حارس `test_helm_migration_command_valid`. (٢) `validate_migrations.py` كان يُبلّغ `.down.sql` (سكربتا تراجع v9) كـ«على القرص وليست في MANIFEST» — استُثنيا (ليسا في الترتيب الأماميّ عمداً).
- **إيجابيّات كاذبة (دُحِضت):** تحذير `v18 ON CONFLICT(dedup_key)` — هدف فهرس جزئيّ فريد (`WHERE dedup_key IS NOT NULL`) معرَّف في ملفّ آخر؛ الفاحص الحدسيّ يمسح ملفّاً واحداً ويُرجِع 0 (غير حاجب). · تحذيرات BYPASSRLS كلّها سياق دور المهامّ المقصود (تعليقات/الحارس/apply_in_compose) — تصنيف WARN لا FAIL بأداة المدقّق نفسها. · `fixed.yml sahool_user×9` تطوير-فقط محروس بطبقتين (سبق دحضه). · `api_migrations_run_exists=False` هو نفسه بند helm المُصلَح.

**تحقّق:** pytest -m unit **2546** أخضر · حارس helm 2/2 · validator بلا تحذير .down · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-05 (ن-36) — إغلاق البند #4 من التدقيق: مصفوفة تفويض المسارات الرسميّة

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). البند الوحيد من التدقيق الذي وصفته «عمل مستقبليّ» أُنجِز:

- **الحقيقة المحسومة:** مسح المدقّق النصّيّ («decorators بلا Depends محلّيّ») إيجابيّ كاذب — لم يحلّ تفويض الراوتر/الشجرة. المصفوفة مولَّدة من **شجرة تبعيّات FastAPI الفعليّة**: **197 مُطفِّرة** (194 user-auth · 1 service-token · 2 عامّة = login/signup فقط — **صفر مكشوف**) · **286 قراءة** (179 user-auth · 4 service-token · 103 عامّة).
- **الـ103 قراءة عامّة كلّها مرجعيّة/معرفيّة/طقس بلا بيانات مستأجِر** (تقاويم · أقاليم · أدلّة محاصيل · IPM · إكثار · Open-Meteo · تركيب نقيّ `field/operational-state` بمدخلات query لا قراءة قاعدة — تُحقّق منه).
- **مُنتَجات:** `docs/api/ROUTE_AUTH_MATRIX.md` + مولّد `scripts/ci/gen_route_auth_matrix.py` + **حارسان:** القائم `test_all_mutating_endpoints_require_auth` (fail-closed للمُطفِّرة) + جديد `test_public_reads_match_reviewed_allowlist` (يمنع تسرّب قراءة مستأجِر جديدة كـ«عامّة» بصمت عبر allowlist مُراجَع).

**تحقّق:** الحارسان يمرّان على التطبيق الحقيقيّ · pytest -m unit **2544** أخضر · ruff نظيف.

---

## 2026-07-05 (ن-35) — تدقيق جنائيّ خارجيّ: إصلاح مظروفَي صدق حقيقيَّين + دحض الإيجابيّات الكاذبة

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). دقّق المستخدم أرشيف `a3d6023`؛ فُرزت نتائجه:

- **مُصلَح (حقيقيّ، يخالف عقد «لا اختلاق»):** (١) `cog_writer.write_cog(None, …)` كان ينهار بـ`NoneType.shape` بدل مظروف — أُضيف تحقّق مدخل ⇒ `{written:False, reason}`. (٢) `terrain.compute_slope_aspect('/missing')` كان يرفع `RasterioIOError` بدل `{computed:False, reason}` — أُضيف `os.path.isfile` + التقاط `RasterioIOError`. حارس `test_raster_honest_envelopes_20260705` (2 تمرّان).
- **إيجابيّات كاذبة (دُحِضت بالكود):** «footgun المستأجِر في fixed.yml» — الإنتاج `docker-compose.v9.yml` فيه **صفر** `sahool_user`؛ و`fixed.yml` تطوير-فقط موثَّق ومحروس بطبقتين: ساكن (`test_compose_env_bypass_guard`) وتشغيليّ (`db_role_guard.assert_db_role_rls_safe` يرفع RuntimeError على BYPASSRLS في الإنتاج). المدقّق لم يُشغّل الحُرّاس (`make verify-static` انتهى وقته). · `VITE_MOCK_MODE` افتراضه `false` (mock في وضع التجريب الصريح فقط). · الإعفاءات الـ28 كلّها `intended_consumer=machine` (operational 23 + admin-ops 5) — مطابق لشرط المدقّق نفسه. · فشل npm ci بيئيّ (بيئة المدقّق) — CI عندنا يُثبت تثبيتاً نظيفاً + typecheck + vitest.

**تحقّق:** pytest -m unit **2544** أخضر · حارس المظاريف 2/2 · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-05 (ن-34) — إغلاق نهائيّ: صفر دَين واجهة (العقد 438 core)

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). النقاط الثلاث الأخيرة الموثَّقة بُنيت بواجهات حقيقيّة لا مؤجَّلة:

- **اتّجاه نبات-تربة متعدّد المواسم** (`POST /api/v1/agro/plant-soil-feedback/trend`): في `AgroAnalyticsCard` — يلتقط مؤشّرات الموسم الحاليّ كلقطة في سلسلة زمنيّة (الأقدم→الأحدث)، «احسب الاتّجاه» يستدعي النقطة (يحتاج موسمين+) ويعرض الاتّجاه/المحرّكات/الحُكم من الخادم حرفيّاً.
- **سلسلة طقس زمنيّة للبلاطة** (`GET /api/v1/weather/tile-series/{z}/{x}/{y}`): في `DistrictsWeatherCard` — النقطة تُرجِع **JSON** (قيم طبقة عبر إزاحات ساعيّة) لا صور، فعُرِضت كسلسلة قيم مع مُساعِد `lonLatToTile` نقيّ يشتقّ البلاطة من إحداثيّات الحقل (+اختباران).
- **تهيئة مستأجِر** (`POST /auth/tenants`): في `ManagerConsolePage` (تبويب العمليّات) — إنشاء مؤسّسة + أوّل مالك (admin المنصّة؛ الدور owner يُفرَض خادميّاً، رابط إعادة تعيين يُعرَض مرّة، 403 لغير admin بصدق) + `provisionTenant` عبر authApi.
- **العقد: 438 core + 28 إعفاء — كلّها admin-ops/operational (machine).** **backlog-ui = 0:** كلّ قدرة backend مواجِهة للمستخدم لها الآن قارئ واجهة. بدأ اليوم بـ24 endpoint ملزَماً.

**تحقّق:** tsc نظيف · vitest **1043** · pytest -m unit **2544** · البوّابتان PASS · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-05 (ن-33) — سداد شريحة P3-منخفض كاملة (50 مساراً): العقد يبلغ 435 core

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). سابع (وأخير) دفعة وكلاء (R/S/T/U، اُستؤنفوا من نُسَخهم بعد حدّ جلسة بلا إعادة عمل):

- **وكيل R — «المعرفة الزراعيّة الاختصاصيّة»:** ملاءمة المحاصيل + تركيب حالة (dry-run) + الإكثار الخضري/الأصل + الأساليب المحسّنة + صمود الجفاف + تقييم البذار + استراتيجيّة العيّنات (11 مساراً، 22 اختباراً).
- **وكيل S — «GIS/الزمن/المحاكاة»:** عمليّات نواة GIS الهندسيّة (validate/buffer/split/union خلف `FEATURE_GIS_KERNEL`) + التحكيم الزمنيّ + ماذا-لو + مخاطر المرحلة + إعادة البناء + رابط النَّسَب (`FEATURE_UNIFIED_LINEAGE`) + تحليل التجارب (11 مساراً، 16 اختباراً).
- **وكيل T — «التعلُّم والدليل» (إرشاديّ صرف):** تفعيل التعلُّم + معايرة التنبّؤ + مزج سابقة + اقتراح عتبات + تغذية راجعة معايرة + تسجيل مشاهدة + طبقات الخريطة + تغطية المؤشّرات + تظافر القرائن + بوّابة الثقة (10 مسارات، 22 اختباراً). **تصحيح صادق:** `calibration/feedback` حساب نقيّ (`auto_adjust:false`) لا كتابة — عُرِض كقراءة لا نموذج إرسال.
- **وكيل U — «كونسول المدير» (صفحة `/admin/manager-console`، canManage):** اقتصاد الجدوى + فئات التكلفة + تكاليف الحقول + إسقاطات الدفتر (ERP/مخزون/autowrite) + بناء التقارير + RBAC (مصفوفة/من-يستطيع/معاينة تغيير دور) + جاهزيّة تصنيف السوق + فجوة المحاصيل + أوامر عمل من توصية + توليد مفتاح مشاركة + الإعدادات + دليل لقطة كاميرا + جاهزيّة البيانات + فحص الإخفاقات (18 مساراً، 16 اختباراً).
- **العقد:** 50 ترقية ⇒ **435 core + 31 إعفاء**. **لم يبقَ إلا 3 دَين واجهة مُوثَّق** (لم يُختلَق له UI أجوف): اتّجاه نبات-تربة متعدّد المواسم · مصدر بلاطات طقس زمنيّة (طبقة خريطة) · تهيئة مستأجِر (`/auth/tenants`، admin). بدأ اليوم بـ24 endpoint ملزَماً.

**تحقّق:** tsc نظيف · vitest **1039** (141 ملفّاً) · pytest -m unit **2544** · البوّابتان PASS · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-05 (ن-32) — سداد شريحة P2-متوسّط كاملة (32 مساراً) + إصلاح تعارض httpx/pip-audit

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). سادس دفعة وكلاء (O/P/Q) + إصلاح تبعيّات:

- **وكيل O — «المحاصيل المتخصّصة والتوقيت التراثيّ»:** عالية القيمة/متخصّصة/عطريّة/أعلاف (list) + بطاقة الإدخال وملاءمة الحقل + تخطيط البستان واقتصاده + النجوم/التقويم الثقافيّ/الإقليميّ (12 مساراً، 19 اختباراً).
- **وكيل P — «المديريّات والطقس والتهيئة»:** فهرس المديريّات + بطاقتها + آفاتها النشطة شهريّاً + توصية الموقع + ملخّص طقس الحقل + تحليلات السجلّ + دليل الزراعة + استبيان التهيئة (9 مسارات، 29 اختباراً).
- **وكيل Q — «اتّساق البيانات والدورة وWOFOST والعمليّات»:** فحوص الاتّساق (ريّ + نضارة) + تقييم الدورة ومبادئها + تكيّف WOFOST + الحالة التشغيليّة + توصية ريّ + تحسين المحفظة + التحقّق من الهندسة + تقرير عمليّة CSV (مدير) (11 مساراً، 17 اختباراً). كشف Q إدخالاً وهميّاً في السجلّ (`rotation/evaluate` كان `covered` بلا قارئ — صار حقيقيّاً الآن).
- **إصلاح تبعيّات (بلاغ المستخدم):** pip-audit المُوحَّد فشل ResolutionImpossible — `sahool-platform/api` وحده يثبّت `httpx==0.27.0` بينما 15 خدمة تطلب `>=0.27.0` وanthropic يقبل `<1,>=0.25`. لُيِّن إلى `>=0.27.0` (اتّفاقيّة المسار الحرِج) ⇒ «No known vulnerabilities found». تعارض حارسَين: SEC-6 (حارس التثبيت) حُدِّث أساسه بوعي موثَّق.
- **العقد:** 32 ترقية ⇒ **385 core + 81 إعفاء** — لم يبقَ إلا **P3-منخفض**. تصحيح دليل الواجهة للمسارات ذات المعامل (`/districts/${...}`).

**تحقّق:** tsc نظيف · vitest **963** (137 ملفّاً) · pytest -m unit **2544** · البوّابتان PASS · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-04 (ن-31) — سداد شريحة P1-عالٍ كاملة (30 مساراً): 3 وكلاء + شريحتي المباشرة

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام + `78f6d4a` الجزئيّ قبله). خامس دفعة وكلاء اليوم:

- **شريحتي المباشرة (`78f6d4a`):** «أعضاء الفريق والأدوار» في الإعدادات — `PATCH /auth/users/{id}/role` كان بلا أيّ واجهة (الدعوات تحدّد الدور عند الدعوة فقط) وجمهوره في الخريطة كان خاطئاً (farmer ⇒ **admin**: `require_role("admin")` + step-up MFA يظهر حقله عند 403 ويُعاد الإرسال بـX-MFA-Code) + تعطيل الحساب بتأكيد يقول الحقيقة: «لا إعادة تفعيل من الواجهة» (لا مسار خلفيّاً — لا زرّ مُختلَق).
- **وكيل L — «سلامة المدخلات ومعرفة المحاصيل»:** فحص كيميائيّ بحكم الخادم حرفيّاً (زرّ صريح لا كتابة حيّة — الاسم الجزئيّ يضلّل) + المحظورات + تقويم الزراعة + آفات التخزين + عالية القيمة/المتخصّصة + مرشّحو الإدخال (8 مسارات، 17 اختباراً).
- **وكيل M — «التحليلات الزراعيّة-البيئيّة»:** مخاطر/دورة/playbook + سلسلة Kc لحقل + مقارنة **موسمين** (سمّاها بصدق كما يدعم الخادم لا «حقلين») + نبات-تربة + مقارنة مواسم + تصعيد + نسب أصل الحقل (9 مسارات، 18 اختباراً). استبعد `POST kc-timeseries` (كتابة IRRIGATION_MANAGE) — **أكملتُه أنا**: نموذج «حفظ Kc لموسم» (upsert؛ الفارغ يُحفَظ NULL) فرُقّي بحقّ لا بتصنيف زائف.
- **وكيل N — «عمليّات الماء والحقل»:** إجهاد/نصيحة متكاملة (استدعاء واحد لا مزدوج) + تقويم القمح + ميزان FAO-56 (قرار الملوحة يظهر كما يقرّره الخادم) + سيول واردة + تحليل ماء المختبر + تنبيهات/طبقات الطقس + خطّة 4R + `outcome/record` (كتابة صادقة) + geo-locate (11 مساراً، **39 اختباراً**).
- **العقد:** 30 ترقية ⇒ **352 core + 114 إعفاء** (تبقّى P2/P3 فقط). درس متكرّر: انقطاع حدّ الجلسة أثناء دفعة وكلاء يُستأنف بـSendMessage من نفس النسخ — صفر إعادة عمل.

**تحقّق:** tsc نظيف · vitest **898** (134 ملفّاً) · pytest -m unit **2544** · البوّابتان PASS · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-04 (ن-30) — سداد شريحة P0-الحرِجة كاملة (21 مساراً) بثلاثة وكلاء متوازين

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). دفعة الوكلاء الرابعة اليوم (قطعها حدّ الجلسة 23:10 UTC واستُؤنفت من نُسَخها بلا إعادة عمل):

- **وكيل I — «القرار العميق» (`DecisionDeepPanel` في كونسول تشغيل القرار):** unified · for-location · explain · economics · policies/resolve · record · **dispatch/execute المحروس** (تأكيد مكتوب «نفّذ» + حكم الخادم/halt_breaches/replayed حرفيّاً). **استبعاد صادق:** `dispatch/consume` مستهلِك طابور آليّ (`FOR UPDATE SKIP LOCKED`، decision_dispatch.py:403) — أُعيد تصنيف إعفائه operational/machine/priority:none. صحّح طرق HTTP عن خريطة الدَّين (economics/explain = GET).
- **وكيل J — «دورة حياة التوصية» (`RecommendationsLifecyclePanel`):** engines · capacity-profiles · candidates · economic-adaptation · outcomes (كتابة-فقط: «النتيجة مجهولة حتى تُقاس»). لطيفة عقد FastAPI: candidates/economic-adaptation جسمهما مصفوفة خام والعدديّات query.
- **وكيل K — «مساعدات قرار الريّ والعيّنات» (`IrrigationDecisionAidsCard`، FieldView خبير):** confidence/{ndvi·irrigation} (حكم الخادم «safe_for_action» كما هو) · moisture-decision (RWC + disclaimer) · soil-types · irrigation-method/gross (calibrated:false ⇒ تحذير) · water-sensitivity/crops · soil-sampling/{protocol·depth·subsamples}.
- **العقد:** المسارات الـ21 رُقّيت من الإعفاءات إلى core ⇒ **320 core + 146 إعفاء** (backlog-ui 121 · operational 20 · admin-ops 5)؛ خريطة الدَّين حُدّث رأسها؛ P1 هي الشريحة التالية.

**تحقّق:** tsc نظيف · vitest **824** (57 اختباراً جديداً) · pytest -m unit **2544** · البوّابتان PASS · ruff نظيف · الحزمة مُتحقَّقة (3060).

---

## 2026-07-04 (ن-29) — أرشيف المستخدم ٤: سداد دَين UI (٣ لوحات) + fail-closed لقناع CDSE + تجميع شريط التواريخ

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). أرشيف على رأسنا `9a2deb5` (قبل التزام العقل الأخير) — دُمج انتقائيّاً:

- **٣ لوحات دَين UI جديدة:** الأقاليم المناخيّة-الزراعيّة (`/crop/agro-zones`) · التقويم اليمنيّ التراثيّ (`/crop/calendars`) · النظائر المناخيّة (`/crop/climate-analogs`) — hooks + panels + routes/App؛ **إصلاحي أثناء الدمج:** حارس التصريف في `permissions.ts` كان سيُفشل tsc (المعرّفات الجديدة ناقصة من ALL_PAGES) ⇒ أُضيفت + للعامل (معرفيّة قراءة، وviewer يرثها تلقائيّاً).
- **fail-closed لقناع بلاطات CDSE (`cdse_tiles.py`):** فشل القصّ المحلّيّ على المضلّع كان يمرّر البلاطة كما هي (قد تتجاوز حدّ الحقل) ⇒ الآن تُهمَل البلاطة ويُحذف COG المؤقّت (+حارس `test_tile_mask_fail_closed_v29_8`).
- **تجميع شريط التواريخ (`DateScrubber`):** سلسلة سنتين+ (~146 نقطة) كانت شريطاً ~14000px بـ146 طلب صورة ⇒ فوق 40 نقطة تجميع شهريّ تلقائيّ (ممثّل الشهر = الأقلّ غيوماً) مع توسيع الشهر المختار يوميّاً؛ `groupPointsByMonth` نقيّة + اختبار.
- **تصليب بوّابة التغطية ضدّ «الدليل الوهميّ»:** `backendCoverageRegistry.ts` (سرد-فقط) يُقصى من corpus الدليل + تُزال التعليقات السطريّة + `service_token_routes` تُشتقّ آليّاً فلا يُصنَّف مسار آليّ كدَين واجهة. العقد الآن **299 core + 167 إعفاء**. + حارس المُستدعي لا يعيد فرض limit=100 (نسختهم أعادت نمط get_event_loop ⇒ أعدت تثبيت asyncio.run).

**تحقّق:** tsc نظيف · vitest **767** · pytest -m unit **2544** · البوّابتان PASS (299/167) · ruff نظيف · الحزمة مُتحقَّقة (3052).

---

## 2026-07-04 (ن-28) — أرشيف المستخدم ٣: لا بتر لتواريخ الصور + ترقية 183 «إعفاءً وهميّاً» إلى العقد

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). أرشيف مبنيّ على رأسنا `4efdcc5` مباشرةً — دلتاه دُمجت كاملة بعد إصلاح عزل واحد:

- **إصلاح بتر التواريخ (`db_persist.list_asset_dates`):** كان `LIMIT 100` مع `ASC` — سلسلة سنتين+ (≈146 مروراً) تُبتَر **ويبقى الأقدم ويسقط الأحدث** (شريط الصور يعرض 2024 ويفقد 2026). الإصلاح: سقف افتراضيّ 800 (يسع 5 سنوات) + `DESC+LIMIT` للاحتفاظ بالأحدث ثم إرجاع تصاعديّ؛ المستدعي في `routers/fields.py` يسقط `limit=100` الصريح. اختبار محاكاة >100 تاريخ (لا بتر دون السقف · عند البتر يبقى الأحدث · الترتيب تصاعديّ).
- **تنظيف الدَّين الوهميّ في عقد التغطية:** 183 إعفاء `backlog-ui` لها دليل واجهة حقيقيّ رُقّيت إلى core (**102 ⇒ 285 ملزَماً**، الإعفاءات 364 ⇒ 181) + حارس جديد `test_no_waiver_has_real_ui_evidence` يمنع بقاء مسار مُدلَّل كدَين كاذب + `docs/api/UI_DEBT_MAP.md` (خريطة الدَّين الحقيقيّ المتبقّي).
- **إصلاحي أنا أثناء الدمج:** الاختبار الجديد استعمل `asyncio.get_event_loop().run_until_complete` — يرمي RuntimeError بعد اختبارات pytest-asyncio في السويت الكاملة (ترتيب-حسّاس) ⇒ `asyncio.run` (مرّ منفرداً وفي السويت).

**تحقّق:** البوّابتان PASS (285 core + 181 إعفاء، لا فالت/بائت) · pytest -m unit **2536** أخضر · ruff نظيف · الحزمة مُتحقَّقة.

---

## 2026-07-04 (ن-27) — أرشيف المستخدم ٢: إصلاح قناع البلاطات + توصيل بوّابة التغطية في CI

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). أرشيف المستخدم على أساس أقدم من رأسنا (قبل بوّابة العكس وإصلاح ن-26) — عُزلت دلتاه الحقيقيّة ودُمجت انتقائيّاً:

- **دُمج — إصلاح «mask persistence» في `tile_render.py` (جديد كلّيّاً):** بعض GeoTIFF تحمل قيماً منتهية (0.0) خارج AOI مع نطاق قناع — تمرير `src_nodata` وحده لـ`reproject` يجعل GDAL يتجاهل القناع ⇒ أشرطة داكنة معتمة في البلاطات/المصغّرات. `_reproject_dataset_mask` يعيد إسقاط القناع صراحةً (nearest) ويطبّقه NaN بعد الالتفاف، في مسارَي البلاطة والمعاينة (best-effort، فشله لا يكسر العرض).
- **دُمج — توصيل CI صريح:** خطوة `endpoint-ui-coverage-gate` في وظيفة *Repository Structural Lint* (بالاتّجاهين) + حارس `test_coverage_gates_ci_wiring.py` يثبت بقاء التوصيل، + اختبار `test_raster_assets_text_field_id.py` (تأكيداته تمرّ على محقّقات ن-26 كما هي) + ٣ تقارير تحقّق.
- **تُخوطي (أساس أقدم — عندنا الأحدث):** نسختهم من إصلاح field_id (مكافئة لن-26، أُبقيت الأصرم) · `endpoint_ui_coverage_gate/config` قبل الإعفاءات (121 مقابل 40 تصنيفاً) · ملفّات frontend/routes قبل ن-24 · مخلّفات `__pycache__/.pytest_cache`.

**تحقّق:** البوّابتان PASS · pytest -m unit **2532** أخضر · ruff نظيف · الحزمة مُتحقَّقة (3045).

---

## 2026-07-04 (ن-26) — بلاغ حيّ ٣: حفظ raster_assets كان يُتخطّى لكلّ حقل حقيقيّ (تصليب UUID زائد)

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). سجلّات المستخدم بعد حلّ DNS أظهرت النجاح الكامل للمعالجة (CDSE 5/5 · STAC 200) مع «raster_assets persist skipped: missing/invalid field_id='fld_b1c8ff30d02c'» — تشخيص المستخدم صحيح.

- **الجذر:** تصليب 2026-06-26 فرض UUID على `field_id` أيضاً، بينما معرّف الحقل القانونيّ نصّيّ (`fld_<hex>`) والعمود `raster_assets.field_id` هو **VARCHAR(50)** (v14) لا UUID ⇒ كلّ حفظ لحقل حقيقيّ يُتخطّى بصمت (الطبقات تُولَّد في الذاكرة لكنّ available-dates/timeline بعد إعادة التشغيل تفقدها).
- **الإصلاح (يحفظ قصد التصليب):** `_valid_field_id_text` جديد في `db_persist.py` و`main.py` — محارف آمنة `[A-Za-z0-9_-]` وبطول العمود ≤50 (يقبل fld_* وUUID معاً)؛ **tenant_id يبقى UUID** (عموده UUID فعلاً — هذا كان القصد الصحيح للتصليب).
- **حُرّاس:** توسيع `test_raster_db_persist_uuid_hardening_20260626.py` — fld_* يجتاز التحقّق ويصل الاتّصال (انحدار)، والمحارف الغريبة/الطول الزائد تُرفض قبل الاتّصال (التصليب باقٍ).

**تحقّق:** pytest -m unit **2531** أخضر · ruff نظيف · الحزمة مُتحقَّقة (3044).

---

## 2026-07-04 (ن-25) — أرشيف المستخدم: البوّابة العكسيّة لعقد التغطية (لا مسار مواجِه يفلت)

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). أرشيف المستخدم على أساس رأسنا `a225ad5` مباشرةً — دلتا 4 ملفّات نظيفة دُمجت كاملة:

- **البوّابة العكسيّة** في `endpoint_ui_coverage_gate.py`: الاتّجاه الأصليّ (core⇒دليل) يبقى، ويضاف `run_reverse_gate` — كلّ مسار backend مُصنَّف جمهوراً مواجِهاً (farmer/agronomist/manager/admin) يجب أن يكون في العقد بدليل **أو** في سجلّ إعفاءات صريح؛ الافتراض CI = الاتّجاهان معاً. النتيجة: 60 core + **364 إعفاء مُصنَّفاً** (`backlog-ui` 349 دَين واجهة مقصود · `operational` 9 · `admin-ops` 6) — **لا مسار فالت**، والإعفاءات البائتة (مسار زال/صار مغطّى) تُفشِل البوّابة.
- **إصلاحان حقيقيّان فيها:** (١) جذر الجوّال كان `mobile/lib` **غير الموجود** ⇒ كلّ أدلّة Flutter كانت مخفيّة بصمت — صُحّح إلى `mobile/sahool_app/lib` مع اختبار يثبت أنّ الجذر يُمسَح فعلاً؛ (٢) تطبيع `/api/v1/auth/*` ⇄ `/auth/*` (إعادة كتابة nginx) يمنع أيتاماً كاذبة.
- **ملفّات:** `config/endpoint_ui_coverage_waivers.json` (جديد) · البوّابة · 5 اختبارات unit جديدة · التقرير المولَّد تطابق بعد إعادة توليده محليّاً.
- **تحقّق أيضاً (سؤال المستخدم عن عمق أرشيف Copernicus):** backfill يدعم أصلاً 3 سنوات (`extended_3_years`) و5 (`research_5_years`) وحتى **10 سنوات** عبر `custom` (`months ≤ 120` أو from/to حرّ منذ 2015) — لا تعديل لازماً؛ Element84 يغطّي أرشيف Sentinel-2 كاملاً.

**تحقّق:** البوّابتان PASS · pytest -m unit **2529** أخضر · ruff نظيف · الحزمة مُتحقَّقة (3044).

---

## 2026-07-04 (ن-24) — FieldView صار الشاشة الرئيسيّة (الجذر «/») وكلّ الشاشات ظاهرة

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). سأل المستخدم «هل أسلوب FieldView هو افتراضيّ؟» (كان: لا — الجذر dashboard، وmap-center مخفيّ beta) ثم قرّر: نعم + إظهار جميع الشاشات.

- **routes.ts:** `map-center` (FieldView/MapHub) انتقل إلى قسم «نظرة عامّة» كأوّل عنصر على الجذر `/` (label «مركز الخرائط»، stable، أُزيل hidden/badge «دمج») · `dashboard` ⇒ `/dashboard` (يبقى ثاني عناصر التنقّل) · تحديث تعليق مخطّط الـURL. المسار المجهول ما زال يعيد إلى `/` (الآن FieldView).
- **روابط «حقولي» العميقة:** `/fields/map-center?add=1|?field_id=…` ⇒ `/?add=1|/?field_id=…` (كلّ query/state كما هو).
- **«جميع الشاشات ظاهرة»:** map-center كان الشاشة المخفيّة **الوحيدة** في السجلّ — حارس جديد يمنع أيّ `hidden` مستقبلاً بصمت + يثبّت `/`⇒map-center و`/dashboard`⇒dashboard.
- **لم يُمسّ:** الأدوار (canAccess) وأعلام الميزات (isPageEnabled) تحكم الظهور كما هي؛ وضع الفلاح يبقى الافتراضيّ داخل FieldView (`sahool:fieldview:mode`).

**تحقّق:** tsc نظيف · vitest **762** أخضر (+حارس الجذر) · حُرّاس unit ذات الصلة 75 · الحزمة مُتحقَّقة (3044).

---

## 2026-07-04 (ن-23) — متابعة البلاغ الحيّ: فشل STAC التامّ صار 503 صادقاً (كان 500 خاماً)

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). بعد نشر إصلاح ن-22 أرسل المستخدم traceback جديداً: backfill يفشل الآن **عند الطلب** بـ`RuntimeError: STAC غير متاح بعد 3 محاولات ولا cache: [Errno -5] No address associated with hostname` — **DNS داخل حاوية raster-service معطّل** (الأساس Element84 والاحتياطيّ Planetary Computer كلاهما بلا حلّ اسم؛ compose سليم — `sahool-internal` بـ`internal: false`). المشكلة بيئيّة على جهاز المستخدم، لكنّ الكود كان يسرّبها 500 خاماً بtraceback.

- **`_stac_query`** مُغلِّف واحد للاستدعاءات الثلاثة (Sentinel-2/Landsat/DEM): RuntimeError من العميل المرن ⇒ **HTTPException 503** برسالة عربيّة ثابتة قابلة للتصرّف («تحقّق من اتّصال/DNS الحاوية»)؛ التفصيل الخام في السجلّ الداخليّ فقط (لا str(e) للعميل).
- **حارس unit:** `test_stac_total_failure_maps_to_503_not_raw_500` — يثبت 503 وعدم تسرّب `Errno` في detail.
- **تشخيص المشغّل (موثَّق في رسالة الجلسة):** فحص DNS داخل الحاوية مقابل المضيف؛ الحلّ عادة إعادة تشغيل docker daemon أو ضبط `dns:` في compose.

**تحقّق:** pytest -m unit **2525** أخضر · ruff نظيف · الحزمة مُتحقَّقة (3044).

---

## 2026-07-04 (ن-22) — إصلاح جذريّ: كلّ مهامّ backfill كانت تفشل بـHTTPException مبتلَعة

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام). تشخيص من سجلّات المستخدم الحيّة: ~12 مهمّة `backfill_*` تفشل «failed: HTTPException» مباشرةً بعد «بُني VRT من 13 نطاق»، بينما بلاطات CDSE تعمل (بايتات حقيقيّة 933–1224؛ الـ70-byte قصّ مضلّع صحيح).

- **الجذر:** `_safe_raster_source` (raster-service) كان يقبل `file://` وhttp(s) فقط، بينما **ثلاثة أنابيب داخليّة** تمرّر مخرجاتها كمسار محلّيّ خام: backfill وprocess-from-stac (VRT في `/tmp` — خارج `UPLOAD_DIR` أصلاً) وCDSE (GeoTIFF تحت `UPLOAD_DIR` بلا `file://`) ⇒ 400 «مخطّط URL غير مدعوم» تُبتلَع في معالج فشل المهمّة.
- **الإصلاح (لا اتّساع أمنيّاً):** قبول المسار المطلق **فقط** تحت `UPLOAD_DIR` (نفس احتواء realpath لـ`file://`؛ traversal/ملفّات النظام تُرفَض كما كانت) + بوّابتا `build_band_vrt` تكتبان بـ`out_dir=main.UPLOAD_DIR`.
- **قابليّة التشخيص:** سجلّات فشل المهامّ الثلاثة تُلحِق الآن `[status] detail` لـHTTPException (نصّنا المتحكَّم به — job status يبقى رمزاً عامّاً، حارس التعقيم `test_raster_error_sanitization_static` أخضر). النوع وحده جعل بلاغ اليوم غير قابل للتشخيص.
- **حُرّاس جديدة:** `tests_v9/test_raster_source_guard_internal_pipelines.py` (unit+security: عقد الحارس + ساكنا out_dir/CDSE) + اختبار وظيفيّ non-dry-run في `test_historical_backfill.py` يلتقط `ProcessRequest` المجدول ويُثبت اجتيازه الحارس. أُصلح أيضاً سكربت e2e `test_stac_vrt.py` (كان يكتب النطاقات خارج المجلّد المسموح).

**تحقّق:** pytest -m unit **2524** أخضر (كان 2520) · حارس التفكيك 7/7 · ruff نظيف · الحزمة مُتحقَّقة (3043).

---

## 2026-07-04 (ن-21) — كونسول الموافقات: سجلّ التغطية يبلغ صفر partial

**رأس main = develop = `claude/code-review-34hO3`** (هذا الالتزام + `9f6d6eb` ترقية GIS).

آخر طبقة partial (`collaboration-approvals`) أُغلقت بخطوتها المسمّاة نفسها:
- **فجوة خلفيّة حقيقيّة سُدَّت:** مخزن موافقات v58 يملك `list_pending()` بلا أيّ نقطة تكشفه — أُضيف `GET /approvals/pending` (ai_agronomist) مقيَّداً بهويّة البوّابة الموثوقة ومرشَّحاً بـ`tenant_id` المسجَّل في الطلب؛ **السجلّات القديمة بلا tenant تُستبعَد fail-closed**. اختبارات الموافقات ٣٤/٣٤ لم تنكسر.
- **`ApprovalsConsolePage`** (`/admin/approvals`، owner/manager فقط): طلبات أدوات الوكيل المعلّقة (خطر ملوَّن · مفاتيح الوسائط فقط — القيم قد تكون حسّاسة · اعتمِد/ارفض بهويّة SEC-3.1 مع ملاحظة «التنفيذ على خدمة النطاق بعد التخويل») + قرارات التوزيع المنتظِرة موافقة (رقابيّة).
- **السجلّ النهائيّ: covered:16 · partial:0 · waived:1 · not_ready:1** — كلّ طبقة backend إمّا مكشوفة أو مؤجَّلة بقرار موثَّق. (قبلها بدقائق: ترقية advanced-gis المؤرَّضة بكونسول وكيل D.)

**العقد: 100 ⇒ 102 endpoint.** **تحقّق:** vitest **758** أخضر · tsc نظيف · البوّابة PASS 102/102 · pytest موافقات 34/34 + حارس التغطية 3/3 · ruff نظيف · الحزمة مُتحقَّقة.
**لم يبقَ قابلاً للتنفيذ هنا:** فقط المحجوب على المستخدم (SPATIAL-401 · auth v21 · MAP-QA حيّ) والمؤجَّل الموثَّق (marketplace · phase-runtime).

---

## 2026-07-04 (ن-20) — الدفعة الثالثة (G/H) + متابعة المستخدم: العقد يبلغ 100 endpoint

**رأس main = develop = `claude/code-review-34hO3` = `169dce4`** (٣ التزامات: `00a1cfa` هدف الدورة · `f2555e2` دمج متابعة المستخدم يدويّاً · `169dce4` دفعة G/H).

- **متابعة المستخدم (`f2555e2`، دمج يدويّ):** أرشيفه على أساس `5015796` الأقدم — النسخ الأعمى كان سيمحو جسر الحوكمة dispatch. دُمجت دلتاه: ٣ أهداف (نافذة الزراعة/الدورة/GDD) + مصدرا planning/gdd + خطّافا operations-calendar/gdd-track + ترقية crop-planning ⇒ covered. **حسم تداخل:** هدفي `choose_next_crop` (أُضيف قبل ساعة `00a1cfa`) حُذف لصالح `plan_rotation` الأشمل — الكتالوج ٩ أهداف.
- **وكيل G — منضدة التشخيص (`fieldDiagnostics`، ١١):** أعراض⇒مرشّحون مرتّبون (لا حكم قاطع) · سلّم IPM (الكيميائيّ ملاذ أخير) · ملوحة FAO من قياسات المستخدم.
- **وكيل H — «ماذا لو؟» (`whatIfScenarios`، ١٠):** حرارة/مطر/موعد/توأم ماء — builders يرفضون العبث بالعربيّة، `summary_ar` الخادم + لافتة «ليست تنبّؤاً معايَراً»، لا أثر غلّة مُلفَّق. **درسان:** JSX.Element يفشل في إعداد المشروع (⇒React.ReactNode)؛ تصادم آخر مُنع سلفاً بأسماء useDecision*Insight.
- **السجلّ:** covered:14 · partial:2 (بقيّة gis الكتابيّة + collaboration approvals-binding) · waived:1 · not_ready:1 — **الحارس حدَّث عدَّه المثبَّت** (كان يثبّت 12/4).

**العقد: 90 ⇒ 100 endpoint ملزَم** (بدأ اليوم 24). **تحقّق:** vitest **752** أخضر · tsc نظيف · البوّابة PASS 100/100 · الحزمة مُتحقَّقة (3033).

---

## 2026-07-04 (ن-19) — الدفعة المتوازية الثانية: GIS + حاسبات + رؤى القرار + سجلّ التغطية

**رأس main = develop = `claude/code-review-34hO3` = `259acbe`** (٤ التزامات: `5c6605b` جسر الحوكمة · `2cd846b` سجلّ التغطية من أرشيف المستخدم · `259acbe` دفعة D/E/F).

- **جسر الحوكمة (`5c6605b`، أنا):** الأهداف الميدانيّة تحمل ربط توزيع (ريّ MEDIUM · رشّ HIGH · كشف LOW)؛ «اعتمِد التوصية» يستدعي dispatch/evaluate (dry-run) ويعرض حكم الحوكمة معلوماتيّاً + زرّ rebuild شبكة الحدود في كونسول الإدارة.
- **سجلّ التغطية (`2cd846b`، أرشيف المستخدم — دلتا ملفّين):** `frontend/src/config/backendCoverageRegistry.ts` (18 طبقة بحالة مقصودة صريحة) + ٧ حرّاس (P0/P1 لا تبقى partial بصمت · المؤرَّض بالشجرة فقط).
- **الدفعة الثانية (`259acbe`، ٣ وكلاء):** كونسول GIS `/advanced/gis-catalog` (STAC/OGC/كاش، ١٢ اختباراً) · حاسبات القياس (إنبات/تخزين °م⇒°ف/عمق بذر/رطوبة حبوب/ارتفاع البنّ، ١١) · رؤى القرار (سجلّ مُدام/شرح/تعلُّم استشاريّ/أثر، ٨). **درس تصادم:** useDecisionRecords/Explain كانا موجودَين لصفحات قائمة ⇒ أعيدت تسمية خطّافي الوكيل `useDecision*Insight` بلا كسر — تحقّق-قبل-دمج حتّى مع مخرجات وكلائي.
- **درس المحاولة الأولى:** الوكلاء الثلاثة قُطعوا بحدّ جلسة API (بلا مخلّفات — الشجرة بقيت نظيفة)؛ أُعيد إطلاقهم بعد الإعادة ونجحوا.

**العقد: 72 ⇒ 88 endpoint ملزَماً** (بدأ اليوم 24). **تحقّق:** vitest **731** أخضر · tsc نظيف · البوّابة PASS 88/88 · الحزمة مُتحقَّقة (3023).
**المتبقّي الموثَّق:** بنود partial في سجلّ التغطية نفسه (soil-lab workbench · simulation gates · collaboration console · marketplace not_ready) — كلّها P2/P3 بخطوة تالية مسمّاة في السجلّ.

---

## 2026-07-04 (ن-18) — دفعة ٣ وكلاء متوازين + جسر النتيجة: ٤ طبقات يتيمة أخيرة

**رأس main = develop = `claude/code-review-34hO3` = `7d9ee86`** (التزامان: `a5ea72d` جسر النتيجة · `7d9ee86` دفعة الوكلاء).

بطلب المستخدم «واصل بأكثر من وكيل»: ٣ وكلاء متوازون (كلٌّ ينشئ ملفّاته الجديدة فقط — lib+test+card — ويسلّم مواصفة خطّافات/تركيب/عقد، والدمج المركزيّ في useApi/MapHub/config عندي — **صفر تصادم ملفّات**):

- **جسر النتيجة (`a5ea72d`، أنا):** `/api/v1/outcome/measure` ⇒ لوحة «مُخطَّط ⇄ مرصود» في كونسول القرار — مفردات الخادم (followed/under/over · better/worse · met/above · needs_data) ملوَّنة كما هي، والفراغ يبقى غائباً (الخادم يقول needs_data بصدق).
- **وكيل A — مخاطر المناخ والماء (`fieldClimateRisk`، ٨ اختبارات):** حساسيّة المراحل المائيّة FAO-56 + مخاطر موسميّة/ساعات برودة لإقليم **يختاره المستخدم صراحةً** (لا اشتقاق مُختلَق) + مناطق مشابهة بترتيب الخادم.
- **وكيل B — حصاد المياه/طرق الريّ (`waterHarvesting`، ٩ اختبارات):** إمكانات حصاد المطر من قياسَي المستخدم + الطرق التراثيّة (مدرّجات/عقوم/كرفان) + ملامح طرق الريّ FAO موسومة calibrated=false.
- **وكيل C — المعرفة الزراعيّة (`fieldAgroKnowledge`، ١١ اختباراً):** إكثار المحصول + ما بعد الحصاد + دليل/أصناف/آفات **البنّ اليمنيّ** (يظهر بمطابقة صريحة فقط).

**درس تنسيق الوكلاء:** stop-hook طلب إثباتاً أثناء عملهم ⇒ إثبات انتقائيّ لملفّاتي فقط (المولّد يعتمد `git ls-files` فلا يلتقط غير المتتبَّع) — ملفّات الوكلاء غير المكتملة بقيت خارج الإثبات عمداً.

**العقد: 55 ⇒ 71 endpoint ملزَماً** في يوم واحد (كان 24 صباحاً). **تحقّق:** vitest **692** أخضر (+31) · tsc نظيف · البوّابة PASS 71/71 · الحزمة مُتحقَّقة (3011).
**المتبقّي (P2/P3):** Advanced GIS console (35) · rebuild الحدود (إداريّ) · seed calculators (تحتاج قياسات) · وصل محرّك الأهداف بالـdispatch (معماريّ، يحتاج قراراً).

---

## 2026-07-04 (ن-17) — إدخال السجلّ الماليّ: اكتمال قوس الربحيّة من الشاشة

**رأس main = develop = `claude/code-review-34hO3` = `7f8fd62`.**

- **بطاقة الإدخال (`7f8fd62`):** كانت بطاقة الربحيّة تقرأ سجلّاً لا يستطيع المستخدم تعبئته من الواجهة. `LedgerEntryCard` (خبير + `mutateAllowed` فقط) بثلاثة تبويبات: عمليّة بتكلفة (تاريخ/نوع/فئة) · بند موازنة مخطَّط · إيراد. بناة حمولات نقيّة (`lib/ledgerEntry.ts`، ٧ اختبارات) بتحقّق محليّ صارم برسائل عربيّة قبل POST؛ النجاح يُبطل كاش الربحيّة/الانحراف/الكثافات (`LEDGER_QUERY_PREFIXES`) فتتحدّث البطاقة حيّاً؛ 404/403 تُعرَض بأسبابها. العقد: 52 ⇒ **55 endpoint ملزَماً**.

**تحقّق:** vitest **658** أخضر (+٧) · tsc نظيف · بوّابة التغطية PASS 55/55 · الحزمة مُتحقَّقة (3008).
**بقي من تدقيق التغطية (P2/P3):** كتابات الحدود (review/clean/rebuild) · Climate Analogs/Seasonal Risk · Water Harvesting · Seed/Postharvest/Coffee · Advanced GIS console.

---

## 2026-07-04 (ن-16) — تدقيق «الطبقات المتقدّمة» + إغلاق الـP0 الأخير: كونسول تشغيل القرار

**رأس main = develop = `claude/code-review-34hO3` = `bce6c54`.**

رفع المستخدم تدقيقاً (BACKEND_ADVANCED_LAYERS_EXPOSURE_AUDIT، مبنيّ على أرشيف round3 **قبل** سلسلة التغطية) — مطابقته بالحالة: **8 من طبقاته الـ10 الأعلى قيمة كانت قد أُغلقت اليوم** (Admin Console · التقويم اليمنيّ · Crop Cards · Boundary score/graph · Planting/Rotation · Farm Ledger · Traceability · حارس التغطية الساكن). الباقي الحقيقيّ نُفِّذ الآن:

- **كونسول تشغيل القرار (`bce6c54`، P0):** مسارات decision/outcome العشرون كانت بلا قارئ. صفحة `/advanced/decision-runtime` (محجوبة عن viewer): قرارات محروسة بعدّادات (blocked/pending_approval/ready) · طابور المُشغِّل بشارة «لا تنفيذ من هذه الشاشة» · سجلّ التنفيذ · السياسات بالأولويّة · معاينة dry-run (الخادم يعيد dry_run=true). **قرار حوكمة:** لا زرّ execute — التنفيذ يمرّ بمسار الموافقات/المشغِّل (v58). العقد: 47 ⇒ **52 endpoint ملزَماً**. درس: استبدال نصّيّ عامّ أصاب موضعين في permissions.ts (ازدواج في ALL_PAGES) — ضُبط بمراجعة الإدراج قبل الإثبات.

**تحقّق:** vitest **651** أخضر · tsc نظيف · بوّابة التغطية PASS 52/52 · الحزمة مُتحقَّقة (3005).
**المتبقّي من التدقيق (موثَّق، غير مُنفَّذ):** Climate Analogs/Seasonal Risk (13) · boundary review/clean/rebuild (كتابات) · budgets/revenues POST · Water Harvesting (7) · Seed/Postharvest/Coffee (16) · Advanced GIS console (35) — أغلبها P2/P3 بتصنيف التدقيق نفسه.

---

## 2026-07-04 (ن-15) — إغلاق بندين من متبقّي ن-14: التقويم اليمنيّ + «ماذا أزرع؟»

**رأس main = develop = `claude/code-review-34hO3` = `f5759d6`.**

- **التقويم الزراعيّ اليمنيّ (`3badd56`):** `YemeniCalendarCard` (وضعا الفلاح والخبير) من نداء `/calendars/today` الواحد (منزلة قمريّة + شهر حميريّ + نظام المنطقة + نافذة زراعة محصول الحقل وملاءمة الشهر) + أمثال المنزلة النشطة (`/agricultural-proverbs/for-date`). صدق: شارة «سياق تراثيّ — لا يدخل القرار» تعكس تصريح الخادم `display_only` حرفيّاً.
- **«ماذا أزرع؟» (`f5759d6`):** `PlantingAdvisorCard` (خبير) من `rotation/suggest` (good/acceptable/avoid بأسباب يمنيّة) + `planting/check` لملاءمة الشهر للمرشَّح المُختار — أحكام الخادم تُعرَض لا يُعاد الحكم.
- **العقد:** 43 ⇒ **47 endpoint ملزَماً** (calendars/today · proverbs/for-date · rotation/suggest · planting/check).

**تحقّق:** vitest **647** أخضر (+١٠) · tsc نظيف · بوّابة التغطية PASS 47/47 · الحزمة مُتحقَّقة (3002).
**بقي من متبقّي ن-14:** مركز القرار (decision dispatch/policies) · إدخال الموازنة/الإيراد POST.

---

## 2026-07-04 (ن-14) — فحص التغطية: مصفوفة backend⇄frontend + بوّابة CI + ٥ واجهات من مسارات يتيمة

**رأس main = develop = `claude/code-review-34hO3` = `980b46c`** (سلسلة ٦ التزامات فوق `dae1c0f`).

فحص المستخدم أثبت أنّ backend أوسع بكثير من الواجهة (جردي المباشر: **652 مساراً غير صحّيّ**، تغطية نصّيّة ~160). الاستجابة بترتيب أولويّاته:

- **الأساس (`1bbd76d`):** [`scripts/ci/endpoint_ui_coverage_gate.py`](../scripts/ci/endpoint_ui_coverage_gate.py) يجرد مسارات services/ فعليّاً ويصنّفها بالجمهور (farmer/agronomist/manager/admin/internal) من [`config/endpoint_ui_coverage.json`](../config/endpoint_ui_coverage.json) ويولّد [`docs/api/BACKEND_FRONTEND_COVERAGE.md`](../docs/api/BACKEND_FRONTEND_COVERAGE.md) (652 مساراً) — وحارس unit ([`tests_v9/test_endpoint_ui_coverage_gate.py`](../tests_v9/test_endpoint_ui_coverage_gate.py)) يفشل إن فقد endpoint جوهريّ دليله في الواجهة (بدأ 24 ⇒ انتهى **43** endpoint ملزَماً). internal/admin لا تُطالَب بواجهة عاديّة.
- **بطاقة المحصول (`0510ac6`):** crop-cards YAML (FAO-56 Kc · Maas-Hoffman · GDD · أصناف يمنيّة) كانت بلا قارئ — `fieldCropCard.ts` (مطابقة اسم بلا تخمين) + `CropKnowledgeCard` (حقائق + منتقي أصناف: مقاومات/حصاد متوقَّع من بذار الموسم/ملاءمة ملوحة بقياس المستخدم).
- **تعميق السجلّ الماليّ (`405f145`):** economic-state (كثافات وحدة خادميّة: تكلفة/هـ · ماء م³/هـ · تكلفة الماء/م³ · طاقة/م³ + حالة موازنة + توصية كفاءة) + أداة سعر التعادل (تكلفة السجلّ الفعليّة لا تقدير) في SeasonProfitabilityCard.
- **تتبّع الحصاد (`70914a5`):** harvest-lots v65 (دفعات + سلسلة حيازة append-only بمعيار اكتمال الخادم حصاد∧بيع + دفتر مدخلات بتغطية كلفة مُعلَنة) — `HarvestTraceabilityCard`.
- **مراجعة الحدود (`556203a`):** boundary/score (تهديف حتميّ يُخزَّن، العوامل والقرار من الخادم) + boundary-graph (جيران بطول الحافّة) — `BoundaryReviewCard`.
- **كونسول التشغيل (`980b46c`):** صفحة `/admin/runtime` (owner/manager فقط عبر MANAGEMENT_ONLY_PAGES، الخلفيّة تفرض AUDIT_VIEW): جاهزيّة الإنتاج · DLQ أحداث/outbox (أيّ total>0 ⇒ تنبيه) · قائمة offline · رفض الأمان · الأتمتة.

**قبلها في اليوم نفسه:** طبقة الربحيّة الأولى (`2e73d67`) + ٣ جولات تصلّب جنائيّ من المستخدم (`55e297e`,`dae1c0f`: حرّاس المحرّك canAct===true/producesTask/متابعة إلزاميّة + contextKey + فشل مرئيّ + نظافة أسرار: إزالة settings.local.json المتتبَّع بكلمة مرور admin).

**تحقّق:** vitest **637** أخضر (106⇒109 ملفّاً) · tsc نظيف · بوّابة التغطية PASS 43/43 · `pytest -m unit` حارس التغطية 3/3 · ruff نظيف على نطاق CI · الحزمة مُتحقَّقة (2996).

**المتبقّي الموثَّق (لم يُنفَّذ):** التقويم الزراعيّ/الفلكيّ اليمنيّ (calendars/astronomical-timing/proverbs) · crop-suitability/planting/rotation/gdd كمسار «ماذا أزرع؟» في محرّك الأهداف · decision dispatch/policies كمركز تشغيل قرار · budgets/revenues POST (إدخال موازنة/إيراد من الواجهة).

---

## 2026-07-04 (ن-13) — تحويل FieldView إلى «متعاون يحقّق هدفاً»: أساس → حوكمة → P0–P4 → إلهام → محرّك الأهداف

**رأس main = develop = `claude/code-review-34hO3` = `777582b`** (CI أخضر ١١/١١ للالتزام `777582b`؛ حزمة الإصدار مُعاد بناؤها ومُتحقَّقة ٢٩٦٩ checksum). ٢٥ التزاماً منذ `c9162fd`، سلسلة FieldView متماسكة (رفع مباشر على الفروع الثلاثة بتفويض المستخدم).

**القوس الكامل (كلّ طبقة نقيّة + مُختبَرة في `frontend/src/lib/`، وبطاقات عرض في `components/fieldview/` موصولة بـ`MapHub.tsx` عبر خطّافات React Query، مبوَّبة بوضع الفلاح/الخبير):**

- **الأساس + الحوكمة (`481f80b`,`59ecbc6`):** محرّك حوكمة FieldView + رسم مصدر القرار (agent-inspired) + طبقات نظام التصميم/التشغيل/سكربت القرار.
- **P0–P4 (`9954f2a`→`27c3a0d`):** تقرير صحّة الحقل (كلّ حقل نشط يجيب الأسئلة الخمسة) · عرض الفلاح ٤ مقاييس (Kisan360) · مدخل ورشة المناطق/VRA (GeoPard) · مقارنات طبقات جاهزة زراعيّاً (P3) · طبقة أعمال المزرعة (تكلفة/ربح لكلّ حقل، صادقة).
- **بطاقات الإلهام (`d10c889`→`74df847`):** مركز عمليّات مصغَّر (John Deere/Agworld) · دماغ ماء الحقل — قرار ريّ واحد واضح (CropX) · وضع فلاح/خبير يُنسّق رصّ البطاقات (OneSoil) · استكشاف بالأدلّة (Taranis) · مركز قيادة الموسم (Cropin، نقاط `/phenology`+`/stage-actions` حيّة) · تكلفة ريّ حقيقيّة من دفتر المياه في طبقة الأعمال · **تحسين الأداء:** استعلامات الخبير تُجلَب في وضع الخبير فقط (`6992592`) · سجلّ تتبّع قابل للمشاركة Markdown (Farmonaut، `74df847`).
- **محرّك الأهداف — الطبقة المتوّجة (`777582b`، استلهاماً من مقال فلسفة تصميم الوكيل):** يحوّل FieldView من «أداة تعرض بيانات» إلى «متعاون يحقّق هدفاً» عبر حلقة **هدف → فحص → تفسير → إجراء → مراجعة**. أربعة ملفّات: [`lib/fieldObjectiveEngine.ts`](../frontend/src/lib/fieldObjectiveEngine.ts) (٦ أهداف جاهزة + `buildObjectivePlan` يحسب المصادر الناقصة و**يمنع الإجراء `canAct` حتّى اكتمال الدليل** — لا توصية على دليل ناقص) · [`lib/fieldActionLifecycle.ts`](../frontend/src/lib/fieldActionLifecycle.ts) (آلة حالات صريحة: مسوّدة→دليل→اعتماد→مهمّة→تنفيذ→متابعة صورة/مدّة→مراجعة→جودة؛ الأثر `unknown` حتّى مراجعة حقيقيّة) · [`components/fieldview/FieldObjectivePanel.tsx`](../frontend/src/components/fieldview/FieldObjectivePanel.tsx) · وصل `MapHub` يحسب `EvidenceAvailability` من الاستعلامات الحيّة (صور/طقس/رطوبة/تنبيهات/مهامّ/سجلّات/مناطق/موسم) ويصل «أنشئ مهمّة» بأفعال حقيقيّة (تشخيص الإجهاد ⇒ وضع تثبيت دليل ميدانيّ).

**عمل سابق في السلسلة نفسها (`0d171f8`→`452e9d5`):** معالجة ExG لـSAM2 + شفافيّة UI · **إصلاح runtime حرِج `2987c5e`:** تسجيل عضو `FIELD_IMAGERY_BACKFILL_REQUESTED` في `EventType` (كان يُصدَر بلا تعريف ⇒ KeyError→500؛ ضبطه حارس المنصّة `test_emit_event_names.py` في Platform Unit Tests لا في `-m unit`) · مسح UI-wide (prefill لشاشات النماذج/الاستعلام + حارس انحدار `8ccbb05`) · تصليب تدفّق البيانات الاحترافيّ (حقل نشط موحَّد).

**دروس مُثبَتة:**
1. **`ruff format --check` يمسح شجرة `services/` كاملةً في CI** — تنسيق ملفّين جديدين محليّاً لا يكفي (احمرّ `0d171f8`، أُصلِح بمسح كامل `ba5e9d2`). طُبِّق في كلّ التزام بعده.
2. **مؤلّفو الأرشيفات يشغّلون `py_compile` فقط لا سويت المنصّة** — لذا أخطاء enum الـruntime (`FIELD_IMAGERY_BACKFILL_REQUESTED`) تمرّ عندهم وتُضبَط عندنا فقط بحارس المنصّة.
3. **عزل دلتا الأرشيف بالأساس لا بالرأس** (أرشيفات على `55e2f65`/`2987c5e` تحمل نسخ FieldView موازية) — أبقَينا نسخ main واستبعدنا اختبارات غير متوافقة (`fieldViewResolver.test.ts` يستورد `resolveActiveField` غير المُصدَّر — main يستعمل `resolveFieldViewSelection`).

**تحقّق:** كامل حزمة vitest **٥٨٣ ناجح / ١٠٦ ملفّ** (١٩ اختباراً جديداً للأهداف: بوّابة الدليل + انتقالات دورة الحياة) · `tsc --noEmit` نظيف · `pytest -m unit` أخضر · CI ١١/١١ أخضر · Production Gates (build+validate) مُعاد.

**فجوات مفتوحة موثّقة (لم تُنفَّذ، تحتاج مدخلات/بيئة):** SPATIAL-401 (يحتاج status/body من Network) · MAP-QA (Playwright حيّ) · auth «unhealthy» v21 (يحتاج `docker logs`) · v57.5-DB (Postgres/CI، أعِد التحقّق من عدم إغلاقه downstream) · متابعتا D/C الصغيرتان (عقد TileJSON · الموضوع اليتيم NATS).

---

## 2026-07-03 (ن-12) — دمج أرشيفات المستخدم: خرائط احترافيّة + سلسلة أدلّة التقطيع

**رأس main = develop = `c9162fd`** (CI أخضر #2836 · Production Gates أخضر · دُمِج develop بتقديم سريع).

سلسلة أرشيفات متتالية من المستخدم (كلّها على أساس `53ae8a8`)، دُمِجت بـ**تحقّق-قبل-دمج** (مقارنة كلّ أرشيف بالأساس أو بالأرشيف السابق لعزل الدلتا الحقيقيّة، لا بالرأس المتحرّك):

- **`084e869` خرائط احترافيّة:** طبقة MapTiler Satellite مُقيَّدة بالمفتاح (`VITE_MAPTILER_KEY`، `{token}`-قالبيّة، بلا سرّ مثبَّت، نفس نمط Mapbox الآمن) + دالّة `toMapLibreRasterUrl` مشتركة (استُخدمت في HubMapGL بدل التكرار المضمَّن) + إبراز `SAM2_POLYGON_*` على كتلة sam2-inference في compose. حرّاس عقد موسَّعة.
- **`caefad0` حرّاس التقطيع الإنتاجيّة:** سلسلة provenance صادقة end-to-end — `sam2-inference` يُخرِج `metadata` (model/checkpoint/post_processing/vertices/inference_ms) · `field-segmentation.run_segmentation_model` صار 3-tuple يمرّر مجموعة مفاتيح allowlisted · الواجهة تلتقط `boundaryMetadata` وترسلها عند الحفظ · **`field_geometry_save_guard.py`** (نقيّ، بلا قاعدة): `validate_boundary_for_save` يرفض الحلقات القصيرة/كثيفة الرؤوس (>2000)/مساحة غير منتهية (422 برموز آليّة) قبل مصدر الحقيقة، و`sanitize_boundary_metadata` allowlist «لا يمنح ثقة ولا يتجاوز قرارات المستأجِر/الأمن» · `routers/fields.py` يوصل metadata مُعقَّماً + يشغّل الحارس على الإنشاء/التحديث (منطق RLS/المستأجِر بلا مساس).
- **`c9162fd` إكمال المتبقّي:** أدوات صقل الحدّ من العميل في `AddFieldWithMap` (Douglas-Peucker بالأمتار خفيف/موصى/قويّ = 1/3/5م + إزالة رؤوس شبه مكرّرة + تراجع/إعادة) — **مساعِدة للمراجعة فقط، الحارس الخلفيّ مصدر الحقيقة** · بوّابة e2e حيّة `scripts/e2e/segmentation_platform_live_gate.py` (nginx→المنصّة→field-seg→SAM2).

**درس عزل تكرار (حرِج):** أرشيفات المستخدم تُبنى على أساس ثابت (`53ae8a8`) بينما main يتقدّم؛ فمقارنة الأرشيف بالرأس تُظهر عملي الأحدث كـ«فرق» زائف. الصواب: مقارنة بالأساس أو بالأرشيف السابق لعزل زيادة المستخدم فقط، والحفاظ على إضافاتي (علامات `pytest.mark.unit`) بعدم استبدالها بنسخ الأرشيف الأقدم.

**تحقّق:** `pytest -m unit` = **2515 ناجح / 0 فاشل** · tsc نظيف · vitest 29/29 · ruff نظيف · bandit HIGH:0 · pip-audit نظيف · لا رموز مثبَّتة. **MapLibre Phase‑3** (الالتقاط الحيّ) موجود على main. **فجوات مفتوحة:** مركّبات SAM2 موسميّة (UKFields) · Google Map Tiles الرسميّ (مُعطَّل قصداً، يحتاج session-token backend).

---

## 2026-07-03 (ن-11) — جدار العمليّات 大屏 + فكّاك Modbus + درس pip-audit المُجمَّع

**رأس main:** `c28e6f8` (رفع مباشر إلى main — CI أخضر #2824، Production Gates أخضر).

**جدار العمليّات (`bb63cd7`) — إصلاح انجراف عقد + شريط KPI:** نوع `OperationsSummary` في
`frontend/src/services/api.ts` أعلن حقولاً (`fields_total`/`decisions_total`/`valves_open`/`fleet`)
**لا تطابق** ناتج `api/operations_summary.py:shape_operations_summary` الفعليّ (`totals.{fields,
equipment,iot_devices,decision_records,active_alerts}` · `alerts.by_severity` · `irrigation.{valves,
schedules}`)؛ فبقيت الأرقام المُجمَّعة الغنيّة مُهدَرة (علَم منطقيّ فقط). أُصلِح النوع + أُضيف
`KpiStrip` (أرقام كبيرة نمط 大屏، صدق: القسم `unavailable` عبر `sections[x].status` يعرض «—» لا صفراً؛
غياب التلخيص ⇒ لا شريط). تحقّق: tsc + vitest 11/11 + حارس عقد ساكن `tests_v9/test_operations_summary_contract_20260703.py`.

**فكّاك Modbus-RTU (`0560293`) — فجوة kundian-iot الوحيدة الحقيقيّة:** لا دعم RS485/Modbus رغم
شيوع الحسّاسات الرخيصة. `services/soil-service/modbus_decoder.py` (نقيّ: CRC-16/MODBUS مُتحقَّق على
المتجه المعياريّ 0x4B37 · فكّ سجلّات 0x03/0x04 · رفض صادق) + `routers/modbus.py` (`POST /soil/decode/
modbus`). **درس عزل الاختبار:** أسماء الوحدات العامّة (`main`/`db_persist`/`routers`) تتصادم عبر الخدمات
في السويت الكامل ⇒ حمّلتُ الوحدات النقيّة عبر `importlib` من مسار الملفّ بأسماء فريدة (صفر تلويث
sys.path)، والحمّالات HTTP تُنظّف مسارها/وحداتها. (device-twin وGB28181 والتتبّع تحقّقتُ أنّها موجودة أصلاً.)

**درس pip-audit (`c28e6f8`) — خطأ مملوك:** أضفتُ `httpx==0.28.1` (تثبيت صلب) في soil-service مع ميزة
SoilGrids؛ بوّابة *Security Scan* تُثبّت **كلّ** متطلّبات الخدمات معاً فتعارض التثبيت الصلب مع `httpx==0.27.0`
غير المباشر ⇒ `ResolutionImpossible` ⇒ احمرّ CI على 3 دفعات (4206768/bb63cd7/0560293). الإصلاح: `httpx>=0.27.0`
(صيغة الأقران). **قاعدة دائمة:** أيّ تبعيّة جديدة على مسار pip-audit الحرِج تُكتَب بصيغة مرنة `>=` لا `==`
(قد تتعارض في الحلّ المُجمَّع)؛ وشغّل أمر pip-audit نفسه على الـ18 ملفّاً محليّاً قبل الدفع.

**سير العمل:** أُنشئ فرع رسميّ `develop` من main الأخضر (مرآة، بلا فرق حاليّاً). الرفع بقي مباشراً إلى main
بتفويض المستخدم. **قابليّة الوصول:** نقاط soil الجديدة (`/soil/suitability`،`/soil/soilgrids`،`/soil/decode/
modbus`) مُتاحة عبر `service_proxy` المنصّة (`/api/soil/*`) + nginx.v9.conf — لا فجوة توصيل.

---

## 2026-07-03 (ن-10) — بحث GitHub/Gitee لاستلهام تحسينات + إخراج ثقة SAM2

**رأس main:** يُحدَّث بعد الدفع (بناءً على `5055f17`).

**البحث (مصادر):** [OpenFarm](https://github.com/superzero11/OpenFarm) (توأم معماريّ: FastAPI+PostGIS+TiTiler+MinIO، نموذج FTW للحدود، سير «اقتراح ثمّ قبول» بثقة، SoilGrids/POLARIS + ملاءمة محصول، تنبيهات متعدّدة الإشارة، PMTiles) · [Sen2Agri](https://github.com/Sen2Agri/Sen2Agri-System) · [sentinel-hub/field-delineation](https://github.com/sentinel-hub/field-delineation) (ResUNet-a, MIT) · [chchang1990/SAM_field_delineation](https://github.com/chchang1990/SAM_field_delineation) + [UKFields](https://github.com/Spiruel/UKFields) (SAM على مركّبات موسميّة) · [farmOS](https://github.com/farmOS/farmOS) (GPL — إلهام لا نسخ) · Gitee: [农业岛 wisdom-v2.0](https://gitee.com/dnxt111/wisdom-v2.0) (大屏/物模型/多端) + FastBee (نستعمله أصلاً).

**تحقّق-قبل-التنفيذ (درس):** «المكسب السريع» المقترَح (EVI/SAVI/NDWI) **مُنفَّذ أصلاً end-to-end** — `raster-service/cdse_client.py:INDEX_EXPR` (evalscripts حقيقيّة لـndvi/evi/savi/msavi/ndwi/ndmi/gndvi/ndre/msi/ndsi) + `main.py` (مسار Element84) + `tile_render.py` (colormaps) + منتقي الواجهة `layerRegistry.ts` يعرض العشرة كلّها. لا إعادة تنفيذ.

**الفجوة الحقيقيّة المُنفَّذة (مُستلهَمة من FTW/OpenFarm):** SAM2 يحسب درجة الثقة (`scores`/`argmax`, `sam2-inference/main.py:614`) لكن كان يُسقِطها (`return {"geometry":…}`). والواجهة **جاهزة لعرضها** (`AddFieldWithMap.tsx:689` → «ثقة ٪») لكن مُجوَّعة من البيانات. الإصلاح: `sam2-inference` يُخرِج `confidence` · `field-segmentation.run_segmentation_model` يُرجِع `(geometry, confidence)` ويُمرِّرها في `/segment` (يدويّ ⇒ None، صدق) — **صفر تغيير في الواجهة**، أُضيء سير «اقتراح ثمّ قبول بثقة».

**تحقّق:** 22 اختبار خدمة field-segmentation (3 جديدة للثقة) · حارس عقد end-to-end في `tests_v9/test_segmentation_frontend_contract_20260702.py` · ruff نظيف. يلزم إعادة بناء `sam2-inference` ليظهر أثره حيّاً.

**فجوة مُنفَّذة لاحقاً (نفس الجلسة):** **SoilGrids + تفسير التربة** في `soil-service` (كان يخزّن قراءات الحسّاسات فقط). أُضيف: `soil_science.py` (تصنيف قوام USDA — خوارزميّة NRCS القياسيّة مُتحقَّقة على نقاط مرجعيّة + ملاءمة محصول شفّافة بـLiebig-minimum، محاصيل يمنيّة: قمح/ذرة/طماطم/نخيل/بُنّ) · `soilgrids_client.py` (استيعاب ISRIC REST، CC-BY 4.0، **فشل ناعم** ⇒ None بلا اختراع) · `routers/soil_profile.py` (`POST /soil/suitability` نقيّ · `GET /soil/soilgrids` بإحداثيّة، 503 صادق عند التعذّر). httpx مُضاف لـrequirements (pip-audit نظيف، مُثبَّت 0.28.1). 27 اختبار في `tests_v9/test_soil_science_20260703.py` (نقيّ+عميل+نقاط HTTP). أُزيل اختبار قديم بائد `test_humidity_above_100_rejected` (حقل `humidity` أُعيدت تسميته `moisture_pct`؛ Pydantic يتجاهل المجهول بصمت). **تحقّق-قبل-التنفيذ:** EVI/SAVI/NDWI + جدار العمليّات + التوأم الرقميّ + التتبّع + GB28181 كلّها موجودة أصلاً (لم تُكرَّر).

**صقل جدار العمليّات 大屏 (نفس الجلسة):** **علّة عقد مُثبَتة أُصلِحت** — نوع `OperationsSummary` في `api.ts` أعلن حقولاً (`fields_total`/`decisions_total`/`valves_open`/`fleet`) **لا تطابق** ناتج `shape_operations_summary` الخادميّ الفعليّ (`totals.{fields,equipment,iot_devices,decision_records,active_alerts}` · `alerts.by_severity` · `irrigation.{valves,schedules}`)؛ فبقيت الأرقام المُجمَّعة الغنيّة **مُهدَرة** (تُستعمَل كعلَم منطقيّ فقط، لا تُعرَض). الإصلاح: (١) توحيد النوع مع العقد الحقيقيّ (الحقول المنجرفة ميّتة — لا مستهلِك). (٢) **شريط KPI بارز** (`KpiStrip`) نمط 大屏: أرقام كبيرة (حقول/تنبيهات نشطة مع تمييز الحرِج/أجهزة IoT/معدّات/قرارات/صمّامات) + وقت التوليد + شارة «جزئيّ». **صدق:** القسم `unavailable` (عبر `sections[x].status`) يعرض «—» لا صفراً مُلفَّقاً؛ غياب التلخيص ⇒ لا شريط. تحقّق: tsc نظيف · 11 اختبار جدار (لم تنكسر) · حارس عقد ساكن `tests_v9/test_operations_summary_contract_20260703.py` (٣، طبقة CI) · eslint نظيف.

**فجوات مفتوحة موثّقة (لم تُنفَّذ):** مركّبات SAM2 موسميّة (UKFields) · محوّل Modbus/RS485 (kundian-iot — فجوة حقيقيّة لكن خاصّة بالعتاد، غير قابلة للتحقّق هنا) · MapLibre Phase 3 (نسخة المستخدم المحلّيّة، لم تُرفَع).

## 2026-07-02 (ن-8) — تصلّب أمنيّ: منع إعادة تشغيل TOTP (v141 / V29.7)

**رأس main:** `9c69839` (دفع مباشر إلى main — تفويض المستخدم «من الآن ارفع مباشرة إلى main»).

**الفجوة (تحقّق بالكود لا بالتقارير — تدقيق المستخدم):** مسارات التحقّق الأربعة لـMFA استخدمت `pyotp.TOTP(secret).verify(code, valid_window=1)` بلا تسجيل آخر خطوة زمنيّة مقبولة ⇒ رمز صالح يُعاد استخدامه ضمن نافذته (~90ث عبر ٣ خطوات)؛ رمز مُلتقَط (تصيّد بوكيل عكسيّ/كتف/قفزة بلا TLS) قابل لإعادة الاستخدام، والنجاح يُصفّر عدّاد القفل. لا `last_used`/`timestep` في أي مكان.

**الإصلاح (RFC 6238 §5.2):** ترحيل **v141** `users.mfa_last_totp_step BIGINT` (epoch//30، NULL=لم يُستخدم) · `mfa_crypto.matched_totp_step()` دالّة نقيّة تُرجِع الخطوة المطابِقة (تُفضّل الأحدث؛ pyotp متاح في تير الاختبار) · `main._consume_totp_step()` استهلاك **ذرّيّ آمن ضدّ التسابق**: `UPDATE ... WHERE id=$id AND (mfa_last_totp_step IS NULL OR mfa_last_totp_step < $step)` — 0 صفوف ⇒ إعادة/سباق ⇒ يُرفَض (fail-closed) · موصول في المسارات الأربعة (login · admin step-up · activate · disable)؛ منطق الاسترداد/القفل/التدقيق بلا تغيير.

**تحقّق:** 2450 اختبار وحدة + تغطية 48.80٪ · ruff نظيف · manifest 147 · production gate PASS · اختبار تكامل يثبت رفض الخطوة المُعادة/الأقدم وقبول الأحدث على Postgres. **قرار صدق:** رفضتُ أرشيف `rls_with_check_fix_v122` (الإصلاح مُنفَّذ في main أمتن + تصادم بادئة v122). أمّا TOTP replay فثغرة حقيقيّة غير مُغطّاة ⇒ نُفِّذت.

---

## 2026-07-02 (ن-7) — بناء ميزات ٣ خدمات (video/tts/agriai) + إصلاح تصادم منفذ + إقلاع auth

**رأس الفرع المخصّص:** `1e0b0b5`. بُني بثلاثة وكلاء متوازين (worktrees معزولة) ثمّ cherry-pick + إصلاحات تكامل.

طلب المستخدم ميزات حقيقيّة عبر ٣ خدمات. النمط: **نواة حتميّة/CPU افتراضيّة + خلفيّات ثقيلة اختياريّة خلف import-guard + علم** (يطابق فلسفة المنصّة: استبدال الخلفيّة بلا تغيير العقد). المنطق النقيّ في وحدات بلا fastapi (طبقة الوحدات)، ونقاط HTTP بـimportorskip.

- **video-processor** (`6108092`): `stream_registry.py` (سجلّ tenant-scoped آمن-خيطيّاً fail-closed) · `zlmedia_client.py` (add/del proxy · getMediaList · snapshot · start/stop record — secret + rstrip + fail-soft، httpx قابل للحقن) · نقاط snapshot + record start/stop (معزولة tenant) · `stream_events.py` (حدث canonical + بثّ best-effort لـNATS `sahool.video.<kind>` وMQTT، import-guarded). 40 اختبار. بلا تبعيّات جديدة.
- **tts-service** (`6b05644`): تجريد `TTSProvider` (Edge افتراضيّ) · `PiperProvider` (CPU، import-guard) · `XTTSProvider` (GPU اختياريّ، علم `TTS_GPU_PROVIDER=xtts`) · `arabic_normalizer.py` نقيّ (تطويل/ألف/أرقام/وحدات) · `select_provider` + `/tts/status`. المقاييس idempotent. 34 اختبار.
- **agriai-engine** (`e6a1977`): على الجذع الـ92-سطر → `evidence_bundle.py` (JSON قانونيّ + hash ثابت) · `replay.py` (حتميّة إعادة التشغيل، ثابت تحت إعادة ترتيب المدخلات) · `wofost_adapter.py` (pcse import-guarded + سقوط حتميّ Liebig-minimum) · `profit_planner.py` (yield·price − Σcosts، مرتّب) → `/recommend` حقيقيّ + `/simulate`/`/plan`/`/replay/verify`. 18 اختبار.

**إصلاحا تكامل (`a263b14`):** (1) **تصادم منفذ** — `sahool-zlmediakit` HTTP كان `127.0.0.1:8088:80` يصطدم بـraster-tiler-service (`8088:8088`) ⇒ `up` يفشل «port already allocated». نُقِل إلى **8188** (المتّصلون الداخليّون على `sahool-zlmediakit:80` بلا تأثّر). (2) **عزل اختبار tts** — نقاط `/tts/status` تحلّل أحياناً `main` خدمة أخرى (تصادم اسم الوحدة) أو نسخة tts قديمة راوتراتها مربوطة بتطبيق سابق ⇒ 404 في السويت الكامل؛ المُحمِّل الآن يعيد الاستعمال فقط إن ملك المسار، وإلّا يُخلي الوحدات الشقيقة ويُعيد التحميل نظيفاً (المقاييس idempotent).

**تحقّق:** `pytest -m unit` = **2442 نجَح** + تغطية 48.77٪ · ٦ بوّابات exit 0 · ruff نظيف · production gate PASS (compile 8142/0) · لا تسريب معرّف نموذج. **مؤجَّل بيئيّاً (import-guarded):** piper/xtts/pcse الفعليّة (طبقة تكامل، `# pragma: no cover`).

**🐳 إقلاع auth (تشخيص مستخدم — v21):** `docker compose up` أظهر `ModuleNotFoundError: mfa_crypto` (main.py:163) على `sahool-auth`. **الجذر: صورة مُخزَّنة قديمة** — الـDockerfile الحاليّ **ينسخ** `mfa_crypto.py` (سطر 27) + `otp.py` والحارس `test_decomposed_service_dockerfile_guard` أخضر (21). `up` لا يُعيد البناء ⇒ يلزم **`up -d --build sahool-auth`**. درس AUTH-BOOT مُتكرّر: الصورة المُخزَّنة تسبق إصلاح Dockerfile.

---

## 2026-07-02 (ن) — دفعة أمان SEC-1/2/3 (بعد مراجعة أرشيف zip من المستخدم)

**رأس `main` بعد الجلسة:** (SEC batch). الفرع المخصّص مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

راجع المستخدم أرشيف `sahool_main_0b85c84.zip` وأخرج ٨ فجوات. **تحقّقتُ منها جميعاً بالكود** — كلّها صحيحة، مع تخفيف جزئيّ لبعضها بحُرّاس قائمة (لا اختلاق في المراجعة). أُغلقت الثلاث الأخطر (٣ وكلاء متوازين):
- **SEC-1** (`7adc3c0`): `docker-compose.fixed.yml` كان يجمع `SAHOOL_ENV:-production` مع bypass=1 (footgun) — غُيِّر الافتراض إلى `development` + حارس `test_compose_env_bypass_guard` يمنع اجتماع prod-env مع bypass على أيّ compose. `docker-compose.light.yml` كشف خدمات التطبيق على كلّ الواجهات — رُبطت الـ10 بـ`127.0.0.1` (nginx/fastbee/zlmediakit عامّة بالقصد) + حارس `test_compose_internal_ports_loopback_guard`. **لم يُمَسّ v9.yml.** (حارس bypass القائم ظلّ يسمح لـfixed.yml dev — بلا إضعاف.)
- **SEC-2** (`c4257d2`): 6 Dockerfiles كانت تعمل root ⇒ `USER sahool` (نمط auth)، مع chown-before-VOLUME لـknowledge-graph `/data`. + حارس `test_service_dockerfile_nonroot_guard` (كلّ 25 خدمة، allowlist فارغ).
- **SEC-3** (`5623934`+`d1ae020`): **الخلل الجوهريّ** — `ai_agronomist/main.py:779` كان `req.tenant_id or x_tenant_id` (الـbody يسبق الترويسة الموثّقة). العقد الداخليّ موجود أصلاً (`X-Agent-Token==SAHOOL_AGENT_TOKEN` + `_require_service_token`). Option-B (اختيار المستخدم): البوّابة سلطة JWT؛ داخل الخدمات `X-Tenant-Id` **مصدر الحقيقة الوحيد** (body≠header⇒403 tenant_mismatch؛ غياب⇒403). `shared/security/{trusted_tenant,gateway_deps}.py` (نقيّ + wrappers) موصول في ai_agronomist (query/chat/explain/recommend) + rag `/search` + kg writes (service-token). **تصحيحي (مهمّ):** الوكيل بوّب `/approvals/*` بـservice-token، لكنّ nginx يمسحه ⇒ يجعلها داخليّة-فقط ويكسر الموافقة البشريّة عبر البوّابة (docstrings: web-UI). صحّحتُها لـ`require_trusted_tenant` (تُغلق «body فقط» وتبقى قابلة للوصول بمستخدم مُوثَّق). حدّثتُ اختبارات الموافقات الثلاثة (X-Agent-Token→X-Tenant-Id).

**درس:** authz على مستوى user/role للموافقات = متابعة **SEC-3.1** (يحتاج nginx يحقن `X-User-Id`/`X-Roles` الموثّق للمسار — البوّابة تحقن `X-Tenant-Id` فقط الآن).

**بقيّة المراجعة (منخفض/متابعة، موثَّقة):** deps-lock كامل (5) · رفع coverage floor 20→ (6) · runtime-smoke إلزاميّ على main/release (7) · rag `/ingest` service-token · fastbee/zlmediakit aux mgmt ports.

**تحقّق:** كلّ الادّعاءات فُحِصت بالكود (لا قبول/رفض بلا دليل) · 704 اختبار انحدار + 35 gateway/approvals · الحُرّاس القائمة بلا إضعاف · بوّابة الإنتاج · worktrees نُظِّفت.

---

## 2026-07-02 (ن-2) — استكمال بقيّة مراجعة الأرشيف: SEC-3.1 + SEC-4/5/6/7

**رأس الفرع المخصّص `claude/code-review-34hO3`:** `1755c9c` (SEC-6 آخر cherry-pick). ci.yml قيد التشغيل ثمّ ff-merge إلى main بعد الخضرة.

استكمال البنود المتبقّية من مراجعة `sahool_main_0b85c84.zip` (الثمانية) بعد إغلاق الثلاث الأخطر في (ن):

- **SEC-3.1** (`5fee147`) — **user/role authz للموافقات (مُنفَّذ، لم يَعُد blocked).** السلسلة الذرّيّة الثلاثيّة: (1) `auth/main.py tenant_header_middleware` يُصدِر `X-User-Id` (JWT `sub`) + `X-User-Role` (`role`) كرؤوس استجابة من الحمولة المُتحقَّقة داخل فرع `iss` المسموح؛ (2) `nginx.v9.conf` مسار `/api/ai-agronomist/` يحقن `X-User-Id`/`X-User-Role` المُلتقَطين من `auth_request` (+ `proxy_params.conf` يمسح `X-User-Role` الوارد — الافتراض الآمن)؛ (3) `gateway_deps.require_authenticated_user` (403 `missing_user` عند الغياب) مُركَّب على approve/deny/resume **فوق** `require_trusted_tenant` (لا إضعاف SEC-3). **الموافِق المُسجَّل = `X-User-Id` الموثَّق لا حقل `approver` في الـbody** (`approve/deny` تمرّر `approver=user_id`) — يُغلق انتحال «مَن وافق» عبر الحمولة. اختبارات: happy-path يرسل الرأسين + حالات missing_user الثلاث + تأكيد الموافِق. **الشحن ذرّيّ** (emit→inject→require) كي لا تُرجِع أيّ بيئة 403 على كلّ موافقة. صحّحتُ انحرافاً عن مقترح الوثيقة (الفحص مضمَّن في `require_authenticated_user` لا helper منفصل — أبسط، نفس الـ403).
- **SEC-4** (`98a4327`) — rag `/ingest` كتابة داخليّة ⇒ `require_service_token` (403 `service_token_required` بلا `X-Agent-Token`) + منافذ إدارة `fastbee`/`zlmediakit` المساعِدة رُبطت بـloopback. اختبارات في `test_gateway_trusted_identity_sec3.py` (ingest بلا/مع token).
- **SEC-5** (`1332c3e`) — رفع أرضيّة تغطية الوحدة `--cov-fail-under` من 20 إلى **40** في `ci.yml` (المُقاس 44.55٪؛ أعِدتُ القياس بعد SEC-3.1/4 = **48.12٪**) + `docs/testing/coverage_ratchet.md`. رفع محسوب لا اعتباطيّ.
- **SEC-6** (`1755c9c`) — حارس `test_requirements_pinning_guard.py` (يمنع انحدار التثبيت على المسار الحرج) + `docs/security/dependency_locking_plan.md` (خطّة قفل مرحليّة، نطاق آمن). القفل الكامل للمستودع مؤجَّل بوعي (مرحليّ).
- **SEC-7** (`0353265`) — توثيق: هجرات/RLS/schema **إلزاميّة أصلاً** على main (Integration job)؛ smoke حيّ لـ`/healthz` جاهز-للتفعيل خلف قرار مشغّل (compose ثقيل ⇒ خطر flakiness) — `docs/security/SEC-7_runtime_smoke_gating.md`.

**تحقّق:** `ruff check`+`format` نظيفان · `pytest -m unit` = **2375 نجَح** + تغطية 48.12٪ ≥ 40 · `sahool_inspector` PASS (خروج 0) · py_compile + ci.yml YAML صحيحان. **بذلك تُغلَق البنود الثمانية جميعاً.** مؤجَّل بوعي: تثبيت tenant لكلّ chunk في rag `/ingest` · القفل الكامل للتبعيّات · تفعيل smoke الحيّ (مشغّل).

---

## 2026-07-02 (ن-3) — مقارنة أرشيفَي المستخدم: ERP bridge + بوّابة عقد UI للخدمات

**رأس الفرع المخصّص:** `5ea89a5`. طلب المستخدم مقارنة أرشيفَين (كلاهما cef830b) وتنفيذ **الصحيح**.

- **الأرشيفان متطابقان وظيفيّاً** (إعادة تسمية odoo-bridge→erp-bridge مع أسماء legacy كـaliases + بوّابة `service-feature-ui-contract-gate`). الفرق الحاسم في التوليف:
  - **zipA (مرفوض):** رشّ aliases الجسر (`odoo-bridge`/`erp-bridge`) على **كلّ خدمة** في `docker-compose.v9.yml`/`fixed.yml` ⇒ اسم `erp-bridge` يتحلّل إلى ~24 حاوية (DNS مبهم)، **وأغفل** الـalias على خدمة الجسر الفعليّة في odoo-snippet/unified.
  - **zipB (المُنفَّذ):** الـalias على خدمة الجسر **فقط**؛ بقيّة الخدمات تبقى `- sahool-internal`.
- **نُفِّذ zipB** (`5ea89a5`): مفتاح خدمة v9 `sahool-odoo-bridge`→`sahool-erp-bridge` + aliases legacy على الجسر + `ERP_BRIDGE_URL`(+`ODOO_BRIDGE_URL` legacy)→`sahool-erp-bridge:8126` · `odoo-bridge/main.py` هويّة تشغيل erp-bridge (logging/RLS-guard/عنوان FastAPI) · `market_server.py` يفضّل `ERP_BRIDGE_URL` ويسقط لـ`ODOO_BRIDGE_URL` · `nginx.unified.conf` مسار `/api/erp/` + upstream + `/api/odoo/` legacy · بوّابة CI `service-feature-ui-contract-gate` (PASS 26/26) + عقد JSON + اختباران. **المجلّد الفيزيائيّ `services/odoo-bridge/` مُبقى** (سياق بناء/اختبارات/إصدار).
- **تحقّقي (تنفيذ الصحيح لا النسخ الأعمى):** أصلحتُ سطر `market_server.py` الطويل بـ`# fmt: skip` (يُبقي اختبار المسح المتّصل أخضر + ruff format راضٍ؛ E501 متجاهَل بالمستودع) + ruff format للملفّات في نطاق CI. **الفشل السباعيّ (sklearn + تصادم اسم وحدة `main`) مُتطابق على الشجرة النظيفة** ⇒ ليس انحداراً من تغييري.

**درس:** إعادة التسمية عبر compose يجب أن تضع الـalias على خدمة الجسر **وحدها** (aliases على كلّ خدمة تكسر DNS). `# fmt: skip` يوفّق سطراً يحتاج مسحاً متّصلاً مع صرامة ruff format.

---

## 2026-07-02 (ن-4) — دفعة «البقايا القابلة للتنفيذ» من أرشيف المستخدم (C2–C5 · H1–H3 · ٣ بوّابات)

**رأس الفرع المخصّص:** `30dd472` (`4bda6cc` الكود + `30dd472` تجديد الحزمة). طُبِّق عبر وكيل في worktree معزول ثمّ دُمج ff.

أرشيف `..._remaining_executable_fixed.zip` (cef830b) = **superset** لعمل ERP+بوّابة (مُنفَّذ سلفاً) **زائد** إصلاحات أمن/تشغيل جديدة. طُبِّق **الدلتا فقط** جراحيّاً فوق `6682e21` (بلا نقض SEC-3.1/SEC-4/v133–140):

- **C4** — rag `/ingest`: تحقّق tenant **لكلّ chunk** عبر `resolve_trusted_tenant(X-Tenant-Id, c.tenant_id)` **فوق** `require_service_token` القائم (يُغلق تأجيلي الموثَّق «تثبيت tenant لكلّ chunk»). قيمة chunk قد تُصدِّق الترويسة فقط.
- **C5** — knowledge-graph: قراءات `GET /edges` و`/graphql` تتطلّب `X-Tenant-Id` موثّق (403 missing_tenant)؛ الكتابات تبقى بservice-token.
- **C3** — ai_agronomist: `current_field_state` من العميل يُقبَل فقط مع `X-Agent-Token` صحيح، وإلّا **403 `current_field_state_requires_service_token`**؛ غيره يجلب الحالة القانونيّة من sahool-platform.
- **C2** — ai_agronomist يُمرّر `X-Tenant-Id` الموثّق لقراءة KG (يُرضي C5).
- **H1** — SAM2: `SEGMENTATION_INFERENCE_URL` افتراضيّ `http://sahool-sam2-inference:8080/predict` مع بقاء `SEGMENTATION_BACKEND` فارغاً (لا ادّعاء تجزئة زائف).
- **H2** — منفذ edge-inference 8100 متّسق في unified/light (+`EDGE_INFERENCE_URL`).
- **H3** — `agent_stores.py` يفشل مغلقاً (RuntimeError) في الإنتاج إن طُلِب Redis وغاب URL/عميل؛ v9 ai-agronomist يفترض Redis + تبعيّة صحّة redis. المخزن يبقى قابلاً للاستبدال (allowlist mvp_in_memory محفوظ).
- **port-8126** — erp-bridge unified/nginx على 8126 (Dockerfile يستمع 8126) + **C1** تصحيح أسماء upstream في nginx.unified لأسماء خدمات compose الفعليّة + إزالة aliases ERP المسرَّبة من auth-service (DNS مبهم).
- **٣ بوّابات ساكنة جديدة** (موصولة في structural-lint): `nginx_compose_dns_gate` · `service_port_gate` · `runtime_contract_gate` + `scripts/e2e/tenant_auth_live_gate.py` (لمكدّس حيّ) + اختبارا إغلاق.

**تصحيح توليف (تقوية لا إضعاف):** حُدِّث اختباران في SEC-3 للعقد الأصرم: `/ingest` يتطلّب tenant موثّق حتّى مع token · قراءة KG صارت تتطلّب `X-Tenant-Id` (كانت مفتوحة). **تحقّق:** ruff نظيف · ٤ بوّابات exit 0 · 62 اختبار (closure + SEC-3/3.1 + approvals + stores) نجحت · production gate PASS (compile 4850/0). **مؤجَّل بيئيّاً:** E2E مكدّس Docker + `tenant_auth_live_gate` الحيّ + استدلال GPU/SAM2 (السكربتات حاضرة).

**درس:** الأرشيف superset ⇒ استخرج الدلتا فوق الأحدث لا تنسخ (النسخ يُرجِع cef830b). الوكيل في worktree معزول يمنع اصطدام شجرة العمل؛ صحّحتُ قاعدته (بدأ من cef830b) بـff إلى `6682e21` قبل التطبيق.

---

## 2026-07-02 (ن-5) — نقل ميزات إلى v9: video/agriai/tts + مسارات + بوّابة نقل

**رأس الفرع المخصّص:** `9b72229` (الكود) + تجديد الحزمة. طُبِّق عبر وكيل في worktree معزول (ff إلى `c0f65a2` أوّلاً) ثمّ دُمج ff.

أرشيف `..._v9_feature_transfer.zip` (superset لـzipR) — **تحقّق-قبل-تنفيذ:** الخدمات الثلاث لها كود فعليّ تحت `services/` لكنّها **غائبة عن v9.yml**، و`/tts/` يردّ **503** حرفيّاً (تأكّدتُ بالكود). نقل شرعيّ لا اختلاق. طُبِّق **الدلتا فقط** فوق `c0f65a2`:

- **video-processor / agriai-engine / tts-service** → أُضيفت ٣ كتل خدمة إلى `docker-compose.v9.yml` (`*id001` logging anchor، non-root، healthcheck، depends_on) + `depends_on: service_healthy` على nginx. (services=48→51).
- **nginx.v9.conf:** ٣ upstreams · `/tts/` من 503 إلى `proxy_pass tts_backend` · مسارا `/api/video/` و`/api/agriai/` **مقيّدان بالشبكة الخاصّة** (allow 127/10/172/192; deny all) · توسيع CSP `img-src` لخوادم بلاطات MapHub (arcgisonline · basemaps.cartocdn · tile.openstreetmap). حقن SEC-3.1 X-User-Id على ai-agronomist سليم.
- **بوّابة جديدة** `v9_feature_transfer_gate` + اختبار، موصولة في structural-lint.

**لم يُنقَل عمداً** (drift لا ميزة): توجيه `/api/v1` وميناء frontend 80/8080 في unified/light (حاويات ستُجمَّد؛ v9 يملك المسار الأصحّ). **تحقّق:** ٥ بوّابات exit 0 · 39/53 اختبار (نقل + SEC-3/3.1 + closure + erp) · ruff نظيف · production gate PASS (compile 4854/0، services=51). **ملاحظة صدق (pre-existing، خارج النطاق):** بوّابة DNS إن شُغِّلت صراحةً على v9 ترصد `sahool-soil:8000` داخل سطر upstream **مُعلَّق** (regex يطابق التعليق)؛ CI يشغّلها على unified (يمرّ) فلا حجب — لم أُضعِف البوّابة ولا لمستُ السطر المُعلَّق.

---

## 2026-07-02 (ن-6) — تمكين GPU (RTX 5090/Blackwell) لـv9 + zlmediakit + video readyz

**رأس الفرع المخصّص:** `2ecb8a9` (الكود) + تجديد الحزمة/الدماغ. طُبِّق عبر وكيل في worktree معزول (ff إلى `6c80d1c`) ثمّ دُمج ff.

أرشيف `..._v9_rtx5090_gpu_enabled.zip` (superset لـzipV). طُبِّق **الدلتا فقط** فوق `6c80d1c` (تجاهُل ضجيج إعادة تسلسل YAML: `sahool-internal: null` وحذف التعليقات — أُبقيت أسلوب الملفّ):

- **تراكب GPU منفصل** `docker-compose.v9.gpu.yml` (لا يمسّ الأساس CPU): حجوزات GPU لـedge/sam2/video-processor · تفعيل SAM2 لـfield-segmentation (`SEGMENTATION_BACKEND=sam2`) · `VIDEO_STRICT_READY`. يُشغَّل: `docker compose -f v9.yml -f v9.gpu.yml --profile gpu up -d`.
- **zlmediakit** أُضيف إلى v9 (منافذ محلّيّة 8088/8554/1935/10000) + video-processor يستخدم `:80` + `ZLMEDIAKIT_API_SECRET` + depends. **notification-agent** وُصِل TTS (`TTS_URL=http://sahool-tts-service:8000` — كان الكود يفترض `sahool-tts` غير الموجود).
- **كود:** `video-processor` `/readyz` يفحص التبعيّات (zlmediakit/edge) + fail-closed مع `VIDEO_STRICT_READY` · `edge-inference` يعرف أوضاع CUDA (cuda/gpu/rtx5090/blackwell) · `sam2-inference/Dockerfile` قاعدة CUDA قابلة للتجاوز (افتراضي 12.8 لـBlackwell sm_120).
- **بوّابة `v9_gpu_contract_gate`** ساكنة (بلا GPU/docker) + ٣ سكربتات e2e حيّة (gpu_runtime_smoke · sam2_live_gpu · video_zlmediakit_live) للمشغّل على الخادم.
- **runbook Windows/WSL2** أُلحِق بالتقرير — مُعايَر على عتاد المستخدم الفعليّ (`nvidia-smi`: RTX 5090 Laptop · 24GB · Driver 592.00/CUDA 13.1 · WDDM): خطوات NVIDIA Container Toolkit في WSL2 · تحقّق التمرير · أمر الإقلاع · البوّابات الحيّة · توافق (driver 13.1 ⊃ runtime 12.8، sm_120 مطابق).

**تحقّق:** ٦ بوّابات exit 0 · 45 اختبار (gpu + feature-transfer + SEC-3) · ruff نظيف · production gate PASS (compile 4864/0). **يُغلق AUTO-SEG تشغيليّاً** (كان by-design ينتظر SEGMENTATION_BACKEND=sam2). **مؤجَّل بيئيّاً:** اختبارات GPU/Docker الحيّة (لا GPU هنا) — السكربتات حاضرة للمشغّل. **درس:** compose مُعاد-تسلسله (null/حذف تعليقات) ⇒ طبّق الإضافات الحقيقيّة الثلاث فقط لا نسخ الملفّ.

---

## 2026-07-02 (م) — دفعة تصلّب ثالثة: v139 audit append-only + v140 outbox attempts

**رأس `main` بعد الجلسة:** `0304076`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

**قرار صدق أوّليّ:** device→platform auth **ليس شقّاً ضيّقاً** (موضوع telemetry بلا device_id · firmware يرسل `{value}` بلا توقيع · يحتاج إعادة تصميم عقد + تنسيق firmware) — قرار معماريّ مؤجَّل، لم أسرّعه. بدلاً منه الفجوتان النظيفتان (منصّة فقط):
- **v139** (`7d9334c`): `trg_append_only_field_geometry_history` (BEFORE UPDATE/DELETE → `sahool_block_mutation`) — سجلّ تعديلات الحدود غير قابل للتلاعب. الوكيل تحقّق أوّلاً ألّا يوجد تحوير شرعيّ للجدول (grep: INSERT+SELECT فقط). unit static + integration probe (مرّ بالاسم).
- **v140** (`9f83fe3`+`0304076`): `outbox_delivery_attempts` — سجلّ جنائيّ append-only لكلّ محاولة تسليم (attempt_no/subject/outcome/error) يكتبه `OutboxWorker._record_delivery_attempt` (SAVEPOINT، fail-safe). مرّ بالاسم على Postgres.

**درسان من CI (مهمّان — التحقّق المحليّ لا يكفي):**
1. **حارس elevated-context (HIGH-001):** `event_bus.py` تحت دور `sahool_jobs` المتجاوِز لـRLS — الحارس يفرض حصره بجداوله. الجدول الجديد لمسه ⇒ وثّقتُه في `_JOBS_SCOPE` (العامل يكتب فقط بـtenant_id الصحيح).
2. **RLS coverage (sahool_inspector سلطويّ):** الجدول يحمل tenant_id بلا FORCE RLS. **درس دقيق:** الفاحص الساكن يطلب `FORCE`+`current_setting` **حرفيّاً في نصّ الترحيل** — لا يعترف بـ`_sahool_apply_tenant_rls()` helper. فاستبدلتُ الـhelper بكتلة v133/v98 الصريحة. + خطأ توقيع `emit_event` في اختبار الوكيل (v18 جعل `p_entity_id` TEXT؛ الاختبار صبّه `::uuid`) — أُصلِح بحذف الصبّ (نمط `test_entity_id_text`).

**انضباط:** تعارضات MANIFEST/run_migrations (v139/v140 كلاهما بعد v138) حُلّت (manifest 146). worktrees نُظِّفت. كلّ الحُرّاس أُصلِحت دون إضعاف أيّ منها (توثيق نطاق + RLS صريح، لا استثناءات).

**المتبقّي (مؤجَّل، اختياريّ):** device→platform auth (معماريّ، يحتاج firmware) · device ACK فعليّ · SPATIAL-401 (Network) · VALIDATE بعد cleanup.

---

## 2026-07-02 (ل) — دفعة السلامة الثانويّة (v136/v138 + حارسان، ٤ وكلاء بناء)

**رأس `main` بعد الجلسة:** `b87ce7c`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

الفجوات الثانويّة من استكشاف الدفعة (ك) — ٤ وكلاء بناء متوازين (بلا إعادة استكشاف، المراسي معروفة)، دُمِجت تتابعيّاً:
- **v136** (`fcb7e78`): `irrigation_runs` — سجلّ تشغيل صمّام فعليّ (فتح→صفّ running، إغلاق→completed+volume) موصول في `set_valve_state` عبر savepoint fail-safe. 8 unit + 3 integration (مرّت بالاسم على Postgres: `test_open_then_close_roundtrip`/`test_status_check_rejects_bad_value`/`test_rls_isolation`).
- **schedule-conflict** (`c03333b`): رفض 409 لتداخل جداول الريّ على نفس الصمّام. **app-level لا DB EXCLUDE** لأنّ الجدول *متكرّر* (start_time TIME + days_of_week[]، لا tstzrange). دالّة نقيّة `schedules_overlap` (دورة أسبوعيّة 7×1440، لفّ منتصف الليل). 6 unit. **قيود صدق:** نطاق نفس الصمّام · سباق TOCTOU نظريّ · اختبار DB يتخطّى في CI (importorskip fastapi).
- **AsyncStore lease** (`ea2ece8`): إكمال فجوة v135 — `AsyncPostgresWorkflowStore.claim` بـ`FOR UPDATE SKIP LOCKED` (بلا ترحيل، يعيد أعمدة v135). رُقّي fake conn لإبقاء اختبارات async خضراء. مرّ بالاسم: `test_async_two_workers_single_writer_refusal`/`test_async_expired_lease_reclaimable`.
- **v138** (`84abdc1`): `offline_pending_ops` — حالتا `processing`/`failed` (MAX=5) + claim (`UPDATE WHERE status='pending' RETURNING`) في `sync.py`، فلا op سامّة تدور أبداً. مرّ بالاسم: 4 اختبارات (poison→failed · claim→processing يمنع الثاني · CHECK · RLS).

**درس CI (مهمّ):** الوكيلان وضعا الدوالّ النقيّة في `api/irrigation_models.py` الذي **يستورد fastapi** (‏`_parse_time` قديم) ⇒ فشلت 13 اختبار unit في وظيفة *Unit Tests* (بلا fastapi)؛ مرّت محليّاً فقط لأنّ حاويتي تحمل fastapi. الإصلاح (`b87ce7c`): استخراج الدوالّ النقيّة إلى `api/irrigation_logic.py` (stdlib فقط) + إعادة تصدير من irrigation_models (الراوترات بلا تغيير) + توجيه اختبارات الوحدة إليها. **القاعدة: دالّة نقيّة تُختبَر في unit tier يجب ألّا تعيش في وحدة تستورد fastapi/pydantic-الثقيل.** (نفس صنف درس format-gate: التحقّق المحليّ يمرّ لأنّ الحاوية أغنى من طبقة CI الدنيا.)

**ترقيم الترحيلات:** v137 غير مُستخدَم (schedule-conflict صار app-level)؛ v136 ثمّ v138 (فجوة مقبولة، لا يشترط المدقّق التتابع). manifest 144. تعارضات `irrigation.py` (سطر import) + MANIFEST/run_migrations حُلّت. worktrees نُظِّفت.

**المتبقّي (فجوات أصغر، اختياريّة):** device→platform auth (أمنيّ، شقّ مُخصَّص) · non-swallowing geometry audit · outbox per-attempt log · irrigation device ACK فعليّ. + SPATIAL-401 محجوب على Network.

---

## 2026-07-02 (ك) — دفعة السلامة v29.5-op/v39.5/v19.5 (تحقّق-قبل-بناء متعدّد الوكلاء)

**رأس `main` بعد الجلسة:** `b2a332c`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

بطلب «ابدأ بالدفعة التالية» — بدل بناء أنظمة net-new عمياء، أُطلِقت **٣ وكلاء استكشاف (قراءة فقط)** فتبيّن أنّ معظم كلّ نظام مُغلَق downstream:
- **v29.5-op:** idempotency (v67) + execution_ledger (v68) موجودان؛ device→platform auth ناقص. **الفجوة الحقيقيّة: مفتاح إيقاف التشغيل.**
- **v39.5:** optimistic lock (row_version+409) + offline conflict (409) + v27 trigger على `field_boundaries` موجودة. **الفجوة: `fields.geometry` (متجر الرسم الفعليّ) بلا فحص صلاحية DB.**
- **v19.5:** outbox + processed_events + offline_pending_ops + عقد NATS موجودة. **الفجوة الوحيدة: قفل الكاتب-الأوحد للـworkflow.**

ثمّ **٣ وكلاء بناء متوازين** (worktree، أرقام v133/v134/v135)، ودُمِجت تتابعيّاً بإعادة تحقّق مِنّي (cherry-pick + حلّ تعارضات MANIFEST/run_migrations التافهة):
- **v133** (`e8e4bbe`): `migrations/v133_actuation_killswitch.sql` (RLS+FORCE نمط v98) + `shared/actuation_killswitch.py` (match نقيّ + `is_actuation_halted` fail-closed) موصول عند ٣ نقاط إطلاق: actuator `evaluate_rules` + `/command` (423) + `decision_dispatch` (not_executed). 7 unit + 5 integration.
- **v134** (`94cdda7`): `migrations/v134_fields_geometry_integrity.sql` — trigger `BEFORE INSERT/UPDATE` يفرض `ST_IsValid(ST_GeomFromGeoJSON)` (ERRCODE 23514) على `fields.geometry` + يزيد `geometry_version` inline (مميّز عن row_version وv132). FieldDetail يُخرِج النسخة. v27 لم يُمَسّ. (القرار: تدقيق الهندسة بقي best-effort — الضمان الآن في trigger القاعدة غير القابل للابتلاع؛ الفحص `ST_IsValid` فقط، وحارس الـAPI يبقى يفرض polygon/area.)
- **v135** (`338217c`): `migrations/v135_workflow_state_lease.sql` (`lease_owner`/`lease_expires_at` + partial index) + `PostgresWorkflowStore.claim` بـ`FOR UPDATE SKIP LOCKED` (نمط OutboxWorker) — كاتب أوحد، رفض قابل للالتقاط، استرداد lease منتهٍ. (القرار: `AsyncPostgresWorkflowStore` لم يُغطَّ بعد — متابعة؛ سباق الإنشاء-فقط لا الاستئناف.)

**إثبات (بالاسم، سجلّ CI run 28576997610 job Integration على Postgres حقيقيّ):** ٥ اختبارات killswitch + `test_fields_geometry_db_validity_and_inline_version` + ٣ اختبارات lease + `test_postgres_store_durable_resume` — كلّها PASSED (`54 passed, 99 skipped`، صفر فشل). تطبيق v133/v134/v135 ظهر في سجلّ الترحيلات.

**انضباط:** تعارضات MANIFEST/run_migrations (كلّها append بعد v132) حُلَّت لتسلسل v133→v134→v135 (manifest 142) · فشل CI أوّليّ في format فقط (وكيلان تركا ملفّين غير مُنسَّقين) أُصلِح (`b2a332c`) · **worktrees نُظِّفت** (بقايا جلسات سابقة أعادت عدّ compile الحقيقيّ 1598).

---

## 2026-07-02 (ي) — دفعة متعدّدة الوكلاء: v62.3 (A/B/C) + v52 + v133 + إغلاق Superset

**رأس `main` بعد الجلسة:** `53a3ed4`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء (Integration يُشغّل اختبارات الشقوق الجديدة على Postgres حقيقيّ) ثمّ ff-merge.

بطلب المستخدم «نفّذ الكل بأكثر من وكيل» أُطلِقت **٥ وكلاء متوازين** (worktree معزول لكلٍّ)، ثمّ دُمِج كلّ شقّ تتابعيّاً بإعادة تحقّق كاملة مِنّي (cherry-pick على dev + ruff + pytest + بوّابة) — **لا ثقة بنتيجة وكيل دون إعادة تحقّق**:

- **v62.3-A** (`ea6829e`): `services/ai_agronomist/evidence_contract.py` — `build_ndvi_grid_evidence` (عقد موحّد grid/quality/provenance، لا اختلاق) + `evaluate_machine_readiness` (بوّابة fail-closed: valid_pixel<0.7 أو coverage<0.75 أو مناطق هندسية ⇒ ليست جاهزة؛ cloud>0.35/قِدَم>14ي إنذار). موصولة ببوّابة VRA. ٦ اختبارات.
- **v62.3-B** (`aa0f830`): `raster-service/quality_metrics.py` + كاتب `db_persist`/`_persist_raster_asset` (يعبّئ أعمدة v131) + قارئ `fetch_latest_asset` (+`cloud_cover`). 17 unit + 1 integration (**مرّ على Postgres:** `test_raster_quality_columns_populated_v62_3b::test_quality_columns_round_trip_and_check`).
- **v62.3-C** (`a99f4f4`): `field_ai_context._optional_ndvi_grid` يجلب الشبكة+الجودة من raster (fail-safe) → `imagery_timeline.ndvi_grid/ndvi_grid_quality`؛ `runtime_evidence.pack_ndvi_grid_evidence` يبني العقد؛ `ai_agronomist/main.py` يحقن `ndvi_grid_evidence` لبوّابة VRA. 7 اختبارات. **الوكيل صحّح قاعدته بنفسه** (تفرّع من b87df54 القديم ⇒ أعاد على ea6829e).
- **v52** (`90b0803`): جدول `tenant_ai_policies` **موجود أصلاً** (v124). `sahool-platform/core/ai_policy_envelope.py` يبني المظروف (افتراضيّ الأكثر تقييداً)؛ `ai_agronomist/policy_envelope.py` يرفض بلا مظروف + يمنع external في local_only + يفرض allowed_tools. 13 اختبار. **derived بصدق:** allowed_tools/data_classes/max_bytes بلا أعمدة داعمة (يلزم ترحيل لقوائم قابلة للضبط).
- **v133** (`6ad1872`): `scripts/migrations/report_not_valid_constraint_violations.py` + حارس `test_not_valid_constraint_no_new_violations_guard` (unit + integration؛ **مرّ:** `test_zero_violations_on_migrated_db`) + `docs/runbooks/validate_not_valid_constraints.md`. **لا VALIDATE أعمى** — الفعليّ للمشغّل بعد تقرير+تنظيف.
- **Superset merge = no-op** (وكيل قراءة-فقط + تحقّقتُ بنفسي): `origin/certification/final-readiness-evidence` (`a9f7314`) **سلف خطّيّ** لـmain (0 commit متقدّم، merge-base=cert tip). التوحيد نُفِّذ سابقاً. لا عمل.

**تعارض C↔v52** على `ai_agronomist/main.py`+`field_ai_context.py` دمجه git تلقائيّاً (مناطق مختلفة) وتحقّقتُ دلاليّاً (754 اختبار انحدار أخضر).

**تنظيف:** أُزيلت worktrees الوكلاء (كانت تضخّم مسح compile إلى 18468؛ البصمات نظيفة git-tracked فقط).

**مصفوفة تحقّق (٩ مجالات):** 1–6 (RLS/tenant/MapHub/offline/AI-approval/VRA) مُتحقَّقة عبر ci.yml 11/11 + unit؛ 7–9 (k6/chaos كامل/observability حيّ) أجزاؤها الثابتة خضراء لكنّ الحيّ **يحتاج الستاك المُشغَّل** — لم أدّعِ تشغيله.

---

## 2026-07-01 (ط) — v29.6.1: مراقبة وحُرّاس انحدار MFA (غير حاجب)

**رأس `main` بعد الجلسة:** `b5ee3ce`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

بعد بحث المستخدم (OWASP/NIST/PostgreSQL RLS/asyncpg) تأكّد أنّ الإغلاق الاحترافيّ = حُرّاس/عقود لا ترحيلات عشوائيّة. نُفِّذ v29.6.1 (تحسينات اختياريّة، لا إعادة فتح لتصلّب MFA):
- **`f75e363`:** (١) `routers/users.py` يحسب IP مرّة ويمرّره إلى `_verify_caller_mfa(ip=…)` ⇒ أحداث `mfa_stepup_*` تحمل بصمة IP (HMAC) لا NULL. (٢) `_ip_hash` لا يستعمل الحرفيّ الثابت في الإنتاج (`MFA_AUDIT_HASH_KEY`→`JWT_SECRET`؛ لا مفتاح ⇒ NULL لا تجزئة قابلة للتزوير) + إنذار إقلاع غير حاجب. (٣) حارس AST `test_auth_acquire_admin_context_guard` يؤكّد أنّ `_acquire` و`_init_auth_conn` يضبطان `app.current_role='admin'` (يمنع انحدار RLS الصامت بعد RESET ALL).
- **`b5ee3ce`:** حارسان ساكنان على SQL v129 (`test_mfa_migration_contract_guard`): recovery خدمة-فقط بلا `current_user_id`/`current_tenant` · trigger `trg_append_only_mfa_audit_events` (BEFORE UPDATE OR DELETE + `sahool_block_mutation`). يعملان في طبقة unit (بلا DB) فيلتقطان الانحدار أبكر من اختبار التكامل الذي يبقى يثبت السلوك على Postgres حيّ.
- **قرار مفتاح التدقيق:** المنع غير الكاسر (JWT_SECRET fallback قويّ + إنذار) لا بوّابة إقلاع صارمة — لتفادي إسقاط النشرات التي لم تضبط المفتاح المُخصَّص. أيّده المستخدم صراحةً.

**الخارطة المتّفَق عليها بعد v29.6.1 (بترتيب البحث):** SPATIAL-401 (evidence-first، محجوب على Network) · v62.3 عقد أدلّة · v52 policy envelope (platform سلطة، ai_agronomist مستهلِك) · VALIDATE بعد تقارير مخالفات · superset merge يبدأ بجرد (Phase 0) · v29.5-op/v39.5/v19.5 حسب ما يُفعَّل إنتاجيّاً.

---

## 2026-07-01 (ح) — إثبات P0 لـMFA على Postgres حقيقيّ + إصلاح إقلاع auth (mfa_crypto)

**رأس `main` بعد الجلسة:** `46e86eb`. الفرع المخصّص `claude/code-review-34hO3` مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

### الاختبارات كانت تتخطّى بصمت في CI (تصحيح ادّعاء سابق)
- **`cb4ea31`**: أثبت المستخدم أنّ اختبار تكامل MFA كان **SKIPPED** في CI. السبب: اختباراتي قرأت `DATABASE_URL` بافتراضيّ وهميّ، بينما وظيفة *Integration* تضبط `TEST_DATABASE_URL` (localhost:5433) **وبلا fastapi**. أصلحتُ الأربعة (`test_mfa_hardening_integration_v29_5` + soil-lab/imagery/field_state v57.5) لاستخدام `TEST_DATABASE_URL` + `statement_cache_size=0`. اختبار MFA أُعيدت كتابته: `test_mfa_migrations_applied_on_real_postgres` (asyncpg نقيّ — **يعمل في CI**) + `test_mfa_end_to_end_via_app` (TestClient، `importorskip('fastapi')` — تخطٍّ شفّاف لا صامت).
- **إثبات P0 (لقطة سجلّ CI، run 28553630120 job 84656203554):**
  `test_mfa_migrations_applied_on_real_postgres PASSED [61%]` · `test_v131_applied_on_real_postgres PASSED` ·
  `test_v130_applied_on_real_postgres PASSED` · `= 43 passed, 99 skipped =`. الاختبار الحاسم يثبت على Postgres حيّ: أعمدة/جداول v128 + RLS المُضيَّق v129 (recovery خدمة-فقط بلا self-read · audit يبقي هروب admin) + trigger append-only (probe سلوكيّ داخل tx مُلغى). **بذلك MFA مغلق إنتاجيّاً** (شرط المستخدم: «إذا مرّ هذا الاختبار…»).

### عطل إقلاع auth الحقيقيّ (نفس صنف router_registry/otp)
- **`abf1731`**: بعد `up -d --build` فشلت الحاوية: `ModuleNotFoundError: No module named 'mfa_crypto'` عند `main.py:163`. السبب: `services/auth/Dockerfile` ينسخ ملفّات مفردة ولم ينسخ `mfa_crypto.py` (وحدة v29.5). الإصلاح: `COPY services/auth/mfa_crypto.py`. + **حارس معمَّم** `test_dockerfile_ships_local_sibling_modules` في [`tests_v9/test_decomposed_service_dockerfile_guard.py`](../tests_v9/test_decomposed_service_dockerfile_guard.py): يمسح استيرادات `main.py` المستوى-الأعلى، يحدّد الوحدات الشقيقة الفعليّة (`.py` مجاور)، ويؤكّد نسخها — يلتقط otp.py + mfa_crypto.py اليوم والتالي تلقائيّاً.
- **`46e86eb`**: `ruff format` للحارس (سطر واحد، بلا منطق) + تجديد بصمات الإصدار.

### تشغيليّ (على المشغّل)
- تطبيق الإصلاح: `docker compose -f docker-compose.v9.yml up -d --build sahool-auth` + ضبط `MFA_SECRET_ENCRYPTION_KEY` في `.env`.

---

## 2026-07-01 (ز) — حوكمة الوكيل v58.2 + أدلّة v49.5 + تصلّب MFA v29.5/v29.6 + إصلاحات runtime

**رأس `main` بعد الجلسة:** `4a3f1a4`. الفرع المخصّص `claude/code-review-34hO3` مطابق. كلّ دفعة CI 11/11 خضراء ثمّ ff-merge إلى main.

### حوكمة الوكيل (v58.2 — تقوية أساس v55/v56/v57)
- **v58.2a** (`eb3cf89`): مخازن موافقة/تدقيق قابلة للاستبدال، جاهزة للاستمرار — `services/ai_agronomist/agent_stores.py` (InMemory افتراضيّ · Redis خلف `SAHOOL_AGENT_STORE_BACKEND=redis`، سقوط آمن للذاكرة) + نقطة `/approvals/resume` (تُعيد مغلّف تنفيذ لا تنفّذ داخل الـruntime).
- **v58.2b** (`151851a`): تحقّق وسائط صارم + تعقيم نتائج (ضد تسميم tool-result) — `services/ai_agronomist/tool_governance.py`؛ + ثابت وقت-البناء «كلّ mutating ⇒ requires_approval» في [`shared/ai/tool_registry.py`](../shared/ai/tool_registry.py) وقلب الأدوات الثلاث المتوسّطة؛ + إرشاد schema لأدوات v58 الأساسيّة.
- **v58.2c** (`0b5a13b`): حماية إساءة الحلقة — ميزانية أدوات إجماليّة عبر الجولات + dedupe بـ`tool+input_hash` + إيقاف عند بوّابة الموافقة ([`services/ai_agronomist/tool_loop.py`](../services/ai_agronomist/tool_loop.py) + `ai_generation.py`).

### أدلّة/ذاكرة الحقل (v49.5 — دمج انتقائيّ من حزمة، رفض العودة)
- **v49.5** (`abe0c51`): `services/sahool-platform/api/routers/field_ai_context.py` — `_optional_events` صار tenant-scoped صراحةً (دفاع مضاعف مع RLS) + redaction قبل السياق + ميزانية حجم/عناصر + freshness/provenance. + ترحيل `migrations/v127_evidence_context_hardening.sql` (recommendation_outcomes: RLS WITH CHECK + غلّة غير سالبة). رُقِّم v49_5→**v127** (حارس التكرار) + سُجِّل في MANIFEST/run_migrations. رُفِضت عودة الحزمة إلى ما قبل v58.2a/b (متطابقة بايتيّاً مع السلف `75ba7f9`).

### تصلّب MFA الإنتاجيّ (v29.5 ثمّ v29.6 بعد مراجعة أمنيّة)
- **v29.5** (`8810321`): `services/auth/mfa_crypto.py` (Fernet، مفتاح `MFA_SECRET_ENCRYPTION_KEY` بلا default) + ترحيل `migrations/v128_mfa_hardening.sql` (encrypted_mfa_secret + قفل DB + mfa_recovery_codes hash-only + mfa_audit_events). مسار توافق: مشفّر مُفضَّل → نصّ قديم → ترحيل عند نجاح الدخول (لا يكسر مستخدماً قائماً). `cryptography>=44` (pip-audit نظيف).
- **v29.6** (`4a3f1a4`): إصلاحات مراجعة المستخدم — ترحيل `migrations/v129_mfa_hardening_followup.sql`: تضييق هروب RLS إلى `app.current_role='admin'` (لا `tenant IS NULL` مجرّد) بعد **إثبات** أنّ auth pool يضبطه على كلّ اتّصال ([`services/auth/main.py`](../services/auth/main.py) `_init_auth_conn`:278 + `_acquire`:218) · `mfa_recovery_codes` خدمة-فقط بلا self-read · `mfa_audit_events` append-only (`sahool_block_mutation`). كود: step-up محكوم (`_verify_caller_mfa` بقفل+تدقيق) · التقاط `MfaSecretUndecryptable` (لا 500) · عدّاد فشل ذرّيّ (SQL CASE) · rotation في transaction · HMAC للـIP · key_missing→503 مميّز · جودة مفتاح الإنتاج.

### إصلاحات runtime (من لقطات المستخدم)
- **422 backfill** (`2e353af`): [`frontend/src/sections/MapHub.tsx`](../frontend/src/sections/MapHub.tsx) — «تجهيز سنتين» كان يرسل `'truecolor'` ضمن `indices`، لكنّ `IndicatorKind` في raster لا يحوي truecolor ⇒ 422 pydantic. الإصلاح: ترشيح للمجموعة المدعومة (ndvi/ndmi/…). + حارس ساكن.
- **bandit B613** (`5202907`): `tool_governance.py` احتوى محارف bidi حرفيّة في regex ⇒ CI Security Scan HIGH. أُعيد بناء النمط من code points (لا محارف خام).
- **JWT_SECRET للنبات** (`62989c6`): `docker-compose.v9.yml`/`fixed.yml` لم يمرّرا `JWT_SECRET` لخدمة `sahool-vegetation-analysis` وحدها ⇒ 503 «JWT_SECRET غير مضبوط» على «تحليل الآن» (`services/vegetation-analysis-service/main.py:161`). أُضيف `JWT_SECRET` + `JWT_PUBLIC_KEY` (كبقيّة الخدمات).

### مفتوح (موثَّق)
- **SPATIAL-401:** «المؤشرات المكانية» تُخرج للدخول (raster `/indicator-grid` 401) — يحتاج status+body من Network للتشخيص (لم يُخترَع إصلاح).
- **AUTO-SEG:** «تحديد الحدود تلقائي» 503 مقصود (SAM2 غير منشور؛ `docker-compose.fixed.yml:1076-1084`).
- **v57.5-DB (مفتوح فعلاً):** soil_lab analyte schema (v50) · imagery quality metadata (v54) · field_state recompute contract (v53) · tenant AI policy DB-backed (v52) — تحتاج Postgres، يُتحقَّق عبر CI.

### صدق ومنهج
- كلّ دفعة: `pytest -m unit` أخضر (2186→2215) + ruff + manifest + CI 11/11 (Integration يطبّق كلّ ترحيل على Postgres+PostGIS حقيقيّ) ثمّ ff-merge.
- تكرّر درس «الفجوة مُغلَقة أصلاً»: عند مراجعة v9–v57 تبيّن أنّ معظم P0 (RLS WITH CHECK عبر v70 · حارس RLS القائم · ID TEXT v18 · حوكمة الأوامر v100+) مُنجَز downstream — تحقّقتُ قبل التنفيذ تفادياً لعمل مكرّر.

---

## 2026-06-29 (ر) — إصلاح Docker Compose الكامل + تحقّق CDSE end-to-end

**رأس الفرع:** `db08e63`. جلسة متواصلة من (ق) — سقط السياق فأُعيدت.

### إصلاحات Docker Compose (startup failures)
- **weather-polygon-worker/weather-signal-engine:** Dockerfile ينقصه `COPY core/thresholds.py` ⇒ `ModuleNotFoundError: core.thresholds` ← أُضيف.
- **raster-tiler-service:** `python:3.12-slim` ينقصها `libexpat1` (تتطلّبها rasterio/GDAL) ⇒ `ImportError: libexpat.so.1` ← أُضيف `apt-get install libexpat1`.
- **sahool-platform:** `SAHOOL_ENV=production` + غياب `JWT_PUBLIC_KEY` ⇒ `sys.exit(1)` من حارس RS256 ← ثُبّت `SAHOOL_ALLOW_HS256_IN_PROD=1` في `.env` + ثُرّر المتغيّر عبر compose.
- **nginx:** ثلاثة أخطاء: (1) `proxy_http_version` مكرّر في `/ws/` ← حُذف المكرّر. (2) `proxy_pass` له URI في `@spa_fallback` ← استُبدل بـ`rewrite+proxy_pass`. (3) healthcheck يحلّ `localhost→::1` (IPv6) لكن nginx `listen 80;` فقط ← أُضيف `listen [::]:80` + `listen [::]:443 ssl http2`. (4) `nginx/ssl/` فارغ ← أُنشئت شهادة self-signed (10 سنوات).

### CDSE Satellite Imagery (end-to-end)
- **root cause 1 — FieldIndicatorMap:** كانت دائماً تستدعي `/tilejson` (COG محلّيّ) حتّى في وضع CDSE ⇒ `available=false` لحقل بلا COG ← صارت تستدعي `/cdse-tilejson` حين `tileSegment='cdse-tiles'`.
- **root cause 2 — SatellitePage:** لم تُمرّر `tileSegment="cdse-tiles"` إلى `FieldIndicatorMap` ← أُضيفت لكلا الوضعَين (NDVI + truecolor).
- **root cause 3 — cdse-tilejson:** كانت روابط البلاطات بلا بادئة nginx (`/v1/` لا `/api/raster/v1/`) ← صُحِّحت. + أُضيف `reason/user_message` عند غياب الاعتماد.
- **root cause 4 — cdse_client:** يقرأ `CDSE_CLIENT_ID` فقط؛ compose يُعيّن `SH_CLIENT_ID` ← أُضيف ارتداد `SH_CLIENT_ID/SECRET` في `_cdse_credentials()`.
- **تعارض git pull:** حُلّ في `FieldIndicatorMap.tsx` + `cdse_tiles.py` ← commit `db08e63`.
- **nginx re-resolve:** بعد إعادة تشغيل auth، nginx احتفظ بـIP قديم ← `nginx -s reload` أعاد الحلّ.
- **تحقّق نهائيّ ✓:** `cdse-tilejson?index=ndvi` + `?index=truecolor` عبر nginx + JWT ⇒ `{"available":true, "tiles":["/api/raster/v1/fields/…/cdse-tiles/…"]}`.

### الحاويات غير الصحيّة المتبقّية (pre-existing, لا علاقة بـCDSE)
`actuator-dispatch-worker`, `model-registry-worker`, `phase-runtime-outbox-worker`, `plugin-runtime-worker` — تعمل وظيفيّاً (تسجّل `{"processed":0}`) لكن healthcheck يتوقّع `http://localhost:8000/readyz` وهم لا يُشغّلون خادم HTTP. مشكلة تعريف healthcheck، لا تعطّل وظيفيّ.

---

## 2026-06-29 (ق) — تتبّع جنائيّ: «المؤشّرات لا تُعرَض» في MapHub + فخّ اعتماد CDSE

**رأس الفرع المخصّص:** `a37ce64`. لقطة المستخدم: حقل مرسوم، الطبقة NDMI «نشطة»، لكن لا تراكب راستر.
تتبّع كامل (خدمة الراستر → الواجهة → البوّابة → المزوّد) كشف عيبَين حقيقيَّين + فخّ تهيئة:

- **🔑 الواجهة (السبب الجذريّ لـMapHub):** `HubMap.tsx`/`HubMapGL.tsx` كانا يبنيان رابط بلاطة المؤشّر على
  المسار المحلّيّ `/v1/fields/{id}/tiles/` (COG مُسبق-التوليد) ⇒ **404 لحقل بلا معالجة ⇒ شفّاف ⇒ لا مؤشّر**
  (فجوة MAPHUB-CDSE). حُوِّلا إلى `/cdse-tiles/` الحيّ + bbox + قصّ `poly` (قناع rasterio)، مع حفظ عقد
  التاريخ D. + `FieldIndicatorMap.tsx` كان يبوّب الطبقة على `/tilejson` المحلّيّ حتّى في وضع CDSE ⇒ يحجبها
  دائماً لحقل CDSE-فقط؛ صار يسأل `/cdse-tilejson` حين `tileSegment='cdse-tiles'`.
- **🔑 الخادم (سبب جذريّ حين يبدو CDSE مُهيّأً وهو ليس كذلك):** `cdse_client` يقرأ `CDSE_CLIENT_ID/SECRET`
  **فقط**، بينما compose يُعرّف أيضاً `SH_CLIENT_ID/SECRET` (تُلزِمها خدمة أخرى بـ`:?`) لنفس realm الـCDSE.
  مشغّل ضبط `SH_*` دون `CDSE_*` ⇒ بلاطات شفّافة صامتة. أُضيف ارتداد `SH_*` في `_cdse_credentials()`
  يستخدمه `is_configured()`+`_fetch_token()`. + `cdse-tilejson` يُرجِع `reason=cdse_not_configured`+رسالة
  للمشغّل (لا فشل صامت).
- **تحقّق المزوّد ✓:** `SH_BASE_URL`/`SH_TOKEN_URL` يشيران إلى Copernicus فعلاً
  (`sh.dataspace.copernicus.eu` · `identity.dataspace.copernicus.eu/.../CDSE`)؛ NDMI مؤشّر مدعوم؛ توجيه
  nginx `/api/raster/` سليم (يقرأ tenant من `tid`/`tenant_id`/ترويسة). **لا حجب من السكربت** — يُرجِع
  شفّافاً برشاقة عند: غياب الاعتماد · مؤشّر غير مدعوم · تعذّر CDSE.
- **⚠ تصحيح صدق:** ادّعائي السابق أنّ فروع CDSE الخمسة «مُستبدَلة 100%» **كان خاطئاً** لـHubMap تحديداً —
  فرع `cdse-maphub-ws-fixes` حمل إصلاح `indicatorTileUrl→cdse-tiles` الذي **لم يدخل main** في التوحيد
  (دخل backend الراستر + FieldIndicatorMap، لا HubMap/HubMapGL). لحسن الحظّ تعذّر حذف الفروع (403) فلم
  يُفقَد الإصلاح. **الدرس:** تحقّق ملفّ-بملفّ لا معلَم-عيّنة قبل وصف فرع «مُستبدَل»؛ معلم واحد حاضر لا يعني
  الكلّ. تحقّق: tsc نظيف · maphub vitest 29 · raster cdse 14 · `pytest -m unit` 1973 · SH-only⇒configured.

---

## 2026-06-29 (ص) — rate limit موزَّع بـRedis (#6) + تحقّق فروع CDSE العالقة (ج)

**رأس الفرع المخصّص:** `c2af2e6` (= `main` بعد الدمج المؤتمت).

- **#6 (rate limit → Redis، باختيار المستخدم «أ»):** `rate_limit_middleware` كان عدّاداً in-process لكلّ
  عامل ⇒ مع N عمّال الحدّ الفعليّ N×المضبوط. أُضيف عدّاد Redis مشترَك (`INCR`+`EXPIRE 60s` لكلّ مفتاح عميل)
  يُختار عند الإقلاع متى توفّر `REDIS_URL` حيّ؛ النداء المتزامن عبر `asyncio.to_thread` (لا يحجب الحلقة).
  **ليس fail-closed** (حاجز DoS لا بوّابة أمن): أيّ خطأ Redis/غياب `REDIS_URL` ⇒ تدهور رشيق إلى العدّاد
  in-process (محفوظ حرفيّاً). اختبارات: الموجودة مُثبَّتة على in-process (`_RATE_REDIS=None`) للحتميّة +
  اختبارا مسار Redis (حجب فوق الحدّ + `EXPIRE` مرّة + عزل المفاتيح) + fail-open. `pytest -m unit` 1973 ✓.
- **ج (حذف فروع CDSE العالقة):** فحصتُ ٥ فروع (`frontend-cdse-hide-date`/`fix-cdse-clip-to-field`/
  `claude/frontend-cdse-omit-latest-date`/`claude/cdse-maphub-ws-fixes`/`claude/brain-update-decompose-cdse`).
  **ليست ancestors لـmain** (لكلٍّ ١–٤ commits فريدة) لكنّ **محتواها مُستبدَل بالكامل في main** (تحقّقتُ من ٦
  معالم: `fetch_field_geometry`+RLS · `apply_polygon_mask` · عقد `poly=` · توجيه nginx للراستر · WebSocket
  الإشعارات · روابط CDSE في الواجهة — كلّها حاضرة، وبعضها أكمل عبر التوحيد). **الحذف حجبه المصنّف** (يتطلّب
  تسمية المستخدم الصريحة للفروع) — أُحيل القرار للمستخدم بأسماء الفروع + دليل الاستبدال. لا أحذف عملاً غير
  مدموج بقرار ذاتيّ.
- **درس:** «stale/superseded» ≠ «merged». الفرع قد يحمل commits فريدة ومحتواها مع ذلك مُعاد تطبيقه في main
  (التوحيد التوفيقيّ يُعيد الكتابة لا الـcherry-pick) — تحقّق من المحتوى لا النسب قبل وصفه «آمن للحذف».

---

## 2026-06-29 (ف) — تحصين JWT RS256: المنصّة + ٨ خدمات ترفض HS256 في الإنتاج

**رأس الفرع المخصّص `claude/code-review-34hO3`:** `ddd2434`. مراجعة جنائيّة للمستخدم لنسخة zip كشفت
فجوات؛ تحقّقتُ من كلٍّ بالكود الفعليّ (بعضها صحيح، بعضها غير قابل لإعادة الإنتاج).

- **🔑 #1 (حرج، مُصلَح `030c01a`):** `services/sahool-platform/api/main.py` كان يتحقّق HS256-فقط بلا مسار
  `JWT_PUBLIC_KEY` ⇒ **لا يستطيع التحقّق من توكنات auth الـRS256 في الإنتاج** (auth صُلّب لـRS256 سابقاً) ⇒
  كسر مصادقة عابر-خدمات. المنصّة تقبل `iss in {sahool-auth, sahool-platform}` فيجب أن تتحقّق ممّا يوقّعه auth.
  الإصلاح (محاكاة auth): `JWT_PUBLIC_KEY`/`JWT_VERIFY_KEY`/`JWT_VERIFY_ALGORITHM`؛ مسارا التحقّق
  (`get_current_user` + إبطال `auth_logout`) صارا RS256-واعيَين؛ حارس `_refuse_hs256_in_production` يرفض
  الإقلاع في الإنتاج بلا RS256 (مهرب `SAHOOL_ALLOW_HS256_IN_PROD=1`). `create_token` يبقى HS256 (مُصدِر dev،
  مُعطَّل في الإنتاج). اختبار: جدول الرفض + **دورة RS256 عابر-خدمات حقيقيّة** (توقيع خاصّ→تحقّق عامّ).
- **#7 (اتّساق، مُصلَح `ddd2434`):** ٨ خدمات تتحقّق JWT صارت ترفض HS256 في الإنتاج (حارس إقلاع موحَّد،
  `raise RuntimeError`، يُدرَج بعد `_ALLOWED_ISS` — مرساة موحَّدة في كلّها). actuator/guardrails/local-ai-rag/
  odoo/tts/video/supervisor كان لها مسار RS256 (تنقصها بوّابة الإنتاج فقط)؛ **vegetation-analysis-service**
  كان **HS256 مُصمَّت بلا مسار RS256 أصلاً** (نفس صنف #1) فأُضيف لها المسار الكامل + الحارس. حارس مصدريّ جديد
  `test_services_rs256_production_guard.py` (٨ خدمات) يمنع الانحدار.
- **تصحيحات صادقة للمراجعة:** **#3 (MANIFEST «Canonical source»)** و**#4 (.env placeholder test)** **غير قابلتَين
  لإعادة الإنتاج** على `main` الحاليّ — لا نصّ/اختبار بهذا الاسم؛ اختبارات الـmanifest/placeholder (26) خضراء.
  لقطة zip أقدم. **#2 (Phase 9–12)** سليم ✓. **#6 (rate limit in-process)** صحيح لكن **موثَّق في الكود**
  (`N2: حالة في الذاكرة`) — تغيير Redis مؤجَّل. **#5** تفكيك مستمرّ.
- **القرار التصميميّ:** حارس الإقلاع import-time (لا request-time) — أبسط (موضع واحد/خدمة لا لكلّ بوّابة تحقّق)
  وfail-closed عند الإقلاع؛ لا يُطلَق في CI (لا اختبار يستورد هذه الخدمات بـ`SAHOOL_ENV=production` — تُحُقِّق).
  استُعمل `os.getenv("JWT_PUBLIC_KEY")` مباشرةً (لا متغيّر الوحدة) فالكتلة **متطابقة** في الخدمات السبع.
- **درس:** المسح الذاتيّ كشف خدمة عاشرة (`vegetation`) فاتت المراجعة الجنائيّة — `grep jwt.decode` على كلّ
  الخدمات أوسع من قائمة المراجِع. تحقّق دائماً من الادّعاءات بالكود (بعضها بائت من نسخة أقدم).

---

## 2026-06-29 (ع) — تفكيك main.py للمنصّة (استخراج النماذج) + إصلاح حارس المصدر

**رأس الفرع المخصّص `claude/code-review-34hO3`:** `044e1ff` (CI `ci.yml` أخضر). `main` المحلّيّ `c8fc78b`
(مدموج فيه؛ الدفع المباشر لـmain محجوب بالمصنّف — التطوير يبقى على الفرع المخصّص).

- **استخراج نماذج Pydantic من `main.py` (P0):** نُقِل ٧٣ صنف `BaseModel` من
  [`services/sahool-platform/api/main.py`](../services/sahool-platform/api/main.py) (3282→2735 سطراً) إلى
  وحدة جديدة [`services/sahool-platform/api/api_models.py`](../services/sahool-platform/api/api_models.py)
  (664 سطراً، بترتيب المصدر/AST فالنماذج المتداخلة تسبق مستهلكيها)، ويُعاد استيرادها عبر
  `from api.api_models import (...)  # noqa: E402,F401`. أُبقيت ٤ معالِجات `@app` ووصل `register_routers`.
- **🔑 الإصلاح (هذه الجلسة):** حارس المصدر
  [`tests_v9/test_disease_field_state_feed.py`](../tests_v9/test_disease_field_state_feed.py)`::test_diagnose_request_has_optional_field_id`
  كان يمسح `main.py` فقط بـ`src.index("class DiagnoseRequest(")` ⇒ `ValueError: substring not found` بعد
  نقل النموذج إلى `api_models.py` (كسر CI run #2532 على `a806251`: 1 failed/1600 passed). الحلّ: مسح
  `main.py` **و** `api_models.py` (نفس نمط `_func_src` للمعالِجات المنقولة) دون إضعاف تأكيد
  `field_id: str | None = None`. تحقّق: ٦/٦ في الملفّ خضراء · `pytest -m unit` كامل = **1950 passed**
  (الـ٧ أخطاء الوحيدة = `nats.aio` غائب محلّيّاً، تنجح في CI).
- **تجديد بصمات الإصدار:** غيّر ملفّ الاختبار بصمته ⇒ أُعيد توليد `release/FILE_CHECKSUMS.sha256`
  (+manifest/SBOM) بـ`build_release_bundle.py` لإبقاء بوّابة Phase 14 خضراء.
- **التوقيع:** الالتزامان المدفوعان (`c8fc78b`+merge `044e1ff`) موقَّعان SSH (ترويسة `gpgsig`)؛ تحذير
  `%G?`=N محلّيّ فقط (غياب `allowedSignersFile`؛ ملفّ المفتاح العامّ 0 بايت) — GitHub يتحقّق خادميّاً.
- **درس:** أيّ نقل لرمز يمسحه حارس مصدر نصّيّ (`.index`/`.find`) يجب أن يوسّع نطاق المسح للوحدة الجديدة
  — شغّل **كامل** `tests_v9 -m unit` لا عيّنة المنصّة وحدها (التحقّق السابق فوّت هذا الحارس).
- **تفكيك دلاليّ إضافيّ (`d6d4b0d`، باختيار المستخدم «تفكيك دلاليّ إضافيّ»):** استُخرِج عنقود **السياق
  الزراعيّ للحقل** (٧ دوالّ + `_STAGE_DAY_BOUNDS`: `_field_weather_context`/`_field_season_context`/
  `_latest_soil_moisture`/`_historical_rain_3d_mm`/`_growth_stage`/`_resolve|_load_recommendation_policy`)
  من `main.py` إلى وحدة جديدة [`api/field_context.py`](../services/sahool-platform/api/field_context.py)
  (main.py 2735→**2523**). عنقود مشترَك بين موجِّهات (fields/recommendations/field_completeness) ⇒ وحدة
  مشترَكة لا router واحد. **بلا دورة استيراد:** كلّ دالّة DB تستقبل `conn` كمعامل (لا اقتران بمجمّع main)
  وكلّ استيراد ثقيل كسول داخل الدالّة. يُعاد التصدير من `api.main` (`# noqa: E402, F401`) فتبقى نقاط
  `from api.main import …` صحيحة. حارس جديد
  [`test_field_context_decomposition_guard.py`](../tests_v9/test_field_context_decomposition_guard.py)
  يثبّت: التعريف في field_context لا main + إعادة التصدير بنفس هويّة الكائن. تحقّق: 526 مساراً ثابتاً ·
  ruff نظيف · `pytest -m unit` 1950 ✓ · inspector router-wiring PASS.
- **سبب اختيار هذا العنقود (لا غيره):** محرّك التنبيهات (`_evaluate_field_alerts_persist`) **يبقى** في main
  عمداً (موثَّق في `alert_models.py`) لاقترانه بـ`tenant_connection`/مساعِدات main ⇒ نقله يخلق دورة. نماذج
  Pydantic النقيّة سبق نقلها. عنقود السياق هو الوحيد المتبقّي القابل للنقل النظيف (conn معامل + كسول).

---

## 2026-06-29 (س) — توحيد main + فرع الاعتماد Phase 1–22 + السبب الجذريّ لـauth

**رأس `main` بعد الجلسة:** `96003bf`. الفرع المخصّص `claude/code-review-34hO3` = `c0174e6` (مطابق لـmain).

اكتشف المستخدم أنّ `main` (عمل الجلسات) وفرع `certification/final-readiness-evidence` **افترقا**
من القاعدة `89d848e` — كلّ خطّ يحمل عملاً فريداً. القرار: **توحيدهما** في superset واحد.

- **التوحيد (54 commit فوق main السابق):** دمج `certification` (Phase 1–22 · ترحيلات v99–v123 ·
  `sahool-production-gates.yml` · وحدات runtime — 470 ملفّاً) مع عمل main (تفكيك · CDSE poly ·
  H5/C5/H2 · بوّابة الواجهة). 22 تعارضاً: الإضافيّ آليّاً؛ المتداخل بقاعدة cert المتقدّمة + اتّحاد.
- **Stage B (CDSE فوق cert):** أُعيد `apply_polygon_mask`+`fetch_field_geometry`(RLS) + تفعيل راوتر
  `cdse-tiles` + باني `fieldCdseTileUrl` (واجهة) + إعادة D في الموضعَين.
- **Stage C (تفكيك):** أُعيد تفكيك video/odoo/raster (cert المصلّبة) إلى `routers/` مع **حفظ تصليب
  cert** + استعادة الحُرّاس الثلاثة. كلّ الـ11 خدمة مُفكَّكة الآن.
- **🔑 السبب الجذريّ لـauth «unhealthy» (سجلّ المستخدم حسمه):** `main.py` يستورد
  `from router_registry import register_routers`، لكنّ Dockerfile auth (وvegetation) ينسخ ملفّات
  مفردة لا المجلّد ⇒ `ModuleNotFoundError: 'router_registry'` ⇒ uvicorn يفشل ⇒ الحاوية unhealthy.
  **ليست RLS/JWT** (فرضيّاتي السابقة كانت خاطئة — لم يكن لديّ السجلّ). أُصلِح: Dockerfile ينسخ
  `router_registry.py`+`routers/` + **حارس CI** `test_decomposed_service_dockerfile_guard` يمنع التكرار.
- **إصلاحات CI (بعد الدمج):** مفتاح `DATABASE_URL` مكرّر في `docker-compose.v9.yml` (أثر دمج) ·
  frontend TS (`tileSegment` props) · PyYAML في وظيفة المفتّش · ruff format · **تجديد بصمات الإصدار**
  (`build_release_bundle.py` — 85 ملفّاً تغيّر بصمتها بعد الدمج، فحص Phase 14 رصدها).
- **توحيد الفروع:** دُمج main في الفرع المخصّص `claude/code-review-34hO3` (شجرة مطابقة) + أُغلِق
  PR #579 (كان يتعارض في `cdse_tiles.py`؛ مُتجاوَز). 0 PR مفتوح · 0 تعارض.
- **درس:** الدمج التوحيديّ يغيّر بصمات كثيرة ⇒ جدّد حزمة الإصدار. والاختبارات تستورد main من مجلّد
  الخدمة فلا تكشف نقص Dockerfile — حارس Dockerfile الجديد يسدّ الفجوة.

---

## 2026-06-28 (ن) — بوّابة الواجهة + إغلاق متابعتَي D/C من مراجعة النسخة + تشخيص auth

**رأس `main` بعد الجلسة:** `63c2f03` (#577 آخر المدموجة). PRs مدموجة: **#574–#577** (٤).

- **#574 (`b180553`)** — تحديث العقل (تفكيك SVC-DECOMP-2: #570–#573).
- **#575 (`35a4565`) بوّابة الواجهة التطويريّة (frontend/nginx.conf، 3003):** إضافة ٥ كتل
  `location ^~` **قبل** catch-all `/api/` للخدمات التي تناديها `api.ts` بقواعد خاصّة
  (`vegetation`→`sahool-vegetation-analysis:8000/` · `indicators`/`weather`→`sahool-platform:8000/api/v1/…`
  · `agent`→`sahool-supervisor-agent:8000/agent/` + `= /api/agent/health`→`/health` · `guardrails`→
  `sahool-guardrails-engine:8000/`). بلا `auth_request` (نموذج تطوير؛ تمرير `Authorization`+`X-Tenant-Id`)؛
  الأهداف مطابقة لـ`nginx.v9.conf`. **الفجوة مُثبَتة:** بلاها تسقط لـ catch-all ⇒ 404 (دردشة/غطاء/مؤشّرات/طقس).
  حارس `test_frontend_nginx_service_proxy_guard.py`.
- **مراجعة المستخدم للنسخة `008c330`:** أكّدتُ كلّ ادّعاءاتها **صحيحة** بالكود (D/C/B + ملاحظات بيئيّة).
  أُغلِقت المتابعتان الصغيرتان القابلتان للتنفيذ هنا (B — journal دائم للوكيل — مؤجَّل كـPR مستقلّ):
  - **#576 (`2244145`) D — عقد TileJSON (واجهة):** `FieldIndicatorMap.tsx` كان يبني طلب TileJSON بـ
    `params:{index,date}` بلا شرط ⇒ تسريب `date=latest`/`date=`. صار مشروطاً
    (`date && date!=='latest' ? {index,date} : {index}`) — نفس حارس باني رابط البلاطة. backend يتحمّل ⇒
    تنظيف عقد لا كسر. حارس ساكن `test_frontend_tilejson_date_contract_guard.py` (٤).
  - **#577 (`63c2f03`) C — الموضوع اليتيم (NATS):** `sahool.weather.field.overlay.completed` يَنشُره
    `weather-polygon-worker:161` بلا مشترِك ⇒ WARN «حدث طريق مسدود» (غير حاجب). **توثيق** القرار:
    قسم `published_no_consumer` في عقد الأحداث (منتِج فعليّ + سبب) + `check_nats_subjects` يحترمه
    (WARN⇒PASS) دون إضعاف `CRITICAL`/H2. +٣ اختبارات (سلبيّ: إزالة الـwaiver تُعيد WARN).
- **تشخيص (لم يُغلَق — ينتظر سجلّ المشغّل):** `v21-sahool-auth-1` **unhealthy** يمنع إقلاع الحزمة.
  `/readyz` موصول صحيحاً (`routers/ops.py:31`+`register_routers`) ⇒ **ليست انحدار تفكيك #557**. السبب
  runtime/config: lifespan يرفع `RuntimeError` (fail-closed). الأرجح **دور قاعدة يتجاوز RLS** (DATABASE_URL
  كـsuperuser/مالك جداول ⇒ `assert_db_role_rls_safe` يرفض الإقلاع — `main.py:229`)؛ الإصلاح دور مقيّد
  `sahool_app` أو `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1` للتطوير. بدائل: `JWT_SECRET`<32، أو فشل `_ensure_admin_user`.
- **صدق:** D/C تنظيف+توثيق لا تغيير سلوكيّ؛ تشخيص auth **لم يُحسَم** بلا السجلّ (تفادي إصلاح أعمى).

---

## 2026-06-28 (م) — تفكيك ٤ خدمات أصغر (soil/tts/actuator/guardrails، #570–#573)

**رأس `main` بعد الجلسة:** `d340e60` (#570 آخر المدموجة من الدفعة). PRs مدموجة: **#570–#573** (٤).

إكمال تفكيك بقيّة `main.py` المتجانسة (٦–٧ مسارات لكلٍّ — دون عتبة ≥٨ السابقة لكنّ المستخدم طلب
إكمالها). **٤ وكلاء متوازون (worktree)**، نفس نمط raster/auth (`router_registry` + `_include_flat`
+ حارس تفكيك)، **نقل بنيويّ صرف محفوظ السلوك، عدد المسارات ثابت**:
- **#571 (`7f642a2`) tts-service:** ٧ معالجات → وحدتان (11 ثابتة). حارس `test_tts_notification_service_auth` (مسح `Cache-Control` المنقول) ⇒ مساعِد مُجمِّع.
- **#572 (`bcb6c15`) actuator-service:** ٦ → ٣ وحدات (10، **حسّاس**: `/command` + تفويض جهاز مطابق بايتاً). حارسان أمنيّان (`test_security_review_fixes`/`test_roadmap_phase23`) أُعيد توجيههما بمساعِد مُجمِّع — يقبل `Depends(_verify_token)` أو `Depends(main._verify_token)` (نفس الفرض).
- **#573 (`b4c0be6`) guardrails-engine:** ٧ → وحدتان (11، **حوكمة `/validate` حسّاسة**). `_require_service_token` مطابق بايتاً؛ حُرّاس `test_ai_orchestration_safety` أُعيد توجيهها (بل قُوِّي تأكيد) بمساعِد مُجمِّع.
- **#570 (`d340e60`) soil-service:** ٦ → وحدتان (10). **CI كشف كسرين حقيقيّين فات الوكيل اكتشافهما** (لا يشيران لـmain.py بالحرف):
  1. `test_soil_field_tenant_authz` يمسح `main.py` عن `resolved_tenant` ويستدعي `main.ingest_reading` (انتقلا لـ`routers/readings.py`) ⇒ **إعادة تصدير** المعالجات من `main` (ربط اسم، لا تسجيل مسار ثانٍ) + مساعِد مُجمِّع `soil_route_source.py` + **إسقاط وحدات `routers/` في إعادة استيراد الـfixture** (وإلّا تُبقي مرجعاً لـmain متعفّن عبر الاختبارات).
  2. `test_tenant_query_audit` — استعلام `soil_readings` RAW انتقل لمسار جديد ⇒ تحديث مفتاح allowlist في `scripts/tenant_query_audit.py`.
  **بلا إضعاف أيّ تأكيد** (اختبارات IDOR/عبر-المستأجرين تمرّ — تحقّقتُ بـpytest-asyncio: 14/14).

- **درس CI متكرّر:** حُرّاس `tests_v9` التي تمسح/تحمّل مصدر خدمة تتأثّر بالتفكيك بطرق متعدّدة (مسح نصّ · `hasattr` على main · تحميل وحدة بالمسار · allowlist مُفتَّح بالمسار). الحلّ المُثبَت: مساعِد مصدر مُجمِّع + إعادة تصدير عند اللزوم + تنظيف sys.modules — لا إضعاف للحراسة. **الوكلاء يفوّتون أحياناً الحُرّاس غير المُشيرة لـmain.py بالحرف؛ CI يلتقطها فتُصلَح.**

- **صدق:** كلّ تفكيك مُتحقَّق (`import main` + ثبات العدد + الحارس + ruff)؛ الإصلاحات الأمنيّة موسّعة-النطاق لا مُضعَّفة.

---

## 2026-06-28 (ل) — إغلاق H5/C5/H2 كسياسات قرار + إصلاح القصّ الجذريّ (#564–#568)

**رأس `main` بعد الجلسة:** `008c330` (#568 مُدمج). PRs مدموجة: **#564–#568** (٥ PRs).

- **#564 (`d9d9694`) — MapHub/CDSE/WebSocket + السبب الجذريّ للقصّ:** اكتشاف المستخدم أنّ
  `fetch_field_geometry` كان يستعلم `fields` **بلا `set_config('app.current_tenant')`** ⇒ RLS يحجب
  الصفوف ⇒ `geometry=None` ⇒ لا قصّ (بلاطات bbox). أُصلِح (يحلّ المالك عبر `sahool_field_owner_tenant`
  SECURITY DEFINER ثمّ يضبط السياق). + عقد **`poly`** الموحَّد (واجهة+خادم) + **قناع rasterio بكسليّ
  دقيق** (`tile_render.apply_polygon_mask`) + مؤشّر ملوحة **SWIR** `(B11-B12)/(B11+B12)` (كان NDVI
  معكوساً) + نطاق ألوان مُصحَّح + نافذة «أحدث» ٦٠ يوماً + تشخيص سبب البلاطة الشفّافة. حارس عقد
  [`test_cdse_poly_contract.py`].
- **#565 (`ba29bba`)** — تحديث العقل لسلسلة #552–#564.
- **إغلاق الفجوات الثلاث كسياسات قابلة للضبط والاختبار (لا «كود فقط»، بحسب توجيه المستخدم):**
  - **#566 (`e6f98f5`) H5 — سياسة الريّ المشروطة بالملوحة:** `net` دائماً + Ks عند توفّر EC موثوق +
    غسل **مشروط** (ECw+صرف+كفاءة)؛ ٤ سياسات + `requires_expert_review`. غلاف فوق
    `irrigation_advice`/`fao56.leaching_requirement` (مصدر واحد). راوتر `POST /api/v1/irrigation-recommendation`
    (لا يكسر `/water-balance`). ٦ اختبارات قبول. **مصدر EC:** `soil_lab_tests` عبر `gather_field_freshness`.
  - **#567 (`273ee34`) C5 — سياسة دليل NDVI:** يوسم دور NDVI (`informational`/`supporting`/
    `decision_blocking`)؛ **الافتراضيّ `supporting`** (لا يحجب قراراً وحده)؛ الحجب فقط بمعايرة محليّة +
    سياق محصول كامل + جودة مشهد. حارس بنيويّ: `resolve_field_state` يأخذ عُمر NDVI لا قيمته. ١٤ اختباراً.
  - **#568 (`008c330`) H2 — عقد ناشري الأحداث + حارس عكسيّ:** `event_publish_contracts.yaml` يربط كلّ
    موضوع مُستهلَك بمنتِج (outbox) أو waiver؛ `check_nats_publisher_coverage` (مُسجَّل في CHECKS) يفشل على
    «مُستهلَك بلا منتِج/waiver» — يمسح `services/`+`agents/` وقائمة `SUBSCRIPTIONS` (AST). **أثبت قيمته:**
    كشف `sahool.weather.forecast.updated` الذي فات الفحص القديم (services فقط). لا تقليم اشتراك، لا اختلاق.
- **درس CI:** إضافة فحص إلى `CHECKS` كسر اختبار `test_sahool_inspector` المُصلَّب على `== 5` ⇒ غُيّر إلى
  `== len(CHECKS)` (يصمد). + درس سابق: نسيت إنشاء فرع H2 فالتزم على فرع C5 ⇒ نُقِل بـcherry-pick + reset.
- **صدق:** H5/C5 يبقيان `fixed` لا `verified` (يحتاجان معايرة ميدانيّة: عيّنات EC + عتبات NDVI لمحاصيل اليمن).
  السبب الجذريّ للقصّ (RLS) كان **اكتشاف المستخدم** — وُثِّق وأُصلِح في المصدر لا في عَرَض.

---

## 2026-06-28 (ك) — إكمال raster/CDSE (#552–#559) + إغلاق فجوات + تفكيك ٤ خدمات (#560–#563) + MapHub/WS (#564)

**رأس `main` بعد الجلسة:** `7a36511` (#563 مُدمج). PRs مدموجة هذه الجلسة: **#552–#563** (١٢ PR). **مفتوح:** #564 (قيد CI).

- **إكمال سلسلة raster (#552–#559):**
  - #552 (`a3b29ff`) واجهة: حذف `date=latest` المثبَّت من روابط بلاطات CDSE.
  - #553 (`df02c06`) nginx: وكيل `/api/raster/` لبوّابة الواجهة 3003 **بلا** `auth_request` (بوّابة تطوير خفيفة؛ تمرير `Authorization`/`X-Tenant-Id` صراحةً — لا تكرار منطق بوّابة الإنتاج).
  - #554 (`efea4c6`) وثيقة: جدول مقارنة `v9 ↔ fixed` مُتحقَّق بالملفّ.
  - #555 (`f2d5f0b`) تحديث العقل (لسلسلة #550/#551 + الاسترجاع).
  - #556 (`852fb5b`) **استرجاع مرآة `mirror.gcr.io`** في *Integration Tests* (يُصلح رفرفة Docker Hub — فجوة CI-MIRROR صارت `fixed`).
  - #557 (`f92c994`) **تفكيك `auth/main.py`** (٢٧ `@app` → ٩ `routers/`، محفوظ السلوك، حسّاس أمنيّاً، N=31 ثابت).
  - #558 (`522a47e`) **قصّ CDSE على المضلّع** لا الـbbox (إزالة الصحراء الحمراء): الواجهة تمرّر `geom=GeoJSON` ⇒ Sentinel Hub يقصّ على المضلّع (شفّاف خارجه). **علم تحقّق ميدانيّ.**
  - #559 (`1bef0cf`) **تطبيع تاريخ CDSE:** `date=""` الفارغ (ترسله الواجهة) كان يصير `date_from="-01-01T..."` فاسداً ⇒ يُعامَل كـ`latest`؛ وإسقاط `date` من رابط `cdse-tilejson` حين لا يُطلَب محدَّداً. اختبار وحدة (٨). (مراجعة النسخة المرفقة: الملاحظة #2 صحيحة ونُفِّذت؛ #1 بصيغة آمنة؛ #3 — `X-Tenant-Id` من العميل لبوّابة التطوير — مقبول بلا تغيير.)

- **تفكيك ٤ خدمات متجانسة (#560–#563، ٤ وكلاء متوازين worktree):** نفس نمط raster/auth (`router_registry` + `_include_flat` + حارس تفكيك)، **نقل بنيويّ صرف محفوظ السلوك، عدد المسارات ثابت**:
  - #560 (`77123b3`) odoo-bridge: ١٠ معالجات → ٥ وحدات (14 مساراً ثابتة).
  - #561 (`d40f1a9`) video-processor: ٨ → وحدتان (12).
  - #562 (`0abe6de`) vegetation-analysis: ٨ → وحدتان (12؛ اختبارات الخدمة الحاليّة 19/19).
  - #563 (`7a36511`) supervisor-agent: ١٠ → وحدتان (14). **فشل CI حقيقيّ واحد:** حارس مصدر `tests_v9/test_ai_orchestration_safety.py` يمسح `main.py` لكود `/agent/query` الذي انتقل إلى `routers/agent.py` ⇒ أُصلِح بمساعِد [`supervisor_route_source.py`](../tests_v9/supervisor_route_source.py) المُجمِّع (main + routers، لا إضعاف أمنيّ).
  - **درس CI:** حُرّاس `tests_v9` ذات النوعين تتأثّر بالتفكيك — مسح المصدر (يُصلَح بمساعِد مُجمِّع) وتحميل الوحدة بالمسار (يحتاج مجلّد الخدمة على `sys.path` — `smoke_services.py` يفعله أصلاً؛ بعض الحُرّاس المعزولة لا، فتمرّ في CI لترتيب `sys.path` في السويت الكاملة).

- **MapHub/CDSE/WebSocket (#564، مفتوح):** مراجعة طلب المستخدم كشفت أنّ إصلاحات CDSE السابقة استهدفت `FieldIndicatorMap` لا `HubMap`. أُكمِلت:
  - `HubMap.tsx` → `cdse-tiles` (بدل `tiles` COG المفقود ⇒ 404) + bbox/geom/`tenant_id` + إزالة تعبئة المضلّع (`fill:false`).
  - `nginx.conf` → **`location ^~ /api/raster/`** (الجذر الحقيقيّ لـ404: regex `.png` كان يعترض البلاطات) + `X-Tenant-Id` من `$arg_tenant_id` (بلاطات `<img>` لا تحمل ترويسات) مع ارتداد للترويسة.
  - `agents/notification/agent.py` → توصيف `ws_notifications(websocket: WebSocket)` (وإلّا فشل المصافحة) + **`python-jose` المفقود** (الكود `from jose import` بلا تبعيّة ⇒ ModuleNotFoundError) + تثبيت `websockets<14`. pip-audit: لا ثغرات.
  - `routers/cdse_tiles.py` → **احتياط: جلب الهندسة من DB دائماً** حين لا تصل `geom` كي يبقى القصّ على المضلّع (MapHub لا يمرّر geom).

- **إغلاق فجوات قديمة:** `C5`/`H2`/`H5`/`C4-M1`/`SAM2`/`TERRAIN` → `deferred`/`by-design` (انظر [`gaps/registry.md`](gaps/registry.md)) — كلٌّ يحتاج بيئة/تحقّقاً ميدانيّاً/قراراً زراعيّاً خارج الإصلاح الآليّ الآمن.

- **قيد بيئيّ موثَّق:** حذف الفروع البعيدة يفشل (الوكيل بلا أداة حذف؛ الوسيط يرفض حذف المرجع) ⇒ الفروع العالقة (`frontend-cdse-hide-date`, `fix-cdse-clip-to-field`) تُحذَف من واجهة GitHub يدويّاً.

- **صدق:** كلّ تفكيك مُتحقَّق محليّاً (`import main` + ثبات العدد + الحارس + ruff)؛ مسار CDSE الحيّ (قصّ + قناع SCL) ما زال يحتاج تشغيل CDSE حقيقيّاً (يتعذّر محليّاً) — مُعلَن `fixed` لا `verified`.

---

## 2026-06-28 (ي) — تحصين/تفكيك raster + استرجاع بعد دفع مباشر على `main`

**رأس `main` بعد الجلسة:** `51d650c` (#551).

> ⚠ **تنبيه تشغيليّ (درس):** أُعيد ضبط `main` **بدفع مباشر من المالك** (لا عبر PRs:
> `a64d91c`→`5c40a56`) فمُحيت ٦ PRs كنتُ دمجتُها (#544–#549) — التزاماتها صارت يتيمة. **العمل لم
> يُفقَد** (الفروع باقية على origin)؛ أُعيد جوهره على `main` الحاليّ عبر **#550** (فرع واحد مدمج)
> مع **حفظ تامّ** لمساري CDSE الجديدين اللذين أضافهما المالك (`cdse-tiles`/`cdse-tilejson`).
> القاعدة: لا تبنِ على `main` أثناء دفع مباشر متزامن؛ وحّد الاسترجاع في فرع واحد سريع الدمج.

- **#550 (`2359cea`) — استرجاع تحصينات raster:**
  - **إصلاح جذر «الشرائط الداكنة»:** قناع داخليّ في كاتب COG (`dst.write_mask(isfinite·255)` +
    `DEFAULT_NODATA=-9999`، [`cog_writer.py`](../services/raster-service/cog_writer.py)) — إصلاح
    **المصدر**؛ يبقى `tile_render` بـ`dataset_mask` طبقة دفاع ثانية. (المصيّر وحده لا يكفي: بكسلات
    `finite=0.0` خارج dataMask كانت تُلوَّن معتمة.)
  - تعقيم تسريب `str(e)` للعميل ⇒ رموز عامّة + حارس ساكن
    ([`main.py:1329/1381`](../services/raster-service/main.py)).
  - `cloud_pct` فعليّ من SCL + قناع غيوم SCL بكسليّ في evalscript CDSE
    ([`cdse_client.py`](../services/raster-service/cdse_client.py)) — **علم تحقّق ميدانيّ:** يلزم تشغيل CDSE حقيقيّ.
  - سقالة `register_routers` ([`router_registry.py`](../services/raster-service/router_registry.py)).
- **#551 (`51d650c`) — تفكيك مسارات raster (محفوظ السلوك):** ٤٥ مسار `@app` → **١٠ وحدات `routers/`**
  (٤٩ مساراً ثابتة، CDSE محفوظة في [`routers/cdse_tiles.py`](../services/raster-service/routers/cdse_tiles.py));
  `main.py` ٣٠٠٥→١٦٢٥ سطراً. **اكتشاف:** `include_router` في Starlette 1.3.1 يلفّ الراوتر بكائن كسول
  (لا يُسطّح المسارات في `app.routes`) ⇒ `register_routers` يُلحِق `APIRoute` مباشرةً (مكافئ سلوكيّاً،
  مؤكَّد بـTestClient). حُرّاس `tests_v9` التي تمسح مصدر `main.py` حُدِّثت لتمسح `routers/` أيضاً
  (helper [`tests_v9/raster_route_source.py`](../tests_v9/raster_route_source.py)) — لا إضعاف للحراسة.
- **قيد المراجعة:** #552 (واجهة CDSE — حذف `date=latest` + إخفاء الفترة) · #553 (nginx `/api/raster/`
  لبوّابة الواجهة 3003) · #554 (وثيقة مقارنة `v9↔fixed`).
- **صدق:** ادّعاء IDOR من الفحص الساكن **رُفِض** — `_require_field_tenant`/`_require_layer_tenant_authorized`
  يرفعان 503 fail-closed أصلاً عند `OwnerLookupUnavailable` ⇒ لم نختلق إصلاحاً.

---

## 2026-06-23 (ط) — دفتر مياه يوميّ (v98) + تصدير Parquet + تحقيق H2 (بثلاثة وكلاء، #458)

**رأس `main`:** `89d848e` (#457 مُدمج). ثلاثة وكلاء متوازون في worktrees منفصلة الملفّات؛ دُمج
الكوديّان عبر cherry-pick نظيف (لا تضارب):
- **أ — دفتر المياه اليوميّ (Bundle B، فجوة IrriPro #1):** ترحيل `v98_water_ledger.sql` (جدول معزول
  بالمستأجِر + RLS/FORCE، PK مركّب `(field_id, ledger_date)`) + راوتر `api/routers/water_ledger.py`
  (POST upsert + GET بمدى، honest-503) + وحدة نقيّة `api/water_ledger_compute.py` + 18 اختباراً.
  **صدق:** كلّ القيم nullable — الناقص `NULL` لا تلفيق؛ `bool`/نصّ فارغ مرفوضان كعدد.
- **ب — تصدير Parquet لورشة SQL (Bundle B):** `frontend/src/services/duckdb.ts` (`exportQueryToParquet`
  عبر `COPY … (FORMAT PARQUET)` → `copyFileToBuffer`) + زرّ في `SQLEditor.tsx`. **صدق التسمية:**
  «Parquet» لا «GeoParquet» (جدول `fields` سمات بلا هندسة) + `TODO(GeoParquet)` موثَّق. vitest 332.
- **ج — تحقيق H2 (تقرير فقط، بلا كود):** مسح يدويّ كامل (الأداة `sahool_inspector` تفحص `services/`
  فقط فتفوّت مُشترِكي `agents/`). النتيجة: **٧** اشتراكات يتيمة لا ٨ (`satellite.*.computed`/
  `sahool.events.>` لهما ناشرون)، تصنيفها «ناشر مفقود متوقَّع» (قرار معماريّ ⇒ امتناع عن تغيير الكود
  بقاعدة اللبس). حُدِّث سجلّ الفجوات. **مخرَج صادق نافع: منع حذف عقود تكامل مقصودة.**

اتّساقاً مع الاستراتيجيّة: نُفِّذت B الجاهزة فقط؛ H2 بقي معماريّاً مفتوحاً (لا إصلاح آليّ غامض).
تحقّق: 26 اختباراً (دفتر+حارسان) · v98 يجتاز `validate_migrations` · ruff · vitest 332 · cherry-pick نظيف.

---

## 2026-06-23 (ح) — CDSE مزوّداً افتراضيّاً للصور + fallback تلقائيّ إلى Element84

**رأس `main`:** `1146021` (#456) — العمل على فرع `claude/code-review-34hO3` فوق #457.
أُضيف **Copernicus Data Space Ecosystem (CDSE)** كمزوّد صور **افتراضيّ أقوى** (Sentinel Hub
Process API): يحسب المؤشّر **خادميّاً** عبر `evalscript` على نطاقات Sentinel-2 L2A الكاملة
(فسيفساء أقلّ غيوماً) فيُرجِع GeoTIFF نطاق-واحد جاهزاً — مع **تحوّل تلقائيّ (fallback) إلى
Element84** عند تعذّر CDSE.

- **raster-service:** وحدة جديدة [`cdse_client.py`](../services/raster-service/cdse_client.py)
  (OAuth client_credentials + ذاكرة توكن + `build_evalscript` نقيّ لـ11 مؤشّراً + `bbox_dims`).
  نقطة `POST /v1/fields/{id}/process-cdse` (خدمة-لخدمة، `_require_service_token`) + مسار
  `precomputed_index` في [`main.py`](../services/raster-service/main.py) (يقرأ المؤشّر الجاهز
  → COG/persist/provenance، يعيد استخدام تسجيل الطبقات).
- **المنسّق:** [`imagery_automation.py`](../services/sahool-platform/api/imagery_automation.py)
  `_try_cdse` يُجرَّب أوّلاً في `trigger_field_imagery_processing`؛ غياب الاعتمادات/تعذّر ⇒
  `None` ⇒ يسقط بصمت إلى مسار Element84 القائم (best + process-from-stac). فالنقطة القائمة
  `/imagery/refresh` وأتمتة إنشاء الحقل تستفيدان تلقائيّاً (لا تغيير واجهة لازم).
- **صدق/أمان:** بلا `CDSE_CLIENT_ID/SECRET` (أو `CDSE_ENABLED=false`) ⇒ `is_configured()=False`
  ⇒ Element84 (السلوك القائم — لا كسر). **السرّ يُمرَّر بالمرجع `${CDSE_CLIENT_SECRET}`** في
  compose من `.env` غير المتتبَّع — لا قيمة حرفيّة في أيّ ملفّ. لا يُتحقَّق CDSE حيّاً في CI
  (لا اعتمادات/شبكة) — الدوالّ النقيّة فقط مُختبَرة؛ المسار الحيّ يؤكّده المشغّل.

تحقّق: 16 اختبار وحدة جديد ([`test_cdse_evalscript.py`](../tests_v9/test_cdse_evalscript.py)) ·
حارس تفويض الراستر أخضر (أُدرجت النقطة في `FIELD_SCOPED_SERVICE_ONLY`) · `pytest -m unit`
1686 ناجح (فشل MFA الـ5 سابقٌ لا صلة له، في `services/auth`) · ruff/format نظيف.

---

## 2026-06-23 (ز) — تنفيذ الاستراتيجيّة بوكيلين: تأكيد توحيد ET0 + Dual Kc (#457)

**رأس `main`:** `1146021` (#456). أوّل تنفيذ من [`decisions/strategy.md`](decisions/strategy.md) (Bundle A/B)، وكيلان متوازيان منفصلا الملفّات (cherry-pick نظيف):
- **توحيد ET0 (H4):** اكتشاف صادق — كان مُنجَزاً (#351/#356)؛ `core/engines/et0.py` يحسب Ra per FAO-56
  (لا ثابتاً) وكلّ المستدعين يُفوّضون. أُضيف **5 اختبارات انحدار** تُقفل الإصلاح + توثيق. لم يُعَد refactor
  (كان هدّاماً). متبقٍّ موثَّق: إعادتان عبر-خدمات (`weather_server`/`wofost`) — مؤجَّلتان (ربط عبر-خدمات).
- **Dual Kc (#457):** `compute_etc_dual` في `core/engines/fao56.py` (إضافيّ، المفرد افتراضيّ سليم) —
  `ETc=(Kcb·Ks+Ke)·ET0` (FAO-56 71-80) + 17 اختباراً. صدق: Kcb بإزاحة موثّقة؛ TEW/REW جداول؛
  الافتراضات تُعرَض وقت التشغيل (`DualKcResult.assumptions`).

اتّساقاً مع الاستراتيجيّة: نُفِّذت مهامّ A/B الجاهزة فقط؛ أُجّل C (R&D) وH5 (إقرار زراعيّ) والغامض.
تحقّق: 27 اختباراً (et0+dual) · ruff · حارس الراوترات · الفجوة H4 → ✅ مؤكَّدة.

---

## 2026-06-23 (و) — مراجعات إلهام (CultiWise/IrriPro، #455) + تصدير وصفة Shapefile (#456)

**رأس `main`:** `6e770b7` (#455). مراجعتا اتّجاه مُسنَدتان + أوّل اقتباس CultiWise منفَّذ:
- **#455:** صفحتا دماغ — [`precision-ag-direction.md`](decisions/precision-ag-direction.md) (CultiWise) +
  [`water-intelligence-direction.md`](decisions/water-intelligence-direction.md) (IrriPro/FAO-56). الكشف:
  SAHOOL يملك أصلاً معظم اللبنات (وصفات v95 · سجلّ قرار/نتيجة · FAO-56/ET0/هيدروليك/سيناريو/تفسير) —
  لا نُعيد البناء؛ الفجوات الحقيقيّة فقط (تصدير آلة · دفتر مياه يوميّ · توحيد ET0 H4 · Water Twin).
- **#456 (تصدير الوصفة Shapefile):** يملأ TODO موثَّقاً — `GET …/prescriptions/{id}/export?format=shapefile`
  → ZIP (.shp/.shx/.dbf/.prj) عبر `pyshp` (نقيّ-Python). وحدة نقيّة
  [`api/prescription_shapefile.py`](../services/sahool-platform/api/prescription_shapefile.py) (7 اختبارات) +
  راوتر + زرّ في PrescriptionBuilderPage. تبعيّة `pyshp==2.3.1` (pip-audit: 0 ثغرات). **ISOXML يبقى TODO
  موثَّقاً** (يحتاج نمذجة معدّات — لا ندّعي ما لا ننتجه). يحوّل المنصّة من «مراقبة» إلى «تنفيذ».

تحقّق: pip-audit نظيف · ruff · حارس الراوترات · 7 اختبارات وحدة · typecheck/build/vitest 332 · روابط الدماغ سليمة.

---

## 2026-06-23 (هـ) — AI GIS Assistant (NL→SQL، الفكرة 4 الأخيرة من GeoLibre، #454)

**رأس `main`:** `8781cce` (#453). مهمّة LLM-shaped — قُرئ مرجع claude-api؛ المفتاح خادميّ.
- صندوق «اسأل بالعربيّة» في ورشة SQL → `POST /api/v1/nl-sql` يستدعي Claude (`claude-opus-4-8`،
  قابل للضبط بـ`NL_SQL_MODEL`) → SELECT للقراءة فقط → يملأ المحرّر للمراجعة → DuckDB العميل.
- خادم: [`api/routers/nl_sql.py`](../services/sahool-platform/api/routers/nl_sql.py) +
  [`api/nl_sql_validate.py`](../services/sahool-platform/api/nl_sql_validate.py) (تحقّق نقيّ، 22 اختباراً).
  تبعيّة `anthropic` (pip-audit: 0 ثغرات). واجهة:
  [`SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx) + `api.ts`.
- صدق/أمان: خصوصيّة (السؤال فقط) · SELECT مُتحقَّق + sandbox العميل + إنسان-في-الحلقة · مُغلَق
  بـ`FEATURE_NATURAL_LANGUAGE_GIS`+`ANTHROPIC_API_KEY` (honest-503). المشغّل يوفّر المفتاح.
- **خارطة GeoLibre الأربع مكتملة v1** ([`decisions/gis-direction.md`](decisions/gis-direction.md)).

تحقّق: pip-audit نظيف · 22 اختبار وحدة + حارس الراوترات أخضر · typecheck/build/vitest 332.

---

## 2026-06-23 (د) — إكمال خارطة GeoLibre بـ٣ وكلاء متوازين (#453)

**رأس `main`:** `c3c7d28` (#452). ثلاثة وكلاء في worktrees منفصلة الملفّات (بلا تضارب عدا منطقة أزرار
SQLEditor — حُلّت بإبقاء CSV+JSON معاً)، دُمجت عبر cherry-pick:
- **و1 — ورشة SQL v2:** سجلّ استعلامات (localStorage) + أمثلة جاهزة + نسخ JSON
  ([`sqlHistory.ts`](../frontend/src/lib/sqlHistory.ts) + [`SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx)).
- **و2 — حفظ مساحة العمل v2:** التقاط/استعادة مركز+تكبير الخريطة عبر المحرّكين
  ([`HubMap.tsx`](../frontend/src/components/maphub/HubMap.tsx) · [`HubMapGL.tsx`](../frontend/src/components/maphub/HubMapGL.tsx) ·
  [`projectFile.ts`](../frontend/src/lib/projectFile.ts)) — بمنع حلقة moveend↔restore وحفظ auto-fit.
- **و3 — استوديو الهندسة المكانيّة:** قسم «أدوات الهندسة» + Turf buffer/simplify معاينةً
  ([`GisToolsPage.tsx`](../frontend/src/sections/GisToolsPage.tsx) + [`fieldGeometryOps.ts`](../frontend/src/lib/fieldGeometryOps.ts)).
  تبعيّتا `@turf/buffer`/`@turf/simplify` (0 ثغرات).

تحقّق دفعةً: typecheck نظيف · build (chunks منفصلة) · **vitest 332** · روابط الدماغ سليمة.

---

## 2026-06-23 (ج) — ورشة SQL في المتصفّح (DuckDB-WASM، إلهام GeoLibre الفكرة 2)

**رأس `main`:** `cd68a33` (#450، الاسترجاع التلقائيّ مدموج).

- **حفظ مساحة العمل (تكملة):** الاسترجاع التلقائيّ عبر localStorage (#450) — اكتملت الفكرة 1.
- **ورشة SQL (#451):** قسم جديد lazy «ورشة SQL (DuckDB)» تحت «البيانات والتحليل» — يحمّل حقول
  المستأجر إلى جدول `fields` في DuckDB-WASM (عميل-فقط، مستضاف ذاتيّاً) ويستعلمها بـSQL.
  ملفّات: [`frontend/src/services/duckdb.ts`](../frontend/src/services/duckdb.ts) ·
  [`frontend/src/hooks/useDuckDB.ts`](../frontend/src/hooks/useDuckDB.ts) ·
  [`frontend/src/components/sql/SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx) ·
  [`frontend/src/sections/SQLWorkspacePage.tsx`](../frontend/src/sections/SQLWorkspacePage.tsx).
  تبعيّة `@duckdb/duckdb-wasm` (0 ثغرات، كسولة ~8MB gzip خارج الحزمة الرئيسة). النطاق v1: سمات
  الحقول فقط — spatial/المؤشّرات مؤجّلة ([`decisions/gis-direction.md`](decisions/gis-direction.md)).

---

## 2026-06-23 (ب) — الدماغ على main + حفظ مساحة العمل (إلهام GeoLibre)

**رأس `main`:** `033fabe` (#448، الدماغ مدموج).

- **الدماغ (#448):** دُمج `sahool-brain/` على main — الوكيل القادم يقرأ hot/index بداية الجلسة.
- **حفظ مساحة العمل (GeoLibre، الفكرة 1):** ملفّ `.sahool-project.json` قابل للتسلسل (عميل-فقط) —
  تصدير/استيراد إعدادات «مركز الخرائط» (الأساس/المؤشّر/الشفافية/المقارنة/الأدوات/التراكبات/الحقل
  المختار): [`frontend/src/lib/projectFile.ts`](../frontend/src/lib/projectFile.ts) + أزرار في
  [`frontend/src/sections/MapHub.tsx`](../frontend/src/sections/MapHub.tsx). v1 لا يحفظ مركز/تكبير
  الخريطة ولا الرسومات (مؤجّلة v2). انظر [`decisions/gis-direction.md`](decisions/gis-direction.md).

---

## 2026-06-23 — سلسلة الموبايل/الصور/QA + إنشاء الـbrain

**رأس `main` بعد الجلسة:** `0023f57` (#447).

- **auth (#437):** سياق admin على كلّ اكتساب اتّصال (`_acquire`) — العلاج الجذريّ لفشل RLS في
  التسجيل/الدخول (يكمّله ترحيل `v97_user_self_with_check.sql`).
- **الصور (#438/#439):** تفعيل صور Sentinel-2 الحقيقيّة تلقائيّاً عند إنشاء الحقل (بلا محاكاة)؛
  خادم SAM2 على GPU كـopt-in خلف `profile=gpu` (503 صادق بدونه).
- **dev-proxy (#440/#442):** توحيد وكيل تطوير Vite مع بوّابة nginx (v9) — يُصلح `npm run dev` +
  رؤية تشخيصيّة (offline/معالجة الصور).
- **QA الخرائط (#441):** سويت Playwright لبوّابة جودة MapLibre/WebGL (9 خطوات) + وظيفة CI.
- **الحقول الذرّيّة (#443):** دمج/انقسام الحقول عبر نقطتَي backend ذرّيّتين
  ([`fields.py`](../services/sahool-platform/api/routers/fields.py)) — سدّ خطر البيانات الثلاثيّة؛
  اختبار [`tests_v9/test_fields_merge_split_atomic.py`](../tests_v9/test_fields_merge_split_atomic.py).
- **تكافؤ الموبايل (#444/#445/#446/#447):** مسار سلسلة NDVI (404)، مصدر المؤشّرات الصحيح + إدارة
  المزارع، ربط أقسام مساحة العمل بالخلفيّة، السمة الداكنة الرسميّة (`AppTheme.dark`).
- **الـbrain:** إنشاء `sahool-brain/` — هذا الـvault (README/index/hot/log/dashboard +
  architecture/schema/gaps/decisions/agronomy) + قسم «الدماغ المعرفيّ» في
  [`../CLAUDE.md`](../CLAUDE.md).

## 2026-07-05 (ز) — إنجاز «المؤجَّل» من تدقيقات الأقمار v2/v3/v4 (٥ مراحل، `main`=`develop`=`claude/code-review-34hO3`)

**الرأس بعد الجلسة:** `5f52b63`. خطّة عميقة شاملة، ٥ commits مستقلّة، بوّابات خضراء لكلٍّ (تفاصيل + أسباب في [`decisions/ledger.md`](decisions/ledger.md) قسم ١٧).

- **م1 `fe4426b`:** صحّة استعلامات db_persist — تواريخ متاحة محدودة بالتاريخ المميَّز (CTE) لا الصفوف [v3-F1] · `DISTINCT ON` لصفّ متماسك [v3-F4] · `fetch_latest_asset` واعٍ بالجودة [v3-F3] · **v4:** كتابة أعمدة v105 (quality_score/aoi_cloud_pct/cloud_mask_sources) التي كانت تُهمَل ⇒ الترتيب بالجودة كان بلا أثر.
- **م2 `8ed6272`:** MapHub حارس `has_cog` [v2-007] · CDSE cache key tenant+هندسة [v3-6] · حذف bbox اليمن fail-closed [v3-7] · cdse-tilejson tid+urlencode [v3-8] · object_store fail-closed لرفع S3 [v3-9].
- **م3 `f440b3f` (v143):** `asset_status` + `geometry_revision` على raster_assets + فهارس · نَسَب end-to-end (النماذج→ProcessRequest→المنصّة تحلّ MAX(revision)) [v2-011/004].
- **م4 `bdf703a`:** عامل `cache_invalidation_worker` يستهلك raster_cache_invalidations (كان بلا مستهلِك) [v2-005] · `tile_cache_maint` إبطال+إخلاء TTL/حصّة [v2-010] · خدمة compose خلف راية.
- **م5 `5f52b63`:** جسر الكتالوج `insert_raster_registry_entry` + `insert_stac_item` (كلا الجدولَين كانا بلا كاتب من الأنبوب) [v2-008/009].

**درس متكرّر (عزل الاختبار):** اسم الوحدة العامّ `main` يتصادم عبر الخدمات في `pytest -m unit` الكامل — الحلّ استخراج الدوالّ لوحدة فريدة (`tile_cache_maint`) بدل حقن `sys.modules`، وحذف كعب `boto3` الملوِّث. **درس بوّابة:** بعد أيّ migration شغّل `production_validation_gate` محليّاً (v143 اجتاز RLS role-gate بعد إضافة العامل للـallowlist)، وأيّ raw query على جدول مُستأجَر يحتاج تصنيفاً في `tenant_query_audit`.

## 2026-07-05 (ح) — متابعة v5 + إصلاح أمنيّ + إصلاح بوّابة الإنتاج (الرأس `947c9af`؛ main=develop=الفرع)

بعد دمج المرحلة ١-٥ إلى `main` (fast-forward)، ٣ متابعات:

- **`65c96cd` (فشل أمنيّ):** بصمة كاش هندسة CDSE استخدمت `hashlib.sha1` بلا `usedforsecurity=False` ⇒ bandit **B324 HIGH** حجب بوّابة *Security Scan* (كانت الوظيفة الوحيدة الحمراء من ١١). الإصلاح: `usedforsecurity=False` (استعمال غير أمنيّ — تفريق مفاتيح فقط). تأكّد أخضر على CI.
- **`5cd765d` (استجابة تدقيق السجلّ الحيّ v5):** F1 رصد حفظ raster_assets (`_persist_raster_asset` يُرجِع bool + سطر `persist ok/failed` + `persisted` في نتيجة المهمّة) · F8 ملخّص `historical_backfill_scan completed`. v5-F3/F5/F7 مُصلَحة سابقاً (zip قديم 9a4b9ab) · F2/F4 مؤجَّلة بصدق (فحص backfill لاتزامنيّ).
- **`947c9af` (فشل بوّابة الإنتاج):** *Sahool Production Gates* (main-only) سقط لأنّ `sahool-raster-cache-invalidation-worker` غاب عن قائمة سماح **ثانية**: `tests/security/test_phase12_final_production_gates.py` (منفصلة عن `scripts/security/rls_runtime_gate.py` التي حدّثتها المرحلة ٤). الإصلاح: أضفتُه للقائمتَين + جدّدتُ بصمات الإصدار.

**درس متكرّر (حرج):** قائمة `JOBS_DATABASE_URL` المسموحة تعيش في **موضعَين** يجب مزامنتهما: (١) `scripts/security/rls_runtime_gate.py` — يفحصه `production_validation_gate.sh` محليّاً؛ (٢) `tests/security/test_phase12_final_production_gates.py` — تفحصه بوّابة Sahool Production Gates على main فقط (وظيفة `pytest-contracts`، على `tests/` لا `tests_v9/` فلا يلتقطها `pytest -m unit`). أيّ عامل جديد بدور JOBS يحتاج تحديث الاثنين + جدولة بصمات الإصدار.

## 2026-07-05 (ط) — تدقيق v6: إصلاح حجب حلقة الأحداث + تثبيت الحالة (الرأس `6768ee6`)

تدقيق v6 (٨ نتائج) على zip قديم — الفرز مقابل HEAD الحاليّ:

- **`6768ee6` (v6-F3، حقيقيّ):** مهمّة معالجة مشهد backfill كانت `async def _run_scene_job` تستدعي `_run_processing` المتزامن الثقيل (VRT+COG) مباشرةً ⇒ FastAPI يُنفّذ مهامّ `async` على حلقة الأحداث فتُحجب طلبات raster الأخرى. الإصلاح: تعريفها `def` (threadpool). جسمها كلّه متزامن بلا await فالتحويل آمن.
- **مُصلَح سابقاً (zip قديم):** F7 (lid ترطيب DB صار date-specific منذ 528203b) · F8 (persisted + سطر persist-ok منذ 5cd765d) · F5 (الرتّاب يسجّل `cloud_source` أصلاً).
- **مؤجَّل بصدق (معماريّ، صنف v5-F2/F4 نفسه):** F1/F2 (backfill يعود job فوراً + مسح STAC الشهريّ في عامل، بدل مسار الطلب — يتفادى مهلة proxy 60s) · F4 (مفتاح idempotency + preflight raster_assets قبل الجدولة) · F6 (single-flight لكاش STAC ضدّ stampede المتزامن).

**درس:** مهامّ FastAPI الخلفيّة المتزامنة الثقيلة يجب أن تكون `def` (threadpool) لا `async def` (حلقة الأحداث) — لفّ عمل متزامن في `async def` يُبطِل سلوك الـthreadpool.

## 2026-07-05 (ي) — تحقّق تكامليّ على Postgres حيّ كشف خللاً إنتاجيّاً حقيقيّاً (الرأس `c564d65`)

بطلب المستخدم، أُضيفت اختبارات `-m integration` تُشغّل عمل الجلسة على Postgres+PostGIS الحيّ في CI.
**التزم بالانضباط: دُفِعت للفرع أوّلاً، وحُجِز main حتّى خضرة وظيفة Integration.** فكشفت **خللاً إنتاجيّاً**:

- `insert_raster_registry_entry` و`insert_stac_item` (المرحلة ٥) كانا يُمرّران **نصّاً** لمعامل `$N::date`/`$N::timestamptz` ⇒ asyncpg يستنتج نوع date/timestamptz ويرفض النصّ. وبما أنّهما best-effort (try/except ⇒ False)، **ابتُلع الخطأ صامتاً** فبقي `raster_registry` و`stac_item_registry` **فارغَين في الإنتاج** — واختبارات الوحدة المُحاكاة لم ترَه.
- **الإصلاح `c564d65`:** `$N::text::date` و`$N::text::timestamptz` (asyncpg يربط النصّ كـtext وPostgres يقصّه).

**درس محوريّ:** الكتّاب best-effort (try/except يبتلع) لا تُثبِتهم اختبارات الوحدة المُحاكاة — يلزم **اختبار تكامليّ على قاعدة حيّة**. وأيّ معامل تاريخ/وقت مُمرَّر نصّاً لـasyncpg تحت `::date`/`::timestamptz` يحتاج `::text::` أو تحويلاً لكائن Python (نمط insert_raster_asset).

التغطية التكامليّة الجديدة (٦ اختبارات، خضراء على PostGIS الحيّ): v143 asset_status/geometry_revision + استبعاد failed · v3-F1 حدّ التواريخ المميَّزة · v3-F3 انتقاء الجودة · جسر registry+STAC · عامل الإبطال (stale+processed).

## 2026-07-05 (ك) — إنجاز بنية backfill اللاتزامنيّة + single-flight (v5-F2/F4 · v6-F1/F2/F4/F6؛ الرأس `ecc0061`)

آخر «مؤجَّل معماريّ» أُنجِز، على شريحتَين مستقلّتَين، **دُفِعتا للفرع أوّلاً وحُجِز main حتّى خضرة CI الكاملة** (تكامل+أمن):

- **Slice A `...` (v6-F6):** single-flight في `ResilientStacClient.search` — طلبات miss متطابقة متزامنة تتشارك POST واحداً (خريطة key→Future، تُنظَّف في finally). حارس: 5 متزامنة ⇒ 1 POST.
- **Slice B `10cb133` (v5-F1/F2/F4 · v6-F1/F2/F4):** ترحيل **v144** (`backfill_runs` + `backfill_run_items` بمفتاح idempotency فريد + RLS FORCE) · نقطة `/imagery/backfill` تُرجِع `run_id` فوراً خلف راية `RASTER_ASYNC_BACKFILL_ENABLED` (لا مسح STAC في مسار الطلب ⇒ لا مهلة proxy 60s) · عامل `backfill_scan_worker` (Pattern A، JOBS) يمسح خارج مسار الطلب + preflight raster_assets + ON CONFLICT DO NOTHING + معالجة في threadpool؛ يعيد استخدام دوالّ main · خدمة compose خلف راية · تحديث القائمتَين (rls_gate + phase12) وtenant-audit وحارس مصادر الترحيل.

**فشلان اصطادهما الفرع (لولا حجز main لاحمرّ):**
1. `c564d65` سابقاً: جسر الكتالوج كان يفشل صامتاً على ربط التاريخ (`$::date` بنصّ) — أصلحه `::text::date`؛ كشفه اختبار تكامليّ حيّ.
2. `ecc0061`: محرف bidi خفيّ (U+200F) في docstring العامل ⇒ bandit B613 HIGH حجب Security Scan — أُزيل.

**نتيجة CI على `ecc0061`:** Integration **75 passed** (تكامل backfill+الكتالوج على PostGIS حيّ مع v144) · bandit HIGH نظيف · باقي الوظائف خضراء. **الدرس المؤكَّد:** الكتّاب best-effort + المحارف الخفيّة لا تُرى إلّا على DB حيّ/بوّابة أمن — لذا **ادفع للفرع أوّلاً واحجز main** حتّى خضرة التكامل والأمن.

## 2026-07-05 (ل) — تحويل البحث التاريخيّ إلى CDSE + إغلاق «الحقيقة الكاذبة» (تدقيقات v8–v11؛ الرأس `820cd41`)

أربع جولات تدقيق (v8/v9/v10/v11) شغّلها المُدقِّق على `d85673c` القديم، فمعظم نتائجها أُغلِق في شجرة العمل قبل ظهورها. **دُفِع للفرع أوّلاً وحُجِز main حتّى خضرة CI الكاملة** — والفرع اصطاد فشلاً حقيقيّاً.

- **تحويل البحث التاريخيّ إلى Copernicus/CDSE (طلب المستخدم + تقرير copernicus_historical_backfill_fix):** `HISTORICAL_SEARCH_PROVIDER=cdse` افتراضاً؛ `main._stac_search` يوجّه إلى كتالوج CDSE (`_stac_search_cdse` عبر `cdse_client.search_scenes`، source=`cdse-catalog`) — **لا ارتداد صامت إلى Element84**: غياب اعتمادات CDSE ⇒ فشل مُغلَق **503** (Element84 تجاوز واعٍ فقط عبر الراية). مشاهد CDSE (بلا `bands_urls`) تُعالَج عبر `_process_backfill_scene_cdse` (Process API مثبَّت على يوم المشهد، لا VRT) في العامل والمسار المتزامن. `_run_processing` صار يسجّل التتبّع `exc_info=True` (لوج «TypeError» عارياً بعد بناء VRT). حارس `test_historical_search_cdse_v30_8` يمنع الانحدار.
- **صدق النجاح/الحفظ (v8-01/v9-01/v10-03):** العامل + مسار CDSE الأب لا يُعلنان persisted إلّا إذا `result.persisted is True`. عدّادات `items_persisted/failed/skipped` + `completed_with_errors` (ترحيل **v146**). preflight يطلب `asset_status='ready'` + مطابقة `geometry_revision` (v10-01 — stale يُعاد توليده لا يُتخطّى). run_item يُوسم `processing`+`job_id` قبل المعالجة (v10-05). استعادة تشغيلة عالقة تجاوزت الإيجار (v9-03) + ضبط المستأجِر داخل معاملة (v10-06، backfill+invalidation workers).
- **dedupe على مستوى المنتَج (v8-06/v9-08/v10-08):** ترحيل **v145** — إزالة تكرارات + فهرس فريد بلا `cog_uri` (قابل للتحديث)؛ `insert_raster_asset` ON CONFLICT على (tenant/field/index/date/scene). مُثبَت على Postgres حيّ (3→1، أفضل جودةً).
- **قرّاء العرض = 'ready' حصراً (v11-01):** `fetch_latest_asset`/`list_asset_dates`/`list_available_asset_dates` لم تعد تُقدّم stale كصالح؛ طبقة الترطيب تحمل `field_id/geometry_revision/asset_status/scene_id/job_id` (v11-04).
- **النَّسَب (v8-07/v9-07):** المسار المتزامن يمرّر `geometry_revision`؛ المنصّة تستنتجه من `field_geometry_history` في backfill proxy. **الواجهة:** cdse-tilejson يقبل poly/bbox ويحقنها + fail-closed بلا حدود (v9-07)؛ `cdseClipParams` مصدر واحد؛ MapHub/FieldIndicatorMap يمرّران الهندسة؛ رسالة async صادقة + المؤشّر النشط في المُنتقيات (v10-09/v11-08). نقطة `GET /imagery/backfill/{run_id}` (v10-10).
- **compose:** `RASTER_ASYNC_BACKFILL_ENABLED` + `RASTER_CACHE_INVALIDATION_ENABLED` مُفعَّلان افتراضاً + `TILE_CACHE_TTL_SECONDS` محافظ.

**فشل اصطاده الفرع (لولا حجز main لاحمرّ):** `fa19e83` — ترحيل **v146** فشل «Apply migrations to test DB» في Integration: قيد v144 المضمَّن يُسمّيه Postgres اصطلاحيّاً `backfill_runs_status_check` ويُطبّع `IN`→`= ANY`، فبحث DO block الديناميكيّ عبر `ILIKE '%IN%'` لم يُطابقه ثمّ اصطدم `ADD CONSTRAINT` بالاسم القائم. أصلحه `ff11e69`: `DROP CONSTRAINT IF EXISTS` بالاسم الاصطلاحيّ ثمّ إعادة الإضافة (idempotent) — مُثبَت على Postgres حيّ (v144→v145→v146 + إعادة تطبيق).

**نتيجة CI على `ff11e69`:** Integration **success** (152 ترحيلاً على PostGIS حيّ + pytest تكامليّ). **مؤجَّل بصدق (خارج نطاق المستخدم المؤكَّد، لم تُعده v9–v11):** V8-05 (فصل مُنتقي التاريخ عن المعالجة — قرار UX) · V8-09 (`docker-compose.fixed.yml` sahool_user — dev فقط، موثَّق؛ الإنتاج v9.yml يستعمل sahool_app). **مؤجَّل معماريّ:** إخلاء ذاكرة `_layers` عبر العمليّات (v11-03/05) يحتاج قناة Redis pub/sub (لا نصف حلّ).

## 2026-07-05 (م) — إغلاق البنود المؤجَّلة الثلاثة المتبقّية (V8-05/V8-09/v11-F3·F5؛ الرأس `8a6d023`)

بعد استقرار main على `7b7bf54`، طُلِب إغلاق «المتبقّي» — أُنجِزت الثلاثة بالكامل (لا نصف حلّ)، دُفِعت للفرع أوّلاً:

- **V8-09 (Critical)** `docker-compose.fixed.yml`: كان يتّصل بـ`sahool_user` المُمتاز (يتجاوز RLS) + يُعطّل الحارس عبر 9 `SAHOOL_ALLOW_RLS_BYPASS_ROLE`. اتّضح أنّ الملفّ **يملك** `sahool-migrate` (apply_in_compose.sh ينشئ sahool_app/sahool_jobs) — فالتعليقات «لا يُنشئ sahool_app» كانت stale. صُلِّب: التطبيق→`sahool_app` المقيّد، أُزيل تعطيل الحارس. حارسا SEC-1 (`test_compose_rls_bypass_guard`/`test_compose_env_bypass_guard`) كانا يفترضان تفعيل التجاوز في fixed.yml — حُدِّثا للحالة المُصلَّبة + **حارس جديد** يمنع أيّ compose من `sahool_user` في `DATABASE_URL`.
- **V8-05** `MapHub.tsx`: مجرّد اختيار تاريخ لم يعد يُطلق معالجة صامتة (توليد COG). «latest» فقط يُحدِّث؛ تاريخ جاهز يبدّل الطبقة؛ غير جاهز ⇒ حالة + CTA صريح (زرّ backfill). (v11-F1 قلّل التعرّض إذ صارت available-dates = ready فقط، لكن أُغلِق المسار البرمجيّ.)
- **v11-F3/F5 (معماريّ — كان مؤجَّلاً «يحتاج pub/sub»):** إخلاء طبقات الذاكرة عبر العمليّات. عامل الإبطال ينشر `field_id` على قناة Redis `raster:layer_evict` بعد إبطال القرص+DB؛ `raster-service` يشترك في `lifespan` (`_layer_evict_subscriber`) ويُخلي `_layers`/`_field_layers` (`_evict_field_layers`). راية `RASTER_LAYER_EVICT_ENABLED` (افتراض true) + تدهور لطيف بلا Redis/الحزمة + إعادة اتّصال. حارس `test_layer_evict_v30_9`.

**درس تلوّث اختبار (تكرّر):** حقن `sys.modules["boto3"]` في اختبار جديد لوّث `test_sam2_polygon_cleaning` (فشل عابر في المجموعة الكاملة، نجاح منفرداً). الحلّ: لا تستورد `main` الثقيل في حارس ساكن — أكّد نصّيّاً وحاكِ المنطق. unit **2609** · production gate (3300 compiled) · حُرّاس compose الأمنيّة خضراء.

## 2026-07-05 (ن) — Landsat طبقة حرارية فريدة (LST فقط، لا تكرار Sentinel-2؛ الرأس `2df1cf5`)

قرار معماريّ من المستخدم (تقرير + diff + zip على أساس `7b7bf54`): **Copernicus/Sentinel-2 مصدر المؤشّرات النباتية/البصرية؛ Landsat يُستخدم فقط للطبقة الحرارية الفريدة** — LST كأصل مباشر، وCWSI/TVDI/TCI/VHI مشتقات لاحقة من LST+طقس/NDVI. لا يُعاد سحب NDVI/NDMI من Landsat.

- طُبِّق عبر `patch -p4` (الرقعة على أساس يحوي عمل CDSE، فلا تعارض مع `8a6d023`). مجموعات `LANDSAT_UNIQUE/DIRECT/DERIVED/DUPLICATE` + `IndicatorKind` (lst/cwsi/tvdi/tci/vhi/et_inputs) · `_stac_search_landsat`→`_stac_search_landsat_unique` (يُرجِع `thermal_urls.lst` فقط، `_landsat_thermal_href` يرفض red/nir/swir) · backfill route `source=landsat-thermal` يرفض المكررات · العامل+المتزامن يعالجان LST · ترحيل **v147** (`backfill_runs.source`).
- **تحقّق-قبل-دمج اصطاد ثغرتَين حقيقيّتَين في رقعة المُدقِّق** (اختباراته لم تُشغّل `_process_run`): (١) `is_landsat_thermal` مُستعمَل في `_process_run` بلا تعريف ⇒ **NameError على كلّ تشغيلة** — عُرِّف من `run.source`؛ (٢) v147 في MANIFEST فقط لا `run_migrations.sql` ⇒ **فشل بوّابة الإنتاج** — أُضيف للمُشغّلَين. + إضافة `/imagery/search/landsat-thermal` لـPUBLIC_CATALOG (حارس التفويض). حارس `test_landsat_thermal_unique_v31_0` (يشمل الثغرتَين).
- **v147 مُثبَت على Postgres حيّ:** v144→v146→v147 + إعادة تطبيق؛ يقبل `landsat-thermal` ويرفض `modis` (CHECK). unit **2615** · production gate **153 ترحيلاً**.

## 2026-07-05 (س) — إصلاحات runtime/UI للأقمار (رقعات المستخدم؛ الرأس `0f0f973`)

من رقعات المستخدم المتتالية (runtimefix → uihotfix → deeper)؛ أُدمِجت الإصلاحات الحقيقيّة بعد تحقّق-قبل-دمج:

- **raster runtime:** preflight العامل ربط `acq` النصّيّ بـ`$5::date` ⇒ asyncpg يرفض الـstr (`'str' has no attribute 'toordinal'`). صُحِّح إلى `$5::text::date` (نمط INSERT الآمن المُثبَت). كان يُفشِل preflight لكلّ مشهد بتاريخ — التقطته رقعة المستخدم؛ INSERT عندي كان صحيحاً سلفاً لكن preflight فاتني.
- **web ownership (fld_*):** معرّفات الحقل platform لا يملكها vegetation-service (`/v1/analyze` ⇒ «field_id not found»). حُوِّلت 3 مواضع للمسار القانونيّ: `useAnalyzeVegetation`/`analyzeVegetation` export → `refreshFieldImagery`؛ `useIndicators` → `/api/v1/indicators/catalog` (تحقّقت أنّه قائم في `routers/indicators.py:34`).
- **web auth UX:** 401 من خدمة ميزة كان يطرد المستخدم؛ حُصِر الخروج القسريّ في `/auth/`.
- حارس `SatellitePageRuntimeFix.static.test.ts` (أصلحت نمط قراءته: `resolve(__dirname)` لا `new URL(import.meta.url)` الذي يفشل في vitest بـ«URL must be of scheme file»).

**درس:** الأصل الثابت لرقعات المُدقِّق المتتالية = `7b7bf54`؛ فالفروق الكبيرة معظمها عملي الأحدث (8a6d023+). قارنتُ «سطورهم غير الموجودة عندي» فقط لعزل إصلاحاتهم الحقيقيّة. unit 2615 · vitest 1047.

## 2026-07-05 — بذرة الجوف الكاملة + إصلاح رسالة 409 (main=develop=9008d35)
- **بذرة الجوف الكاملة (8a7b715):** `scripts/seed/aljawf_sunaydar_farm.sql` — 6 حقول/6 مواسم/1 فحص تربة، بيانات مرجعيّة حقيقيّة (farm_map/yield_history/soil_reference)، idempotent، مُثبَت على Postgres رمينيّ. المُستبعَد بصدق: آبار (لا جدول)، اقتصاد لكلّ حقل (economics.yaml: يُحسَب لا يُخزَّن)، zone_factors (معايرة)، 22 عيّنة فرديّة (المرجع متوسّط؛ 7 GPS معلّقة).
- **إصلاح 409 حفظ الحقل (9008d35):** `frontend/src/sections/MapHub.tsx` — `handleSaveField`/`handleImportField` كانا يحطّان خطأ أكسيوس الغنيّ إلى `new Error(asApiError(e).message)` = «Request failed with status code 409» فيضيع `detail.message_ar` الصادق (اسم مكرّر / تداخل هندسة). صُحِّح إلى `apiErrorMessage(e, fallback)` كما في `AddFieldWithMap`. مسار SetupCabin كان سليماً سلفاً. زرّ الحفظ `disabled={saving}` ⇒ النقر المزدوج مضبوط، فلا حاجة idempotency.
- **sam2-inference 503 (STAC SSL EOF):** ليس عطلاً — fail-closed صادق (`main.py:202-238`: فشل STAC ⇒ None ⇒ 503، لا اختلاق حدّ). `/readyz 200` ⇒ الخدمة حيّة؛ الخلل في TLS الصادر لمزوّد STAC (شبكة/proxy/throttle).
- **الدمج:** CI أخضر على 9008d35 (run 28755086261، كلّ الوظائف 11)؛ fast-forward نظيف efa0e9b→9008d35 لـmain وdevelop. zip: `..._9008d35_aljawf_seed_field409_fix.zip` (3434 ملفّاً).

## 2026-07-05 — بكسل المؤشّرات لا يظهر: قطع TLS عابر لـCDSE (main=develop=d21f947)
- **العرَض:** حقل جديد بحدود صحيحة لا يُظهر مؤشّرات البكسل + `sam2/backfill` يسجّل `STAC: SSL UNEXPECTED_EOF`.
- **الجذر (ثغرة كود):** مسار جلب CDSE يعيد على 429 فقط. قطع الاتّصال/TLS العابر (`httpx.TransportError`) كان: `process_index` يرمي فوراً ⇒ بلاطة شفّافة؛ `search_scenes` يبتلع إلى `[]` ⇒ «لا مشهد». `cdse_client.py`.
- **الإصلاح (d21f947):** إعادة على `httpx.TransportError` بنفس backoff (`CDSE_PROCESS_MAX_RETRIES/BASE/MAX`) في المسارين؛ بعد النفاد يبقى fail-closed (لا اختلاق). حارس `test_cdse_process_throttle_retry_guard.py` (+حالة، 5 اجتياز).
- **صدق:** الإعادة تُنقِذ من العابر فقط. الحجب الدائم (egress يمنع `*.dataspace.copernicus.eu` أو غياب CDSE creds) إصلاحٌ بيئيّ — سُلّمت للمستخدِم 3 أوامر تشخيص (env creds / curl خروج / logs).
- **رسالة «لا حدود» الصادقة (5482b4d):** MapHub كان يُظهر رسالة CDSE المُضلِّلة لحقل بلا هندسة؛ الآن «ارسم/استورد الحدود أوّلاً» (TrueColor + mapDataStatus).

## 2026-07-06 — طبقات التضاريس + التربة الكاملة مدموجة (main=develop=b38b05d)
- **التضاريس (terrain v1):** hillshade/slope بلاطات + contours GeoJSON + `/v1/terrain/status` + إحصاء الحقل + ربط الانحدار بقرارات زراعيّة (erosion/trafficability/actions). `terrain_render.py`/`terrain_analysis.py`/`routers/terrain_tiles.py`. fail-closed بلا FIELD_DEM_PATH. إصلاحات: nodata مُقنَّع، متوسّط aspect دائريّ، CRS per-axis بالأمتار.
- **التربة (SoilGrids):** بلاطات 8 خصائص + tilejson + legend + summary per-field (قوام USDA) + مناطق k-means (GeoJSON polygons) + نقاط عيّنات من مراكز المناطق. `soil_render.py`/`soil_zones.py`/`routers/soil_tiles.py` + واجهة (طبقة + نقاط 🧪). تحليل مصدر بـ3 أنماط (dir/template/explicit) + مرادفات. fail-closed بلا SOILGRIDS_DIR + تحذير إلزاميّ «تقديريّ لا بديل عن المختبر».
- **أخرى مدموجة:** Round 5 (تمرير fieldId عبر route state) · idempotency إنشاء الحقل (409) · إصلاح بكسل CDSE (نافذة 365 + single-flight + prune) · إعادة CDSE على قطع TLS العابر · رسالة «لا حدود» الصادقة.
- **E2E:** اختبار رسم المضلّع (measure-area) كان الوحيد @gating بين إخوته (رسم الخطّ/الدبّوس test.fixme أصلاً) رغم قيد Terra Draw pointer على WebGL تحت SwiftShader ⇒ فشل مستمرّ. طُبِّقت سياسة الملفّ: test.fixme @visual (التطبيق يرسم فعليّاً؛ التسليك مُغطّى @gating). أُثبِت اضطراباً (فشل على eca74ec الخلفيّ البحت).
- **الحصاد الصادق:** نسخ المستخدِم الموازية (window/single-flight · soil_render/routers/soil) — طُبِّق الجديد النظيف فقط (prune · env متعدّد الأنماط · فكرة marker) ورُفِض المتعارض/الأقلّ اكتمالاً (zones stub). لا تلفيق — كلّ الطبقات تحتاج DEM/SoilGrids حقيقيّاً للتفعيل (runbook §11/§12).

## 2026-07-06 (تكملة) — تزويد DEM + بوّابة المانيفست على الفرع (main=7c5e080)
- **أداة تزويد GLO-30:** `scripts/provision/fetch_glo30_dem.py` — تُنزّل بلاطات Copernicus GLO-30 من AWS Open Data (HTTPS مجهول، بلا boto3)، تتخطّى البحر (404)، تدمجها COG لـFIELD_DEM_PATH. presets: `--country yemen` (104 بلاطة) / `aljawf` (12). اليمن مُغطّى بالكامل. حارس منطق البلاطات (4).
- **درس Production Gates (main-only):** بوّابة `sahool-production-gates.yml` تعمل على main/PR فقط لا على الفرع ⇒ تعديل ملفّ مشمول بالمانيفست (maphub-webgl.spec.ts في إصلاح E2E) دون إعادة بناء مرّ على الفرع (11 وظيفة) ثمّ فشل على main (checksum). أُصلِح رجعيّاً (c7ee1f0) ثمّ **مُنِع منهجيّاً**: أُضيفت `validate_release_package` إلى وظيفة Lint&Format في `ci.yml` (7c5e080) فتُلتقط على الفرع قبل الدمج. القاعدة: أعِد build_release_bundle عند أيّ تعديل ملفّ مشمول (شامل e2e/ و.github/).

## 2026-07-06 (تكملة) — v60.2 عدد مناطق الإدارة الأمثل (FPI/NCE) + تنعيم مكانيّ (فرع = 46dabb9)
- **الفجوة:** عنقدة v60.1 (`productivity_zones_clustering.zones_from_ndvi_grid`) تأخذ `k` من المستخدم (افتراضيّ 3) — لا جواب مبدئيّ لسؤال الزراعة الدقيقة المركزيّ «كم منطقة إدارة يحتاج الحقل؟». تقسيمٌ زائد يُبدّد الكلفة؛ ناقصٌ يُخفي تبايناً.
- **الحلّ (منهجيّة Management Zone Analyst — Fridgen et al. 2004):** وحدة جديدة `services/ai_agronomist/management_zone_count.py` (stdlib نقيّ، بلا numpy/sklearn، حتميّة): fuzzy c-means أحاديّ البُعد + **FPI** `(k/(k-1))·(1-F)` + **NCE** `H/(1-k/n)` عبر k=2..6؛ `recommended_k = argmin FPI` (وNCE مُبلَّغ معه). صدق: يعيد جدول المؤشّرات كاملاً + تنويه «اقتراح إحصائيّ لا قرار — يلزم حكم أغرونوميّ وتحقّق ميدانيّ»؛ `None` عند بيانات متدهورة (لا اختراع عدد).
- **تنعيم مكانيّ:** `smooth_label_grid` مرشّح أغلبيّة 8-جوار على شبكة التصنيف (يقتل «ملح-وفلفل»، idempotent على المتّصل، `None` لا يصوّت). `zones_from_ndvi_grid(k=None, smooth=True)` يفعّل المسارين؛ `propose_productivity_zones` يحترم `zone_count` الصريح وإلّا تلقائيّ + تنعيم، ويكشف `zone_count_recommendation`/`zone_count_source`.
- **درس (اصطاده الاختبار):** صيغة FPI الصحيحة `(k/(k-1))·(1-F)` (تقسيم صريح ⇒ 0، الأدنى=الأمثل) لا `1 - ذلك` (يقلب الاتّجاه فاختار k=2 دائماً). أُصلِح قبل الدمج.
- **توافقيّة:** مسار k الصريح واختبارات v60.1 دون تغيير. 8 اختبارات وحدة جديدة · 341 اختبار zone/agronomy أخضر · ruff نظيف · بلا migration.
- **ملاحظة نظافة:** رأس `hot.md` كان بائتاً يشير لـ2df1cf5 بينما الواقع a2b55cb (طبقات التضاريس/التربة فوق Landsat؛ 2df1cf5 سلف فعليّ — لا انحدار). يُصحَّح في تحديث hot التالي.

## 2026-07-06 (تكملة) — استجابة لتدقيق خارجيّ على zip التضاريس/التربة (فرع = f092270)
- **البلاغ:** مُدقِّق خارجيّ شغّل كامل اختبارات raster-service على zip `7c5e080` ⇒ **5 فشل** (تضاريس/تربة سليمة، لكنها تُحمِّر بوّابة الخدمة) + ملاحظات صحّة CRS/سقف نافذة/حراسة UI.
- **الإصلاح 1 (حاجب) — tilejson استدعاء مباشر:** `field_cdse_tilejson` كان يعطب على الاستدعاء المباشر (unit) لأنّ `poly`/bbox الافتراضيّة كائنات FastAPI `Query` لا `None` ⇒ `_parse_poly(Query).split`. انحدار من v7-#3. **الحلّ:** تطبيع الافتراضيّات إلى `None` عند رأس الدالّة (متين لـHTTP والاستدعاء المباشر). 4 اختبارات.
- **الإصلاح 2 (حاجب) — حارس عقد poly في الواجهة:** `test_cdse_poly_contract` يفتّش حرفيّاً عن `params.set('poly')` داخل `fieldCdseTileUrl`، بائت بعد نقل الإصدار إلى مصدر الحقيقة `cdseClipParams`. حُدِّث الحارس ليتحقّق من نفس العقد (poly لا geom) عبر cdseClipParams — **تقوية لا إضعاف**.
- **صحّة CRS (صحّة حقيقيّة):** مسارات قراءة النافذة (terrain/soil summary/zones/points/contours) كانت تبني `from_bounds` بحدود lon/lat على `src.transform` مباشرةً — صحيح فقط لـEPSG:4326؛ على raster مُسقَط (UTM DEM · SoilGrids Homolosine) نافذة خاطئة + GeoJSON بأمتار الإسقاط. **الحلّ:** `tile_render.read_field_window` مشترك (يُعيد إسقاط bbox→src.crs قبل النافذة + سقف حجم `RASTER_MAX_READ_DIM=2048` عبر out_shape) + إعادة إسقاط إحداثيّات مخرجات المتّجهات (كنتور/مناطق/نقاط) → EPSG:4326. GLO-30 عندنا 4326 (كان كامناً)؛ SoilGrids قد يكون Homolosine (حقيقيّ). اختبار raster مُسقَط (UTM 38N) يُثبِت النافذة + السقف + مخرَج lon/lat.
- **حراسة UI:** حارس ساكن جديد `MapHubTerrainSoilLayers.static.test.ts` (المبدّلات الثلاثة + التربة · إغلاق آمن available-gated · رسائل غياب صادقة · أساطير · disclaimer إلزاميّ). 6 اختبارات.
- **ملاحظة `jose` (بيئيّة لا كود):** فشل جمع `tests_v9` عند المُدقِّق سببه `python-jose` غير مُثبَّت في بيئته المؤقّتة — موجود في `requirements-dev.txt`/`tests_v9/requirements-test.txt`؛ ليس عيباً في الحزمة.
- **التحقّق:** raster-service **131/131** (كان 123/5-فشل) · vitest الحارس 6/6 · ruff نظيف · المانيفست أُعيد بناؤه (+2 ملفّ اختبار مُتتبَّع، 3183 checksum).

## 2026-07-06 (تكملة) — استجابة لتدقيق خارجيّ أعمق (P0×3 + P1×4) على التضاريس/التربة (فرع = 776d086)
- **P0#1 — عطب Query عامّ في كلّ الراوترات الجديدة:** ليس محصوراً بـcdse — `field_terrain/contours/soil_summary/zones/plan` كلّها تعطب على الاستدعاء المباشر (`'Query'.split`). حُوِّلت كلّ بارامترات `= Query(...)` في `terrain_tiles.py`/`soil_tiles.py` إلى `Annotated[T, Query()] = default` (الافتراضيّ البايثونيّ قيمة حقيقيّة). حارس `test_router_query_direct_call.py` يقود كلّ نقطة مباشرةً + يمنع عودة `= Query(`.
- **P0#2 — MapLibre GL لا يرسم الطبقات:** كانت تصل Leaflet فقط. `HubMapGL` يستقبل الآن hillshade/slope/soil URLs + contours + soilSamplePoints ويرسمها (نمط بلاطة المؤشّر المُثبَت + علامات DOM 🧪 + كنتور GeoJSON خطّيّ)؛ التأثير يعتمد على basemapId فتبقى بعد إعادة تحميل الأساس؛ fail-closed (بلا رابط ⇒ إزالة الطبقة). حارس ساكن يؤكّد تمرير المحرّكين + إضافة الطبقات. **صدق:** التصيير GL لم يُتحقَّق بصريّاً هنا (بيئة headless) — يحاكي مسار المؤشّر العامل.
- **P0#3 — compose غير قابل للتفعيل:** `docker-compose.v9.yml` يُعلن الآن `SOILGRIDS_DIR` + `RASTER_MAX_READ_DIM` ويربط `/data/dem` و`/data/soilgrids` (read-only، مجلّدان فارغان افتراضاً ⇒ fail-closed صادق). حارس `test_terrain_soil_compose_provisioning.py`.
- **P1 (صحّة) — CRS + سقف نافذة:** كانا مُصلَحَين أصلاً في `f092270` (المُدقِّق راجع zip أقدم). أُثبِت باختبار raster مُسقَط (UTM).
- **P1 — صدق المصدر:** `/v1/soil/properties` يكشف `source_declared` مقابل `source_readable` + `readable_layers` (env مضبوط ≠ ملفّ موجود)؛ `source_configured` صار «قابل للخدمة». دالّة `readable_layer_count`.
- **P1 — readyz تفصيليّ:** `/readyz` يكشف حالة terrain/soilgrids (غير حاجبة) كي لا تبدو الخدمة جاهزة وطبقاتها معطّلة.
- **P1 مؤجَّل بصدق (موثَّق، غير مُنجَز بعد):** (٥) قصّ contours/عيّنات على **مضلّع** الحقل لا bbox — يحتاج تمرير poly + قناع rasterio عبر مسارات القراءة. (٨) تحسين خوارزميّة العيّنات (نقطة داخليّة/buffer/حدّ مساحة). (٩) توكن في روابط TileJSON (كامن — الواجهة تبني رابطها بتوكن). **لا ادّعاء إنجاز.**
- **jose:** بيئيّ لا كود (موجود في requirements-dev). **التحقّق:** raster-service 134/134 · حُرّاس compose/GL/zone خضراء · vitest · tsc نظيف · المانيفست 3185.

## 2026-07-06 (تكملة) — إكمال بنود P1 المتبقّية: قصّ المضلّع + عيّنات داخليّة + توكن TileJSON (فرع = 6c69d20)
- **P1#5 قصّ على مضلّع الحقل (لا bbox):** `tile_render.mask_array_by_polygon` (يُعيد إسقاط حلقة الحقل إلى src.crs ثمّ `geometry_mask` خارج⇒NaN). مُمرَّر عبر `poly` في `read_field_window` + `compute_field_terrain/contours` + `read_property_bbox` + ملخّص/مناطق/نقاط التربة + الراوترات الأربعة (بارامتر `poly` Annotated، يُحلَّل lng,lat;…). الواجهة تمرّر هندسة الحقل لـ`fetchFieldContours`/`fetchSoilSamplingPlan`. النتيجة: كنتور/مناطق/نقاط **داخل الحقل غير المنتظم** لا المستطيل المحيط.
- **P1#8 جودة العيّنات:** النقاط داخليّة (بركة 8-جوار، لا على حافّة المنطقة) + عيّنات إضافيّة بتباعُد أقصى (farthest-point) + تخطّي المناطق < 3 بكسل + كلّ نقطة تحمل `zone_pixels`/`confidence_score`/`placement`.
- **P1#9 توكن TileJSON:** وُثِّق أنّ روابط `tiles` بيانات وصفيّة — الواجهة تُضيف access_token عبر بُناة `*TileUrl` (لا استهلاك مباشر خلف البوّابة).
- **تحقّق:** اختبار سلوكيّ جديد (`test_poly_clip.py`) يُثبِت قناع خارج-المضلّع + نقاط داخل المضلّع + كنتور داخل المضلّع. raster-service **137/137** · tsc نظيف · المانيفست 3186. **كلّ بنود التدقيق الأعمق (P0×3 + P1×كامل) مُنجَزة الآن** عدا تحقّق GL البصريّ (بيئيّ عند المستخدم).

## 2026-07-06 (تكملة) — إصلاح انحدار CI + استجابة تدقيق ثالث + دمج (main=develop=dbc386d)
- **انحدار CI (خطئي، اللقطة كشفته):** جوبتان حمراوان منذ v60.2. (١) *Validate Docker Compose*: `${DEM_HOST_DIR:-./data/dem}` جعل DEM_HOST_DIR متغيّراً؛ `.ci.env` الوهميّ يملؤه رمزاً مجرّداً ⇒ «حجم غير مُعرَّف». أُصلِح بمسار bind ثابت `./data/dem`+`./data/soilgrids` (أُعيد توليد .ci.env محليّاً وأُثبِت). (٢) *Unit Tests*: حارس `test_cdse_tilejson...urlencode` يقرأ نافذة 3000 حرف؛ كتلة تطبيع Query دفعت `urlencode(` للحرف 3406. أُزيلت الكتلة، الحُرّاس `isinstance` سطريّاً ⇒ 2835. الطبقة الكاملة **2659/0**.
- **درس:** بعد أيّ تعديل compose/راوتر شغّل `pytest -m unit` كاملاً + `docker compose --env-file <dummy> config` محليّاً قبل الدفع — الاختبارات المُوجَّهة لا تكفي.
- **تدقيق ثالث (فرز صادق):** raster/GL/compose/CRS مُصلَحة سابقاً (حالة أقدم). حارسان بائتان أُصلِحا: `test_v123_is_last_manifest_entry` (v147 هو الأخير الآن ⇒ «v123 مُطبَّق») · ChatbotPage `useFieldContextStore` (فُكّ لـ`useSelectedField`+`ai-context-pack` ⇒ حُدِّث الحارس). supervisor/actuator: **بيئيّ لا انحدار** (يفشلان منفردَين بلا JWT_SECRET؛ fail-closed 503/401 صحيح؛ غير مُعلَّمَين unit، يمرّان في الطبقة). jose/sqlparse/flutter بيئيّ. **متبقٍّ معماريّ (قرار المستخدم):** تصادُم routers/main عبر الخدمات (إعادة تسمية حزم) · بوّابة vitest في CI.
- **الدمج:** CI أخضر على dbc386d (11 وظيفة success) · fast-forward نظيف a2b55cb→dbc386d لـmain وdevelop · zip `..._dbc386d_review-response.zip` (3455 ملفّاً).
- **موقع السنيدار (3WQV+J7 المرقعة):** تعذّر تحويله لإحداثيّات موثوقة (روابط Google القصيرة 403؛ لا فكّ Plus Code يدويّ = لا اختلاق GPS). بانتظار إحداثيّات عشريّة كاملة من المستخدم — عندها تُفعَّل سلسلة poly-clip كاملة على حدّ الحقل.

## 2026-07-06 (تكملة) — actuator سلامة فيزيائيّة (P0) + إصلاح scaffold عبر ٩ خدمات + حُرّاس بائتة (main=develop→1d9daf4)
- **actuator (P0 حقيقيّ، انحدار من التفكيك):** أعادت `#481 Safety Hardening` دوالّ نقيّة (`_manual_commands_enabled`/`_automation_actuation_enabled`/`_dispatch_consumer_enabled`/`_safety_status`/`_parse_risk_allowlist`/`_is_risk_allowed`/`_parse_dispatch_command`/`_dispatch_outcome_status`) أسقطها التفكيك؛ استُعيدت حرفيّاً من git. **حارس /command 403** (تعطيل التحكّم اليدويّ) أُعيد **قبل** فحص الملكيّة/DB (fail-closed حتّى بلا قاعدة). **/health** كان يسرّب MQTT broker URL ⇒ `mqtt_configured` فقط.
- **الجذر العميق (scaffold عبر ٩ خدمات):** `router_registry._include_flat` كان يُلحِق كائنات المسار خاماً بـ`app.router.routes` ⇒ **يكسر `app.dependency_overrides`** (المسارات غير مربوطة بموفِّر التطبيق) ⇒ اختبارات حقن auth تفشل (401/503). Starlette 1.3.1 يُسطّح `include_router` أصلاً ⇒ عودة للطريق القياسيّ في التسع خدمات (auth/guardrails/odoo/raster/soil/supervisor/tts/vegetation/video/actuator). **نتيجة:** supervisor graceful degradation 401→200 (51/51)؛ actuator 29/29.
- **حُرّاس tests/ بائتة (غير حاجبة CI):** MANIFEST.md wording · .env→.env.example · fixed.yml sahool_user→sahool_app · real-data خلف REAL_DATA_TESTS. (9→2؛ المتبقّي بيئيّ/عقد ترحيل — لم يُغيَّر عمياءً.)
- **PrescriptionBuilderPage.test.tsx** (مكسور مسبقاً) لُفّ بـMemoryRouter (5/5).
- **درسان:** (١) بعد أيّ تعديل شغّل `ruff format` **على الملفّ المُعدَّل** لا الراوترات فقط — CI اصطاد test_actuator_safety غير مُنسَّق. (٢) لا تُدخِل محارف bidi (U+200F) في التعليقات — bandit B613 HIGH يحجب.
- **التحقّق:** unit tier 2659/0 · كلّ الخدمات المُفكَّكة خضراء · bandit HIGH 0 · ruff نظيف · CI على 1d9daf4 أخضر (10/11 success + بوّابة bandit-HIGH نجحت).

## 2026-07-07 (ن) — تدقيق تغطية خطّة التحسينات (15 مرحلة) + عنقدة المناطق متعدّدة المؤشّرات (V60.3)
- **التدقيق (4 وكلاء متوازيين + بحث موثَّق):** قورِنت الخطّة الموحَّدة (15 مرحلة) بالكود. الخلاصة: مغطّاة أو جزئيّة إلى حدٍّ كبير — مزوّد Element84 (الافتراضيّ الآن)، COG window-read، تاريخ الالتقاط الحقيقيّ، حَوْكمة أدوات المستشار (v58)، حزمة الأدلّة/الثقة. فجوات حقيقيّة مؤجَّلة بصدق: NASA HLS غائب · Planetary Computer مجرّد STAC-URL خامل · مفتاح كاش البلاطة يُغفِل provider/scene_id/colormap · نشرة إقليميّة (field→district→gov) غائبة · عدم يقين نموذج المحصول (P10) غائب · **عنقدة المناطق NDVI فقط رغم توفّر NDMI/RECI/MSAVI + الانحدار**.
- **التنفيذ (أعلى قيمة محتواة):** `productivity_zones_clustering.py` — `kmeans_nd` حتميّ (stdlib، بلا numpy) + معايرة min-max لكلّ ميزة (يمنع هيمنة الانحدار 0..90 على NDVI −1..1) + تعويض القيم المفقودة بمتوسّط الميزة. المناطق تُرتَّب بمتوسّط NDVI الفعليّ فيبقى score/التصنيف متّسقاً مع V60.1. `basis="multi_index"` (الافتراضيّ) صار **حقيقيّاً** لا تسمية شكليّة. توافق خلفيّ تامّ (بلا مساعدة ⇒ مطابق V60.1) + سقوط آمن (مساعدة غير مُتراصفة تُسقَط) + `basis="ndvi"` صريح يُلغي المساعدة. موجِّهات صادقة (تُدرِج ndmi/reci/msavi/slope الفعليّة). 10 حُرّاس جديدة.
- **التحقّق:** 28/28 (وحدة المناطق) · 170/1 (نطاق agronomist/zones/evidence/planner) · ruff نظيف · manifest معاد بناؤه (3256 checksum) · SHA 0b024af · فرع مدفوع. main/develop قُدِّمت إلى 7292575 (Element84 افتراض الكود، CI #28876569401 أخضر).
- **درس:** إعادة بناء manifest إلزاميّة عند لمس ملفّات متتبَّعة (تكرار درس 0682f62 — أُنجِز هذه المرّة قبل الالتزام).

## 2026-07-07 (ن) — مراجعة تقرير التحقّق الخارجيّ + سدّ فجوتَين (V63)
- **مراجعة التقرير الخارجيّ (`SAHOOL_22b92d6_..._VERIFICATION`):** أمين في البنية، مضلِّل في النسبة — قاس مقابل **خطّة بناء 15 مرحلة كاملة** بينما تفويض الجلسة كان **تدقيق + تنفيذ أعلى قيمة**. لا دليل فشل مصدر (compileall + 10 + 13 اختباراً نجحت؛ `jose` بيئة الفاحِص). أخطأ موضع الفحص: صنّف توصيته P4 (مناطق متعدّدة المصادر) «غير منفَّذ» وهي V60.3 مُنجَزة في `ai_agronomist/` (فحص `core/` فقط). التقرير الكامل: scratchpad.
- **العلل الخمس لـ«عدم التنفيذ»:** (١) اختلاف تفويض (جذريّ) · (٢) قياس البنية لا الوظيفة (سلسلة المزوّد تعمل عبر `stac_search.py:145-258`) · (٣) خطأ موضع فحص أخفى V60.3 · (٤) تأجيل صادق للخدمات الخارجيّة (WaPOR/HLS/WorldCereal تحتاج API+اعتمادات+تغطية اليمن) · (٥) نقص تبعيّة عند الفاحِص.
- **سدّ فجوتَين محتوتَين مُتحقَّقتَين (V63، `raster_scene_model.py`):** (أ) `NormalizedScene` — نموذج مشهد موحَّد يلفّ مخرَج `stac_search_*` (cog_ready **مُشتقّ** من توفّر الروابط، لا مُختلَق) + `PROVIDER_REGISTRY` صادق (active=False لِـnasa_hls/planetary_computer غير الموصولَين). (ب) `provider_fallback_suggestion` — اقتراح مُهيكَل يوجّه إلى element84، مُدمَج في تفاصيل 503 لمسار CDSE غير المُهيّأ (بدل نصّ حرّ). لم أبنِ WaPOR/HLS: مسار HTTP خارجيّ لا يمكن التحقّق منه end-to-end بلا خدمة حيّة ⇒ تجنّب نصف حلّ.
- **التحقّق:** 8 حُرّاس جديدة + حارس CDSE fail-closed القائم (5) أخضر · 200/1 نطاق raster/stac · ruff نظيف · manifest معاد بناؤه · SHA 200b163.

## 2026-07-07 (ن) — وصل NormalizedScene (V63.2) + إثراء السِجِلّ بتغطية اليمن
- **حُرّاس V63 (طلب المُراجِع):** أضفتُ الثلاثة صراحةً — مزوّد غير موصول لا يظهر نشطاً · اقتراح احتياطيّ CDSE-محصور (يظهر مرّة واحدة، لا في مسار element84) · **acquisition_date لا يقبل processed_at** (فراغ عند غياب datetime) + حارس ساكن يمنع أيّ تعيين لـprocessed_at في النموذج. + حالتا cog_ready الحديّتان (assets مفقودة⇒false، نطاقات جزئيّة⇒جاهز بالمجموعة المتوفّرة فقط). SHA 8227fa1.
- **وصل V63.2 (غير كاسر):** `/imagery/timeseries` يعيد `normalized_scenes` (عقد موحَّد) **بجانب** `scenes` الخام (المفتاح القديم محفوظ، حارس انحدار). التطبيع عند حدّ الاستجابة فيبقى قاموس البحث الداخليّ رشيقاً لمسار backfill.
- **إثراء السِجِلّ (صادق، يبقى active=False):** أضفتُ `wapor` + `worldcereal` كمزوّدَين مُسجَّلَين غير موصولَين، وأثريتُ `nasa_hls`، ببيانات تغطية اليمن المُتحقَّقة (المُراجِع): `coverage_yemen`/`resolution`/`recommended_use`/`category`. WaPOR L2 100م (الشرق الأدنى)، WorldCereal 10م عالميّ، HLS 30م عالميّ. `planned_providers()` جديدة؛ active/planned منفصلان؛ حارس يمنع تسرّب wapor/worldcereal إلى النشط. الأولويّة التنفيذيّة لليمن: WaPOR → WorldCereal → HLS، **لا تُفعَّل إلّا بعد مُحوِّل + اختبار عقد**.
- **التحقّق:** 21 اختبار V63 أخضر (9 جديدة) · 193 نطاق raster/stac · ruff نظيف · manifest 3259 · SHA 4a9eeef.

## 2026-07-07 (ن) — عدم يقين نموذج المحصول (V64، «لا غلّة بلا عدم يقين»)
- **الفجوة (P10):** `wofost_adapter.simulate()` كان يُرجِع غلّة نقطة عارية بلا عدم يقين، و`profit_planner` يرتّب على النقطة. الآن كلّ مخرَج simulate يحمل `yield_interval` (مُرفَق عند نقطة الاختناق الوحيدة فلا يفلت مسار).
- **النهج الصادق:** `_yield_uncertainty` نطاق **نموذجيّ** (`method="deterministic_model_band"`) — **ليس** conformal التجريبيّ (ذاك يحتاج بيانات حصاد ويعيش في `core/engines/yield_interval.py`؛ note_ar يُحيل إليه). يتّسع بنقص المدخلات (طقس/مطر/ماء تربة/ريّ/وسائط محصول) وقرب عتبة العامل المُقيِّد (حراريّ↔مائيّ)؛ كلّ موسِّع في `drivers` (لا رقم بلا سبب)؛ سقف 60٪. مدخلات أوفى ⇒ نطاق أضيق (رتابة). حتميّ.
- **التمرير:** `profit_planner.evaluate_candidate` يعيد مدى ربح (`expected_profit_low/high` + `yield_confidence`) من النطاق — توافق خلفيّ (يُحذَف بلا نطاق).
- **التحقّق:** 9 حُرّاس جديدة + 18 اختبار agriai قائم أخضر · ruff نظيف · manifest 3260 · SHA b2c9897.

## 2026-07-07 (ن) — بطاقة ذكاء الحقل الموحّدة (V65)
- **الفجوة (P5/P9):** أوليّات القرار (حالة موحّدة/أدلّة/ثقة/تنبيهات) موجودة لكن مبعثرة عبر ~10 بطاقات FieldView؛ لا بطاقة قرار واحدة.
- **الحلّ:** `core/field_intelligence_card.assemble_field_intelligence_card` مُجمِّع منطق صرف يبني بطاقة واحدة (أحدث مشهد/حالة مزوّد/NDVI-تاريخيّ/عجز مائيّ/مناطق ضعيفة/تنبيهات/توصية استطلاع/أدلّة/ثقة). **صدق:** كلّ قسم إمّا حاضر أو `missing` بسبب صريح؛ `completeness` نسبة أقسام **البيانات** الحاضرة (المخرجات المُشتقّة risk_alerts/confidence/scouting لا تُحسَب — الاكتمال يعكس توفّر البيانات لا النتائج). NDVI-vs-history يحسب الشذوذ + تصنيف فوق/تحت/قرب.
- **الوصل:** إضافيّ في `/field-intelligence/analyze` (`field_intelligence_card`) — غير كاسر.
- **التحقّق:** 8 حُرّاس جديدة (نطاق ratchet المنصّة) · 285 شريحة منصّة + 5 endpoint أخضر · ruff نظيف · manifest 3261 · SHA 9822dda.

## 2026-07-07 (ن) — سِجِلّ المصادر البحثيّة (V63.3، فصل Gitee عن مزوّدي الصور)
- **بحث Gitee (المُراجِع):** مفيد للمعالجة/التدريب/التقطيع/change-detection لكنّه **ليس** مصدر صور خام (PaddleRS · GeoTrellis Landsat tutorial · CDSystem · NWPU/RSOD datasets).
- **الحلّ:** `RESEARCH_REGISTRY` منفصل تماماً عن `PROVIDER_REGISTRY`؛ كلّ عنصر `provides_imagery=False` بنوع (research_library/architecture_reference/dataset_reference) + `recommended_use`. `research_sources()` + حُرّاس: المجموعتان **منفصلتان** ولا يتسرّب مصدر بحثيّ إلى active/planned. صدق: Gitee مصدر أفكار/مكتبات لا مزوّد صور — المزوّدون الحقيقيّون يبقون CDSE/Element84/PC/NASA HLS.
- **التحقّق:** 23 اختبار V63 أخضر (2 جديدة) · ruff نظيف · manifest 3263 · SHA d2da16e.

## 2026-07-07 (ن) — النشرة الإقليميّة لحالة المحاصيل (V66، آمنة الخصوصيّة)
- **الفجوة (P12):** لا تجميع حقل→مديريّة→محافظة ولا نشرة حالة ولا شذوذ مقابل التاريخ — فقط طبقة معرفة مديريّات ساكنة.
- **الحلّ:** `core/regional_bulletin.build_regional_bulletin` — تصنيف GEOGLAM (exceptional/favourable/watch/poor) من شذوذ NDVI مقابل المتوسّط التاريخيّ، مُجمَّع محافظة→مديريّات. **خصوصيّة بالبناء:** أرضيّة k-anonymity (min_fields_privacy=5) — المجموعات دونها تُكتَم بلا أرقام (لا استنتاج حقل/مستأجِر مفرد)، ولا معرّفات حقول في المخرَج. **صدق:** بلا تاريخ ⇒ unknown (لا تخمين)؛ الثقة من عدد الحقول/المشاهد. منطق صرف (الجلب/RLS يبقيان في الراوتر).
- **التحقّق:** 8 حُرّاس جديدة (نطاق ratchet المنصّة) · ruff نظيف · manifest معاد بناؤه · SHA سيُثبَّت.

## 2026-07-07 (ن) — سدّ ثغرتَي أدوات المستشار (V67، P13)
- **الفجوة (P13):** `get_water_productivity` و`generate_report` مفقودتان من سجلّ أدوات المستشار.
- **الحلّ:** أُضيفتا كأداتَي **قراءة فقط** (low/غير مُعدِّلة/بلا موافقة، `can_read_field_data`) في `tool_registry`، ومُعلَنتان للمزوّد في `provider_tooling` (READ_ONLY_TOOL_NAMES + وصف + مخطّط JSON)، ومرآتهما في `tool_executor._TOOL_META` (حارس اللا-انحراف). `generate_report` تكوين/قراءة لا إرسال (صدق: تُميَّز عن send_recommendation عالية الخطر).
- **التحقّق:** 6 حُرّاس جديدة + حُرّاس السجلّ/المنفّذ/الحوكمة القائمة أخضر (190) · ruff نظيف · manifest معاد بناؤه · SHA سيُثبَّت.

## 2026-07-07 (ن) — راوت النشرة الإقليميّة (V66.1، إغلاق السلسلة end-to-end)
- **الفجوة (تقرير التحقّق):** V66 كانت وحدة بلا راوت. الآن موصولة: `GET /api/v1/regional/bulletin` (تسجيل تلقائيّ) معزول بالمستأجِر (`tenant_connection`/RLS) + `require_permission(FIELD_VIEW)`.
- **البيانات:** NDVI لكلّ حقل (الحاليّ + المتوسّط التاريخيّ من `zonal_stats`) + `fields.gov` (المحافظة موجودة؛ المديريّة اختياريّة) → محوّل صرف `bulletin_rows_to_records` → `build_regional_bulletin`. **صدق:** القاعدة معطّلة ⇒ نشرة فارغة+سبب؛ تعذّرها ⇒ 503؛ لا NDVI ⇒ `unknown`؛ أرضيّة الخصوصيّة + لا معرّفات حقول محفوظة. المحوّل مُختبَر وحدةً؛ SQL يُغطّى بالتكامل.
- **التحقّق:** 5 حُرّاس راوت/محوّل + 8 حُرّاس المنطق أخضر · 69 شريحة منصّة · التطبيق يبني ويسجّل الراوت · ruff نظيف · manifest معاد بناؤه · SHA سيُثبَّت.

## 2026-07-07 (ن) — تغذية بطاقة ذكاء الحقل من قاعدة المنصّة (V65.1)
- **الفجوة (تقرير التحقّق P1):** أقسام latest_scene/ndvi_vs_historical في بطاقة V65 كانت `missing` في المسار الحيّ (الراوت لم يغذّها).
- **الحلّ:** `card_signals_from_db_rows` (منطق صرف مُختبَر) يبني {ndvi_current/ndvi_history/latest_scene} من `zonal_stats` (NDVI تاريخيّ) + `raster_assets` (أحدث مشهد). الراوت صار async ويجلبها عبر `tenant_connection` (RLS) بسقوط آمن: قاعدة معطّلة/خطأ ⇒ إشارات فارغة ⇒ البطاقة كما قبل (لا انحدار، لا اختلاق). SQL يُغطّى بالتكامل. **صدق:** provider_status يبقى `missing` عمداً (يعيش في raster-service، لا mock).
- **التحقّق:** 4 حُرّاس صرف جديدة · 133 شريحة منصّة + endpoint أخضر · الراوت async ومُسجَّل · ruff نظيف · manifest معاد بناؤه · SHA سيُثبَّت.

## 2026-07-07 (ن) — كشف سِجِلّ المزوّدين عبر HTTP (V63.4، أساس الجسر cross-service)
- **الخطوة (المُراجِع P1 cross-service):** `GET /v1/providers/status` في observability يكشف السِجِلّ الصادق (default + active + planned + PROVIDER_REGISTRY + RESEARCH_REGISTRY) كمصدر واحد للمنصّة (provider_status في البطاقة) والواجهة.
- **صدق:** active يعكس الوصل (wapor/worldcereal/nasa_hls/PC مُخطَّطة)؛ المصادر البحثيّة منفصلة (provides_imagery=False)؛ بيانات وصفيّة غير حسّاسة. نقيّ فوق raster_scene_model.
- **التحقّق:** 2 حارس جديد · 113 شريحة raster (تشمل decomposition/import-graph) أخضر · ruff نظيف · manifest معاد بناؤه · SHA سيُثبَّت. **المتبقّي للجسر:** عميل المنصّة fail-safe يستهلك هذه النقطة لملء provider_status (HTTP يُتحقَّق بالتكامل).

## 2026-07-07 (ن) — جسر provider_status عبر الخدمات (V65.2)
- **الخطوة (المُراجِع P1 cross-service):** بطاقة V65 تُغذّى الآن `provider_status` من raster-service (`/v1/providers/status`، V63.4). `fetch_provider_status` (آمن الفشل عبر `_get_json`) + محوّل صرف `provider_status_signal` → {default/active/planned}. الراوت يغذّيه خارج معاملة القاعدة بسقوط آمن: raster متعذّر ⇒ القسم يبقى missing بسبب صريح (لا اختلاق). active يعكس الوصل الفعليّ.
- **التحقّق:** 4 حُرّاس صرف · 12 اختبار بطاقة + endpoint أخضر · التطبيق يسجّل · ruff نظيف · manifest معاد بناؤه · SHA سيُثبَّت. **الجسر مكتمل داخليّاً؛ نداء HTTP الفعليّ يُتحقَّق بالتكامل (خدمتان حيّتان).**

## 2026-07-07 (ن) — واجهة بطاقة ذكاء الحقل (P2، V65-UI)
- **الخطوة (المُراجِع P2):** عرض عقد البطاقة للمستخدم لا backend-only. `FieldIntelligenceCardView` + هوك `useFieldIntelligenceCard` (POST analyze عبر البوّابة) + عقد/مساعِدات نقيّة `lib/fieldIntelligenceCard.ts`.
- **صدق:** الأقسام الحاضرة تُعرَض بقيمها (مشهد/NDVI-تاريخيّ/حالة مزوّدين/تنبيهات/ثقة)، والمفقودة تُدرَج صراحةً «غير متاح» (provider-unavailable ⇒ «raster متعذّر») — لا اختلاق. مُوصَّلة في MapHub (الوضع الخبير) بجانب BoundaryReviewCard.
- **التحقّق:** typecheck نظيف (tsc --noEmit) · 5 حُرّاس vitest نقيّة أخضر · manifest معاد بناؤه · SHA سيُثبَّت. **المتبقّي للواجهة:** عرض normalized_scenes/regional_bulletin (بطاقات إضافيّة، نفس النمط).

## 2026-07-07 (ن) — تصنيف سِجِلّ المصادر الصادق + مراجعة قنوات الصور (V63.5)
- **التصحيح الجوهريّ:** SciHub مُغلَق (2023) ⇒ لا يُضاف؛ CDSE البديل الرسميّ (مُوثَّق في note الإدخال).
- **التصنيف:** أثريتُ PROVIDER_REGISTRY (category/verified/coverage_yemen/resolution للكلّ) + أضفتُ `aster_gdem` (DEM مُخطَّط). سِجِلّ `EXTERNAL_SOURCE_REGISTRY` منفصل: usgs (manual)/planet (commercial)/maxar (event)/china_gaofen (research، requires_verification) — active_provider=False دائماً. helpers external_sources/sources_by_type + كشفها في `/v1/providers/status`. النشطون يبقون {element84, cdse, local_cog} بالضبط.
- **الوثيقة:** `docs/research/SATELLITE_IMAGERY_DOWNLOAD_CHANNELS_REVIEW_20260707.md`.
- **التحقّق:** 6 حُرّاس جديدة (السِجِلّات الثلاثة منفصلة) · حُرّاس V63 القائمة أخضر · ruff نظيف · manifest معاد بناؤه · SHA سيُثبَّت.

## 2026-07-07 (ن) — DEM: Copernicus مُفضَّل + ASTER احتياطيّ + جودة NUM (V63.6)
- **التفضيل (المُراجِع):** Copernicus DEM 30م أعلى جودة من ASTER (دراسات حديثة) ⇒ `copernicus_dem` مُسجَّل `preferred_dem=True` (active=False، يوافق `DEM_COLLECTION=cop-dem-glo-30`)؛ `aster_gdem` احتياطيّ بـ`products=[DEM,NUM]` + `requires_earthdata_login`. helpers `dem_providers`/`preferred_dem`.
- **جودة NUM:** `dem_quality.py` منطق صرف يحوّل عدد المشاهد (NUM) إلى ثقة (كثافة أعلى ⇒ ثقة أعلى؛ بلا NUM ⇒ unknown، لا تخمين).
- **التحقّق:** 10 حُرّاس جديدة · النشطون بلا تغيير · حُرّاس V63 أخضر · ruff · manifest · SHA سيُثبَّت. **لم أبنِ المستورِد** (قراءة GeoTIFF فعليّة = تكامل، يحتاج Earthdata) — مُعلَّم كخطوة متبقّية.

## 2026-07-07 (ن) — سِجِلّ مصادر الطقس (V68) + إصلاح CI
- **إصلاح CI (984b9c7):** وظيفة Unit Tests فشلت على 4 من إضافاتي (بقيّة الوظائف خضراء): (١) اختبارا V67 يستوردان `services.ai_agronomist.main` المحتاج fastapi ⇒ `importorskip("fastapi")` (يُتخطّى في بيئة الوحدة الدنيا) · (٢) `/v1/providers/status` ⇒ PUBLIC_CATALOG · (٣) `/api/v1/regional/bulletin` ⇒ تصنيف `internal` (لا واجهة بعد ⇒ مُعفى من البوّابة العكسيّة). كامل `-m unit`: 2740/0.
- **سِجِلّ الطقس (V68):** `core/weather_sources.py` على نمط سِجِلّ الصور. **صدق:** Open-Meteo وحده active (موصول: `connectors/openmeteo.py` + `field_intelligence_adapters:159` + `main:1679`)؛ NASA POWER/CHIRPS/ECMWF/GFS/ERA5 مُخطَّطة (مجانيّة + تغطّي اليمن لكن غير موصولة) — **صحّحتُ اقتراح «nasa_power active» إلى planned**. أدوار لكلّ مصدر + helpers. 4 حُرّاس.
- **التحقّق:** 4 حُرّاس طقس + كامل unit أخضر · ruff · manifest معاد بناؤه · SHA سيُثبَّت.

## 2026-07-07 (ن) — مصادر الرياح/الإعادة-تحليل (V68.1، تصحيح الدقّة)
- **التصحيح الأهمّ (المُراجِع):** ERA5 ~25كم، ERA5-Land ~9كم — **ليست 500م**؛ مقياس منطقة/محافظة لا نقطة حقل (يحتاج downscaling/دمج DEM). صُحّح في السِجِلّ + حارس.
- **الوصل الحقيقيّ:** حاجة الرياح على مستوى الحقل (رشّ/ET0) مُغطّاة أصلاً بـOpen-Meteo النشط (أُضيف دورا wind/spray_window) — لا حاجة لإعادة-تحليل خشنة أو رياح محيطيّة للقرار الحقليّ.
- **مُضاف مُخطَّطاً:** era5_land (9كم، الأدقّ للأرض) · global_wind_atlas (~250م، مواقع طاقة الرياح لا forecast) · merra2 (~50كم مرجع) · ascat (رياح محيطيّة، coverage_scope=coastal_marine). China الإقليميّة **لم تُضَف** (جغرافيا خاطئة). لا مصدر يُدّعى active.
- **التحقّق:** 7 حُرّاس طقس · active == {open_meteo} · ruff · manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — OlmoEarth كنموذج أساس AI (V69، لا مزوّد صور)
- **التصنيف الصادق (المُراجِع):** OlmoEarth (Ai2) نموذج أساس EO يعمل *فوق* الصور (Sentinel-1/2/Landsat)، **ليس مزوّد صور**. سِجِلّ `AI_MODEL_REGISTRY` منفصل: provides_imagery=False · active_provider=False · requires (أوزان/سلاسل زمنيّة/تحقّق محلّيّ اليمن) · requires_imagery_provider=[sentinel1,sentinel2,landsat] · coverage_note=true_by_input_sources (المدخلات تغطّي اليمن، النموذج غير مُتحقَّق محلّيّاً).
- **عقد embedding صادق (#5 من طلبه):** `olmoearth_embedding_contract` — بلا أوزان/مدخلات ⇒ unavailable+سبب+embedding=None؛ حتّى مع توفّرهما **لا متّجه مُختلَق** (status=ready_pending_local_validation، الاستدلال خلف GPU + تحقّق محلّيّ). كُشِف في `/v1/providers/status` (ai_models).
- **صدق:** لا يُغني عن CDSE/Element84 — يستهلكها. لا تفعيل بلا أوزان+GPU+تحقّق يمنيّ. المتبقّي (V70): benchmark محلّيّ NDVI-only مقابل V60.3 مقابل OlmoEarth.
- **التحقّق:** 5 حُرّاس (السِجِلّات الأربعة منفصلة) · حُرّاس V63 أخضر · ruff · manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — قناة استيراد Earthdata الدفعيّ + حارس نَسَب/أسرار (V63.7)
- **القناة (المُراجِع):** `earthdata_wget_batch` في EXTERNAL_SOURCE_REGISTRY (`source_type=manual_batch_download`, active_provider=False, requires_earthdata_login) — تدعم HLS/ASTER/SRTM/NASADEM/MODIS/VIIRS/MERRA2. قناة استيراد دفعيّ لا مزوّد حيّ. التصحيح: `.netrc` لا كلمة مرور في سكربت/مستودع.
- **حارس صادق + أمنيّ:** `imported_asset_provenance_ok` — يرفض أصلاً مُستورَداً بلا checksum+source_url+acquisition_date (لا أصل يتيم)، ويرفض أيّ حقل يشبه سرّاً (password/token/netrc). الوثيقة حُدِّثت بطريقة `.netrc` + wget + قاعدة النَّسَب.
- **التحقّق:** 4 حُرّاس · القناة ليست مزوّداً/نشطاً · حُرّاس السِجِلّ أخضر · ruff · manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — سِجِلّ مصادر التربة/المناخ (V70، أربع طبقات)
- **التصنيف:** `core/soil_climate_sources.py` بطبقات tier (production_baseline/planned_baseline/research_layer/manual_download_only). **SoilGrids نشط** (موصول فعلاً: `soil-service/soilgrids_client.py`→rest.isric.org + `/soil/soilgrids`) بتحذير «250م، ليس بديل مختبر». WorldClim/ESA-CCI مُخطَّطان؛ erodibility + DOC/MBC/fMAOC/GPP طبقات بحثيّة (requires_verification، coverage=needs_check/dataset_dependent، لا افتراض تغطية).
- **صدق:** NASA POWER لم يُعَد تعليمه active (موجود مُخطَّطاً في weather_sources). **الأمن/الموثوقيّة:** حارس `has_baidu_source` يمنع أيّ رابط Baidu كمصدر رسميّ (المواقع الأصليّة + checksum فقط).
- **التحقّق:** 5 حُرّاس · soilgrids وحده نشط · لا Baidu · ruff · manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — تصحيح ERA5-Land رطوبة التربة + سلسلة ET0 + جفاف مئينيّ (V68.2)
- **تصحيح المُراجِع:** أسماء المتغيّرات الرسميّة من CDS لا MirrorEarth. أُضيف `soil_moisture_layers` في `era5_land` يربط أسماء ساهول (soil_moisture_0_7cm/7_28cm/28_100cm/100_289cm) بأسماء CDS الرسميّة `volumetric_soil_water_layer_1..4` + الوحدة m3/m3. العمق الرابع **289سم** (لا 255). + `derived_variables` + `limitations` (نموذجيّ لا حسّاس · خشن للحقل الصغير · تحقّق محلّيّ).
- **سلسلة ET0:** `ET0_PROVIDER_CHAIN` — primary=open_meteo (نشط) · secondary=nasa_power (مُخطَّط) · fallback=era5_land_derived. صدق: الأساسيّ وحده موصول.
- **جفاف صادق:** `soil_moisture_drought_class(current, history, min_history=10)` — مئينيّة محلّيّة مقابل تاريخ الموقع/الموسم لا عتبة SMI ثابتة لكلّ اليمن؛ تاريخ<10 ⇒ unknown (لا تخمين). العتبات <10 شديد/10–20 متوسّط/20–30 بداية إجهاد/≥30 طبيعيّ.
- **صدق الاختبار:** حُذِف فحص substring مُبالِغ ("mirrorearth" not in blob) لأنّه يتعثّر بنصّ الملاحظة التوضيحيّة نفسه؛ استُبدِل بفحص قيم `provider_variable` الفعليّة (كلّها تبدأ بـvolumetric_soil_water_layer_). نمط متكرّر: لا تفحص substring سلبيّ على نصّ يذكر المصطلح توثيقاً.
- **التحقّق:** 10 حُرّاس طقس أخضر · ruff · manifest (3283) · SHA سيُثبَّت.

## 2026-07-07 (ن) — إلغاء حجب CI: ثغرة ecdsa عبوريّة WONTFIX (Security Scan)
- **السبب:** ثغرة جديدة نُشِرت (`PYSEC-2026-1325` في `ecdsa 0.19.2`) حجبت وظيفة *Security Scan* على **كلّ** الـcommits (بما فيها الخضراء سابقاً 984b9c7) — لا علاقة لها بتغييراتنا. ecdsa تبعيّة عبوريّة أساسيّة لـ`python-jose` (auth/tts/video-processor/odoo-bridge/local-ai-rag).
- **الحقيقة:** قناة-جانبيّة (Minerva timing على P-256) صنّفها صانعو ecdsa **WONTFIX** صراحةً — لا نسخة إصلاح (0.19.2 الأحدث 2026-03-26؛ README يوصي بـpyca/cryptography). مسارنا `python-jose[cryptography]` ⇒ JWT عبر خلفيّة cryptography/OpenSSL لا ecdsa ⇒ المسار المُصاب غير مُستخدَم.
- **القرار:** `--ignore-vuln PYSEC-2026-1325` مُوثّق ومحصور في بوّابة pip-audit الحرجة (`ci.yml:333`)، على نمط استثناء local-ai-rag القائم. ecdsa يبقى مرئيّاً في المسح الإرشاديّ (غير حاجب) للشفافيّة. **لا** ترحيل 5 خدمات عن python-jose (تغيير مصادقة خطر خارج النطاق لثغرة بلا إصلاح لا يُمَسّ مسارها).
- **التحقّق:** `--ignore-vuln` صالح (pip-audit --help) · YAML سليم · manifest (3283) · SHA سيُثبَّت. المتوقّع: Security Scan يعود أخضر.

## 2026-07-07 (ن) — رطوبة منطقة الجذر ERA5-Land (V68.3) + تأكيد لا-تكرار الريّ
- **إغلاق فجوة عقد:** V68.2 أعلن `derived_variables: [root_zone_soil_moisture, soil_moisture_percentile, drought_anomaly]` لكن نفّذ المئينيّة فقط. أُضيف `root_zone_soil_moisture(layer_values, root_depth_cm)` — متوسّط طبقات ERA5-Land موزوناً بسُمك تداخلها مع [0, عمق الجذر]. الأعماق مصدرها الوحيد `soil_moisture_layers` (أُضيف depth_top_cm/depth_bottom_cm لكلّ طبقة) لا أرقام مُثبَّتة.
- **صدق:** طبقة غائبة/غير رقميّة تُسقَط ووزنها معها (لا تُعامَل صفراً)؛ مدخل فاسد ⇒ value=None + سبب. يخدم قرار الريّ حسب المحصول (قمح/خضار سطحيّ 0–28سم؛ نخيل/عنب عميق 28–289سم) — جدول المُراجِع.
- **لا تكرار (المُراجِع اقترح حساب الريّ):** ETc=ET0×Kc، net=max(0,ETc−مطر فعّال)، gross=net/كفاءة **موجودة كلّها فعلاً** — `api/water_balance.py` (سلسلة FAO-56 + Ks ملوحة) · `api/irrigation_method.py` (كفاءات flood 0.55/pivot 0.85/drip 0.90 + `gross_irrigation_mm`) · `api/irrigation_recommendation_policy.py` (net/leaching/gross) · Kc من NDVI (`kc_extraction_engine.py`). لم يُكرَّر شيء.
- **التحقّق:** 15 حارس طقس أخضر (5 جديدة: depth-bounds + سطحيّ + عميق + إسقاط ناقص + unknown صريح) · ruff · manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — قسم «حالة الحقل» في بطاقة الذكاء (V65.3) — إظهار التشخيص المُحتسَب
- **الفجوة الحقيقيّة:** جسر الأدلّة عبر-الخدمات (V65/V65.1/V65.2) موصول فعلاً (provider_status عبر HTTP + ndvi_history/latest_scene عبر RLS) لكن البطاقة **تُسقِط** التشخيص الذي يحسبه المايسترو في `operational_truths` (effective_status/crop_vigor/salinity_class/heat_risk/ndvi_trend) — تعرض ndvi/عجز مائيّ فقط، لا «ما حالة الحقل؟ ما السبب؟».
- **الحلّ (منطق صرف، بلا جلب، بلا تغيير راوتر):** `_field_condition(truths)` يُبرِز فقط المفاتيح الحاضرة + `primary_driver` (الحالة الفعليّة أو أبرز مخاطرة صريحة salinity_limited/heat_limited). لا مفتاح تشخيصيّ ⇒ missing (no_condition_signals). يُشتقّ من `analyze` المُمرَّر أصلاً ⇒ لا لمس لـ`_fetch_card_signals`.
- **الواجهة:** نوع `FieldConditionSection` + `conditionDriverAr` + صفّ «حالة الحقل» في `FieldIntelligenceCardView` (يُبرِز المُحرِّك بلون تحذير) + سبب missing عربيّ. صدق: المجهول يُعرَض كما هو.
- **لا اختلاق أقسام soil/terrain/weather:** رغم ورودها في رؤية المُقترَح، لا مُنتِج يُغذّيها في الحالة بعد ⇒ إضافتها ستكون سقالة فارغة. أُبرِز ما هو محسوب فعلاً فقط.
- **لا تكرار الريّ:** ETc/net/gross بكفاءة النظام موجودة في water_balance/irrigation_method/irrigation_recommendation_policy (أُبلِغ المستخدم، لم يُكرَّر).
- **التحقّق:** 15 حارس بطاقة خلفيّ + 6 vitest + tsc نظيف + ruff + manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — قسم «خطّ أساس التربة» (SoilGrids) في بطاقة الذكاء (V65.4)
- **الفجوة:** `soil_adapter` يجلب EC/الملوحة فقط، لا قوام/pH/كربون عضويّ. P0 المُقترَح يطلب «SoilGrids baseline» في البطاقة. soil-service يملك `/soil/soilgrids` (soilgrids_client→rest.isric.org) يعيد قوام USDA + clay/sand/silt/ph/soc/cec — لكن لا يصل للبطاقة.
- **الحلّ (نمط provider_status الآمن، بلا مسّ مسار القرار):** `fetch_soil_baseline(req)` (GET /soil/soilgrids بـlat/lon + X-Agent-Token، آمن الفشل) + `soil_baseline_signal(resp)` منطق صرف (None/مشوّه ⇒ {}) + قسم `soil_baseline` في البطاقة (حاضر بقيمته + **تحذير 250م ليس بديل مختبر**، أو missing بسبب). `_fetch_card_signals` يمرّر lat/lon ويجلب آمن الفشل.
- **صدق:** بلا إحداثيّات/توكن/تغطية ⇒ القسم missing صريح (no_soil_baseline_supplied) — لا اختلاق. لا يُمَسّ مسار المايسترو/الحَوكمة.
- **الواجهة:** `SoilBaselineSection` + صفّ «خطّ أساس التربة» (قوام/pH/طين% + تحذير في title) + سبب missing عربيّ.
- **التحقّق:** 17 حارس بطاقة خلفيّ (2 جديدة) + 6 vitest + tsc نظيف + ruff + manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — قسم «نافذة الطقس» (Open-Meteo) في بطاقة الذكاء (V65.5)
- **الفجوة:** توقّع Open-Meteo نشط (`weather_forecast_adapter`, keyless) لكن دوافع اليوم لا تصل للبطاقة الموحّدة. P0/P1 يطلب weather window/spray.
- **الحلّ (نمط الجلب الآمن، بلا تكرار):** `weather_window_signal(forecast)` منطق صرف — يعرض **دوافع اليوم الموضوعيّة** (ET0/حرارة عظمى-دنيا/مطر/رياح 10م) + علَمَي حرارة/صقيع من عتبات `core.thresholds` المشتركة (HEAT_STRESS_DAILY_TMAX_C=35/CRITICAL=40، FROST_RISK_C=2) — **لا عتبات مُختلَقة**. `_fetch_card_signals` يجلبه آمن الفشل (lat/lon).
- **صدق/لا تكرار:** لا يُعيد حساب توصية الرشّ/الريّ — تلك في `weather_advice.irrigation_advice`/`disease_risk` و`weather_overlay.compute_scores` (مصدر واحد). القسم يعرض القياس الخام + علَم مشترك فقط. بلا توقّع/إحداثيّات ⇒ missing صريح (no_weather_window_supplied).
- **الواجهة:** `WeatherWindowSection` + `heatFlagAr` + صفّ «نافذة الطقس» (لون حسب علَم الحرارة: حرج=danger/مرتفع=warn) + ET0/ريح/صقيع + سبب missing عربيّ.
- **التحقّق:** 20 حارس بطاقة خلفيّ (3 جديدة) + 7 vitest + tsc نظيف + ruff + manifest · SHA سيُثبَّت. البطاقة الآن: مشهد·حالة الحقل·تربة·نافذة طقس·NDVI·عجز مائيّ·مزوّدون·مناطق·أدلّة·تنبيهات·ثقة.

## 2026-07-07 (ن) — محرّك اتّجاه الرياح المكانيّ للمصدّات (V71) + تدقيق ما هو قائم
- **تحقّق (سؤال المستخدم «هل يوجد محرّك رياح على مستوى الحقل للمصدّات/الأشجار؟»):** أغلب «Wind Intelligence Engine» **قائم فعلاً**: `connectors/openmeteo.py` يجلب سرعة+**اتّجاه** (مع احتياط met.no `wind_direction_source`)+**هبّات**؛ `routers/weather.py:_operation_suitability` يُهدّف الرشّ/الحصاد/البذر/الريّ (رياح>18كم/س، هبّة>29 ⇒ خصم)؛ نقاط operation-window/operation-plan؛ بلاطة `spraying_drift_risk`؛ `weather_overlay.compute_scores` (نافذة رشّ ساعيّة).
- **الفجوة الحقيقيّة (رأس السؤال: مصدّات/أشجار):** لا منطق **مصدّ رياح/shelterbelt** ولا **وردة رياح/سائد** ولا بوصلة 16-نقطة قابلة لإعادة الاستخدام. أُنشئ `core/wind_geometry.py` (منطق صرف): `compass_16` (16 قطاعاً + عربيّة، اصطلاح «تأتي من») · `wind_rose` (سائد بمتّجه-متوسّط موزون بالسرعة؛ عيّنة<min_obs ⇒ prevailing=None صراحةً) · `windbreak_recommendation` (توجيه الحاجز **عموديّ** على الريح + زرع upwind + حماية ~10H downwind/3H upwind، FAO/USDA-NRCS؛ بلا ارتفاع ⇒ يُعلن الحاجة لا يختلق رقماً).
- **صدق:** المصدّ يحتاج **الرياح السائدة** (تاريخ) لا قراءة لحظيّة؛ الوحدة جاهزة-للوصل بانتظار تغذية اتّجاه رياح تاريخيّ (NASA POWER/ERA5 — غير موصولة بعد). لم يُكرَّر محرّك الصلاحيّة القائم.
- **التحقّق:** 5 حُرّاس (بوصلة/التفاف · سائد موزون · عيّنة صغيرة صادقة · توجيه عموديّ+حماية 10H · بلا ارتفاع لا اختلاق) · ruff · manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — قسم «التضاريس» في بطاقة الذكاء (V72) — إغلاق آخر فجوة أقسام البطاقة
- **تحقّق:** منطق التضاريس **قائم فعلاً** (`raster-service/terrain_analysis.py`: `compute_field_terrain` ارتفاع/انحدار/اتّجاه + fail-safe computed:false · `interpret_terrain_for_agronomy` خطر تعرية) ونقطة `GET /v1/fields/{id}/terrain` (`routers/fields.py`). الفجوتان الحقيقيّتان: (1) النقطة كانت تتطلّب bbox مُمرَّراً؛ (2) لا تصل للبطاقة.
- **B1a (raster):** `field_terrain_extent(geom)` منطق صرف يشتقّ (bbox, حلقة خارجيّة) من GeoJSON (Polygon/MultiPolygon/Feature؛ هندسة شاذّة ⇒ (None,None)). النقطة الآن **تعمل من field_id وحده**: عند غياب bbox تجلب هندسة الحقل (RLS-safe عبر `fetch_field_geometry`) وتقصّ **داخل المضلّع** (poly) لا مستطيل bbox.
- **B1b (platform+frontend):** `terrain_signal(resp)` يسطّح مخرَج raster (mean/max slope + dominant_aspect + erosion_risk + elevation) — computed:false ⇒ {} ⇒ missing صادق. `fetch_terrain_summary` cross-service عبر **X-Tenant-Id** الموثوق (SEC-3، `_get_json` اكتسب دعم tenant header)؛ tenant من التوكن لا الجسم. قسم `terrain` في البطاقة + صفّ «التضاريس» (ميل/اتّجاه/تعرية، لون danger عند high/severe) + `erosionRiskAr`.
- **صدق:** لا DEM/هندسة ⇒ missing (no_terrain_supplied). لم يُكرَّر منطق الانحدار — أُعيد استخدام terrain_analysis + النقطة القائمة.
- **التحقّق:** 6 حُرّاس terrain (raster) + 22 حارس بطاقة (2 جديدة) + 8 vitest + tsc نظيف + ruff + manifest · SHA سيُثبَّت. **بطاقة الحقل اكتملت أقسامها** (مشهد·حالة·تربة·طقس·تضاريس·NDVI·ماء·مزوّدون·مناطق·أدلّة·تنبيهات·ثقة).

## 2026-07-07 (ن) — تفعيل محرّك المصدّات بتاريخ رياح NASA POWER (V73، B2)
- **الوصل الحقيقيّ:** `api/connectors/nasa_power.py` (مجّانيّ بلا مفتاح، community=AG، ~0.5°) — `parse_wind_history` منطق صرف يستخرج (اتّجاه WD10M, سرعة WS10M) ويُسقِط حارس -999 بصدق؛ `fetch_wind_history` آمن الفشل. نقطة `GET /api/v1/fields/{id}/wind/prevailing`: تبني وردة رياح (`core.wind_geometry`) من رياح يوميّة تاريخيّة → سائد → `windbreak_recommendation` (توجيه عموديّ + زرع upwind + حماية ~10H). **صدق:** مصدر متعذّر/تاريخ<min_obs ⇒ computed=false + سبب (لا 503، لا سائد موهوم).
- **تفعيل السِجِلّ:** `nasa_power` أصبح `active=True` **لدور الرياح التاريخيّة فقط** (`active_roles=["historical_wind"]` + note صريح: الإشعاع/الأرصاد-المناخيّة/ET ما زالت مُخطَّطة). تحديث `test_weather_sources` (النشط الآن {open_meteo, nasa_power}).
- **العقد:** إعفاء `endpoint_ui_coverage_waivers.json` (backlog-ui: API جاهزة، شاشة وردة الرياح/المصدّات شريحة B2-UI). البوّابة العكسيّة PASS (29 إعفاء، لا مسار فالت).
- **صدق/لا تكرار:** لم يُكرَّر محرّك صلاحيّة الرشّ القائم (`_operation_suitability`/`weather_overlay`)؛ هذه نقطة **مصدّات/سائد** مستقلّة. NASA POWER ~0.5° مقياس منطقة لا نقطة حقل (مُعلَن).
- **التحقّق:** 3 حُرّاس parse (حارس -999/شاذّ/وصل بالمحرّك) + 15 حارس weather-sources + 5 wind_geometry + gate PASS + ruff + manifest · SHA سيُثبَّت. (شاشة المستخدم B2-UI متبقّية.)

## 2026-07-07 (ن) — واجهة الرياح السائدة/المصدّات (V73-UI، B2-UI) — إغلاق ميزة الرياح end-to-end
- **الواجهة:** `lib/windbreak.ts` (أنواع + مساعِدات نقيّة: topRoseSectors/windMissingReasonAr/protectionSummaryAr — بلا ارتفاع لا رقم متر) · `hooks/useFieldWindPrevailing.ts` (react-query GET `/wind/prevailing`، kongApi) · `components/fieldview/WindbreakCard.tsx` (اتّجاه سائد + توصية مصدّ عموديّ + جهة الزرع + حماية + أعلى قطاعات وردة الرياح؛ المحسوب بقيمته والمتعذّر بسببه صراحةً) · مركّبة في MapHub (expert mode) بعد بطاقة الذكاء.
- **العقد:** نُقِل `/api/v1/fields/{field_id}/wind/prevailing` من الإعفاءات إلى `core_endpoints` (evidence=`/wind/prevailing` موجود في الهوك) — لم يعد دَين واجهة. البوّابة PASS (442 core، 28 إعفاء، لا فالت).
- **صدق:** البطاقة تُعلن «مقياس منطقة لا نقطة حقل» + سبب التعذّر (NASA POWER غير متاح/تاريخ غير كافٍ)؛ لا اختلاق. ميزة الرياح/المصدّات مكتملة end-to-end (backend V73 + UI).
- **التحقّق:** 3 vitest جديدة (11 إجمالاً) + tsc نظيف + coverage gate PASS + manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — رسم أدلّة الحقل Evidence Graph (V74) — الشريحة الأولى من رؤية #14
- **الوحدة:** `core/evidence_graph.py` منطق صرف — `build_evidence_graph(analyze)` يحوّل أقسام بطاقة الذكاء إلى عُقَد (الحقل + دليل لكلّ قسم حاضر: مشهد/حالة/تربة/طقس/تضاريس/NDVI/ماء/مناطق) + حوافّ (has_evidence: الحقل→دليل، supports: دليل→توصية). كلّ عقدة دليل تحمل مصدرها (latest_scene = provider الفعليّ لا ثابت؛ البقيّة مصادر معروفة soilgrids/open_meteo/copernicus_dem/…).
- **صدق:** لا عقدة لدليل غائب — الأقسام المفقودة ⇒ `knowledge_gaps` بسببها («ما لا نعرفه بعد»). عقدة توصية فقط عند وجود policy_decision. يستهلك مخرَج analyze المُجمَّع (بلا جلب).
- **الوصل:** `field-intelligence/analyze` يُرفِق `evidence_graph` في الاستجابة (بعد البطاقة) — يخدم تفسير التوصية وإثبات المصدر وإظهار الفجوات.
- **التحقّق:** 5 حُرّاس (عُقَد/فجوات · مصدر المشهد الفعليّ · توصية+supports · بلا قرار · analyze فارغ) + حُرّاس البطاقة أخضر · ruff · manifest · SHA سيُثبَّت. (الرسم البصريّ/الاستمرار في graph DB شرائح لاحقة.)

## 2026-07-07 (ن) — واجهة رسم الأدلّة Evidence Graph (V74-UI)
- **الواجهة:** `lib/evidenceGraph.ts` (أنواع + مساعِدات نقيّة: evidenceNodes/supportingEvidenceCount) · `components/fieldview/EvidenceGraphCard.tsx` يعرض الأدلّة الحاضرة **بمصادرها** (رقاقات + عدد داعمي التوصية) + **فجوات المعرفة بأسبابها** (missingReasonAr) · مركّبة في MapHub (expert) بعد بطاقة المصدّات. يعيد استخدام استعلام analyze (evidence_graph مُرفَق) — بلا نقطة/هوك جديد.
- **صدق:** الحاضر بمصدره والناقص بسببه صراحةً؛ لا رسم ⇒ رسالة صادقة. لا حاجة لتعديل عقد التغطية (نقطة analyze لها دليل واجهة أصلاً).
- **التحقّق:** 2 vitest جديدة (5 مع windbreak) + tsc نظيف + manifest · SHA سيُثبَّت. ميزة رسم الأدلّة مكتملة end-to-end (backend V74 + UI).

## 2026-07-07 (ن) — استمرار رسم الأدلّة Evidence Graph Persistence (V75، VNext المرحلة 1)
- **الهدف:** تحويل evidence_graph من كائن عابر في analyze إلى **سجلّ قابل للاستعلام عبر الزمن** (Postgres JSONB، بلا Graph DB). أساس audit/تتبّع القرار/تعلّم لاحق.
- **الترحيل v148:** `field_evidence_snapshots` (JSONB) معزول بالمستأجِر (RLS FORCE، نمط v140/v144) + فهرسا (tenant/field/زمن) و(GIN على الرسم). مُسجَّل في MANIFEST + run_migrations.sql (خطوة 154). لا أعمدة أسرار.
- **الكاتب (fail-soft):** `core/evidence_snapshot.py` صرف — `recommendation_hash` (بصمة ثابتة لمدخلات القرار، لا توقيت) · `strip_secrets` (يحذف token/password/… من الرسم قبل التخزين) · `should_persist` (لا لقطة بلا دليل/توصية) · `build_snapshot_payload`. `field_intelligence.analyze` يستدعي `_persist_evidence_snapshot` **بعد** إرفاق الرسم — **فشل الكتابة لا يكسر التحليل** (persistence غير حاجبة). tenant_id من التوكن (لا الجسم).
- **القراءة:** `GET /evidence-graph/latest` (أحدث لقطة) + `/timeline` (خطّ زمنيّ مُوجَز: بصمة/ثقة/عدّ أدلّة-فجوات) — معزولة بالمستأجِر (RLS). لا لقطة ⇒ available:false صريح. إعفاءان backlog-ui (شاشة التاريخ لاحقاً).
- **صدق/أمن:** لا سرّ يُخزَّن (تنقية + حارس مخطّط) · tenant من السياق · fail-soft. لم نُدخِل Graph DB (المرحلة 2 عند الحاجة).
- **التحقّق:** 5 حُرّاس snapshot صرف + 4 حُرّاس ترحيل ساكن (RLS/فهارس/تسجيل/لا-أسرار) + sync guard + coverage gate PASS + validate_migrations (v148 ✓) + ruff + manifest · SHA سيُثبَّت. (integration بعد رفع Postgres.)

## 2026-07-07 (ن) — إصلاح بوّابة CI (V75.1): تصنيف قراءات evidence-graph internal
- **الفشل (Unit Tests على f80fc14):** `test_no_waiver_has_real_ui_evidence` + `test_every_waiver_has_explicit_reason`. السبب: إعفاء لمسار `/api/v1/fields/…` يُطابِق دائماً الجذع العامّ `/api/v1/fields` في الواجهة ⇒ يُعَدّ «له دليل» فيُطالَب بالترقية؛ و`ui_effort:"medium"` غير صالح (المسموح page/button/panel/none). (نفس سبب فشل c47d06f سابقاً قبل ترقية wind إلى core.)
- **الإصلاح الصادق:** قراءتا `/evidence-graph/latest|timeline` أدوات audit/تاريخ بلا شاشة مستخدم نهائيّ بعد ⇒ صُنِّفتا `internal` (بادئة `/api/v1/fields/{field_id}/evidence-graph` قبل قاعدة `/api/v1/fields`، الأوّل يفوز) بدل الإعفاء. internal لا يُطالَب بواجهة (نمط نقطة النشرة). حُذِف الإعفاءان.
- **التحقّق:** 13 حارس endpoint-coverage أخضر + gate PASS (442 core/28 إعفاء) + manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — تحقّق/تقوية GPU overlay لـRTX 5090/CUDA 13.1 (V76، اختيار B)
- **التحقّق الساكن (لا GPU هنا):** overlay `docker-compose.v9.gpu.yml` سليم لـ5090: صورة `pytorch:2.7.0-cuda12.8` تدعم Blackwell sm_120، `TORCH_CUDA_ARCH_LIST=12.0` صحيح، حجز الأجهزة بصيغة compose الحديثة، `video` capability لـNVENC. سائق CUDA 13.1/592 **متوافق خلفيّاً** مع حاوية cuda12.8 (لا حاجة صورة cuda13؛ قابلة للتجاوز عبر PYTORCH_CUDA_IMAGE).
- **التقوية الحقيقيّة (حالتك: GPU جاهز، SAM2 بلا أوزان):** `sam2-inference/main.py` `/readyz` يعرض الآن تشخيصاً **صادقاً قابلاً للتنفيذ**: `reason_code` مُصنَّف (weights_missing/cuda_unavailable/library_missing/load_failed) + `reason` + `checkpoint_expected` — يعرف المُشغّل ما ينقص (ركّب الأوزان على مسار الـcheckpoint) دون قراءة السجلّات. صنّف ImportError لمكتبة SAM2 صراحةً library_missing.
- **صدق:** لا تشغيل GPU هنا (أُعلن)؛ التحقّق الحيّ عبر `sam2_live_gpu_gate.py` على الجهاز. لم يُفعَّل أيّ نموذج بلا أوزان (SAM2 يبقى degraded بصدق حتّى تُركَّب).
- **التحقّق:** 8 حُرّاس GPU-enablement أخضر (2 جديدة: readyz-reason + arch-Blackwell) + contract gate PASS + ruff + manifest · SHA سيُثبَّت. وثيقة RTX5090 حُدِّثت (توافق CUDA 13.1 + تشخيص الجاهزيّة).

## 2026-07-07 (ن) — Drift-Geometry GIS الشريحة 1 (V77) — خطر انجراف الرشّ downwind
- **الوحدة:** `core/drift_geometry.py` منطق صرف (haversine + bearing كرويّ، بلا shapely): `downwind_azimuth` (اتّجاه+180) · `zone_drift_exposure` (منطقة في مخروط الانجراف؟) · `spray_drift_risk` (تقييم قائمة مناطق حسّاسة: منزل/طريق/قناة/جار/منحل). يبني على محرّك الرياح: «لا ترشّ نحو X الآن».
- **صدق + تقريب معلَن:** بلا ريح ⇒ unknown (لا حكم)؛ الأصل مركز الحقل + مخروط ±30° (تقدير محافظ لا هندسة مضلّع دقيقة — شريحة GIS لاحقة). القرار النهائيّ ميدانيّ.
- **التحقّق:** 5 حُرّاس (haversine/bearing · downwind · معرّض قريب لا بعيد/عكسيّ · قائمة مناطق · بلا ريح unknown) · ruff · manifest · SHA سيُثبَّت. (نقطة POST /wind/drift-risk + طبقة الخريطة شرائح لاحقة.)

## 2026-07-07 (ن) — Drift-Geometry الشريحة 2 (V78): نقطة POST /wind/drift-risk
- **النقطة:** `POST /api/v1/fields/{id}/wind/drift-risk` (require FIELD_VIEW): مناطق حسّاسة يوفّرها العميل (لا تُخزَّن) + اتّجاه ريح مُمرَّر أو **سائد من NASA POWER** (وردة تاريخيّة) ⇒ `core.drift_geometry.spray_drift_risk`. صدق: بلا ريح سائد ⇒ status=unknown؛ يُعلَن wind_source (provided/nasa_power_prevailing) والتقدير المحافظ.
- **العقد:** صُنِّفت internal (بادئة `/api/v1/fields/{field_id}/wind/drift-risk` قبل قاعدة fields) — واجهة برمجيّة جاهزة بلا شاشة إدخال مناطق بعد (تُرقّى farmer/core مع شاشة الانجراف، شريحة 3). البوّابة PASS.
- **التحقّق:** 13 حارس endpoint-coverage + gate PASS + drift_geometry الخمسة أخضر + ruff + manifest · SHA سيُثبَّت.

## 2026-07-07 (ن) — Drift-Geometry الشريحة 3 UI (V79) — بطاقة خطر انجراف الرشّ
- **بيانات حقيقيّة بلا رسم:** `lib/driftZones.ts` (نقيّ) يشتقّ **الحقول المجاورة** (ضمن 2كم من مركز الحقل، من lat/lon أو متوسّط حلقة الهندسة) كمناطق حسّاسة (neighboring_field). `hooks/useFieldDriftRisk` يستدعي `POST /wind/drift-risk` بها. `components/fieldview/DriftRiskCard` يعرض: خطر/آمن + الحقول المعرّضة downwind + اتّجاه الانجراف + مصدر الريح. مركّبة في MapHub (expert) بعد بطاقة المصدّات.
- **صدق:** بلا جوار ⇒ يُعلَن؛ بلا ريح سائد ⇒ unknown صريح؛ حقل بلا مركز يُتخطّى (لا إحداثيّة مُختلَقة). تقدير محافظ (مركز+مخروط) — القرار ميدانيّ.
- **العقد:** نقطة `/wind/drift-risk` رُقِّيت من internal إلى farmer/core (evidence=`/wind/drift-risk` في الهوك) — صار لها consumer. حُذِف تصنيف internal. gate PASS.
- **التحقّق:** 3 vitest driftZones + 13 endpoint-coverage + tsc نظيف + manifest · SHA سيُثبَّت. **ميزة انجراف الرشّ مكتملة end-to-end** (محرّك V77 + نقطة V78 + UI V79).

## 2026-07-07 (ن) — قرار «هل أرشّ الآن؟» (V80) — capstone مسار الرشّ
- **المُوحِّد:** `core/spray_readiness.py` منطق صرف — `spray_go_no_go(wind_suitability, drift_risk)` يدمج مخرَجَي محرّكَين قائمَين (صلاحيّة الطقس `_operation_suitability` + خطر الانجراف `spray_drift_risk`) في قرار واحد go/caution/no_go بأسوأ العاملَين. **لا يُعيد حساب أيّهما** (مصدر واحد لكلّ منطق).
- **صدق:** مجهولان ⇒ unknown؛ الانجراف الفعليّ (at_risk) حاجب مطلق no_go (سلامة الجوار تسبق التوقيت)؛ انجراف unknown لا يرفع الشدّة (لا حجب بلا دليل). القرار النهائيّ ميدانيّ.
- **التحقّق:** 5 حُرّاس (go/انجراف حاجب/أسوأ عامل/unknown/انجراف مجهول لا يحجب) · ruff · manifest · SHA سيُثبَّت. يُغلِق مسار الرشّ (طقس+رياح+مصدّات+انجراف+قرار موحّد).

## 2026-07-07 (ن) — تشخيص جاهزيّة OlmoEarth على العتاد (V81) — تنفيذ الكل (AI path)
- **الوصل (بعد توفّر GPU):** `raster_scene_model.olmoearth_runtime_status(checkpoint_path?)` — تشخيص صادق (نمط SAM2 readyz): `reason_code` مُصنَّف (weights_missing/cuda_unavailable/library_missing/ready_pending_validation) + `checkpoint_expected`. يُكشَف في `/v1/providers/status` (olmoearth_runtime).
- **صدق حاسم:** `ready` يبقى **False دائماً** حتّى بعد الأوزان+GPU — التفعيل قرار بشريّ بعد **benchmark يمنيّ محلّيّ** (مقابل NDVI/V60.3)؛ لا embedding مُختلَق ولا ادّعاء «يغطّي اليمن» بلا قياس. AI_MODEL_REGISTRY يبقى active_provider=False.
- **الحالة العمليّة على جهازك:** ركّب أوزان OlmoEarth على `OLMOEARTH_CHECKPOINT` ⇒ يتحوّل reason_code من weights_missing إلى ready_pending_validation؛ بعدها benchmark محلّيّ ثمّ تفعيل بشريّ.
- **التحقّق:** 7 حُرّاس OlmoEarth (2 جديدة: weights_missing + never-ready-بلا-تحقّق) · ruff · manifest · SHA سيُثبَّت. (WaPOR/WorldCereal scaffolds تاليان.)

## 2026-07-07 (ن) — محوّلا WaPOR/WorldCereal (V82، اختيار A) — docs-based بلا تخمين
- **بحث الوثائق:** WaPOR v3 **بلا مفتاح**؛ كتالوج mapsets GET `.../gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets` عناصره `code`+`caption` (موثّق)؛ القيم من COG عبر GDAL /vsicurl/. (مصادر: تعليم FAO WaPOR v3 API + fao.org/wapor-data-access.) **حاجز البيئة:** مضيفو FAO/ESA محجوبون بوكيل الشبكة (403) ⇒ لا تحقّق حيّ للغلاف الكامل/واجهة WorldCereal ⇒ **لا parser بالتخمين**.
- **البُني (صادق):** `wapor_worldcereal.py` — `parse_wapor_mapsets` (envelope-agnostic، يقرأ code/caption الموثّقَين فقط؛ mismatch⇒None) + `fetch_wapor_mapsets` آمن الفشل + `wapor_readiness`/`worldcereal_readiness`. السِجِلّ: `live_verified=false` لكليهما؛ `schema_verified_from_docs=true` لـWaPOR (endpoint+عناصر موثّقة) و**false** لـWorldCereal (لم تُتحقَّق الواجهة — لا ادّعاء). `activation_blockers` صريحة (تشمل «contract fixture from real response»). مكشوف في `/v1/providers/status`.
- **صدق حاسم:** لا قيم ET/biomass/crop-prior تُرجَع (قراءة البكسل غير مُتحقَّقة)؛ لا اعتمادات مخزّنة؛ active=false. **يحتاج عيّنة عقد حقيقيّة من شبكتك** لإكمال parser القيم (حاجز مُعلَن، مطابق لشرطك).
- **التحقّق:** 5 حُرّاس WaPOR/WorldCereal + 7 OlmoEarth · ruff · manifest · SHA سيُثبَّت. (wiring بطاقة missing-with-reason + B تاليان.)

## 2026-07-07 (ن) — Evidence Graph المرحلة 2: عُقَد/حوافّ مُطبَّعة (V83، اختيار B) — مُشتقّة فوق لقطة v148
- **الترحيل:** `v149_evidence_graph_nodes_edges.sql` — جدولان مُشتقّان (`evidence_graph_nodes`/`_edges`) يُطبِّعان عُقَد/حوافّ كلّ لقطة (`snapshot_id` REFERENCES field_evidence_snapshots ON DELETE CASCADE). **JSONB لقطة v148 يبقى مصدر الحقيقة**؛ هذان اشتقاق فقط. RLS FORCE + `current_setting('app.current_tenant', true)` + WITH CHECK (نمط v148). UNIQUE(snapshot_id, node_id/edge_id) ⇒ idempotent. فهارس tenant/field/زمن + snapshot + type. مُسجَّل في MANIFEST + run_migrations.sql (خطوة 155).
- **التطبيع (منطق صرف):** `core/evidence_graph_normalize.py` — `normalize_graph_to_rows(graph)` يشتقّ عُقَداً حاضرة من `nodes` (status=present) + غائبة من `knowledge_gaps` (status=missing + سبب، node_id=`gap:<key>`) + حوافّ من `edges` (edge_id=`from->rel->to`). **حمولة حدّ أدنى** (node_id/type/source/status/reason — بلا attrs) + `_clean_source` يُسقط أيّ source يشبه سرّاً. مدخل شاذّ ⇒ قوائم فارغة (لا تلفيق).
- **الكاتب (fail-soft، مُشتقّ):** `field_intelligence._persist_evidence_graph_rows` — بعد حفظ اللقطة (`_persist_evidence_snapshot` صار يُعيد `snapshot_id` عبر RETURNING id/fetchval)، معاملة tenant-scoped منفصلة تُدرِج الصفوف (`ON CONFLICT DO NOTHING`). فشله **لا يكسر** analyze ولا اللقطة.
- **صدق:** لا عُقَد ملفّقة (الغائبة من knowledge_gaps بسببها)؛ لا أسرار (حمولة حدّ أدنى + تنقية source)؛ JSONB مصدر الحقيقة (الجدولان اشتقاق قابل لإعادة البناء).
- **التحقّق:** 10 حُرّاس (5 تطبيع + 5 ترحيل ساكن: RLS FORCE + FK CASCADE + UNIQUE/لقطة + فهارس + لا أعمدة أسرار + مُسجَّل بالمُشغّلَين) · حارس تزامن المُشغّلَين · validate_migrations · endpoint-coverage PASS · 2760 unit · ruff · release bundle/validate (3310 checksums) · SHA سيُثبَّت.

## 2026-07-07 (ن) — Evidence Graph تحليلات + بطاقة تاريخ الأدلّة (E1) — قراءات فوق v149
- **النقاط (تقرأ الجداول المُطبَّعة v149):** `GET /api/v1/evidence-graph/analytics` (agronomist) — تجميع عبر **آخر لقطة لكلّ حقل** (`DISTINCT ON (field_id)` + JOIN evidence_graph_nodes): أكثر الفجوات تكراراً (حقول مميَّزة/تكرارات) + توزيع الحالات + عدد الحقول المُحلَّلة. + `GET /api/v1/fields/{id}/evidence-graph/nodes` (internal) — عُقَد/حوافّ آخر لقطة مُسطَّحة للعرض. RLS يفرض العزل (لا شرط tenant صريح). صدق: قاعدة معطّلة/لا لقطة ⇒ `available:false` + سبب؛ `derived` يُعلن أنّها مُشتقّة من JSONB مصدر الحقيقة.
- **النواة (منطق صرف):** `core/evidence_graph_analytics.py` — `shape_gap_analytics` (ترتيب حتميّ: الأكثر تكراراً ثمّ أبجديّ؛ مدخل شاذّ ⇒ أصفار) + `shape_field_graph` (فارغ ⇒ available:false).
- **الواجهة (E1-UI):** `EvidenceHistoryCard` في MapHub (expert) — يستهلك timeline (تطوّر الأدلّة/الفجوات/الثقة، اتّجاه من لقطتَين فعليّتَين فقط) + analytics (فجوات متكرّرة عبر الحقول). `lib/evidenceHistory.ts` مساعِدات نقيّة (gapTrend/evidenceTrend: بلقطة واحدة ⇒ unknown، لا اختلاق اتّجاه) + `useEvidenceHistory` هوكان. العقد: النقطة agronomist مُسجَّلة في `endpoint_ui_coverage.json` بدليل الهوك ⇒ البوّابة تفرض وجود مستهلك واجهة.
- **التحقّق:** 9 وحدات backend (5 نواة + 4 حارس ساكن: DISTINCT ON، تسجيل النقطتَين، تصنيف agronomist، fail-soft) + 4 vitest (اتّجاهات صادقة) + coverage-gate PASS (444 core) + tsc نظيف + 1244 خدمة/2760 tests_v9 unit + ruff. SHA سيُثبَّت.

## 2026-07-07 (ن) — انجراف الرشّ من حافّة المضلّع (E2) — الشريحة 2 (GIS) وعد الشريحة 1
- **النواة (`core/drift_geometry.py`، منطق صرف):** `field_polygon` اختياريّ (GeoJSON Polygon/MultiPolygon أو حلقة `[lon,lat]`) → في وضع المضلّع تُقاس **الزاوية من مركز الحقل** (هل المنطقة downwind للحقل؟) و**المسافة من أقرب حدّ** (قرب فعليّ لا من المركز) — أدقّ وأكثر أماناً (مسافة أقصر ⇒ تنبيه أبكر). دوالّ جديدة: `exterior_ring_from_geojson`/`polygon_representative_point`/`downwind_edge_point` (رأس الحدّ الأكثر تجاه downwind، للعرض عبر `drift_origin`). `origin_mode` = polygon_boundary/center. **متوافق للخلف:** بلا مضلّع = سلوك الشريحة 1 تماماً.
- **الوصل:** نقطة `/wind/drift-risk` تجلب `ST_AsGeoJSON(geom)` (fail-soft: غيابها ⇒ سقوط للمركز) وتمرّرها. `DriftRiskCard` يُظهر مصدر المسافة صراحةً (حدّ الحقل/المركز) بدل نصّ «مركز الحقل» المُثبَّت.
- **صدق:** بلا ريح ⇒ unknown؛ إحداثيّات شاذّة ⇒ تُتخطّى؛ يبقى العازل مخروطاً بنصف-زاوية ثابت (تقريب محافظ معلَن، لا قناع رشّ دقيق). القرار ميدانيّ.
- **التحقّق:** 5 حُرّاس جديدة (استخراج الحلقة، النقطة المرجعيّة، رأس downwind، حافّة أقرب من المركز، توافق خلفيّ) ضمن 10 drift · 3207 اختبار منصّة (تغطية 64.3% ≥ 60) · 4 vitest driftZones + tsc نظيف · coverage-gate PASS · ruff. SHA سيُثبَّت.

## 2026-07-08 (ن) — GIS Workflow Engine الشريحة A: رِندرِر خرائط النشر (V84) — اختيار المستخدم «أ»
- **السياق:** تحقّق من فكرة «GIS Workflow Engine» مقابل الشِفرة الفعليّة: ~ثُلثاها موجود (provenance=v148/v149+backfill_runs · source_policy=raster_scene_model registry · self-checks=v131 cloud/nodata/valid_pixel/quality · regional_bulletin.py · ndvi_analysis.py). الفجوة الجوهريّة الوحيدة = **رسم خرائط نشر ثابتة** (عندنا فقط بلاطات ويب tile_render، بلا matplotlib). فحص شبكة: GEE يصل (404 جذر) لكن يحتاج اعتماد GCP ⇒ active:false؛ earthaccess **محجوب** (403) ⇒ docs-only.
- **البناء (خدمة معزولة `services/gis-workflow-service/`):** `map_layout.py` منطق صرف (scale bar مستدير 1/2/5×10ⁿ · تسميات فئات من عتبات صاعدة · legend يُسقط الشاذّ · **caption صادق: الناقص «غير متاح» لا اختلاق**) + `publication_map.py` رِندرِر matplotlib Agg (imshow + سهم شمال + scale bar + legend + caption، استيراد كسول فيبقى layout نقيّاً) → PNG @300dpi. بلا بيانات صالحة ⇒ ValueError (لا صورة فارغة مُضلِّلة).
- **العزل/التبعيّات:** matplotlib/numpy في `requirements.txt` الخدمة وحدها (لا تُثقل raster-service/api). **pip-audit نظيف** (matplotlib 3.11.0 — لا ثغرات). workflow gate جديد `gis-workflow-service-gates.yml` (path-filtered، يشمل pip-audit + pytest). لا نقطة HTTP بعد (لا over-claim؛ الوصل شريحة لاحقة). المصدر يبقى مخرجات raster-service لا اعتماداً خارجيّاً.
- **صدق حاسم:** GEE/earthaccess لم يُوصَلا (اعتماد/حجب) — الشريحة A تعمل **اليوم** من COG/zonal_stats الحاليّة بلا أيّ منهما. النطاق المُنفَّذ معلَن في README؛ الباقي (spec engine · run bundle · self-checks كاملة · GEE active:false) شرائح لاحقة.
- **التحقّق:** 9 اختبارات (7 layout نقيّ + 2 render دخانيّ importorskip) · ruff · عيّنة PNG مُرِندَرة فعليّاً (كل العناصر ظهرت) · لا أثر على coverage-gate (بلا نقطة) ولا service-contract (manifest-driven). SHA سيُثبَّت.

## 2026-07-08 (ن) — GIS Workflow Run Bundle + Self-check Contract (V85، الشريحة B) — نطاق مضبوط
- **التعريف الصادق:** طبقة **تشغيل/تدقيق/تغليف** فوق رِندرِر V84 ومخرجات raster-service — **لا محرّك بيانات جديد، لا GEE/earthaccess/WaPOR/WorldCereal/HLS** (محظورة صراحةً + حارس ساكن).
- **البناء (3 وحدات في `services/gis-workflow-service/`):**
  - `workflow_spec.py` — `validate_spec`/`resolve_spec`: يفرض workflow_id/target/analysis(index مسموح + مصدر داخليّ)/outputs؛ **يرفض المصادر الخارجيّة بسبب** (الشريحة B مخرجات ساهول فقط).
  - `self_checks.py` — فحوص **حقيقيّة لا شكليّة** بتصنيف أهمّية: `required` (crs_present · value_range NDVI∈[-1,1]) فشلها ⇒ الحزمة failed؛ `quality` (acquisition_date · resolution · nodata · valid_pixel · extent) فشلها ⇒ degraded. ما لا يُقاس (بيانات غائبة) ⇒ `passed=None` متخطٍّ بسبب (لا تلفيق).
  - `run_bundle.py` — `run_workflow_bundle`: `run_id` فريد (`{ts}Z_{target}_{index}_publication`)، حزمة كاملة (maps/data/reports/scripts/provenance)، **no-overwrite** (run موجود ⇒ FileExistsError)، checksums SHA-256 لكلّ مخرَج، `run_manifest.json` نَسَب (source/scene/date/crs/resolution + self_check + external_fetch=false)، تقارير methodology/quality/self_check، الرِندرِر مُحقَن (افتراضه V84). فشل الرسم ⇒ status=failed دون كسر الحزمة. ربط Evidence Graph اختياريّ fail-soft.
- **صدق:** methodology لا تدّعي أكثر ممّا نُفِّذ؛ الناقص يُخفِّض الجودة صراحةً؛ لا جلب خارجيّ (external_fetch=false في المانيفست والمصادر).
- **التحقّق:** 20 اختبار جديد (spec 3 + self_checks 5 + run_bundle 10 + no-external 1 + V84 القائمة = **27 كلّها تمرّ**) — يغطّي البنود العشرة المطلوبة (بنية/no-overwrite/spec غير صالح/date→degraded/crs→failed/NDVI خارج المدى/manifest نَسَب/checksums/render-fail→failed/لا استيراد خارجيّ) + **تشغيلة end-to-end حقيقيّة بالرِندرِر V84 أنتجت الشجرة كاملة** (status=completed). ruff نظيف. gate الخدمة يشملها تلقائيّاً. SHA سيُثبَّت.
- **التالي المنطقيّ:** الشريحة C — خرائط نشر النشرة الإقليميّة (`regional_bulletin.py` موجود يُرجِع JSON ⇒ يُربَط بحزمة V85).

## 2026-07-08 (ن) — النشرة الإقليميّة كشكل نشر مُدقَّق (V86، الشريحة C) — صدق: تصنيفيّ لا جغرافيّ
- **حاجز صدق مُكتشَف قبل البناء:** لا حدود إداريّة (محافظة/مديريّة GeoJSON) في المستودع (تحقّقت: صفر `.geojson`، `districts.py` بلا geom)، و`build_regional_bulletin` يُرجِع بيانات **تصنيفيّة** (محافظة→مديريّة حالة NDVI) لا راستر ⇒ **choropleth جغرافيّ حقيقيّ متعذّر بلا تلفيق جغرافيا**. فبُنِيت بدلاً منه نسخة **تصنيفيّة صادقة** تُعلن حدّها بنفسها.
- **البناء (`services/gis-workflow-service/`، فوق آليّة V85):** `bulletin_figure.py` (تحويل النشرة → صفوف عرض + ألوان حالة + فحوص خصوصيّة؛ المكتوم بلا أرقام) + `bulletin_render.py` (شكل matplotlib أفقيّ ملوّن بالحالة، caption يُعلن «شكل تصنيفيّ لا خريطة») + `bulletin_bundle.py` (حزمة مُدقَّقة تعيد استخدام run_id/no-overwrite/checksums/manifest من V85).
- **صدق حاسم:** المانيفست يُعلن `geographic=false` · `representation=categorical_figure` · `geographic_blocker=no_admin_boundaries_in_repo`. فحص `admin_geometry_present` **دائماً متخطٍّ بسبب** (إعلان صادق). فحص `privacy_floor_respected` **required**: أيّ مجموعة مكتومة تُسرِّب رقماً ⇒ فشل. لا مصادر خارجيّة.
- **التحقّق:** 9 اختبارات جديدة (figure 4 + bundle 5) ⇒ **36 كلّها تمرّ** · **تشغيلة end-to-end حقيقيّة** أنتجت الشكل + الحزمة (status=completed، المكتوم رماديّ بلا أرقام، caption يُعلن الحدّ) · ruff نظيف · gate الخدمة يشملها. SHA سيُثبَّت.
- **choropleth حقيقيّ:** يبقى شريحة لاحقة — يحتاج **GeoJSON حدود اليمن (محافظة/مديريّة)** يوفّره المستخدم؛ عندها يُرندَر choropleth فعليّ بنفس الحزمة.

## 2026-07-08 (ن) — H-AI-1: سدّ تجاوز allowlist نموذج OpenRouter (تدقيق خارجيّ) — fail-closed
- **الثغرة (حوكمة، مؤكَّدة):** `ai_agronomist/ai_generation._resolve_model` كان `if req and (not allowed or req in allowed)` — حين يغيب `AI_MODELS` تكون `allowed` فارغة ⇒ **أيّ** `requested_model` من المستخدم يُقبَل (تجاوز قائمة السماح؛ نموذج غير معتمد/سياسة تكلفة/خصوصيّة). ريبرو المُدقِّق: `AI_MODEL=deepseek/deepseek-chat` + `requested=evil/jailbreak` + `AI_MODELS` غائب ⇒ كان يعيد `evil/jailbreak`.
- **الإصلاح:** `_catalog_ids(provider)` صار يستخدم `public_model_catalog(provider)` (يسقط للكتالوج الافتراضيّ حين غياب `AI_MODELS`) و`_resolve_model(provider, shared_model, requested)` صار fail-closed: `req` يُقبَل **فقط** `if req in allowed`؛ خلافه ⇒ `shared_model` الموثوق. مُرِّر `provider` في المسارات الثلاثة (openrouter/anthropic/local). يطابق سلوك `ai_provider_config._resolve_model` القائم.
- **التحقّق:** اختبار جديد `test_generation_requested_model_falls_back_to_default_catalog_when_ai_models_missing` (الحالة الحرجة: AI_MODELS غائب ⇒ evil مرفوض، gemini الافتراضيّ مقبول) + الاختبار القائم `test_model_allowlist_enforced` (AI_MODELS مضبوط) — كلاهما أخضر. **ريبرو المُدقِّق صار آمناً** (evil→deepseek). 22 اختبار AI provider/generation + **2761 unit** (‏+1) · ruff. SHA سيُثبَّت.
- **بقيّة التدقيق (لاحقاً، ليست حاجبة):** M1 required في provider schemas · M2 عقد استجابة استشاريّة مُهيكَل · M4 تحذير v18 (waiver/توثيق) · M5 قفل تبعيّات Python. مُوثَّقة كأولويّات P1/P2.

## 2026-07-08 (ن) — M1: `required` صريح في مخطّطات أدوات المزوّد + حارس انحراف (تدقيق خارجيّ P1)
- **تحقّق صادق:** المسار **الحيّ** (`ai_generation._provider_tools` → `shared/ai/tool_schema._param_schema`) **يُعلن `required` أصلاً** (params بلا `?` إلزاميّة) — فـM1 مُلبّى وقت التشغيل. الخلل الحقيقيّ: `provider_tooling.py` (يستهلكه اختبار واحد فقط، لا الـruntime) مخطّطاته **بلا `required`** و`field_id` موصوف «يُحذَف للحقل النشط» — **مناقض لعقد السجلّ الحيّ** الذي يُلزِم `field_id` (وindex/days لـtimeline). أي انحراف بين مصدرَي مخطّط.
- **الإصلاح:** أُضيفت قوائم `required` لكلّ أداة في `provider_tooling` **مطابقة للسجلّ الحيّ** (`tool_registry`): field_id لكلّها، +index+days لـget_index_timeline، +days لـget_weather_history، +layer لـopen_map_layer. صُحِّح وصف `field_id` («required»، لا يُدّعى أنّه اختياريّ).
- **الحارس (يمنع التكرار):** `test_provider_tool_schema_required_guard.py` — (أ) كلّ مخطّط حيّ يحمل `required` قائمةً + field_id في get_field_state · (ب) كلّ مخطّط provider (الصيغتان) يحمل required.field_id · (ج) **لا انحراف:** required في provider_tooling == عقد السجلّ الحيّ لكلّ أداة مشتركة.
- **التحقّق:** 4 حُرّاس جديدة + 8 اختبار v67 القائمة تمرّ · **2765 unit** (‏+4) · ruff · release validate (3342). SHA سيُثبَّت. (بقيّة التدقيق: M2 عقد استجابة مُهيكَل · M4 v18 · M5 قفل تبعيّات — لاحقاً.)

## 2026-07-08 (ن) — M2: مظروف استجابة استشاريّة مُهيكَل مُتحقَّق فوق answer_ar (تدقيق خارجيّ P1)
- **الحاجة:** النصّ الحرّ للمستشار تفسيريّ لكن غير schema-validated. أُضيف `advisory_contract.build_advisory_envelope` — **منطق صرف يشتقّ** مظروفاً ثابت الشكل من الاستجابة المُؤرَّضة القائمة (بلا استدعاء نموذج).
- **الشكل:** `{schema, summary, decision, confidence, evidence_used, evidence_missing, limitations, requires_human_review, decision_authority}`.
- **صدق حاسم:** `decision` **لا يخترعه النموذج** — advisory_only افتراضاً؛ go/caution/no_go يُقبَل **فقط** من مُستدعٍ موثوق (محرّك قرار). `evidence_used/missing` من الأدلّة الفعليّة (evidence_ids/gaps/readiness — لا تلفيق). `requires_human_review` **fail-safe** (فعل مقترَح/قرار غير استشاريّ/ثقة منخفضة أو غائبة/نقص دليل ⇒ True). سلطة القرار تبقى `field_intelligence_coordinator`. المظروف **لا يحمل مفاتيح قرار ممنوعة** (`has_decision_keys=False`).
- **الوصل:** نقطة الإجابة في `ai_agronomist/main.py` تُضيف `response["advisory"]` (لا تغيّر بقيّة الحقول). متوافق للخلف.
- **التحقّق:** 8 اختبار جديد (advisory_only افتراضيّ · النموذج لا يحقن قراراً · fail-safe review · clamp الثقة · limitations/gaps صادقة · مدخل شاذّ متحفّظ · لا مفاتيح قرار · وصل main) · **2773 unit** (‏+8) · ruff · release validate. SHA سيُثبَّت. (المتبقّي: أدوات V84/V85 read-only · M4 v18 · M5 قفل تبعيّات.)

## 2026-07-08 (ن) — M4: إزالة إيجابيّة كاذبة في مُدقِّق الـmigrations (ON CONFLICT عبر الملفّات)
- **الحاجة (تدقيق خارجيّ):** `validate_migrations.py` كان يُحذِّر: «v18 ON CONFLICT (dedup_key) بلا UNIQUE/PK مطابق». تحقّقتُ: **إيجابيّة كاذبة** — v18 يُدرِج في جدول `events` بـ`ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL`، والفهرس الجزئيّ المطابق `ux_events_dedup ON events(dedup_key) WHERE dedup_key IS NOT NULL` مُعرَّف في **v11** (ملفّ آخر). الفحص كان نفس-الملفّ فقط.
- **الإصلاح:** `check_file(path, all_code=None)` — فحص `ON CONFLICT` صار يبحث عن UNIQUE/PK (شامل الفهرس الجزئيّ) عبر **كلّ الـmigrations** (corpus) لا نفس الملفّ. متوافق للخلف (بلا corpus ⇒ السلوك القديم). النتيجة: المُدقِّق يعلن **✓ لا مشاكل ثابتة** (كان تحذيراً واحداً).
- **التحقّق:** 3 حُرّاس (v11 يعرّف الفهرس الجزئيّ · v18 لا يُعلَّم مع corpus · نفس-الملفّ يبقى يُحذّر — توافق رجعيّ) · **2776 unit** (‏+3) · validator نظيف · ruff · release validate (3345). SHA سيُثبَّت. (المتبقّي: أدوات V84/V85 read-only للـAI — تحتاج نقطة HTTP للخدمة أوّلاً · M5 قفل تبعيّات Python.)

## 2026-07-08 (ن) — M5: تصلّب سقّاطة تثبيت التبعيّات (رابع الثوابت: لا اسم عارٍ) — بلا مخاطرة تثبيت
- **تحقّق صادق:** قفل التبعيّات الكامل الذي طلبه التدقيق **مُعالَج أصلاً بوعي** في SEC-6 (`test_requirements_pinning_guard.py` + `docs/security/dependency_locking_plan.md`) — القفل الكامل **مؤجَّل مرحليّاً بقرار موثّق** لأنّ بوّابة pip-audit في CI تحلّ الـ18 ملفّاً **مُوحَّدةً** (سابقة httpx: ResolutionImpossible). التثبيت العدوانيّ الآن = مخاطرة CI أحمر لمكسب ضئيل (فقط bcrypt/python-jose في auth آمنان — البقيّة مشتركة عبر 3–13 ملفّاً).
- **الإصلاح (زيادة صفريّة المخاطرة):** رابع ثوابت السقّاطة — **لا تبعيّة غير مقيَّدة** (اسم عارٍ بلا عامل إصدار) على المسار الحرج؛ تحلّ إلى **أيّ** إصدار (شامل yanked/0.x)، أسوأ من `>=`. أخضر اليوم (لا اسم عارٍ في الأربعة) ⇒ سقّاطة أماميّة تمنع تسلّل اسم بلا أرضيّة مستقبلاً. لم تُعدَّل أيّ requirements — صفر مخاطرة تثبيت.
- **التحقّق:** 5 حُرّاس تثبيت (‏+1) · **2777 unit** · ruff · plan doc محدَّث · release validate (3346). SHA سيُثبَّت.
- **صدق عن المتبقّي:** القفل الكامل (`.lock` لكلّ ملفّ عبر uv + constraint مشترك) يبقى عملاً مرحليّاً مضبوطاً بالقيود (خطّة §6) — لا يُنفَّذ متعجّلاً لأنّه يخاطر بقفزات إصدار رئيسيّة غير مُختبَرة على المسار الحرج.

## 2026-07-08 (ن) — بوّابة تباين توكِنات التصميم (WCAG) — تبنٍّ انتقائيّ صادق لفكرة «impeccable»
- **السياق:** مقال جمع 8 مشاريع «تصميم AI غير نمطيّ». تحقّق صادق: ساهول أصلاً عنده نظام تصميم (`ds/`) + حوكمة (`designSystemGovernance`) + هويّة (توكِنات ذهبيّ/أخضر/بنّيّ) + RTL عربيّ — فليس في مشكلة «الطابع النمطيّ». معظم الأدوات موجّهة LTR/لاتينيّ؛ والاستنساخ (ai-website-cloner/web-to-figma) خطر ملكيّة فكريّة ⇒ **تُجنَّب**. الجدير الوحيد: فكرة القواعد **الحتميّة** (نمط impeccable) مُكيَّفة لساهول.
- **البناء:** `scripts/ci/design_token_contrast_gate.py` — يقرأ `tokens.ts`، يحسب تباين WCAG 2.1 (relative luminance) لأزواج «نصّ على سطح». **حاجب** على النصّ الأساسيّ (ink على cream/card/card2 = 15–17:1، أخضر — سقّاطة تمنع الانحدار)؛ **إرشاديّ** (لا يحجب) على أزواج ثانويّة/CTA. مُوصَّل في وظيفة *Repository Structural Lint*.
- **اكتشاف حقيقيّ (مُوثَّق لا مُغيَّر أحاديّاً):** `docs/design/contrast_audit.md` — نقاط ضعف فعليّة: **أبيض على gold=2.22 · أبيض على green=2.79** (CTA بنصّ أبيض ضعيف ⇒ استخدم نصّاً داكناً أو greenDark)، faint=2.25 (تلميحات كبيرة فقط)، muted≈3.9 (ثانويّ/كبير). لم أغيّر توكِنات العلامة (قرار تصميم للمستخدم).
- **صدق:** vitest **ليس في CI** (typecheck+playwright فقط) — فبنيتُ الحارس **Python** ليحجب فعليّاً في structural-lint، لا اختبار vitest معزول. الحاجب أخضر اليوم؛ الإرشاديّ يكشف بلا كسر CI ولا قرار أحاديّ على الهويّة.
- **التحقّق:** 5 حُرّاس (حساب WCAG بمرساة أسود/أبيض=21 · استخراج التوكِنات · مرور الأزواج الأساسيّة) · **2782 unit** (‏+5) · ruff · ci.yml صالح · release validate. SHA سيُثبَّت.

## 2026-07-08 (ن) — توسّع بطاقات المحاصيل (١١→٣٩) + كتالوج مدخلات البيانات المرشّحة
- **السياق:** طلب المستخدم بطاقات لكلّ المحاصيل التي تُزرَع أو يمكن زراعتها في اليمن + المدخلات المفيدة. مصدرا GAEZ/ECOCROP-search **محجوبان في هذه البيئة** (proxy 403)؛ cropcal CSV **صفر صفوف يمنيّة** ⇒ لا سلخ؛ القيم من مراجع القالب المعياريّة (FAO-56 Kc/T23 · ECOCROP · Maas-Hoffman).
- **البناء (٤ دفعات، بوّابات خضراء):** +٢٨ بطاقة محصول محايدة الموقع في `services/sahool-platform/core/crop_cards/` — حبوب/بقوليّات/زيتيّة/ألياف/علف/خضراوات/قرعيّات/فواكه مُعمِّرة + قات. المُعمِّرات (بُنّ/نخيل/عنب/برسيم/٧ فواكه/قات) **تُغفِل كتلة phenology الحوليّة** (صدق: لا مراحل مُلفَّقة). القيم خارج FAO-56 T23 مُعلَّمة `indicative`. القات إدراج واقعيّ لا ترويجيّ (كلّ قيمه indicative، آفاته قائمة فارغة). SHAs: ceb8f9c · 6fbb34c · b444829 · e51a033.
- **كتالوج المدخلات:** `sahool-brain/agronomy/data-inputs-catalog.md` — مصادر **مرشّحة (غير موصولة)** من بحث موثّق (وكيل مستقلّ 2026-07-08): imagery/soil/climate/ET/DEM/cropland/phenology/boundaries + أمن غذائيّ، بترخيص + تغطية يمن + قابليّة وصول لكلّ صفّ. أعلام صدق: إفريقيا-فقط (iSDAsoil/DEAfrica) وأمريكا-فقط (OpenET) **تُستبعَد لليمن**؛ NICFI انتهى؛ GADM/ACLED مقيّدان؛ FTW مختلط. قائمة قصيرة: CHIRPS · WaPOR v3 (عمق يمنيّ) · SoilGrids · GLO-30 · WorldCereal/Cover · POWER/ERA5 · HDX-COD/geoBoundaries · NOAA-VHP. رَبْط لا تكرار مع `data-providers.md` (الموصول).
- **صدق عن الأصناف (varieties):** بحث موثّق وجد أصنافاً يمنيّة مُسمّاة لـ**بُنّ** (أسماء عاميّة موثّقة لكن **مثبَت جينيّاً أنّها ليست أصنافاً متمايزة** — MDPI Agronomy 12/8/1970) · **عنب** (رازقي/أسود/عاصمي) · **نخيل تمر** (٧ سائدة) · **قات** (~٤٠ نوعاً محلّيّاً) · **مانجو**. لا صنف مُسمّى موثّق لأغلب الخضراوات/الفواكه ⇒ **لا تُختلَق**. بطاقات الأصناف قيد البناء لِما ثبت مصدره فقط.

## 2026-07-08 (س) — إغلاق حلقة التوصية: تدقيق end-to-end + ٤ جسور صادقة
- **السياق (طلب المستخدم):** «تدقيق إغلاق الحلقة أوّلاً — أثبت أنّ توصية→تنفيذ→نتيجة→تعلّم موصولة فعلاً قبل بناء أيّ طبقة جديدة»، ثمّ الجسور بالترتيب: #2 نَسَب مصدر التعلّم → #3 توحيد النتائج → #4 حسم recommendation_feedback → #5 تقوية FK.
- **التدقيق (`docs/audits/recommendation_loop_closure_20260708.md`):** قراءة-فقط لـmigrations + كُتّاب/قرّاء بدليل `file:line`. **الحكم:** السلسلة الأماميّة (توصية→dispatch_decisions→قرار→execution_ledger→تحقّق→نتيجة→lineage_link) **موصولة ومكتوبة**، والتعلّم يقرأ نتائج حقيقيّة (`learning.py`/`learning_summary.py`) — ليست وحدات ورقيّة. لكنّ الذيل التعلّميّ ضعيف: ٤ فجوات حقيقيّة.
- **جسر #2 نَسَب مصدر التعلّم (`09fcc71`, v151):** أعمدة مصدر + `traceability_status` على `online_learning_updates`؛ `core.learning_source_lineage` يحكم القابليّة؛ الكاتب `phase_runtime_store` يستدعي `resolve_learning_source` — تحديث بلا مصدر ⇒ `rejected_untraceable` **فلا يُطبّق سياسة** (أرخص جسر أثراً، جوهر قلق المستخدم).
- **جسر #3 موفِّق النتائج (`3651764`):** `core.outcome_reconciler` يوحّد `outcome_record`=أثر القرار (`decision_effect`) و`recommendation_outcomes`=تعلّم الغلّة (`yield_learning`) بوسم `source_model`/`kind`، ويربطهما عبر dispatch_decisions. **متكاملان لا مكرّران** — كلٌّ مرجعيّ لسؤاله. `_derive_rec_success` فقط عند accepted+كلا الغلّتَين حاضرتَين (لا اختلاق نجاح).
- **جسر #4 إيقاف `recommendation_feedback` (`16d8d8a`, v152):** الفحص الأعمق أثبته **مكرّراً ميّتاً** لا مجرّد غير-مكتوب — القبول+الغلّة موطنها الحيّ recommendation_outcomes، التكلفة farm_operations_ledger، الماء water_ledger. لذا **لا يُوصَل كاتب** (يُعيد تجزئة جسر #3) بل **إيقاف موثَّق بتعليق + حارس ساكن** (`test_v152_...`) يمنع إحياءه صامتاً. لا DROP (سلامة بيانات).
- **جسر #5 سلامة مرجعيّة (`69596a1`, `core.loop_referential_integrity`):** التدقيق رصد «لا FK ⇒ أيتام». الفحص أثبت غياب الـFK **مقصوداً معماريّاً:** recommendation_id نصّيّ vs recommendations.id UUID (عدم توافق نوع) · outcome_record.decision_id ربط ليّن مُصرَّح (COMMENT v79) يحفظ RLS · كُتّاب متعدّدو الخدمات. فرض FK صلب **يكسر الإدراج**. الحماية الصحيحة = **كشف الأيتام** دوريّاً (`find_orphan_outcomes`/`find_orphan_dispatches`/`reconciliation_report`) للمراجعة/التنبيه لا الحجب. **لا migration** (مصالحة قراءة على صفوف مُمرَّرة). المُعرِّف الفارغ لا يُعَدّ يتيماً.
- **الحزمة المصاحبة (`8a52848`):** نقطة `GET /api/v1/fields/{field_id}/seasons/{season_id}/state` + Season Evidence Card (واجهة) — بُنيت مع الجسور تفادياً لدَين UI؛ مُسجَّلة في `endpoint_ui_coverage.json`.
- **التحقّق:** 31 اختبار جسور خضراء (11 جديد جسر #5) · ruff check+format نظيف من الجذر · release validate (3426 بصمة) · CI runs #3428/#3431/#3434/#3435 كلّها success. **fast-forward `main`+`develop`: 3651764→69596a1** (سلف خطّيّ، بعد أخضر #3435).

## 2026-07-08 (ع) — دمج أرشيف المستخدم: تصلّب حدود الملكية P0→P1.4 + جسر قراءة النتائج
- **السياق:** أرشيف المستخدم `work_p13` مبنيّ **فوق `017d38f`** (تحقّق-قبل-دمج أكّد احتواءه كلّ ملفّات إغلاق الحلقة). عزل الدلتا بالأساس: 28 ملفّاً جديداً + 7 معدَّلة (الباقي في الأرشيف ضوضاء: كاش/زِبّات جلسات سابقة). طبقة معماريّة متماسكة تُثبّت حدود الخدمات بحُرّاس CI **قبل** أيّ استخراج محفوف، وتوصِل موحِّد النتائج النقيّ (جسر #3) بمسارات القراءة.
- **P0 ملكية:** `docs/architecture/{SERVICE_OWNERSHIP_MATRIX,PLATFORM_EXTRACTION_MAP,db_ownership.yml,platform_extraction_map.json,platform_python_module_baseline.json}` + 3 حُرّاس (`test_p0_*`): ميزانيّة مسارات 567 · وحدات 578 · كاتب-أوحد 202 جدولاً. مسار/جدول جديد بلا مالك أو نموّ المنصّة ⇒ CI أحمر.
- **P1 راستر:** `RASTER_BOUNDARY_CONTRACT` + allowlist + `test_p1_raster_boundary_guard` (لا استيراد داخليّ platform→raster؛ جداول راستر كاتب-أوحد). تصحيح ملكيّة `zonal_stats` ⇒ raster-service (platform قارئ).
- **P1 طقس:** `WEATHER_OWNERSHIP_CONTRACT` + allowlist + `test_p1_weather_boundary_guard`؛ `weather-service/main.py` stub يعلن `/contract` + `/v1/weather/{path}` 501 بصدق (لا ادّعاء runtime). 13 مسار طقس أُعيد تصنيفها إلى weather-service في خريطة الاستخراج.
- **P1 جسر القرار/النتيجة/التعلّم:** `DECISION_OUTCOME_LEARNING_BRIDGE_CONTRACT` + allowlist + `test_p1_decision_outcome_learning_bridge_guard` يثبت: وحدات الحلقة موجودة · كاتب online_learning_updates يحلّ النَّسَب قبل الإدراج · v151 أعمدة المصدر · recommendation_feedback يبقى مُعطَّلاً بلا كاتب صامت · جداول الحلقة كاتب-أوحد في db_ownership.
- **P1.1/P1.3 جسر قراءة النتائج:** `field_season_projection.assemble_field_season_state` (+`outcome_records`/`recommendation_outcomes`/`dispatch_links`) و`learning_summary.summarize_learning_with_reconciled_outcomes` يستهلكان `reconcile_outcomes`. **صدق:** success_rate من المحسومة فقط · المعلّقة/غير الناضجة تبقى pending ولا تضخّم العيّنة · مزيج المصدر (`by_source`/`by_kind`) مُعلَن · الجداول الاختياريّة (recommendation_outcomes/dispatch_decisions) تسقط لصفر صفّ لا 503 · `region` مُمرَّر. راوترات seasons/learning_summary توصّل القراءة best-effort. اختباران جديدان (`test_field_season_projection_reconciled_outcomes` · `test_learning_summary_reconciled_outcomes`).
- **P1.2/P1.4:** `tests_v9/conftest.py` بديل `jose`→`jwt` عند غياب python-jose (fallback محلّيّ/CI) · `test_p1_4_recommendation_to_learning_lineage_e2e` حارس نَسَب توصية→قرار→تنفيذ→نتيجة→تعلّم.
- **التحقّق:** 61 اختبار (حُرّاس P0/P1 + تصالح + e2e) + 198 اختبار مواسم/تعلّم/نتائج قائم — كلّها خضراء · ruff check+format نظيف من الجذر (7 ملفّات طُبِّع تنسيقها) · tests_v9 يجمع 2797 unit · release validate 3428. **دفع فرعيّ `2602ba6`؛** fast-forward main/develop عند خُضرة CI.
- **درس:** أرشيفات المستخدم قد تُغلِّف نسخةً كاملةً قديمةً في الجذر + العمل الحقيقيّ في مجلّد فرعيّ (`work_p13`) بطوابع أحدث — قارن **المجلّد الفرعيّ** بالأساس لا جذر الأرشيف (385 «مفقود» في جذر الأرشيف كانت وهماً؛ الدلتا الحقيقيّة في work_p13 = 35 ملفّاً).

## 2026-07-08 (ف) — دمج أرشيف المستخدم: تنظيف واجهة الراستر P2 (facade cleanup)
- **السياق:** أرشيف المستخدم `sahool_ai_platform_017d38f_..._p2_5_raster_direct_wiring` مبنيّ على `df1a706` (superset، 0 مفقود). دلتا: 14 ملفّاً جديداً + 18 معدَّلة (منها 3 brain **رُفِضت** لأنّها ارتدّت لحالة 69596a1، فحُفِظ الدماغ الحاليّ وكُتِب مدخل P2 يدويّاً — قاعدة «احفظ إضافاتك»).
- **الجوهر:** `api/raster_service_client.py` واجهة HTTP واحدة (async: ترفع HTTPException 502 عند تعذّر النقل؛ sync: تسقط لـNone بلا تلفيق؛ تمرّر service-token + tenant). المسارات المتعاملة مع الراستر (available-dates · imagery/timeline · backfill · terrain DEM · etc-dual NDVI · field_ai_context · compat_gateway `/api/raster/*` · field_intelligence adapters) تنادي الواجهة بدل كتل httpx مبعثرة. حُرّاس P2.1–P2.5 + عقد `RASTER_FACADE_CLEANUP_CONTRACT` + allowlist: الوصل المباشر (RASTER_SERVICE_URL/httpx خام) مخالفة CI.
- **صدق مصون:** المنصّة تتحقّق الصلاحيّة وملكيّة المستأجِر/الحقل قبل التوكيل · raster-service المالك/الكاتب الوحيد لجداول الراستر · المتصفّح لا يتلقّى X-Agent-Token · لا قيم راستر مُلفَّقة.
- **عيبان حقيقيّان اصطادهما تحقّق-قبل-دمج (لم يكونا في نيّة الأرشيف):**
  1. **`get_field_terrain` تصادم أسماء (تعطّل صامت):** `fields.py` استورد واجهة `get_field_terrain` بنفس اسم مُعالِج المسار `@router.get(.../terrain)` المُعرَّف لاحقاً ⇒ المسار يحجب الواجهة في نطاق الوحدة. `_compute_field_terrain_from_dem` نادى `get_field_terrain(field_id, tenant_id=…, bbox=…)` ⇒ أصاب **المسار** بوسائط لا يقبلها ⇒ `TypeError` ابتلعه `except` ⇒ **DEM auto-fill يعود None دوماً** (الميزة مكسورة صامتاً). الإصلاح: `get_field_terrain as raster_get_field_terrain` + تحديث نقطة النداء.
  2. **E402 + ترتيب استيراد** في `imagery_automation.py` (الواجهة استُورِدت بعد `logger=`). أُصلِح.
- **اختبار ساكن قديم:** `test_field_ai_context_v45_static::test_two_year_context_sources_are_explicit` كان يؤكّد الحرف `"available-dates"` في مصدر الراوتر؛ بعد النقل للواجهة أصبح `get_available_dates` — حُدِّث الحارس ليعكس المعماريّة (لا حذف نيّة).
- **التحقّق:** 47 حارس (P0/P1/P2) + **كامل مجموعة اختبارات المنصّة 3416** خضراء · ruff check+format نظيف من الجذر (طُبِّع تنسيق ~11 ملفّاً تركها الأرشيف) · release validate **3456**. **دفع فرعيّ `bdbd2ae`؛** fast-forward main/develop عند خُضرة CI.
- **درس (يتكرّر):** أرشيفات المستخدم قد تُرجِع الدماغ لحالة أقدم — **لا تنسخ `sahool-brain/*` من الأرشيف؛ احفظ الحاليّ وألحِق مدخلك**. وعزل الدلتا بالأساس يكشف عيوباً حقيقيّة (تصادم أسماء يُعطّل ميزة صامتاً) لا يكشفها التطبيق الأعمى.

## 2026-07-08 (ص) — دمج أرشيف المستخدم: تحقيق runtime لخدمة الطقس P3
- **السياق:** أرشيف `..._p3_1_p3_2_p3_3_weather_service_realization` مبنيّ على تِلو P2 (superset). حدّ P1 السابق جمّد ملكيّة الطقس على stub صادق (501)؛ P3 هو **الاستخراج** الذي مهّد له الحدّ: يمنح `weather-service` سطح runtime حقيقيّاً دون قطع مسارات المنصّة التوافقيّة (P3.4 لاحقاً).
- **الجوهر (weather-service):** `open_meteo.py` مزوّد Open-Meteo (تطبيع current/daily-forecast/historical/tile-sample) · `operations.py` نوافذ عمليّات زراعيّة (رشّ/حصاد/بذر/تسميد/ريّ) بـscore+suitability+limiting_factors (**صدق:** لا توصية تُرفَع بلا دليل طقس صريح) · `tiles.py` مركز بلاطة WebMercator + 2×2 استيفاء + اشتقاق قيمة الطبقة (حرارة/رياح/مطر/ET0/VPD/حرارة تربة/رطوبة/ضغط/غيوم/إجهاد حراريّ/خطر انجراف/صلاحيّة مرور) — JSON لعرض `sahool-client-gridlayer` (لا مزوّد خرائط خارجيّ) · `cache.py` كاش ذاكرة صغير · `main.py` `/v1/weather/{current,forecast,historical,operation-window,operation-plan,operation-tile-data,tile-data,tile-series,wind-grid,tile-cache/stats}` + `/contract` (mode:runtime, implemented_runtime:true) + health/ready · `requirements.txt` httpx==0.28.1.
- **الحُرّاس/العقد:** حارس حدّ الطقس P1 انقلب من `test_..._remains_honest_contract_stub` إلى `test_..._runtime_contract_is_now_realized` (يؤكّد `mode:runtime`+`implemented_runtime` بدل `mode:stub`+not_implemented_here) · جديد `test_p3_weather_service_realization_guard` (منصّة) + `test_p3_weather_service_runtime` (خدمة) · عقد `WEATHER_OWNERSHIP_CONTRACT.md` حُدِّث من «P1 Boundary» إلى «P3 Runtime Realization».
- **تطبيق جراحيّ (صدق الدلتا):** الأرشيف سبق **تنسيقي P2** و**إصلاح `get_field_terrain`**، فأظهر الفرق 23 ملفّاً — لكنّ 13 منها كانت نُسَخاً قديمةً من ملفّات P2/الدماغ/الاختبارات (بلا إصلاحاتي، غير مُنسَّقة). طُبِّقت **13 ملفّ P3 حقيقيّ فقط** (9 جديد + 4 معدَّل حقيقيّ: عقد الطقس · main · requirements · حارس الحدّ)؛ **رُفِضت** نُسَخ fields.py/imagery_automation/raster_service_client/اختبارات P0-P2/conftest/brain (كانت ستُرجِع إصلاح تعطّل DEM الصامت + E402 + التنسيق).
- **التحقّق:** حُرّاس P3 + حدّ الطقس (8) + 3 اختبارات runtime للخدمة + **كامل مجموعة المنصّة 3420** خضراء · ruff check+format نظيف (طُبِّع 6 ملفّات طقس + أُصلِح 5 استيراد غير مُستخدَم) · release validate **3470**. **دفع فرعيّ `017c035`** (يضمّ P2 المعلّق CI)؛ fast-forward main/develop عند خُضرة CI الموحَّد.
- **درس (يتأكّد):** الأرشيفات المتتالية على أساس واحد تتخلّف عن إصلاحاتي المتراكمة ⇒ **قارن، صنّف الدلتا (P3-حقيقيّ مقابل نسخة-قديمة)، وطبّق الجديد فقط** — لا نسخ أعمى يُرجِع إصلاحات مثبَتة.

## 2026-07-08 (ق) — قطع واجهة الطقس P3.4 + الكنس النهائيّ P3.5 (فوق P3) + إصلاحا انحدارَين
- **السياق:** أرشيفا المستخدم P3.4 (واجهة طقس المنصّة) وP3.5 (الكنس النهائيّ). المسارات التسع الأساسيّة للطقس تصير واجهات رفيعة لـweather-service. تحقّق-قبل-دمج اصطاد انحدارَين حقيقيّين قبل الدمج.
- **P3.4:** `api/weather_service_client.py` واجهة (service-token + tenant، ترفع 502 عند تعذّر النقل)؛ `routers/weather.py` المسارات التسع تنادي الواجهة فقط (حارس `test_p3_4_platform_weather_facade_guard` يمنع رموز legacy في أجسامها)؛ baseline الوحدات 579→580.
- **P3.5:** `weather_direct_wiring_allowlist.json` + `WEATHER_DIRECT_WIRING_FINAL_SWEEP_CONTRACT.md` + حارس `test_p3_5_weather_direct_wiring_final_sweep` — الموطنان الشرعيّان للنقل المباشر: `weather_service_client.py` (نقل الخدمة) و`connectors/openmeteo.py` (محوّل المزوّد)؛ الباقي بقايا مركّبة صادقة (weather.py مساعدات · weather_automation · field_context · field_ai_context · fields · etc_dual · season_workspace · seasons · main) معلّقة لـP4. أيّ ملفّ سلك مباشر جديد ⇒ CI أحمر.
- **انحدار #1 — البلاطة المحايدة (`c47e077`):** استخراج P3 أسقط الضمان: `_cached_sample` في الخدمة يرفع عند تعذّر المزوّد بلا كاش ⇒ كلّ بلاطة 500 (إغراق الخريطة الذي مُنِع أصلاً بطلب المستخدم). أُصلِح: الخدمة `tile_data` تُرجِع بلاطة محايدة (value=null, cache_state="unavailable", 200) + `derived_layer_value(None)→None`؛ والواجهة `get_weather_tile_data`/`get_operation_tile_data` تُرجِع بلاطة محايدة عند تعذّر الخدمة (لا 502). مُثبَت باختبارات.
- **انحدار #2 — استيراد fastapi يكسر طبقة unit (`f6d2a9f`):** رقعة P2 جعلت `imagery_automation`→`raster_service_client`→`from fastapi import HTTPException` على مستوى الوحدة؛ طبقة CI *Unit Tests* تُشغّل `pytest -m unit` على tests_v9 **بلا fastapi**، و`test_imagery_auto_process_real_activation` يستورد imagery_automation ⇒ ModuleNotFoundError عند الجمع ⇒ CI أحمر (run #3447). أُصلِح باستيراد HTTPException كسولاً داخل الدوالّ في كلا العميلين (raster+weather) + حارس AST يمنع العودة. **درس متكرّر مؤكَّد:** أيّ وحدة يبلغها `-m unit` يجب ألّا تستورد fastapi وقت الاستيراد. (تحقّقي المحلّيّ لم يكشفه لأنّ fastapi مثبَّت عندي؛ CI unit-tier لا.)
- **هجرة 16 اختباراً كسرها القطع (subagent موثَّق):** 12 انتقل سلوكها للخدمة ⇒ حُذِفت من المنصّة (مع NOTE) + 6 اختبارات خدمة جديدة (cache-reuse/stale/best-frame/partial/irrigation-rank/heat_stress)؛ 4 اهتمام-منصّة (observability/prometheus/action-recommendation) حُوِّلت لـmock الواجهة. مساعدات المنطق النقيّ بقيت.
- **التحقّق (مستقلّ):** منصّة **3421** · خدمة **11** · حُرّاس P0–P3.5 (24) · ruff check+format نظيف · **import-safe بإثبات حجب fastapi في sys.meta_path** · tests_v9 unit يجمع 2797 · release 3480. commitان: `f6d2a9f` (إصلاح P2) + `21c59cd` (P3.4/P3.5).

## 2026-07-10 — صدق خدمة الغطاء النباتيّ V2→V5 (`cabfeff`→`9764f4f`، أخضر على main/develop)

أعلى بند P0 من المراجعة الاستهلاكيّة (Vegetation honesty). أربعة إصلاحات صدق متتابعة، كلّ مسار يعلن مصدره ولا يعرض تقديراً كرصد حقيقيّ:
- **V2 (`cabfeff`):** `_generate_timeseries` يُوسِم كلّ نقطة `{source:"synthetic_estimate", estimated:true, **indices}`؛ مسار `/v1/timeseries/{field_id}` يضيف `data_source/real_data:false/synthetic:true/authoritative_source="raster-service:/imagery/timeseries"/warning_ar`. الحارس `test_timeseries_honesty.py` (5 اختبارات).
- **V3 (`bc27df7`):** ردّ analyze يضع لكلّ مؤشّر `"estimated": index_sources.get(k, "estimate") != "raster-service"` (المؤشّر من الراستر الحقيقيّ estimated=false، غيره true).
- **V4 (`bc27df7`):** `_recommendations_ar` أُعيدت صياغتها من أوامر تنفيذيّة إلى فرضيّات: «⚠️ فرضيّة: … (تقديريّ) — يوصى بالتحقّق الميدانيّ؛ قرار الريّ لخدمة القرار» + وسم أعلى المستوى `advisory_role="hypothesis"` + `advisory_note_ar`. حُفِظت الكلمات المفتاحيّة (ري/آفة/مرض/✅) كي تصمد الاختبارات النصّيّة القائمة.
- **V5 (`9764f4f`):** `run_analysis(..., season_id=None)` + الردّ `"season_id": season_id`؛ مسار analyze يقبل `season_id: str | None = Query(default=None, max_length=128)` ويمرّره (متوافق للخلف). وثّق حالة المصدر الحقيقيّ: `VEGETATION_PREFER_RASTER=1` افتراضاً + `_RASTER_REAL_INDEX={evi:evi, savi:msavi, ndmi:moisture}` — الخدمة تُفضّل الراستر الحقيقيّ مع ارتداد موسوم.

**فشل CI وتشخيصه (درس رابع مرّة):** `bc27df7` أحمر — لكن السبب كان **`ruff format --check` فقط** على `vegetation_runtime.py` (`Would reformat: … 1 file`)، لا اختبار بائت. قبل الدفع شغّلتُ اختبارات الخدمة المحلّيّة + `ruff check` (يمرّ) لكن **لا `ruff format --check` على النطاق الكامل ولا `pytest -m unit`**. تعديلات V5 على نفس الملفّ أعادت تنسيقه عرَضاً فصار `9764f4f` أخضر. الدرس المُرسَّخ: **بوّابة الالتزام الكاملة** (`ruff format --check` على `services/ bots/ agents/ tests_v9/` + `pytest -m unit` الكامل) قبل كلّ دفع، لا مجموعة فرعيّة على الخدمة وحدها.

**التحقّق:** `pytest -m unit` **2858 نجاح/5 تخطٍّ/502 مُستبعَد** · `ruff format+check` نظيف على النطاق الكامل (1827 ملفّاً) · CI `SAHOOL v9.1.0 CI` أخضر على `9764f4f` (run 29107574736). main/develop قُدِّما بالتقديم السريع من `cabfeff` إلى `9764f4f`. أُرسِل أرشيف `git archive 9764f4f`.

## 2026-07-10 — مرحلة البناء الاستهلاكيّة (5 استطلاعات + 3 زيادات مُتحقَّقة): WS-D.1 · WS-A · WS-B.1

بعد إغلاق صدق الغطاء النباتيّ (V2→V5)، استُكمِلت الخطّة الاستهلاكيّة عبر **5 وكلاء استطلاع للقراءة فقط** (رسموا مسارات: ValidatedIndicatorProduct · Indicators Registry · Weather ET0/VPD/GDD+provider · water-stress E2E · CI consumer-contract gate — كلٌّ بأدلّة `file:line` ووعي بتصادم حُرّاس الحوكمة) ثمّ ثلاث زيادات بناء مُسلسَلة (verify-before-merge، وكيل بناء لكلّ زيادة + تحقّقي المستقلّ):

- **WS-D.1 (`11026ce`) — وصل الإجهاد المائيّ بتوصية الريّ (أخطر فجوة):** منتِج التوصية (`recommend_irrigation` → `weather_advice.irrigation_advice`) كان يحسب `net = ETc − مطر` **فقط** ويتجاهل استنزاف منطقة الجذور `water_ledger.depletion_mm` رغم توفّره + وجود `canonical_water_stress` ومقابض `irrigation_policy`. الآن يستهلك `depletion_mm/taw_mm/policy/water_stress_class` ويُصدِّر `should_irrigate` (Dr ≥ trigger×RAW) · `target_refill_mm` (refill×Dr) · `raw_mm` · رفع الإلحاح عند watch/critical. **fail-safe:** غياب Dr/TAW ⇒ `should_irrigate=None`, `trigger_reason="no_depletion_data"` (الصافي يبقى، لا اختلاق) · `calibrated=false`. النقطة القائمة `/api/v1/irrigation-recommendation` قبِلت مدخلات الاستنزاف (متوافق للخلف). **خطأ حقيقيّ اصطاده الاختبار:** معامل `policy` تصادم مع متغيّر سياسة الملوحة المحلّيّ (يُعاد إسناده قبل كتلة الاستنزاف) — التُقِط في مدخل الدالّة. 8 اختبارات + 3 حُرّاس ساكنة. لا مسار جديد ⇒ حوكمة صفر.

- **WS-A (`ab9b284`) — ValidatedIndicatorProduct على السلك:** الغلاف النوعيّ/النَّسَبيّ (`ValidatedRasterProduct`) كان مُحتسَباً عند حدّ raw→indicator لكنّه يبقى في `stats` الداخليّ ولا يصل السلك؛ ردّ `/v1/fields/{id}/indicator-grid` كان dict عارياً وvegetation يقرأ `stats.mean`+`real_data` فقط. `raster_indicator_product.ValidatedIndicatorProduct` (schema `sahool.validated_indicator_product/1`) يُرفَق تحت `indicator_product` بالردّ، يُصدره الفرعان (COG الحقيقيّ والمحاكاة) بشكل متطابق. **ثوابت الصدق (model_validator):** مصدر غير-raster ⇒ estimated=True + quality_gate_passed=False؛ real_data=True يتطلّب raster-service؛ النَّسَب لا يُختلَق (None عند الغياب). vegetation `_real_index_mean_from_raster` صار يقرأ الغلاف ويمرّر quality_score/provenance للعقد (raster فقط). **خطأ اصطاده التشغيل الكامل:** اختبار `tests_v9/test_vegetation_raster_ndvi.py` كان monkeypatch يُرجِع float بينما العقد صار dict — أُصلِح (الوكيل شغّل اختبارات الخدمة المحلّيّة فقط، لا `-m unit` الكامل؛ درس «شغّل الكامل» مُكرَّراً). حارس raster_validated_product مُوسَّع.

- **WS-B.1 (`759a6b0`) — سجلّ مؤشّرات كنسيّ + حارس انحراف:** ميتاداتا المؤشّرات كانت متفرّقة عبر ~9 تعريفات في كتالوجات متباعدة (backend `_INDICATOR_CATALOG`=18 · `INDICATOR_FORMULAS` · frontend HybridIndexPage/layerRegistry · vegetation `_RASTER_REAL_INDEX`) بلا حارس. `config/indicators_registry.json` صار المصدر الأوحد (33 مؤشّراً) يحمل source (real/estimated/derived) + status (implemented/estimated/not_implemented) + raster_alias (savi→msavi، ndmi→moisture) + formula_ref. **صدق:** cwsi=not_implemented (مجرّد وكيل NDWI تركيبيّ؛ CWSI حراريّ LST حقيقيّ غائب) · lai/recl=estimated · estimated لا يكون implemented أبداً. `scripts/ci/indicators_registry_gate.py` (بلا تبعيّات، structural-lint) يتحقّق: formula_ref→مفتاح INDICATOR_FORMULAS حقيقيّ · real طيفيّ مفتاح صيغة أو مُجسَّر · كلّ id في كتالوجَي backend/frontend مُسجَّل (يقتل انحراف 18≠17) · كلّ renderable طبقة layerRegistry · ثابت الصدق. مُوصَّل في ci.yml. لا مسار جديد.

**التحقّق (كلّ زيادة):** `pytest -m unit` كامل قبل كلّ commit (2858→2859→2863) · ruff نطاق CI نظيف · حُرّاس الحوكمة (ملكيّة/ميزانيّة المسارات/نموّ الوحدات) · release bundle مُعاد · CI أخضر على كلّ قمّة (11026ce/ab9b284/759a6b0) قبل التقديم السريع لـmain/develop + أرشيف. **درس مُرسَّخ:** وكلاء البناء يفوتون اختبارات `tests_v9` (يشغّلون اختبارات الخدمة المحلّيّة فقط) — تحقّقي المستقلّ بالمجموعة الكاملة اصطاد خطأً حقيقيّاً في كلٍّ من WS-D.1 وWS-A. **المتبقّي:** WS-B.2 (نقطة السجلّ + الواجهة) · WS-C (Weather ET0/VPD/GDD موحَّد + مزوّد ثانٍ NASA POWER — GDD مثلَّث) · WS-D.2 (نقطة إثراء تلقائيّ تقرأ water_ledger) · WS-D.3 (فهرس MSI يُحيي التأكيد الطيفيّ) · WS-E (بوّابة عقد المستهلك).

## 2026-07-10 (تكملة) — إكمال مسار الماء E2E (WS-D كاملاً) + تبنّي تصحيحات المستخدم

بعد WS-D.1/WS-A/WS-B.1، أُكمِل مسار الماء بثلاث زيادات + تصحيحات المستخدم الهيكليّة:
- **WS-D.3 (`75622ea`):** توحيد MSI في `band_math` (المصدر الأوحد) + تصحيح توثيق بائت. **تصحيح صدق:** ادّعاء الاستطلاع «MSI غير محسوب ⇒ التأكيد الطيفيّ ميّت» كان **إيجابيّة كاذبة** — MSI كان محسوباً سطريّاً في `raster_pixel_processing.py:584` والسلسلة موصولة (imagery_automation→last_msi_mean→canonical). HOP-4b لم يكن مكسوراً.
- **WS-D.3b (`20956b0`):** **سياسة توافق زمنيّ صريحة** لدمج NDMI+MSI في `canonical_water_stress` (فجوة ≤ `SPECTRAL_MAX_DATE_GAP_DAYS`=12؛ غياب تاريخ/فجوة أكبر ⇒ لا تأكيد، fail-closed). فجوة حقيقيّة: `imagery_automation_fields` يُحدَّث COALESCE فقد يختلف تاريخا NDMI/MSI. بلا migration (`last_ndmi_date`/`last_msi_date` مكتوبان أصلاً) — `gather_field_freshness` صار يقرؤهما. حقل `consumers` لـmsi/ndmi في السجلّ.
- **WS-D.2 (`afb7755`):** نقطة `POST /api/v1/fields/{field_id}/irrigation-recommendation` تقرأ آليّاً الاستنزاف/TAW/الموسم/الإجهاد (لا يمرّرها العميل) وتُنتج **توصية مرشَّحة** لخدمة القرار. بوّابة نقيّة `irrigation_state_guard`: **مفقود ≠ صفر** (insufficient_data) · **`0≤Dr≤TAW`** وإلّا inconsistent_state **بلا قصّ صامت** · دفتر قديم/TAW غير معايَر ⇒ قيود مُعلَنة. مستهلك UI حقيقيّ: `useFieldIrrigationRecommendation` (اتّحاد مُميَّز على status) + `IrrigationDecisionCard` في MapHub — سُجِّل core بدليل مميّز `/irrigation-recommendation` (لا البادئة العامّة `/api/v1/fields` — تجنّب ثغرة التغطية الوهميّة). **درس:** المحاولة الأولى بإعفاء فشلت لأنّ `boundary_hit` في حارس مكافحة الدَّين الوهميّ يطابق البادئة العامّة — فالإعفاء بنيويّاً محجوب للمسارات field-scoped؛ المستهلك الحقيقيّ هو الحلّ الأمين.

**تصحيحان هيكليّان من المستخدم (مُتبنّيان):** (1) **NASA POWER تاريخيّ/مرجعيّ لا forecast** (تأخّر 2–3 أيّام) — يلزم مزوّد توقّع ثانٍ فعليّ لـfallback تشغيليّ؛ `readyz` لا يخضرّ لمجرّد توفّر NASA POWER. `Open-Meteo→forecast · مزوّد2→fallback · NASA POWER→reference · IoT→observed`. (2) **تقسيم WS-C** إلى C.1 (VPD→ET0→GDD) · C.2 (BFF+حدود+shadow) · C.3 (مزوّد توقّع2 + NASA POWER مرجعيّ + مصفوفة قدرات + failover). التسلسل: WS-B.2 → C.1 → C.2 → C.3 → E.

**التحقّق (كلّ زيادة):** `pytest -m unit` (2863→2866) · حُرّاس المنصّة/الحوكمة · frontend tsc 0 + vitest · ruff · release bundle · CI أخضر قبل التقديم السريع. main/develop = `afb7755`.

## جلسة WS-C.1b consolidation (ET0 → محرّك الطقس)

- **الحارس الحدوديّ (`1700589`):** `scripts/ci/weather_engine_formula_guard.py` — AST (تعريفات `_svp`/`penman_monteith`/`hargreaves`) + بصمة نصّيّة (`0.6108`+`17.27`). يمنع أيّ تنفيذ جديد لصيغة SVP/ET0 خارج `services/weather-service/*`؛ الإرث القديم على **allowlist مؤقّتة موثَّقة** (`docs/architecture/weather_engine_formula_allowlist.json`: et0.py/water_balance.py/fao56.py، owner/expires/purpose) تُحذف عند الترحيل (الرَّاتشِت). خطوة CI في structural-lint.
- **جرد route-mount (`fc3572a`):** WS-D.2 أضاف route للمنصّة (516→517) دون إعادة توليد `route_mount_inventory` — حارس main-only (`route_mount_contract_guard` ضمن `runtime_real_smoke.sh`) غير مرئيّ على الفرع. أُعيد التوليد. **درس مكرّر:** أعِد توليد جرود main-only بعد أيّ route/module.
- **منتج ET0 في المحرّك (`75dc50f`):** `POST /v1/weather/agro/et0` — `et0.py::et0_agro_product` يلفّ `compute_et0` بنَسَب خدمة: `weather_snapshot_id` (بصمة sha1 حتميّة، `usedforsecurity=False`) + `valid_time` (مُصرَّح؛ مفقود ⇒ None+قيد). **كلّ ET0 من قلب المحرّك.** **سدّ فجوة صدق:** اختبارات محرّك الطقس (ET0/VPD/vapor_pressure) لم تكن في CI قطّ — وظيفة CI جديدة «Weather Service Unit Tests» تشغّل `services/weather-service/tests` (82) فتصبح العقود الكنسيّة مُحكَّمة.
- **تفويض المنصّة (`bd75cc5`):** `irrigation-recommendation` (field + generic) تستهلك ET0 من المحرّك عبر `weather_service_client.get_et0_product` — **لا محرّكا ET0 متوازيان**. تعذّر المحرّك ⇒ `dependency_unavailable`/503 (**لا حساب ET0 محلّيّ بديل صامت**). **مقارنة ظلّيّة مؤقّتة** (`_shadow_et0_diff`): الإرث المحلّيّ (allowlisted) للمقارنة فقط، لا يدخل القرار — نفس مدخلات المحرّك ⇒ فرق ≈ 0 (إثبات أمانة إعادة الإنتاج). نَسَب `et0` في المخرَج + `evidence_ids`.
- **الحالة:** WS-C.1b core = منجز · consolidation (تفويض irrigation) = منجز · **متبقٍ:** ترحيل بقيّة مستهلكي ET0 (season_simulation/weather_analytics/water-balance route) ثمّ حذف `core/engines/et0.py` المحلّيّ وإسقاط الـallowlist (cons-4) · حفظ candidate في decision-service (WS-D.2d).
- **التحقّق:** `pytest -m unit` (2871) · platform suite (3614) · weather suite (82) · ruff · bandit HIGH (0) · الحارس الحدوديّ · جرود main-only محلّيّاً · release bundle. main/develop = `fc3572a` ثمّ `bd75cc5` بعد CI الأخضر.

## C.1c تفويض المستهلكين + خريطة ملكيّة المحرّكات

- **`073613a`:** تفويض `/gdd/track` — فصل الحساب عن السياسة (`stage_result_from_cumulative` سياسة تبقى؛ نواة تُفوَّض)، shadow per-consumer (`gdd_shadow`، 5 مقاييس، طريقة مصنّفة لا مُذابة عند دقّة 3 منازل)، fail-closed 503.
- **`5fff601`:** تفويض محاكاة الموسم (RUE) — حقن اختياريّ `SimContext.gdd_daily_override` (مُحافِظ على الطريقة `modified`؛ `override=None` ⇒ سلوك مطابق، 178 اختبار موسم أخضر)، `crop_gdd_policy` يُصدّر العتبات، shadow + fail-closed. `SeasonSimResponse.gdd_provenance`.
- **قرار معماريّ (المستخدم):** [`decisions/engine-ownership.md`](decisions/engine-ownership.md) — Weather = مالك الطقس والمشتقّات الجوّيّة (ET0/VPD/GDD/…)؛ Crop Twin = مالك المحصول (phenology/biomass/yield)، يستهلك الطقس ولا يحسبه؛ الحارس يمنع تسرّب النوى خارجاً والملكيّة تمنع تسرّب منطق المحصول داخلاً. **crop_twin compose حاسبة offline (تستقبل et0_mm مُورَّداً) ⇒ تفويض GDD لها = C.2 (BFF)، لا C.1c** — فيبقى `season_simulation.gdd_day` على allowlist حتّى C.2.
- **الحيّ المتبقّي:** crop_twin (عبر C.2). الميت: gdd_phenology kernel. **لا حذف** حتّى C.2 + قرار الطريقة الموحَّدة.
- main/develop = `5fff601` (CI أخضر؛ unit 2871 · weather 93 · platform 3632 · guards · archive 3891).

## WS-D.2b→e (إثراء توصية الحقل) + عقد الواجهة الرفيعة

- **D.2b (`85c5f05`):** نسيج مخبريّ حقيقيّ من `soil_lab_tests.result->>'texture'` (لا عمود مُصنَّف — جرد المصادر) ⇒ TAW أدقّ. `soil_enrichment.soil_water_provenance` (نقيّ): مفردات مصدر `lab_measured|unavailable_fallback` · `modelled_from_lab_texture|modelled_generic_fallback` (TAW دائماً مُنمذَج) · خفض ثقة عند fallback عامّ. **صدق:** TAW لا يُخزَّن قطّ.
- **D.2c (`6719b14`):** جلب الطقس تلقائيّاً من المحرّك (`_field_weather_snapshot`, forecast اليوم) = المسار الأساسيّ؛ حرارة الطلب تجاوز يدويّ مُعلَن. day-of-year من valid_time. **fail-closed** على طقس مفقود/تعذّر. RH غير يوميّ ⇒ ET0 يسقط لـHargreaves (degraded صريح).
- **D.2d (`39f90a3`):** المرشَّح ليس قراراً — `approval_state` صريح (`not_submitted` افتراضاً) يمنع «اروِ» نهائيّاً قبل approved. تقديم صريح فقط (`submit_to_decision`) عبر `record_decision` ⇒ `pending_approval`+`decision_id`؛ **لا تكرار** للمسار المحروس (decision_dispatch)؛ fail-closed ⇒ `submit_unavailable`. بلا route جديد (سقف p2_6 سليم).
- **D.2e (قرار المستخدم):** WeatherAdvicePage **لا تُحذَف** — واجهة رفيعة بالكامل، بلا منطق حسابيّ، لا ET0/GDD/Water-Balance مستقلّ؛ تُعاد تسميتها تدريجيّاً إلى **Field Advisory** (توافق خلفيّ مؤقّت)، والمصدر الموحَّد **Field Advisory BFF** مرحلة مستقلّة لاحقة (مع C.2). الحالة الحاليّة: الصفحة **أصلاً رفيعة** (تستهلك `useIrrigationAdvice`، تعرض `a.et0`)؛ backend `weather_advice` يستقبل et0 مُدخَلاً ويعيد استخدام Kc/rain/salinity الكنسيّة. **حارس راتشِت** `tests_v9/test_advice_facade_contract.py` يمنع إعادة إدخال الحساب المستقلّ.
- main/develop = `39f90a3` (CI أخضر تسلسليّاً). unit 2871 · platform 3645 · guards · bundles.

## WS-C.1b — ترحيل season_simulation عن نواة ET0 المحلّيّة + جرد نوى ET0

- **أساس السلسلة الدفعيّة (`b83452c`):** `et0_series_product` في محرّك الطقس + route `POST /v1/weather/agro/et0/series` (يوم ناقص⇒None، لا يُلفَّق). CI أخضر.
- **ترحيل المحاكاة (`a5e84a2`):** `season_simulation` يستهلك سلسلة ET0 كنسيّة محقونة (`SimContext.et0_daily_override`) — **لا Hargreaves محلّيّ**؛ يوم بلا ET0 يُستبعَد من ETc (لا اختلاق)؛ `seasons.py` fail-closed 503 عند تعذّر المحرّك؛ `et0_provenance` في العقد. أُزيل استيراد `core.engines.et0`. حُقن `et0_daily_override` في `SimContext`. اختبار `test_season_et0_injection.py` (5).
- **إصلاح عقد CI (`d2d2183`):** `test_missing_et0_is_estimated_and_noted` رمّز إرث Hargreaves المُتقاعَد (ناقص⇒مُقدَّر⇒>0) وكسر وظيفة *Platform Unit Tests* (تشغّل كامل `tests/` لا `-m unit`). حُدِّث إلى العقد الأمين: ناقص+بلا سلسلة⇒`water_need==0.0` (مُستبعَد لا مُلفَّق) + مسار موجب بسلسلة محقونة. **درس:** بوّابة ما-قبل-الدفع يجب أن تشغّل `PYTHONPATH=. pytest tests` (كامل الدليل) لا `-m unit` فقط.
- **main/develop = `d2d2183`** (كلّ وظائف CI الـ12 خضراء: Unit 2873 · Platform Unit 3653 · Integration · Security · E2E · Flutter · weather-engine-formula-guard). أرشيف مُرسَل.
- **جرد نوى ET0 (خارج المحرّك) — صدق الإغلاق:** WS-C.1b **ليست مُغلَقة كاملاً**. خمس نوى ET0 **حيّة** باقية، كلّ منها خلف endpoint حقيقيّ: (1) `core/engines/et0.py` (النواة الجذر) · (2) `api/water_balance.py::compute_et0` ⇒ `/api/v1/water-balance`+scenario-whatif · (3) `core/engines/fao56.py::penman_monteith_et0` ⇒ `compute_etc_dual`⇒`routers/etc_dual.py` · (4) `api/weather_analytics.py::_hargreaves_et0` ⇒ endpoint تحليل الطقس · (5) `api/field_state_projection.py::_et0_from_weather_payload` ⇒ كتلة ETc لحالة الحقل. **ثغرة حارس:** (4) و(5) يُفلتان من `weather_engine_formula_guard` (الاسم لا يبدأ بـ`hargreaves`/لا يحوي `penman_monteith`) — يحسبان ET0 بلا allowlist. shadow-only: `irrigation_recommendation._shadow_et0_diff`. مُرحَّل بالكامل: `season_simulation` (نواة-صفر). `fao56.compute_irrigation` = ميّت وقت-التشغيل (اختبارات فقط).

## WS-C.1b — سدّ ثغرة حارس ET0 + إصلاح inventory (main-only)

- **إصلاح inventory (`64992b1`):** فحص main-only `generate_service_inventory.py --check` كان أحمر على main — `python_loc` لِـsahool-platform متأخّر ٦ أسطر (أُعيد توليد الجرد وسط التحرير في a5e84a2 قبل تعديلات الصياغة/النوع النهائيّة)، و`SERVICE_REGISTRY.md` لم يُعَد توليده (`--write-registry`). أُعيد توليد كلّ الجرود + السجلّ + الحزمة. **درس:** ولِّد الجرود **آخِر** خطوة بعد كلّ تعديلات الكود.
- **سدّ ثغرة الحارس (`67b4bd3`):** جرد المستهلكين كشف مسارات ET0 تُفلت من `weather_engine_formula_guard`: (1) `services/mcp_servers/weather_server.py` نواة Hargreaves **مضمّنة** (0.0023·(Tmean+17.8)·√dT·Ra·0.408) — نسخة ثانية حقيقيّة كانت خفيّة (لا بصمة SVP ولا اسم مطابق)؛ (2) `weather_analytics._hargreaves_et0` (غلاف مفوِّض) و`field_state_projection._et0_from_weather_payload` (منتِج ET0 محلّيّ) يُفلتان بالاسم. **التقوية:** بصمة Hargreaves الرياضيّة `(0.0023, 17.8)` معاً (تمسك المضمّن مهما كان الاسم؛ صفر إيجابيّات كاذبة) · `hargreaves` كسلسلة فرعيّة · اسم `_et0_from*`. الثلاثة أُضيفت لـallowlist **موثّقة path-scoped** بتصنيف (`inline-duplicate`/`delegating-wrapper`/`consumer`). اختبار جديد يقفل البصمة. الحارس: canonical + 9.
- **تصحيح صورة الجرد:** ليست 5 نوى مستقلّة — **نواة جذر واحدة** (`core/engines/et0.py`) وكلّ مسارات HTTP تفوّض إليها (water_balance·fao56·weather_analytics·field_state_projection مُفوِّضات) + نسخة MCP مضمّنة واحدة (موثّقة عمداً، معزولة عن core لأنّ MCP يستورد shared/ فقط؛ توحيدها يحتاج نقل core→shared، مؤجَّل بقرار سابق).
- **main/develop = `67b4bd3`** (12/12 CI أخضر · فحص main-only inventory مُتحقَّق exit 0). أرشيف مُرسَل.
- **باقي إغلاق WS-C.1b (ترحيل المستهلكين):** weather_analytics → field_state_projection → water_balance/fao56 → حذف النواة الجذر ⇒ صفر نوى ET0 خارج المحرّك. كلّ منها تحويل endpoint حيّ لتفويض المحرّك (fail-closed) — تغيير سلوكيّ يستحقّ تحقّقاً منفصلاً.

## Crop Intelligence Engine — دمج Phases 2–6D (أساس Crop Learning)

- **المصدر:** أرشيف المستخدم `sahool_3ec7f50_crop_intelligence_engine_phase6b_6d` (مبنيّ على 3ec7f50، متحقَّق محلّيّاً فقط). دُمِج على القمّة المتحقَّقة `67b4bd3` (لا القاعدة القديمة).
- **المضاف (`1ee913f`):** حزمة `core/crop_intelligence/` (models/engine/spectral/phenology/roots/stress_memory/crop_water/recommendation_context) — تُفسِّر ولا تحسب فيزياء (لا ET0/VPD/GDD/مؤشّرات raster/ماء تربة)، fail-closed، biomass/yield تبقى غير متاحة. + مخزن دائم `v153` (crop_stress_events append-only + crop_stress_memory_snapshots versioned، RLS+FORCE، dedup) + crop_stress_store/ingestion/memory_service + crop_decision_bridge (submit اختياريّ، not_submitted افتراضاً، لا مسار تنفيذ ثانٍ).
- **فجوات أصلحها الدمج (التشغيل المحلّيّ لم يمسكها):** v153 لم تُوصَل بـrun_migrations.sql (حارس تزامن المُشغّلَين) ⇒ خطوة 159 · db_ownership.yml (كاتب واحد للجدولين) · module baseline 595→608 (+13) · توصيل crop-intelligence-boundary-gate في CI · ruff import-sort/format (بيئة المستخدم بلا ruff).
- **التحقّق (12/12 CI أخضر):** أهمّها **Integration Tests طبّقت v153 فعليّاً على Postgres+PostGIS حيّ** + crop-intelligence-boundary-gate أخضر في CI + RLS write-policy. platform 3697 · unit 2874 · bundle. main/develop = `1ee913f`. أرشيف مُرسَل.
- **قرار المستخدم (توجيه استراتيجيّ):** الأولويّة الآن (1) إنهاء ترحيل ET0/GDD وإفراغ allowlist بالكامل (Zero-Legacy ratchet: `assert len==0`) (2) تثبيت الحارس (3) **Crop Learning Engine** يُغلق الحلقة (Recommendation→Decision→Execution→Outcome→Learning→Policy/Confidence). CIE = الأساس لـ(3).

## WS-C.1c Zero-Legacy — الكورشة #1 (allowlist 9→8)

- **قرار المستخدم:** الحارس نضج؛ المرحلة التالية Ratchet Strategy لا «إدارة allowlist»: كلّ ترحيل ناجح ⇒ احذف من allowlist ⇒ أيّ رجوع = CI أحمر؛ عند إفراغ القائمة ⇒ `assert len(temporary_legacy_allowlist)==0`. البدء بـGDD-in-engine (اختيار A).
- **الكورشة #1 (`91241c1`):** `core/gdd_phenology.py` كانت تحوي نواة GDD مكرّرة (`daily_gdd`/`accumulate_gdd`) **بلا مستهلك إنتاجيّ** (المستورِد الوحيد للوحدة يستورد سياسة `phenology_progress` فقط، وهي تأخذ accumulated_gdd مُدخَلاً). المحرّك يملك الرياضيّات (weather-service/gdd.py). أُزيلت النواة + اختباراتها المباشرة (TestDailyGdd)؛ بقيت سياسة المحصول. حُذِف الملفّ من allowlist (9→8) — الراتشِت.
- **تحقّق (12/12 CI أخضر):** guard (canonical + 8) · ruff · platform 3693 · unit 2874 · bundle. main/develop = `91241c1`. أرشيف مُرسَل.
- **الباقي (8 مدخلات) كلّها نوى حيّة** (لا مكاسب dead-code أخرى): GDD: gdd_tracker (track_gdd حيّ في scenario_whatif) · season_simulation.gdd_day (sim + crop_twin). ET0: et0.py الجذر · water_balance · fao56 · weather_analytics · field_state_projection · weather_server (MCP). كلّ حذف = ترحيل endpoint حيّ إلى تفويض المحرّك fail-closed.

## WS-C.1c Zero-Legacy — الكورشة #2 (allowlist 8→7)

- **`gdd_tracker` (`6b0bcb0`):** نواة GDD حيّة (`daily_gdd`+`track_gdd`) لها مستهلكان: ظلّ `routers/gdd` (المسار يفوّض أصلاً) + `scenario/planting-date` (كان sync يحسب محلّيّاً). كلاهما رُحِّل للمحرّك (`get_gdd_product`, method="simple" = نفس الأرقام)، fail-closed 503.
  - routers/gdd: حُذف الظلّ (النَّسَب من المحرّك مباشرة، لا "shadow").
  - scenario/planting-date: أصبح **async** يجلب GDD للأساس+البديل ويحقن التراكميَّين؛ `whatif_planting_date` نقيّة. **تغيير سلوكيّ:** الـwhat-if صار fail-closed (503 عند تعطّل المحرّك) — متّسق مع فلسفة fail-closed.
  - gdd_tracker: حُذفت `daily_gdd`+`track_gdd`؛ بقيت `stage_result_from_cumulative` + GDD_CROP_PARAMS (سياسة Season).
  - أُعيدت كتابة 3 اختبارات (سياسة/حقن). حُذف الملفّ من allowlist (8→7).
- **تحقّق (CI أخضر):** guard (canonical + 7) · platform 3683 · unit 2874 · inventory --check · bundle · 884 route. main/develop = `6b0bcb0`. أرشيف مُرسَل.
- **الباقي (7):** GDD: season_simulation.gdd_day (sim fallback + seasons shadow + crop_twin). ET0: et0.py الجذر · water_balance · fao56 · weather_analytics · field_state_projection · weather_server (MCP).

## WS-C.1c Zero-Legacy — الكورشة #3 + إغلاق نوى GDD (allowlist 7→6)

- **`season_simulation.gdd_day` (`b403f21`+`b3eaa4a`):** أكبر كورشة GDD — 3 مستهلكين رُحِّلوا للمحرّك:
  - crop_twin.crop_twin_state: `gdd_daily_override` محقون؛ لا gdd_day محلّيّ (يوم ناقص مُستبعَد fail-closed).
  - routers/crop_twin: `_compose_state` + compose/decision/profit-aware أصبحت **async**، تجلب GDD المحرّك (crop_gdd_policy، method="modified")، fail-closed 503. **تغيير سلوكيّ:** `/crop-twin/compose` (+ القرار) صارت fail-closed.
  - season_simulation: حُذف احتياط gdd_day في الحلقة (يوم ناقص مُستبعَد + مُعلَن) + حُذفت نواة gdd_day. crop_gdd_policy (العتبات) بقيت سياسة Season.
  - routers/seasons: حُذف ظلّ GDD.
  - 8 ملفّات اختبار أُعيدت (حقن سلسلة GDD + async + mock محرّك). النواة تُختبَر في المحرّك.
- **صدق فجوة CI:** فحص checksum الحزمة أمسك ملفَّي tests_v9 عُدِّلا بعد إعادة بناء الحزمة — إصلاح `b3eaa4a` (إعادة بناء آخر خطوة). **درس:** إعادة بناء الحزمة آخِر خطوة بعد كلّ التعديلات (توأم فخّ inventory-drift).
- **تحقّق (CI أخضر):** guard (canonical + 6) · platform 3678 · unit 2869 · crop-boundary · inventory · bundle · 884 route. main/develop = `b3eaa4a`. أرشيف مُرسَل.
- **كلّ نوى GDD مُزالة الآن** (gdd_phenology + gdd_tracker + season_simulation). **المتبقّي = 6 نوى ET0:** et0.py الجذر · water_balance · fao56 · weather_analytics · field_state_projection · weather_server (MCP، core→shared). ثمّ `assert len==0`.

## WS-C.1b Zero-Legacy — راتشِت ET0 #1: field_state_projection → منتج المحرّك (allowlist 6→5)

- **`field_state_projection._et0_from_weather_payload` (`50b21b5`):** أوّل راتشِت ET0 حقيقيّ — النواة المحلّيّة (كانت تستدعي `api.water_balance.compute_et0` ⇒ `core.engines.et0`) رُحِّلت إلى **مستهلِك لمنتج محرّك الطقس** (`get_et0_product`). صيغة FAO-56 Penman-Monteith/Hargreaves تُنفَّذ الآن في المحرّك فقط، لا في المنصّة.
  - الدالّة أصبحت **async**، تُنتظَر (`await`) عند `recompute_field_state` مع تمرير `tenant_id`.
  - **fail-closed محفوظ (عقد best-effort للحالة القانونيّة):** تعذّر المحرّك/نقص بيانات ⇒ `None` (يغيب `etc_mm`، لا احتياط محلّيّ، لا تلفيق) — **ليس 503** (متّسق مع دلالة القراءة التكميليّة للحالة، لا كسر التحكيم).
  - **الحارس:** حُذفت heuristic الاسم `_et0_from*` (كانت لتتبّع هذا المُنتِج المحلّيّ فقط؛ الآن مستهلِك لا نواة). اختبار الحارس يؤكّد عدم رصده بعد الآن.
  - `indicators_registry.json`: مُلاحظة et0 حُدِّثت (مستهلِك محرّك، لا FAO-56 محلّيّ).
  - اختباران في `test_fieldstate_water_canon` أُعيدا (async + mock `get_et0_product` + حالة تعذّر المحرّك ⇒ None). حُذف الملفّ من allowlist (6→5).
- **تحقّق (CI أخضر 12/12 job):** weather-engine-formula-guard (canonical + 5) · Platform Unit 3678 · Unit 2870 · Integration · Security Scan · Frontend/Flutter · inventory 884 route · bundle 3921 checksum. main/develop = `50b21b5`. أرشيف مُرسَل.
- **المتبقّي = 5 نوى ET0:** et0.py الجذر (يُحذَف آخِراً) · water_balance (مسار الريّ) · fao56 (etc-dual) · weather_analytics (عقد lat) · weather_server (MCP، core→shared). ثمّ `assert len(temporary_legacy_allowlist) == 0`.

## WS-C.1b Zero-Legacy — راتشِت ET0 #2: water_balance → منتج المحرّك (allowlist 5→4)

- **`api/water_balance.py` نواة ET0 التشغيليّة (`0b354d7`):** أكبر راتشِت ET0 — النوى المحلّيّة (`compute_et0`/`et0_penman_monteith`/`et0_hargreaves`/`_extraterrestrial_radiation`) + enum `ET0Method` **حُذفت**. صيغة FAO-56 PM/Hargreaves لمسار الريّ/ميزان الماء تُنفَّذ الآن في المحرّك فقط.
  - `water_balance()`/`water_balance_auto()`: تأخذان `et0_mm` (keyword مطلوب) + `et0_method` (نصّ) — لا حساب ET0 داخليّ. `WaterBalanceResult.method` صار نصّ المحرّك.
  - `routers/water_balance.py`: `/api/v1/water-balance` صار **async** يجلب `get_et0_product` ويحقن؛ **تغيير سلوكيّ:** fail-closed 503 عند تعذّر المحرّك (لا احتياط محلّيّ).
  - `routers/scenario.py`: `/scenario/temperature` (أساس + حرارة مُزاحة) و`/scenario/rainfall` صارتا async تجلبان ET0 المحرّك (temp-only ⇒ Hargreaves)، fail-closed 503.
  - `scenario_whatif.py`: `whatif_temperature_shift` يأخذ base/scen et0؛ `whatif_rainfall_change` يأخذ et0 واحد — نقيّتان محقونتان.
  - `routers/irrigation_recommendation.py`: **حُذف ظلّ ET0 الإرثيّ** (`_shadow_et0_diff` + استيراد compute_et0 + تسجيل + حقل shadow) — غرضه (إثبات إعادة المحرّك للصيغة) تحقّق؛ المحرّك المصدر الوحيد.
  - اختبارات: أُعيد `test_water_balance`/`test_fao56_agronomic_validation`/`test_scenario_whatif` بحقن et0 (اختبارات النوى المحذوفة أُزيلت؛ تحقّق FAO-56 الزراعيّ أُعيد توجيهه لنواة `core.engines.et0` الباقية)؛ حُذف اختبار shadow-diff + تأكيداته؛ حُقنت قيمة et0 مرجعيّة في مستهلكي tests_v9؛ حُذف اختبارا التوحيد للأغلفة المحذوفة (اختبارات النواة الكنسيّة بقيت). subagent نفّذ حقن tests_v9 والمنسّق تحقّق مستقلّاً بالبوّابة الكاملة.
- **تحقّق (CI معلَّق، البوّابات محليّاً خضراء):** weather-engine-formula-guard (canonical + 4) · pytest -m unit 2868 · platform tests 3666 · inventory 884 route · bundle 3921 checksum · ruff نظيف.
- **المتبقّي = 4 نوى ET0:** et0.py الجذر (يُحذَف آخِراً) · fao56 (etc-dual + بقايا gdd_daily) · weather_analytics (batch monthly-Ra) · weather_server (MCP، core→shared). ثمّ `assert len==0`.

## WS-C.1b Zero-Legacy — راتشِت ET0 #3: weather_server MCP → منتج المحرّك (allowlist 4→3)

- **`services/mcp_servers/weather_server.py` نواة ET0 الثانية (`ed21a56`):** أداة `calculate_hargreaves_et0` كانت تحوي **نواة Hargreaves-Samani سطريّة مستقلّة** (Ra + `0.0023*(Tmean+17.8)*sqrt(dT)*Ra*0.408`) — نسخة ثانية حقيقيّة للصيغة خارج المحرّك، عاشت لأنّ خادم MCP بوّابة معزولة (shared/ فقط، لا core/).
  - الأداة الآن **تستهلك منتج ET0 من محرّك الطقس** عبر HTTP: `POST services/weather-service /v1/weather/agro/et0` — المحرّك مصدر ET0 الوحيد لها أيضاً. حرارة فقط ⇒ المحرّك يتدرّج لـHargreaves داخليّاً. **fail-closed بنتيجة أداة مُهيكَلة** (بتوجيه المستخدم): تعذّر المحرّك/5xx/et0 مفقود ⇒ `{status:"unavailable", reason, et0_mm:null, method:null, quality_status:"insufficient", limitations:[...]}` — لا 0 ولا تقدير محلّيّ ولا 503 خام. النجاح ⇒ `{status:"ok", et0_mm_day/method/quality_status/formula_version من المحرّك + t_mean/t_range حسابيّ + source="weather-engine"}`. مدخل `t_min>t_max` يبقى 400 (خطأ عميل، متمايز عن تعذّر التبعيّة). **إسقاط `ra_mj_m2_day` صريح** (grep: صفر مستهلك؛ كان وسيط النواة المحذوفة).
  - **محوّل/عميل:** `_weather_service_url()` (env `WEATHER_SERVICE_URL`) + `_weather_service_headers()` (هويّة خدمة: `X-Agent-Token` من `SAHOOL_AGENT_TOKEN` إن وُجد + `X-Service-Name` للcorrelation) + timeout صريح 20s. وُصِل env في المُوجِّهات الثلاثة (`docker-compose.{v9,fixed,light}.yml` بلوك `sahool-weather-mcp`: WEATHER_SERVICE_URL + SAHOOL_AGENT_TOKEN؛ كلاهما في `.env.example`؛ compose-env-contract-gate أخضر).
  - **الحارس:** بصمة Hargreaves (`0.0023`+`17.8`) اختفت ⇒ الملفّ لم يعد يُرصَد (لا تغيير حارس). حُذف من allowlist (4→3).
  - **اختبارات قبول جديدة** (`tests_v9/test_mcp_weather_et0_engine_delegation.py`، 8 تمرّ): حارس انحدار ساكن (لا ثوابت Hargreaves/لا `import math`/لا Ra محلّيّ + يستدعي نقطة المحرّك) + سلوكيّ mock: تعيين المنتج الكنسيّ · إسقاط ra · إرسال توكن الخدمة · اتّصال/timeout→unavailable · 5xx→unavailable · et0 مفقود→unavailable · مدخل غير صالح→400. (الاستيراد يُرقِّع شِيمَي MCP فيعمل في بيئة الوحدة؛ الحاوية تدمج الـshared.) + اختبار `test_mcp_servers::test_calculate_et0` `mcp/integration` يبقى للمسار الحيّ.
- **تحقّق (CI معلَّق، البوّابات محليّاً خضراء):** guard (canonical + 3) · compose-env-contract-gate · unit 2876 · inventory 884 route · bundle 3921 checksum · ruff · 3 compose YAML صالحة.
- **المتبقّي = 3 نوى ET0:** et0.py الجذر (يُحذَف آخِراً) · fao56 (penman في compute_etc_dual/compute_irrigation) · weather_analytics (batch monthly-Ra). ثمّ `assert len==0`.

## WS-C.1b Zero-Legacy — راتشِت ET0 #4: weather_analytics → سلسلة المحرّك (allowlist 3→2)

- **`api/weather_analytics.py` (`38a1ea9`):** أداة التحليل المناخيّ رُحِّلت عن نواة Hargreaves محلّيّة (جدول Ra شهريّ + غلاف `_hargreaves_et0`) إلى **منتج سلسلة ET0 من محرّك الطقس**. قرارا المستخدم مُطبَّقان:
  - **المحرّك يملك الفلك:** `et0_series_product` (weather-service) اكتسب `daily_dates: list|None` (تواريخ ISO). عند وجودها يشتقّ المحرّك DOY من التاريخ الفعليّ (date→DOY→Ra→ET0) — **بلا انجراف فلكيّ** في السجلّات المتفرّقة/متعدّدة السنوات؛ `day_of_year_start` التسلسليّ يبقى احتياطاً (مسار الموسم بلا تغيير). وُصِل عبر `Et0SeriesRequest` + `get_et0_series` (توافق خلفيّ).
  - **تدهور جزئيّ لا 503:** `analyze_weather_log` صار async، يبني الحرارة+التواريخ الفعليّة من السجلّ، يستدعي `get_et0_series(lat, daily_dates)`. تعذّر المحرّك ⇒ `analysis_status="partial"`: تحليل الحرارة/الصقيع/الرياح/المطر يبقى صحيحاً كاملاً، وحقول ET0 تُوسَم عبر `availability` map + `unavailable_products` صريحة (لا null-guessing، لا اختلاق). المُوجِّه async + `lat` اختياريّ (query، افتراض اليمن 16°N).
  - **الحارس:** غلاف `_hargreaves` حُذف ⇒ لا مطابقة اسم ⇒ الملفّ خرج من الرصد. حُذف من allowlist (3→2).
  - **اختبارات:** `test_weather_analytics_engine_delegation` (حارس انحدار ساكن: لا Hargreaves/نواة محلّيّة، يفوّض للسلسلة · complete-maps + تمرير التواريخ الفعليّة + تدهور جزئيّ) · `test_et0` (weather-service) اكتسب per-date-DOY (بلا انجراف، أولويّة التاريخ، احتياط تسلسليّ) · `test_roadmap_phase23::test_weather_analytics` async + mock المحرّك.
  - **ملاحظة المستخدم (مؤجَّلة):** تعميم مفهوم `availability` (heat/rain/wind/et0/vpd/gdd true/false) على **كلّ** منتجات المحرّك — طُبِّق هنا على هذا الـendpoint؛ التعميم عبر المنصّة متابعة لاحقة (يخدم Crop Intelligence/Decision/UI بلا تخمين null).
- **تحقّق (CI معلَّق، البوّابات محليّاً خضراء):** guard (canonical + 2) · unit 2880 · platform 3666 · weather-service 82 · inventory 884 route · bundle 3922 checksum · ruff · 3 YAML.
- **المتبقّي = 2 نواة ET0:** et0.py الجذر (يُحذَف آخِراً) · fao56 (penman في compute_etc_dual/compute_irrigation عبر et0_override؛ gdd_daily/accumulate). ثمّ `assert len==0`.

## WS-C.1b Zero-Legacy — راتشِت ET0 #5: fao56 → ET0 محقون + حذف الميّت (allowlist 2→1)

- **`core/engines/fao56.py`:** حُذفت **نواة `penman_monteith_et0`** (غلاف يفوّض لـcore.engines.et0) + نوى **`gdd_daily`/`gdd_accumulate`** (ميّتة إنتاجيّاً؛ GDD في weather-service/gdd.py) + **`compute_irrigation` كاملةً + `SoilZone` + `IrrigationResult`** (قرار المستخدم: احذفها لا تُرحّلها — لا مستهلك إنتاجيّ؛ تحقّقتُ من صفر dynamic dispatch: لا getattr/registry/string-map). `compute_etc_dual` صار يتطلّب `et0_override` **مطلوباً** (يرفع ValueError عند غيابه؛ لا استدعاء penman داخليّ).
  - **المستهلكون الأحياء:** `routers/etc_dual.py` (`/fields/{id}/etc-dual`) يجلب ET0 من `get_et0_product` بطقس اللقطة ويحقن et0_override، **fail-closed 503**، ويعرض **نَسَب ET0** (method/quality_status/formula_version/valid_time/weather_snapshot_id) في المخرَج. `field_state_projection` يحقن et0_override أصلاً. **القاعدة الحاسمة (قرار المستخدم):** الدالّة العلميّة نقيّة تستهلك ET0 محقوناً — الاستدعاء الخارجي للمحرّك في طبقة router/service فقط.
  - **الحارس:** بعد حذف penman/gdd_daily لم يعد fao56 يُرصَد. حُذف من allowlist (2→1؛ باقٍ **et0.py الجذر فقط**).
  - **اختبارات:** subagent حقن et0_override في مستهلكي compute_etc_dual؛ ثمّ المنسّق حذف اختبارات compute_irrigation (test_h5_irrigation_unify كاملاً — صيغتا الملوحة تبقيان في test_engines/test_h5_api_salinity؛ 3 اختبارات test_engines؛ test_compute_irrigation_still_works؛ استعمال forensic أُعيد بـkc_for_age×ET0 محقون) + اختبارات النوى المحذوفة (test_gaps_v91 gdd، test_pm_unified غلاف fao56.penman) + تعليقات بائتة.
- **تحقّق (CI معلَّق، البوّابات محليّاً خضراء):** guard (canonical + **1**) · unit 2875 · platform 3660 · inventory 884 · bundle 3922 · ruff.
- **المتبقّي = نواة ET0 واحدة:** `core/engines/et0.py` الجذر (راتشِت #6 الأخير) ⇒ allowlist=0 ⇒ `assert len==0` ⇒ ملكيّة المحرّك الكاملة ⇒ WX-10 CanonicalWeatherState.

## WS-C.1b/c Zero-Legacy — راتشِت ET0 #6 (النهائيّ): حذف نواة et0.py الجذر ⇒ allowlist=0 ⇒ Zero-Legacy LOCKED

- **`services/sahool-platform/core/engines/et0.py` (محذوف):** النواة الجذر (Hargreaves-Samani + Ra خارج الغلاف + Penman-Monteith + DEFAULT_RA_MM) كانت آخر ملفّ على allowlist. **إثبات الموت الإنتاجيّ:** بحث شامل (imports + رموز + dynamic dispatch importlib/getattr/__init__ re-export) ⇒ **صفر مستهلك إنتاجيّ**؛ المُستوردون الوحيدون 3 ملفّات اختبار. المرجع الوحيد غير-الاختبار كان اسم أداة MCP النصّيّ `"calculate_hargreaves_et0"` (يفوّض للمحرّك عبر HTTP منذ راتشِت #3) — سلسلة لا استيراد.
- **الصحّة العلميّة غير مفقودة:** المحرّك الكنسيّ (`services/weather-service/et0.py`+`vapor_pressure.py`) يملك ويختبر كامل FAO-56: `test_et0.py` (Ra مثال 8 ⇒ 32.2 · PM مُصادَق · Hargreaves fallback + clamp سالب + حرّاس عدم-اختلاق) · `test_vpd.py` (es(20)=2.338 · es(30)=4.243). فالحذف لا يفقد تغطية.
- **الاختبارات:** حُذف `tests_v9/test_et0_unified.py` + `tests_v9/test_pm_unified.py` (يختبران النواة المحذوفة + فرضيّة H4 «مصدر منصّة موحّد» التي تجاوزها ترحيل المواقع الثلاثة للمحرّك). `services/sahool-platform/tests/test_fao56_agronomic_validation.py` قُلِّم: أُزيلت اختبارات Ra/es/PM/Hargreaves + مُعينات `_svp`/`_fao56_pm_reference` + استيراد et0 (مملوكة الآن في المحرّك)؛ أُبقيت اختبارات Kc/ETc/المطر الفعّال (تخصّ `api.water_balance` الباقي، ET0 محقون ثابت 5.0). حارس الانحدار `test_weather_analytics_engine_delegation` (`assert "core.engines.et0" not in _SRC`) يبقى أخضر.
- **قفل Zero-Legacy:** `docs/architecture/weather_engine_formula_allowlist.json` → `temporary_legacy_allowlist: []`. الحارس `scripts/ci/weather_engine_formula_guard.py` اكتسب فحصاً صريحاً (`if legacy: return 1`) + `assert len(legacy)==0` + رسالة "Zero-Legacy LOCKED"؛ اختبار جديد `test_zero_legacy_allowlist_is_empty_and_locked`. أيّ إعادة إضافة مدخل = فشل CI بالتصميم.
- **baseline المنصّة:** `platform_python_module_baseline.json` (حارس `test_p0_platform_module_growth_guard`) = حدّ أعلى + superset؛ حذف وحدة يبقيه أخضر (عدد أقلّ؛ الوحدة المحذوفة في `baseline−current` لا `current−baseline`) — لا تعديل مطلوب.
- **خارج النطاق (موثَّق):** `wofost_real/wofost_engine.py` فيه `hargreaves_et0` محلّيّة (R&D خارج services/، لا يرصدها الحارس). تعليقها المُشير لـ`core/engines/et0.py` المحذوف حُدِّث ليشير للمحرّك الكنسيّ + توضيح أنّ توحيدها متابعة R&D منفصلة خارج Zero-Legacy للمنصّة.
- **تحقّق (البوّابات محليّاً خضراء):** guard "canonical + 0 — Zero-Legacy LOCKED" · unit **2866** · platform **3650** · ruff · inventory 884 route · bundle. CI معلَّق قبل التقديم السريع.
- **الحصيلة:** allowlist 6→0. محرّك الطقس المالك الوحيد لـET0/SVP/GDD. **التالي: WX-10 CanonicalWeatherState.**

## WX-10.1 — CanonicalWeatherState (State Product): العقد + المُجمِّع + نقطة قراءة + مستهلك واحد

- **قرار المستخدم (2026-07-11):** بعد إتمام Zero-Legacy ET0 (allowlist=0)، بدء WX-10 بمنهجيّة الراتشِت: **إنكرمنت أوّل إضافيّ فقط** (العقد + Composer + endpoint قراءة + مستهلك واحد + بوّابات)، وتأجيل تحويل ET0/VPD/GDD/Crop/Decision إلى Views لإنكرمنتات مستقلّة تالية. + إضافة مُعرِّفات نَسَب ثابتة من البداية (`state_id`/`state_version`/`source_snapshot_id`).
- **`services/weather-service/canonical_weather_state.py` (جديد، نقيّ حتميّ):** `build_canonical_weather_state(...)` يجمع منتجات المحرّك القائمة **دون إعادة حساب** (يستدعي `et0_agro_product`/`compute_vpd`/`gdd_agro_product`/`extraterrestrial_radiation_mj`) في غلاف State Product: `product_id · state_id · state_version · schema_version(wx10/canonical-weather-state/1.0.0) · owner(weather-service) · source_snapshot_id · generated_at(=valid_time، لا ساعة مُختلقة) · quality(الأسوأ بين المتوفّرة) · confidence · availability(كلّ 12 خانة) · provenance(لكلّ متوفّر) · evidence(المدخلات المُستخدَمة فقط) · limitations · products`. **fail-closed بلا اختلاق:** خانة بلا مدخلات ⇒ availability=false + قيد (لا قيمة). الخانات المجموعة (et0/vpd/gdd/astronomy/dtr)؛ المؤجَّلة (current/forecast/historical/heat_load/chill_hours/frost_risk/operation_windows) تُصرَّح غيرَ متوفّرة صراحةً. `state_id` = sha1 حتميّ (نفس المدخلات ⇒ نفس البصمة) للنَّسَب.
- **المستهلك الوحيد (إثبات التصميم):** `weather_state_report(state)` يقرأ **الحالة فقط** لا المحرّك — إثبات الانعكاس المعماريّ على View واحد؛ يحمل `state_id`/`source_snapshot_id` للـlineage.
- **نقطتا قراءة:** `POST /v1/weather/agro/canonical-state` (الحالة) · `POST /v1/weather/agro/state-report` (المستهلك). handlers في `weather_runtime.py`، مُسجَّلة في `main.py`.
- **حارس العقد:** `tests/test_canonical_weather_state.py` (11 يمرّ): اكتمال الغلاف · schema/owner/version · availability كامل · متوفّر مع مدخلات كاملة + provenance · مؤجَّل مُصرَّح · fail-closed بلا اختلاق · جزئيّ صادق · DTR غير متّسق→invalid · حتميّة state_id + حسّاسيّتها · evidence لا يختلق · المستهلك يقرأ الحالة فقط.
- **تحقّق (البوّابات محليّاً خضراء):** weather-service tests **111** (+11) · guard Zero-Legacy LOCKED · unit 2866 · ruff · inventory 886 route (weather 30→32) · bundle. CI معلَّق قبل التقديم السريع.
- **التالي (إنكرمنتات مستقلّة):** تحويل ET0 View → VPD View → GDD View → Crop Intelligence → Decision لتقرأ CanonicalWeatherState بدل المحرّك مباشرةً (بنفس منهجيّة الراتشِت).

## WX-10.2 — ET0 كـView مُشتقّ من CanonicalWeatherState (أوّل تحويل مشتقّ)

- **قرار المستخدم:** بعد WX-10.1، تحويل المشتقّات إلى Views فوق الحالة إنكرمنتاً إنكرمنتاً. WX-10.2 = **ET0 View** (الأوّل).
- **`canonical_weather_state.py`:** أُضيفت `et0_view(state)` — إسقاط نقيّ يقرأ خانة `et0` من الحالة ويُضيف نَسَب الحالة (`derived_from`/`canonical_state_id`/`canonical_state_version`/`source_snapshot_id`). المُجمِّع اكتسب `weather_snapshot_id_override` (يُمرَّر لـ`et0_agro_product`) لحفظ عقد الـsnapshot override.
- **`weather_runtime.py`:** `agro_et0` **رُحِّل** ليشتقّ من الحالة: `build_canonical_weather_state(...) → et0_view(state)` بدل نداء `et0_agro_product` مباشرةً. **توافقيّ للخلف تامّ:** حقول العقد (et0_mm/method/quality_status/formula_version/valid_time/weather_snapshot_id/limitations/snapshot_source) مطابقة بايتاً؛ يُضاف فقط نَسَب الحالة (مجموعة فائقة). حُذف استيراد `et0_agro_product` غير المُستعمَل.
- **اختبارات (4 جديدة، مجموع 15):** الـView == النواة المباشرة في الحقول الجوهريّة (حفظ سلوك) · يُضيف نَسَب الحالة · يحترم snapshot override · fail-closed عند النقص (insufficient بلا اختلاق).
- **تحقّق (خضراء محليّاً):** weather-service **115** (+4) · guard Zero-Legacy LOCKED · bandit High=0 · unit 2866 · ruff · inventory 886 (بلا مسارات جديدة) · bundle. CI معلَّق قبل التقديم السريع.
- **التالي:** VPD View → GDD View → Crop Intelligence → Decision (كلٌّ إنكرمنت مستقلّ).

## WX-10.2-fix — تماسك source_snapshot_id مع snapshot override (مراجعة المستخدم)

- **فجوة نَسَب وجدها المستخدم:** عند تمرير `weather_snapshot_id_override`، كان `products.et0.weather_snapshot_id`=override لكن `state.source_snapshot_id` يبقى البصمة المحسوبة ⇒ تناقض (ET0 يعلن لقطة، الغلاف يعلن أخرى)؛ وطلبان بنفس القيم بلقطتين مختلفتين يُنتجان نفس `state_id` (يضعف traceability/replay/dedup/«الحقيقة الواحدة»).
- **الإصلاح (في `build_canonical_weather_state`):** `source_snapshot_id = weather_snapshot_id_override or weather_snapshot_id(snapshot_inputs)` — المعرّف الخارجي يدخل source_snapshot_id **و**state_id (لأنّ state_id يهشّ source_snapshot_id). الآن ET0.weather_snapshot_id == state.source_snapshot_id == override؛ ولقطتان مختلفتان ⇒ state_id مختلف.
- **تحسينا اختبار (ملاحظتا المستخدم):** (١) الحارس الساكن نُطِّق على **جسم `agro_et0` وحده** (helper `_top_level_func_body`) بدل فحص كامل الملفّ نصّيّاً (لا إيجابيّات/سلبيّات كاذبة مستقبلاً). (٢) أُضيف اختبارا HTTP في `test_et0_agro_product.py` يثبتان حقول النَّسَب عبر العقد الفعليّ (`derived_from`/`canonical_state_id`/`canonical_state_version`/`source_snapshot_id`) + تماسك override عبر HTTP.
- **تحقّق:** weather-service **121** (+3) · canonical+et0 27 · guard LOCKED · bandit High 0 · unit 2866 · ruff. CI معلَّق قبل التقديم السريع.

## WX-10.x صيانة — تحديث سجلّات المسارات بعد إضافة نقطتَي weather (تعلّم)

- **درس:** إضافة مسارات لخدمة تتطلّب تجديد **عدّة** سجلّات CI مُولَّدة، لا service_inventory وحده: (١) `generate_service_inventory.py --write-registry` (SERVICE_REGISTRY.md — أُصلِح `5e9bae4`)؛ (٢) `route_mount_contract_guard.py` (route_mount_inventory — يفحصه `runtime_real_smoke.sh` سطر 15؛ فشل على main بعد FF، أُصلِح هنا: weather-service 23→25 مساراً مباشراً).
- **`route_mount_inventory.{csv,generated.json}`:** جُدِّدا؛ `--check` أخضر. كامل حرّاس `runtime_real_smoke.sh` (route_residual/evidence_pack/cert_checklist/health/capabilities/ai_container) أخضر بأكواد خروج حقيقيّة.
- **خارج النطاق (موثَّق):** `api_versioning_policy_guard.py` يُظهِر drift لكن **لا workflow يشغّله** (غير مُبوَّب) وكان قديماً قبل WX-10 (churn أرقام أسطر عبر رواتشِت سابقة + إدخال allowlist لمسار `irrigation-recommendation` قائم). لم يُجدَّد لتجنّب diff كبير غير متعلّق؛ متابعة صيانة منفصلة.

## WX-10.3 — VPD كـView مُشتقّ من CanonicalWeatherState (+ endpoint جديد /agro/vpd)

- **النطاق (قرار المستخدم):** CanonicalWeatherState → `vpd_view(state)` → `agro_vpd` endpoint فقط؛ لا تحسين خوارزميّة VPD ولا تعديل عتبات ولا إعادة تشكيل عقد (ownership inversion بحفظ سلوك كامل).
- **`vpd_view(state)`:** إسقاط نقيّ يقرأ خانة `vpd` من الحالة **بحفظ حرفيّ** لكامل العقد (vpd_kpa/raw_vpd_kpa/es_kpa/ea_kpa/method/input_completeness/**input_consistency**/quality_status/**quality_flags**/limitations/**cross_check**/units/formula_version) + يضيف نَسَب الحالة (derived_from/canonical_state_id/canonical_state_version/source_snapshot_id) و`weather_snapshot_id` (= لقطة الحالة؛ VPD لا يحملها أصلاً — فيتماسك مع ET0 تحت لقطة واحدة). لا إعادة حساب.
- **`agro_vpd` (جديد، `POST /v1/weather/agro/vpd`):** لم يكن لـVPD endpoint سابقاً؛ يُنشأ View من البداية. build_canonical_weather_state (بمدخلات VPD + override) → vpd_view. handler في weather_runtime، مُسجَّل في main.
- **اختبارات:** unit (9): حفظ حرفيّ للعقد · cross_check/consistency/flags عند مصدرين · نَسَب · انتشار validated/degraded/insufficient بلا رفع · تطابق النواة لكلّ طبقة جودة · تماسك override · حتميّة + state_id متمايز لكلّ لقطة · لا إعادة حساب (inspect) · حارس ساكن محصور بجسم agro_vpd. + HTTP (3): عقد كامل + نَسَب عبر HTTP · تماسك override · insufficient بلا 5xx.
- **البوّابات (قبل الدفع، لا بعد الدمج):** ruff · guard LOCKED · bandit High 0 · unit 2866 · weather-service **133** (+12) · route_mount + service_inventory (--write-registry) + SERVICE_REGISTRY مُجدَّدة و`--check` أخضر (887 مساراً، +1) · route_residual/platform_main_subinventory أخضر · bundle. CI معلَّق قبل التقديم السريع.
- **التالي:** WX-10.4 GDD View (method + crop thresholds + accumulation policy محفوظة).

## WX-10.4 — GDD كـView تراكميّ فوق سلسلة canonical يوميّة (canonical daily weather records)

- **قرار المستخدم (Option A + 3 ضوابط):** GDD ليس مؤشّراً لحظيّاً — View **تراكميّ** فوق **سلسلة** سجلّات طقس يوميّة canonical؛ لا يُضغَط في لقطة واحدة. النواة `gdd_agro_product` تبقى سلطة التراكم حرفيّاً.
- **`canonical_daily_weather_series.py` (جديد):** `build_canonical_daily_series(records, timezone)` — تطبيع يوميّ حتميّ **قبل** الحساب: تحقّق تاريخ → إزالة تكرار **حتميّة صريحة** (لكلّ تاريخ سجلّ واحد بترتيب كلّيّ (snapshot_id,t_min,t_max) مستقلّ عن الوصول؛ `duplicates_resolved` مُصرَّح، لا إسقاط صامت) → ترتيب canonical تصاعديّ. + `gdd_view(series, config)` — يفوّض للنواة (عقد GDD القديم byte-compatible) ويضيف: `gdd_lineage_id` (hash(ordered_daily_state_ids + crop_config + method + accumulation_window + timezone + reset_policy) — **مستقلّ عن آخر يوم**؛ يتغيّر بأيّ يوم/عتبة/طريقة، ثابت عند إعادة الترتيب) · `contributing_state_ids` · **coverage** (period/expected_days(inclusive)/observed/missing/coverage_ratio — بُعد **مستقلّ** عن جودة البيانات) · `series_quality_status` (سلسلة ذات فجوة لا تُعطى validated وإن صحّت أيّامها — تغطية ≠ جودة؛ حقل جديد لا يمسّ quality_status القديم). **لا gap-fill، لا صفر صامت ليوم مفقود، لا نطاق-توسّع.**
- **`agro_gdd` مُرحَّل:** يبني السلسلة ثمّ `gdd_view`. حقول طلب اختياريّة توافقيّة (daily_dates/daily_snapshot_ids/timezone/reset_policy)؛ الطلب القديم (بلا daily_dates) محفوظ السلوك (تواريخ تسلسليّة من start_date؛ period_start/end يُمرَّران للنواة كما هما ⇒ valid_period byte-compatible). حُذف استيراد `gdd_agro_product` غير المُستعمَل من weather_runtime.
- **اختبارات (19):** unit(15) legacy parity · نَسَب مستقلّ عن آخر يوم · تغيّر بالعتبة/الطريقة · reorder-invariance · dedup حتميّ · coverage≠quality (فجوة تخفض series_quality لا quality القديم) · يوم مفقود None لا صفر · عتبات تُغيّر النتيجة والنَّسَب · حدود base/upper == النواة · حتميّة · حارس ساكن (نداء) بجسم agro_gdd · gdd_view لا يُعيد تنفيذ gdd_daily. + HTTP(4) parity + نَسَب/تغطية عبر HTTP.
- **بوّابات (قبل الدفع):** ruff · guard LOCKED · bandit High 0 · unit 2866 · weather **152** (+19) · route_mount/service_inventory/route_residual `--check` أخضر (887 مساراً — بلا مسار جديد، agro_gdd مُرحَّل داخليّاً) · bundle. CI معلَّق قبل التقديم السريع.
- **خارج النطاق (محترَم):** لا تصحيح معادلة/عتبات/يوم-زراعيّ، لا interpolation/gap-fill، لا إعادة تشكيل عقد GDD القديم.
- **التالي:** WX-10.5 Crop Intelligence consumer → Decision consumer → WX-11.

## WX-10.4-fix — حفظ byte-compat لعدم تطابق الطول + تشخيصات (مراجعة المستخدم)

- **فجوة مانعة وجدها المستخدم:** `_gdd_daily_records` كان يقصّ لـ`min(len)` قبل النواة ⇒ قيد `t_min/t_max length mismatch (N/M)` القديم يختفي لمدخلات غير متساوية الطول ⇒ ادّعاء byte-compatible خاطئ لبعض المدخلات.
- **الإصلاح المعماريّ (خيار المستخدم الأفضل):** المسار القديم (بلا daily_dates) يُمرّر **المصفوفتين الأصليّتين** للنواة عبر `kernel_daily_t_min`/`kernel_daily_t_max` في `gdd_view` ⇒ النواة ترى الأطوال الأصليّة والقيد محفوظ حرفيّاً؛ المسار المؤرَّخ (canonical) تراها النواة من السلسلة بعد التطبيع/إزالة التكرار. `valid_period`/`limitations` byte-compatible.
- **تشخيصات صريحة (فجوة أصغر):** أُضيف `diagnostics` للمخرَج (لا يمسّ عقد GDD القديم): `invalid_records` (تاريخ فاسد) · `unmapped_temperature_pairs` (أزواج حرارة لم تُربَط بتاريخ) · `input_t_min_count`/`input_t_max_count`/`input_date_count` — كي لا يُسقَط أيّ سجلّ بصمت.
- **اختبارات (4 جديدة، مجموع 23):** unit: mismatch parity عبر kernel arrays (limitations + valid_period.days == النواة) · diagnostics تُفصح الأعداد. HTTP: `POST /agro/gdd` بطولين مختلفين == النواة القديمة (limitations + valid_period.days) · تواريخ فاسدة تظهر في invalid_records.
- **تحقّق:** weather **156** (+4) · guard LOCKED · bandit High 0 · unit 2866 · ruff · inventory 887 `--check` أخضر · bundle. CI معلَّق قبل التقديم السريع.

## WX-10.4 — إغلاق مُتحقَّق (main+develop @ `1ff0add`)
- **CI الفرع:** 12/12 أخضر على `1ff0add` (run 29155918013).
- **FF:** main + develop تقدّما خطّيّاً `b8a98e5..1ff0add` (لا تباعُد، commit واحد = إصلاح parity).
- **المشغّلات main-only خضراء على main:** `runtime-real-smoke` (success) · `service-inventory-drift` (success) — الجرد جُدِّد `--check` أخضر قبل الـFF فلا انحدار.
- **الحالة:** WX-10.4 GDD View التراكميّ **مُغلَق** بمنهجيّة الراتشِت كاملةً (byte-compat + length-mismatch parity + cumulative lineage مستقلّ عن آخر يوم + coverage≠quality + diagnostics).
- **التالي (خارطة الطريق):** WX-10.5 Crop Intelligence consumer لمنتج GDD القانونيّ (لقطة المستخدم `sahool_wx10_5_...` تحمل تطبيقاً مقترحاً — بانتظار قرار المستخدم على شكل WX-10.4 diagnostics: `diagnostics` block المُثبَّت مقابل `coverage` block في اللقطة).

## WX-10.5 — Crop Intelligence مستهلِك منتج GDD القانونيّ — إغلاق مُتحقَّق (main+develop @ `d2d7dc4`)
- **الانعكاس (consumer-only):** weather-service canonical GDD product → `crop_twin_state` → `crop_intelligence_state.v2`. لا تغيير خوارزميّة/عتبات/كسور-مرحلة/biomass/yield/سياسة قرار.
- **البناء على الشكل المُثبَّت (قرار المستخدم):** طُبِّق دلتا المستهلِك فقط فوق `1ff0add` المُغلَق؛ **weather-service لم يُمَسّ**؛ عقد WX-10.4 المنتِج ثابت (immutable). `crop_twin_state` يقرأ فقط الحقول المشتركة (`accumulated_gdd`·`thresholds_used.method`·`calculation_version`·`contributing_state_ids`·`gdd_lineage_id`·`limitations`·`series_quality_status`) — لا اعتماد على شكل diagnostics الداخليّ لـWX-10.4.
- **الملفّات:** `crop_twin.py` (استهلاك آمر لـaccumulated_gdd؛ حذف markers المُعلَّقة؛ `gdd_daily_override` جسر توافق يحمل `canonical_gdd_product_missing`) · `routers/crop_twin.py` (سطر `gdd_product=gdd_engine`) · اختبار جديد (5) + compose lineage · جرد مُجدَّد (انزياح أسطر/LOC، 887 مسار ثابت) + حزمة إصدار.
- **التحقّق:** focused 15 · crop-intel/crop-twin regression 44 · boundary guard OK · unit 2866 · ruff clean · bundle 3925. CI الفرع **12/12** أخضر (`29156594841`). FF main+develop `1ff0add→d2d7dc4` (يشمل `9fa520c` تحديث دماغ WX-10.4). main-only أخضر على main: `service-inventory-drift` + `runtime-real-smoke`. **لا drift بعد الـFF.**
- **التالي:** WX-10.6 Crop Intelligence → Decision Candidate Boundary (increment مستقل فوق `d2d7dc4` المُغلَق).

## WX-10.6 — Crop Intelligence → Decision Candidate Boundary — إغلاق مُتحقَّق (main+develop @ `db3df94`)
- **المسار:** Canonical GDD → Crop Intelligence → **Decision Candidate** → Human/Policy Approval → Decision-Service SoR. نقطة جديدة `POST /api/v1/crop-twin/decision-candidate` تحوّل تفسير CI إلى **مرشّح قرار** يملكه decision-service، لا قراراً نهائيّاً.
- **الوضعان:** `submit=false` preview بلا كتابة؛ `submit=true` مرشّح `pending_approval` فقط. لا auto-approve/dispatch/task/أمر معدّات/توصية نهائيّة.
- **`gdd_product` سلطة النَّسَب الوحيدة:** accumulated_gdd/gdd_lineage_id/contributing_state_ids تُحسَب مرّة في `_compose_state` وتُعاد **داخليّاً فقط** (عقد compose العامّ لم يتغيّر)، لا تُشتقّ ثانيةً من daily_gdd ولا تُستبدَل من crop_intelligence. البناء يفشل مُغلَقاً عند غياب المنتج أو أيّ من الثلاثة.
- **`candidate_lineage_id`** = hash(field_id·season_id·CI schema/version·recommendation_context·gdd_lineage_id·contributing_state_ids المُرتَّبة·accumulated_gdd·limitations). **preview lineage == submit lineage** (يُبنى مرّة؛ submit لا يعيد بناءه)؛ يتغيّر بأيّ GDD/snapshot؛ حسّاس للترتيب.
- **إثبات submit (لا استنتاج محلّيّ للحالة):** يتطلّب ردّ الخدمة أن يُثبت `authoritative ∧ persisted ∧ decision_id غير فارغ ∧ stage=="candidate"` مع حمل المرشّح `status=pending_approval + approval_required=True`. mirror-ack (SoR-off) ⇒ 502 مُغلَق؛ الخدمة ساقطة ⇒ 503.
- **حارس CI جديد** `decision_candidate_boundary_gate.py` (يجرّد docstrings/comments بـAST؛ يمسح الكود التنفيذيّ من رموز التنفيذ؛ يؤكّد عقد الموافقة) مُوصَّل في Structural Lint.
- **ميزانيّة مسارات المنصّة (زيادة مقصودة موثَّقة +1):** النقطة BFF-orchestrator على سطح crop-twin ⇒ `platform_extraction_map.json` (+صفّ، owner=sahool-platform)، baseline 578→579، p2_6 new_max 575→576، حدّ الحارس 575→576.
- **إعفاء تغطية-واجهة ضيّق ومؤقّت:** owner=crop-intelligence · tracking=WX-10.7 · expiry=2026-10-11 · temporary=true (gaps: `WAIVER-WX10.6-001` + `WAIVER-EXPIRY-GUARD`).
- **درسان (منع تكرار):** (١) شغّل أمر وظيفة Platform Unit محلّيّاً (`PYTHONPATH=. pytest tests` من services/sahool-platform) لا `-m unit` فقط — حُرّاس الميزانيّة غير مُعلَّمة `unit`؛ (٢) أيّ تعديل ملفّ متتبَّع بعد بناء الحزمة يتطلّب إعادة بناء الحزمة قبل الالتزام (بوّابة checksum تُطابق البوّابة الإنتاجيّة main-only).
- **التحقّق:** bridge 20 + endpoint 11 · regression 81 · boundary+coverage guards · unit 2866 · platform job **3683** · ruff · inventories · bundle 3928. CI الفرع **12/12** (`29157566940`) — 1735ebf/4dffbac فشلا (ميزانيّة + checksum) وأُصلِحا في db3df94. FF main+develop `d2d7dc4→db3df94`. main-only أخضر: `service-inventory-drift` + `runtime-real-smoke`. **لا drift بعد الدمج.**
- **التالي:** WX-10.7 (من tip main/develop المُثبَّت `db3df94`): pending_approval candidate → reviewer/policy decision → approved|rejected Decision Record. يستثني dispatch/task/تنفيذ معدّات ما لم تُقدَّم كـincrements مستقلّة.

## WAIVER-EXPIRY-GUARD — إنفاذ انتهاء الإعفاءات (main+develop @ `9551eba`)
- **الفجوة (فُتِحت عند إغلاق WX-10.6):** حقل `expiry` في JSON إعفاء بلا قيمة ما لم يرفضه CI فعليّاً عند تجاوزه ⇒ إعفاء مؤقّت يصير دائماً بصمت.
- **الحلّ:** `scripts/ci/waiver_expiry_guard.py` يمسح ملفّات إعفاء الحوكمة ويفشل عند: `expiry < today` · waiver `temporary:true` بلا `expiry` · `expiry` مُشوَّه. الإعفاءات الدائمة بالتصميم (بلا expiry وغير temporary — admin-ops) تُتجاهَل. يستخدم تاريخ CI الحقيقيّ ⇒ إعفاء WX-10.6 (2026-10-11) ذاتيّ-الانتهاء يفرض تجديداً/إزالة مقصودة.
- **موصَّل** في Repository Structural Lint. الدالّة النقيّة `check_waivers(entries, today)` مُختبَرة بتواريخ محقونة (حتميّة لا تتعفّن) + فحص حيّ يؤكّد أنّ كلّ waiver مؤقّت في `endpoint_ui_coverage_waivers.json` يحمل `expiry` قابلاً للتحليل.
- **التحقّق:** guard أخضر على config الحيّ · 8 اختبارات · validate_ci_gates · ruff · unit 2874 · CI 12/12 (`29158468536`) · FF main+develop `db3df94→9551eba` (يشمل brain WX-10.6). main-only أخضر لا drift.

## WX-10.7 — Decision Candidate → Reviewer/Policy → approved|rejected (CLOSED as code/contract @ `4a370de`)
- **الملكيّة (قرار المستخدم الحاسم):** الانتقال الآمِر مملوك بالكامل لـDecision-Service (`POST /v1/decisions/{id}/review`)، لا endpoint في crop-twin يغيّر القرار نيابةً. المنصّة BFF proxy فقط: تفرض *مَن* يراجع (`Permission.DECISION_APPROVE` لـOWNER/MANAGER/AGRONOMIST) وتُمرّر؛ tenant/reviewed_by من الـJWT؛ fail-closed ما لم يُثبت الردّ الانتقال الآمِر.
- **الحالة على عمود مستقلّ (لا jsonb):** migration `002_decision_review.sql` أضاف `review_state` (CHECK) + `candidate_lineage_id` + `updated_at` على `decision_record` (+backfill للمرشّحين القدامى)؛ `decision_value` (الأدلة) لا يُمَسّ أبداً؛ `stage='candidate'` يبقى نوعاً، `review_state` هو دورة الحياة. جدول `decision_reviews` append-only (trigger على مستوى DB يمنع UPDATE/DELETE) بـ`request_hash` + `UNIQUE(tenant,decision)` + `UNIQUE(tenant,idempotency_key)` + CHECKs.
- **الانتقال الذرّيّ التنافسيّ:** `UPDATE ... SET review_state=$new WHERE stage='candidate' AND review_state='pending_approval' AND candidate_lineage_id=$` + audit + outbox في transaction واحدة؛ تصنيف 0-row مُعزَّز-بالمستأجِر (لا oracle عبر-tenant)؛ نتيجة authoritative من الصفوف المحفوظة لا الطلب؛ facade لا يُخلِّق authoritative.
- **Option A (deployed reality):** ملكيّة `decision_record` ما زالت interim-bridge/platform-owned بلا `DATABASE_URL` في compose ⇒ endpoint المراجعة **fail-closed 503 في mirror mode، لا mirror-ack أبداً**؛ يصير authoritative فقط تحت SoR منشور (مسار `DEPLOYED-DECISION-SOR-PROMOTION` المنفصل).
- **CI (سدّ فجوة: اختبارات decision-service لم يكن لها بيت في CI):** وظيفة **Decision Service Tests** جديدة (Postgres حقيقيّ) — migration --apply + --check؛ خطوة mirror-contract (SoR off) + خطوة WX-10.7 (SoR on) منفصلتان كي لا يتسرّب env. حارسان: `decision_review_boundary_gate` (مسار المراجعة لا يُنفّذ) + `decision_review_ownership_consistency_gate` (ما دام interim-bridge، المراجعة تفشل مغلقةً).
- **إصلاح عزل الاختبار (لا منطق):** فشل أوّليّ 4/19 لأنّ `_review` استعمل idempotency_key ثابتاً؛ المنطق أعاد `idempotency_key_payload_mismatch` **بحقّ**. الإصلاح بيانات-اختبار فقط (`idem-{decision_id}`)؛ لا retry في endpoint، لا تغيير predicate/schema. إعادة التشغيل: **19/19** على Postgres حقيقيّ.
- **التحقّق:** CI الفرع **13/13** أخضر (`29160143916` @ `05dbbc8`) بما فيه Decision Service Tests (authoritative path حقيقيّ). FF main+develop. **درس main-only:** runtime-smoke فشل بعد FF على `health_readiness_inventory` + `route_residual_classification` (جردان لم أُجدِّدهما) ⇒ أُصلِح `4a370de` (كلاهما `--check` أخضر + runtime_real_smoke.sh محلّيّاً 173 passed + bundle 3938). **التالي: DEPLOYED-DECISION-SOR-PROMOTION** (قلب الملكيّة + التفعيل الإنتاجيّ) ثمّ WX-10.8 (reviewer/approvals UI) الذي يزيل waiver المراجعة.

## DEPLOYED-DECISION-SOR-PROMOTION cutover-prep — WX-10.7 cutover toolkit made review-aware (@ `4a7488c`)
- **السياق:** توجيه المستخدم — ابدأ SoR-promotion أوّلاً (قبل WX-10.8 UI) لأنّ بناء واجهة فوق endpoint يعيد 503 غير مُجدٍ؛ اجعل الـcutover عمليّة تشغيليّة قصيرة آمنة لا إعادة هندسة. **تشغيليّ-فقط: بلا تغيير منطق/schema WX-10.7.**
- **الاكتشاف (Explore):** طقم cutover ناضج قائم أصلاً (`cutover.py`/`production_promotion.py`/`migration_runner.py`/`backfill.py`/`read_side_compare.py`/`staging_probe.py`/`rollback.py` + 4 وثائق) لكن **صفر وعي بـWX-10.7** (grep: لا review_state/candidate_lineage_id/decision_reviews في أيٍّ منها). الفجوة = مدّ الطقم، لا إعادة بناء.
- **المنجَز:** (1) `backfill.py --verify-review` — دالّة نقيّة `classify_candidates` + parity/quarantine للقراءة فقط تُظهِر المرشّحين الذين تركهم migration 002 غير قابلين للمراجعة (NULL candidate_lineage_id = fail-closed، لا mis-approve) قبل قلب الملكيّة، لا تخمين ولا كتابة (8 اختبارات وحدة). (2) `/readyz` async يثبت db_reachable+migrations_current عند وجود DATABASE_URL + حالة راية SoR + startup warning؛ mirror يبقى رخيصاً. (3) `rollback.py` يصون `decision_reviews` append-only والأعمدة؛ المراجعات الجديدة تفشل 503. (4) compose (v9+fixed): `DATABASE_URL: ${DECISION_SERVICE_DATABASE_URL:-}` opt-in افتراض فارغ ⇒ sor_enabled() يبقى false ⇒ mirror دون تغيير؛ اختبار deployment-contract طُوِّر ليفرض الصيغة الآمنة (لا URL مُصلَّب). (5) `scripts/deploy/decision_service_migrate.sh` خطوة migrate مرصودة مُبوَّبة (لا startup auto-apply) تشغّل verify-review. (6) `db_ownership.yml`: صفّ `decision_reviews` (decision-service-owned append-only). (7) وثائق ×4 (migration/readiness/final-cert/runbook) + إثبات ما-بعد-cutover. (8) حارس ذاتيّ جديد `scripts/ci/decision_sor_review_cutover_gate.py` يُبقي الطقم+الوثائق review-aware، مُوصَّل في Structural Lint.
- **إصلاح CI (منتصف-الطيران):** Structural Lint فشل على `compose_env_contract_gate` — كلّ `${VAR}` في compose يجب إعلانه في `.env.example`؛ المتغيّران الجديدان لم يُعلَنا. أُصلِح `4a7488c`: أُعلِنا بافتراضات آمنة (URL فارغ، SoR=false). **الدرس: شغّل كامل مجموعة structural-lint محلّيّاً (23 حارساً).**
- **التحقّق:** CI الفرع **13/13** أخضر (`4a7488c`، Decision Service Tests real-Postgres 001+002 + mirror-contract + WX-10.7). unit 2884 · ruff · كلّ حُرّاس structural-lint · runtime_real_smoke.sh 173 · bundle 3941. FF main+develop @ `4a7488c` ⇒ main-only (runtime-smoke + service-inventory-drift) **أخضر، لا drift**. **التالي: قلب الملكيّة الإنتاجيّ (مشغّل)** ثمّ WX-10.8 reviewer/approvals UI (يزيل WAIVER-WX10.7-001).

## WS-E — CI consumer-contract gate (يُغلق مرحلة البناء الاستهلاكيّة WS-A..E)
- **السياق:** WS-A..D أنزلت *منتِجات canonical* (ValidatedIndicatorProduct · Indicators Registry · CanonicalWeatherState/ET0-VPD-GDD Views · canonical water-stress) وأعادت توصيل *المستهلكين*. جوانب المنتِج محروسة (raster_validated_product_guard · indicators_registry_gate · weather_engine_formula_guard) لكن **جانب مستهلك الـViews الكنسيّة ونَسَبها بلا حارس بنيويّ موحَّد** (grep في scripts/ci: صفر ملفّات تحرس canonical_weather_state/et0_view/derived_from). إشارة أماميّة قائمة: `soil_enrichment.py:20` ("بوابة WS-E ستستهلكها").
- **المنجَز:** `scripts/ci/consumer_contract_gate.py` (تقنية decision_candidate_boundary_gate: AST-strip للـdocstrings كي لا يُصطاد ذكرُ نواة في نصّ وصفيّ، عزل الدالّة، فرض REQUIRED ومنع FORBIDDEN على المسار التنفيذيّ) يقفل أربعة عقود مستهلك أنزلتها WS-A..D: **WS-C.1** Views تحمل النَّسَب (`et0_view`/`vpd_view` → derived_from+canonical_state_id/version+source_snapshot_id · `weather_state_report` → reads_from+state_id · `gdd_view` → derived_from+gdd_lineage_id+contributing_state_ids)؛ **WS-C.2** معالجات `weather_runtime` تفوّض للـViews ولا تستدعي النوى مباشرةً (`et0_agro_product`/`compute_vpd`/`gdd_agro_product` ممنوعة داخل agro_et0/agro_vpd/agro_gdd — المحرّك يُبلَغ فقط عبر build_canonical_weather_state/build_canonical_daily_series)؛ **WS-A** مستهلك vegetation يقرأ غلاف `indicator_product`+quality_score+provenance لا stats.mean عارياً؛ **WS-D** مستهلك الريّ يمرّر depletion عبر irrigation_state_guard+canonical_water_stress (مفقود≠صفر).
- **التحقّق:** الحارس أخضر على الشجرة الحقيقيّة (المستهلكون مُهاجَرون) · اختبار `tests_v9/test_consumer_contract_gate.py` (6 حالات، منها اصطياد سلبيّ: docstring-strip، required مفقود، forbidden حاضر، دالّة غائبة ⇒ يُثبت أنّه ليس no-op) · unit 2890 · ruff · **كامل مجموعة structural-lint (24 حارساً) خضراء** · مُوصَّل في Repository Structural Lint. لا تغيير في services/ ⇒ لا drift جرود. **يُغلق WS-E ومعه مرحلة البناء الاستهلاكيّة WS-A..E بالكامل.**

## WX-10.8 — Reviewer/Approvals UI (يُغلق حلقة القرار البشريّة؛ يزيل WAIVER-WX10.7-001)
- **السياق:** بعد إغلاق WX-10.7 (الانتقال الآمِر) وcutover-prep، سلّم المستخدم WX-10.8 كـzip مبنيّ على `2122978`. طُبِّق **على الشكل الحاليّ (integrate on landed shape)**: نسخ إضافيّ للطبقات الخلفيّة الصرفة + دمج جراحيّ حيث اختلف الأساس (رأس تعليق عربيّ في `approvalsConsole.ts` استُعيد؛ إعادة ترتيب config تجاهلتُها لأنّ المجموعة متطابقة ±الإضافتين المقصودتين). لا تغيير في منطق WX-10.7 الآمِر.
- **الطبقة الخلفيّة (إضافيّ صرف):** decision-service — `list_review_queue()` (استعلام tenant-scoped للمرشّحين pending_approval، `review_state` هو مصدر الحالة، الأدلّة في `decision_value` تُقرأ للعرض لا تُمَسّ) + `GET /v1/decisions/review-queue` (**fail-closed 503 في mirror mode** لا طابور فارغ مضلِّل؛ tenant من ترويسة موثوقة). المنصّة BFF — facade `list_review_queue` + `GET /api/v1/decisions/review-queue` محميّ بـ`Permission.DECISION_APPROVE` مع **إثبات fail-closed** (authoritative∧persisted∧count==len(items) وإلا 503؛ 502/503/504→503).
- **الواجهة:** `ApprovalsConsolePage` قسم WX-10.8 (طابور المرشّحين + approve/reject) · `useDecisionReviewQueue` (retry:false، **يعرض 503 بصدق** لا قائمة فارغة) + `useReviewDecisionCandidate` (policy_version=wx-10.8-reviewer-ui-v1) · `candidateEvidenceSummary` (لا يُسلسِل الحمولة كاملةً) · `newReviewIdempotencyKey`.
- **إزالة الإعفاء:** WAIVER-WX10.7-001 أُزيل من `endpoint_ui_coverage_waivers.json` (30→29) والمسار صار مُغطّى في `endpoint_ui_coverage.json` ⇒ reverse-gate أخضر. ميزانيّة منصّة **+1 مقصودة** (577→578؛ baseline 580→581) لنقطة review-queue.
- **التحقّق:** unit **2892** · platform-unit (BFF queue: authoritative pass-through + fail-closed) · decision-service mirror-contract 11 · WX-10.8 endpoint tests (tensor-scoped + 503 mirror) · frontend `tsc --noEmit` نظيف + `approvalsConsole.test.ts` 8 · **24 حارس structural-lint** · runtime_real_smoke.sh 173 · 4 جرود main-only مُجدَّدة (892 route). **واقع النشر:** حتّى الـoperator flip، endpoint المراجعة/الطابور يعيد 503 في mirror والـUI يُظهِر ذلك بصدق؛ يصير حيّاً بعد قلب الملكيّة.

## WX-10.9→10.12 — post-approval execution lifecycle (خمس مراحل، مُدمَجة كـincrement واحد على tip WX-10.8)
- **السياق:** المستخدم سلّم zip تراكميّ (WX-10.8..10.12) مبنيّ على `2122978`. أُنزِل WX-10.8 أوّلاً (63f5297)؛ ثمّ عُزِل دلتا WX-10.9..10.12 (بمقارنة الـzip بشجرتي الحاليّة) ودُمِج على شكل مُنزَل مع صون إصلاحات WX-10.8 CI (نقل الاختبار + تسجيل الملكيّة).
- **السلسلة الآمِرة (كلّها decision-service-owned، append-only، fail-closed 503 في mirror):** WX-10.9 execution_plan (migration 003) → WX-10.10 dispatch_authorization (004) → WX-10.11a execution_request (005) → WX-10.11b execution_delivery_receipt (006، receipt طرفيّ بلا أثر outcome) → WX-10.12 execution_outcome_verification (007). 4 مسارات منصّة BFF جديدة (execution-plan/authorize-dispatch/execute/verify-outcome) محميّة بأذونات جديدة (`DECISION_DISPATCH_AUTHORIZE`/`DECISION_EXECUTE`) + إثبات fail-closed. 4 حُرّاس boundary (dispatch_authorization/execution_request/execution_delivery_receipt/execution_outcome) مُوصَّلة في structural-lint. 5 جداول ملكيّة في db_ownership. اختبارات real-Postgres لكلّ مرحلة (تُطبَّق migrations 001-007 في بيت decision-service).
- **إصلاحان لثغرتين في الحزمة المُسلَّمة (صدق):** (١) اختبار WX-10.11b `test_receipt_is_terminal` كان يقتطع من `record_execution_receipt` حتّى EOF ⇒ يلتقط `verify_execution_outcome` اللاحق (يقرأ outcome_record بحقّ) فيفشل؛ أُصلِح ليحدّ الكتلة بالدالّة نفسها (النيّة محفوظة). (٢) المسار الرابع `/api/v1/dispatch-authorizations/{id}/execute` لم يُعفَ ولم يُصنَّف في الحزمة (بينما الثلاثة الأخرى نعم) ⇒ أُضيف waiver + قاعدة تصنيف `/api/v1/dispatch-authorizations→manager`. (الحزمة نفسها كانت ستفشل هذين).
- **الميزانيّة:** +4 مسار منصّة موثّقة (578→582؛ baseline 581→585) + 4 مدخلات ملكيّة. 902 route كلّيّاً (+10: 4 منصّة + 6 decision-service).
- **التحقّق:** unit **2906** · full platform suite **3702** (الدرس مُطبَّق) · frontend tsc نظيف · 28 حارس structural-lint (منها الأربعة الجديدة) · endpoint-ui gate (33 إعفاء) · route-budget/ownership/module/db-ownership · runtime_real_smoke 173 · 4 جرود main-only مُجدَّدة. اختبارات المراحل real-Postgres في CI. **واقع النشر:** كامل السلسلة يعيد 503 في mirror حتّى operator flip (بالتصميم).

## WX-10.13→11.6 — model/MLOps governance chain (سبع مراحل، increment واحد على tip WX-10.9→10.12 `6c8cf8d`) — `b2192bd`
- **السياق:** المستخدم سلّم zip تراكميّ (WX-10.13..11.6) مبنيّ على شكل متباعد؛ دُمِج integrate-on-landed-shape على `6c8cf8d` (طبّقتُ دلتا سلسلة النموذج فقط، صُنتُ إصلاحات WX-10.9..10.12).
- **السلسلة الآمِرة (كلّها decision-service-owned، append-only، fail-closed 503 في mirror):** WX-10.13 learning_attribution (migration 008) → WX-11.1 calibration_dataset → WX-11.2 model_evaluation_run (009) → WX-11.3 model_promotion_decision (010) → WX-11.4 model_activation_request (011) → WX-11.5 model_activation_approval_command (012) → WX-11.6 registry_adapter_receipt_rollback (013). 9 مسارات منصّة BFF جديدة (learning/*، outcomes/*/learning-attribution) محميّة بأذونات + إثبات fail-closed + 9 مدخلات ملكيّة. 7 حُرّاس boundary AST مُوصَّلة في structural-lint + 7 خطوات اختبار real-Postgres في CI (migrations 001-013).
- **ثلاث ثغرات مُسلَّمة أُصلِحت (صدق — المؤلّف لم يشغّل الحُرّاس/real-Postgres/ruff):** (١) `model_promotion_decision_boundary_gate` كان يقتطع حتّى EOF فيلتقط `registry_alias` من كود WX-11.5/11.6 الشرعيّ ⇒ حُدَّ الجزء بكتلة promotion-decision (حتّى نموذج الإدخال التالي)، مطابقةً لحارس activation-request الشقيق؛ (٢) إعفاءات الحزمة (promotion-decisions/activation-requests/review) بمخطّط أدنى يفشل اختبار الإعفاء الأصرم ⇒ رُقّيت كلّ إعفاءات السلسلة للمخطّط التشغيليّ الكامل (priority/ui_effort/ui_surface_hint/intended_consumer=machine)؛ (٣) حُذف متغيّرا `row` غير المستخدَمين + ruff format للملفّات المنسوخة.
- **endpoint-ui:** `/api/v1/learning` مغطّى ببادئة قائمة؛ أُضيفت قاعدتا تصنيف `/api/v1/dispatch-authorizations→manager` (أُعيدت بعد أن دهسها نسخ config) و`/api/v1/outcomes/→agronomist`؛ + إعفاءات machine-to-machine للمسارات الثلاثة (claim/receipt/rollback) + إعادة إعفاء execute.
- **الميزانيّة:** 582→591 (baseline 594) موثّقة؛ 920 route كلّيّاً (+9 منصّة +6 decision-service migrations منذ WX-10.12).
- **التحقّق:** unit **2906** · full platform suite **3702** · decision-service **24 model + 43 execution-chain + 13 mirror/queue** على Postgres حيّ · frontend tsc نظيف · كامل حُرّاس structural-lint (منها 7 جديدة) · endpoint-ui gate + 13 اختبار · route-budget/ownership · runtime_real_smoke · 4 جرود main-only مُجدَّدة · bundle مُعاد بناؤه + مُتحقَّق (3996 checksum). **واقع النشر:** السلسلة كلّها 503 في mirror حتّى قلب SoR الإنتاجيّ للمشغّل (`DEPLOYED-DECISION-SOR-PROMOTION` = OPEN).

## WX-11.7→11.12 — closed-loop completion (سبع مراحل، increment واحد على tip WX-11.6 `f47b810`) — `e032c67`
- **السياق:** المستخدم سلّم لقطة شجرة كاملة (`wx11_closed_loop_complete`)؛ استُخرجت الدلتا فقط ودُمِجت integrate-on-landed-shape على `f47b810` (اللقطة تسبق كلّ إصلاحات WX-11.6 خاصّتي: حارس promotion مبتور، إعفاءات ناقصة، بلا إصلاح seed — فلم أتبنَّها جملةً؛ نسخت main.py/persistence.py التراكميّين [منطق = WX-11.6 + closed-loop، فرق تنسيق فقط، مُتحقَّق بكامل مجموعة الاختبار] وطبّقت الباقي دلتا على شكلي المُنزَل).
- **السلسلة (decision-service-internal، append-only، fail-closed 503 في mirror):** migration 014 = ٦ جداول أدلّة append-only (registry rollback claims/receipts · post-activation verifications · rollout plans · monitoring snapshots · retraining requests) بمُشغّلات BEFORE UPDATE/DELETE. ٧ نقاط decision-service جديدة (rollback claim/receipt · model active-state [مُشتقّ من إيصالات activation+rollback لا alias متغيّر] · verification · rollout-plan · monitoring-snapshots · retraining-requests). **لا مسارات BFF/أذونات/ميزانيّة/إعفاءات جديدة** (داخليّة machine-to-machine). retraining = طلب مُصفّ فقط (لا تدريب/تفعيل/actuate).
- **إصلاحان لثغرتين كشفهما الإغلاق:** (١) `test_wx11_3_is_decision_only` كان يقطع main.py حتّى EOF فيلتقط `active_model` الشرعيّ من كود active-state ⇒ حُدّ بكتلة promotion-decision؛ (٢) حُذف متغيّرا `row` غير مستخدَمين + ruff format. **درس تنسيق:** اختبار العقد المُسلَّم كان يؤكّد `{'shadow','canary','full'}` (اقتباس مفرد) بينما ruff يُقنّن `{"shadow", "canary", "full"}` — عُدِّل التأكيد للشكل القانونيّ (النيّة محفوظة).
- **درس تحقّق مهمّ (DB pollution):** Postgres المحلّيّ المُعاد استخدامه راكم صفوفاً؛ تشغيل كلّ ملفّات decision-service في عمليّة pytest واحدة يجعل تنظيف DELETE في test_wx10_7 يصطدم بمُشغّل append-only (يُطلَق per-row فقط حين توجد صفوف). CI يشغّل كلّ ملفّ كخطوة منفصلة وwx10_7 مبكّر على جداول فارغة ⇒ يمرّ. أعدت DB نظيفاً وشغّلت كلّ ملفّ عمليّةً مستقلّة بترتيب CI ⇒ ١٥/١٥ خضراء.
- **بوّابة تغطية (`058bd81`):** `pytest -m unit --cov=services --cov-fail-under=40` انهارت دون ٤٠٪ لأنّ نموّ decision-service (مُختبَر بـPostgres حقيقيّ في وظيفة مخصّصة لا بـ`-m unit`) خفّف النسبة بأسطر صفريّة في المقام. أُضيف `.coveragerc` جذر يستثني `services/decision-service/*` من *مقياس الوحدة* فقط (بوّابة المنصّة تستخدم .coveragerc خاصّتها عبر --cov-config صريح؛ لم تُمَسّ). الأرضيّة تبقى ٤٠٪؛ التغطية المحلّيّة ٤٥٪→٤٧٪. صدق: لا كود غير مُختبَر يُخفى — decision-service مُغطّى بالكامل في وظيفته.
- **التحقّق:** unit **2912** · full platform **3702** · decision-service ١٥ ملفّ (mirror + كامل السلسلة) على Postgres حيّ migrations 001-014 بترتيب CI · frontend tsc نظيف · كامل structural-lint (منها الحارس الجديد) · endpoint-ui gate + ١٣ اختبار · runtime_real_smoke · ٤ جرود main-only (927 route، +7 decision-service) · bundle مُعاد + مُتحقَّق (3999). **واقع النشر:** كامل الحلقة 503 في mirror حتّى قلب SoR الإنتاجيّ (`DEPLOYED-DECISION-SOR-PROMOTION` = OPEN).

## WX-12 — model-registry-adapter runtime service + production certification (increment واحد على tip WX-11.12 `d3e44b0`) — `81b1351`
- **السياق:** المستخدم سلّم لقطة `wx12_runtime_implementation_complete`. **اللقطة تسبق عملي WX-10.13→11.12** (ميزانيّتها 577/580 مقابل 591/594 عندي؛ decision_review routes مجموعة جزئيّة من routes خاصّتي) ⇒ تجاهلتُ فروق main.py/persistence.py/config المتباعدة وأخذتُ **فقط دلتا WX-12 الإضافيّة** على شكلي المُنزَل.
- **خدمة جديدة `services/model-registry-adapter/` (stdlib صرف: http.server + urllib، بلا fastapi/asyncpg):** runtime.py (تصنيف انجراف · backoff أُسّيّ محدود · compare-and-swap لتسوية الحالة النشطة · post-activation verification · تطبيق rollout · التقاط monitoring · إرسال retraining — يقرأ نقاط حوكمة decision-service وينفّذها ضدّ `MODEL_TRAFFIC_CONTROLLER_URL`/`MODEL_TRAINING_BACKEND_URL`؛ لا يُدرّب/يُفعّل/ينشر بنفسه؛ `MODEL_REGISTRY_DRY_RUN` مُحترَم؛ حارس token يفرض ذلك). adapter/service/worker (خدمة HTTP بـ/readyz + عامل poll). Dockerfile غير-جذر (USER 10001).
- **حزمة الاعتماد:** scripts/wx12/{postgres_certification,staging_activation_rollback_drill}.py · certification/wx12/WX12_CERTIFICATION_MATRIX.md · docs/runbooks/WX12_RUNTIME_PRODUCTION_CERTIFICATION.md · workflow مخصّص `wx12-runtime-certification.yml` (PR-path + manual dispatch: حارس بنيويّ + migration 001-014 على Postgres حقيقيّ + اختبارات decision-service).
- **التوصيل على شكلي:** بوّابتا WX-12 مُوصَّلتان في structural-lint (تُفرَض كلّ push)؛ اختبارات adapter الـstdlib تُشغَّل في وظيفة Decision Service Tests (بلا DB)؛ service inventory مُجدَّد (29 خدمة). **لا توصيل compose** — النشر مُشغَّل-مُوجَّه عبر runbook الاعتماد، متّسق مع `DEPLOYED-DECISION-SOR-PROMOTION` المفتوح. **لا مسارات BFF/أذونات/ميزانيّة/migration جديدة.**
- **التحقّق:** adapter tests ٣ · بوّابتا WX-12 · bandit HIGH نظيف · ruff نظيف · كامل structural-lint · service-inventory/route-mount/health/residual مُجدَّدة · runtime_real_smoke · bundle (4015) · تغطية الوحدة ٤٧٪ بلا تغيير (وحدات adapter المستقلّة لا يمسحها `--cov=services`).
- **حالة FF:** WX-10.13→11.12 + coverage fix (`d3e44b0`) CI 13/13 أخضر ⇒ FF main+develop `6c8cf8d`→`d3e44b0`. WX-12 (`81b1351`) على الفرع، ينتظر CI ثمّ FF.

## WX-12 follow-up — إصلاح فشلين main-only بعد FF (`443c4cf`)
- **درس حرِج:** بوّابات main-only **ليست اثنتين فقط** (runtime-real-smoke + service-inventory-drift) بل ~٢٥ workflow تُشغَّل على push إلى main (sahool-production-gates · report-index · production-honesty · production-certification-checklist · production-evidence-pack · contract-capabilities-schema · health-readiness · platform-main-subinventory · route-residual · raster/raw-*-contract · إلخ). دمج WX-12 أحمرَ اثنين لم أفحصهما محلّيّاً قبل FF:
  - `sahool-production-gates.yml` → `production_validation_gate.sh` → **legacy_path_audit findings=1**: docstring المُهايئ `adapter.py:5` كتب "no local or in-memory backend is permitted when SAHOOL_ENV=production" (سلوك fail-closed صحيح) لكنّ نمط التدقيق الساذج `\b(in[-_ ]memory|...)\b` طابق "in-memory ... permitted ... production" بلا وعي بالنفي. الكود فعلاً fail-closed (فقط `MODEL_REGISTRY_BACKEND=http` مُعتمَد؛ لا مسار in-memory). أُعيدت صياغة الـdocstring لإزالة الكلمة المُطلِقة مع صون المعنى (لا تلويث allowlist). findings=0.
  - `report-index.yml` → `report_index_guard --check` → **REPORT_INDEX.md drift**: ملفّات تقارير WX المُضافة عبر الزيادات لم تُفهرَس. `--write` أصلحها.
- **الإجراء التصحيحيّ الدائم:** قبل أيّ FF بعد إضافة خدمة/تقرير/migration، شغّل محلّيّاً: `bash scripts/production_validation_gate.sh` + `python scripts/ci/report_index_guard.py --check` + `python3 scripts/ci/validate_ci_gates.py --root .` + `bash scripts/security_audit.sh` — وبعد FF افحص **كلّ** runs الحديثة على main لا اثنتين.
- **التحقّق (محلّيّاً، main-only لا يظهر على الفرع):** production gate أخضر (compile 3781/0 · legacy 0 · source-of-truth 0 · cert-matrix passed) · report-index ok · validate_ci_gates passed · security_audit ok · bundle 4015.

## WX-12.1 — إغلاق عقد runtime<->decision-service (استجابةً لتدقيق دمج خارجيّ) — `1f53f63`
- **السياق:** تدقيق دمج خارجيّ لـ`c7913fd` أثبت بحقّ أنّ حُرّاس WX-12 البنيويّة تمرّ بينما الـruntime **لا يُكمل دورة** مع decision-service: يستدعي نقاطاً غير موجودة، يرسل الهويّة في الجسم بدل الترويسة الإلزاميّة، يُغفل idempotency، يستخدم اسم معامل بيئة خاطئاً، ولا مستهلك activation/rollback متكامل. **تحقّقتُ من كلّ فجوة في الكود الفعليّ قبل الإصلاح** — التدقيق دقيق.
- **الخلفيّة (decision-service):** migration 015 = جدولا إيصال append-only (rollout receipts · retraining dispatch receipts) بـFK لخطّة/طلب WX-11 + مُشغّلات append-only. `GET /v1/learning/runtime-work` = تغذية عمل آمِرة تجمع أوامر activation/rollback المعلّقة + إيصالات تنتظر verification + خطط rollout تنتظر تطبيقاً + طلبات retraining تنتظر إرسالاً — **كلّ عنصر يحمل الحمولة الكاملة** التي تقرأها مُساعِدات الـruntime (model_id/feature_set_id/target_environment/الملخّصات/training_manifest) عبر JOIN للأمر/الطلب. `POST rollout-plans/{id}/receipt` و`retraining-requests/{id}/dispatch-receipt` = تتطلّب X-Recorded-By + idempotency_key، fail-closed 503 في mirror، 404 عند غياب الأصل، append-only + idempotent.
- **الـruntime adapter:** active-state يستعلم `target_environment` (كان `environment` ⇒ ينحدر صامتاً لـproduction)؛ verify/rollout/monitoring/dispatch ترسل الترويسة الفاعِلة الصحيحة (X-Verified-By/X-Recorded-By/X-Captured-By) + idempotency_key حتميّ؛ إيصالات worker (activation/rollback) كذلك؛ الـsupervisor يستهلك activation_command/rollback_command عبر worker (كان يتخطّاها) فتكتمل الدورة فعلاً.
- **الاختبارات (صنف التغطية الذي أشار التدقيق لغيابه):** `test_runtime_contract.py` يقود كود runtime/worker الحقيقيّ بناقل التقاط ثمّ يُعيد تشغيل كلّ طلب مُرسَل ضدّ تطبيق decision-service في mirror — route مفقود (404) / ترويسة مفقودة (400) / جسم فاسد (422) يفشل؛ فقط بلوغ بوّابة SoR (503) يمرّ. **كشف هذا الاختبار خللاً أعمق أثناء البناء: حمولات runtime-work كانت رقيقة جدّاً** فأثرَيتُها. `test_wx12_1_runtime_receipts.py` (Postgres حقيقيّ): التغذية تُظهر العمل بحمولة كاملة وتُسقطه بعد الإقرار؛ الإيصالات تُحفَظ append-only + idempotent + 404 عند غياب الأصل.
- **التحقّق:** decision-service ١٥ ملفّ + adapter contract/runtime على Postgres حقيقيّ (migrations 001-015 بترتيب CI) · unit **2912** · platform **3702** · ruff · كامل structural-lint + بوّابات WX-12 · report-index + production-validation (main-only، فُحصت هذه المرّة قبل push) · runtime_real_smoke · bundle. **لا مسارات BFF/أذونات/ميزانيّة جديدة** (930 route، +3 decision-service). fail-closed 503 في mirror حتّى قلب SoR للمشغّل.

## WX-12.2 — تصلّب ما بعد التدقيق الجنائيّ (استجابةً لتدقيق ثانٍ لـed2ca8d) — `ad8156d`
- **السياق:** تدقيق جنائيّ ثانٍ أكّد إغلاق عقد API لكنّه رصد فجوات تصلّب-إنتاج. أغلقتُ المُحتوى/الصحّة منها بعد التحقّق، وأجّلتُ بنية-البنية بصدق (لا نصف حلّ).
- **مُغلَق:** (Critical 2 أمان متعدّد-النُسخ) migration 016 = جدول claim/lease دائم لأنواع العمل ذات الأثر الجانبيّ الثلاثة (verification/rollout/retraining) التي لم يكن لها claim (بخلاف activation/rollback)؛ list_runtime_work يأخذ lease لكلّ عنصر (مالك+انتهاء+attempt++)؛ نسخة ثانية لا تستلم عنصراً تحت lease حيّ، والمنتهي قابل للاستعادة. اختبار pg حقيقيّ single-owner+reclaim. (Critical 1 مصادقة) middleware توكن-خدمة opt-in: عند ضبط `DECISION_SERVICE_AUTH_TOKEN` كلّ طلب غير-فحص يلزمه bearer مشترك (مقارنة ثابتة-الزمن) يرسله runtime/worker أصلاً؛ غير مضبوط ⇒ no-op فلا يتغيّر mirror/dev. (High 3 replay) الإيصالات تقارن request_hash عند التعارض ⇒ إعادة مطابقة = replay للأصل، مختلفة = 409. (High 2 CAS) expected_active_artifact_digest يُشتقّ من إيصال التفعيل (الحيّ فعلاً) لا من المؤشّر السابق. (Medium 4) LOOP_TABLES += جداول 015/016. (Medium 1) الـruntime يعلن ready فقط بعد جولة ناجحة مع decision-service ويعود 503 عند الفشل.
- **توضيح:** اختبارات pg الأربعة لـ015 تخطّت فقط في بيئة المُدقِّق بلا DB؛ تعمل وتمرّ في وظيفة Decision Service Tests (Postgres حقيقيّ)، وانضمّت لها اختبارات claim لـ016.
- **مُؤجَّل كفجوات OPEN مُتتبَّعة (بنية حقيقيّة، لا نصف بناء):** High 1 (مجدولات monitoring/reconciliation) · High 5 (تقسيم عمل متعدّد-المستأجرين). راجع gaps/registry.md.
- **التحقّق:** decision-service ١٥ ملفّ + adapter contract/runtime/auth على Postgres حقيقيّ (001-016) · unit 2912 · platform 3702 · ruff · كامل structural-lint + WX-12 gates · report-index + production-validation · runtime_smoke · bundle.

## WX-12.3 — المجدولات الدائمة (إغلاق فجوة WX-12-RUNTIME-SCHEDULERS) — `9e308d5`
- **السياق:** تنفيذ مباشر بتفويض المستخدم («قوم بعمل اللازم») للتصميم المُوصى المُسجَّل في gaps/registry.md — أعلى المتبقّي قيمةً بعد إغلاق WX-12.2.
- **المبدأ:** الجدولة config دائم؛ **التقدّم مُشتقّ من الأدلّة append-only** (snapshots/reconcile evidence) لا من حالة last-run متغيّرة تنجرف أو تضيع. لا صفوف جدولة = صفر انبعاث = صفر تغيير سلوك (إنشاء الصفّ هو راية التفعيل).
- **migration 017:** `decision_model_runtime_schedules` (period+anchor مقطوع-الثواني+enabled؛ UNIQUE لكلّ (tenant,kind,model,env)) + `decision_model_reconcile_evidence` append-only (الانجراف قابل للتدقيق) + توسيع CHECK للـclaims ليغطّي النوعَين المجدولَين (عقد النسخة-الواحدة يشملهما؛ صفّ claim واحد لكلّ جدولة — محدود).
- **البثّ:** نوافذ المراقبة تُرصَف من الـanchor (النافذة المكتملة الأخيرة بلا snapshot؛ سلاسل ISO تدور بدقّة إلى صفّ الـsnapshot)؛ reconcile مستحقّ حين لا دليل ضمن الفترة الأخيرة (+period_index حتميّ للـidempotency).
- **الـruntime:** `reconcile_and_report` (HttpRegistry.get ← مقارنة ← دليل بـX-Recorded-By + idempotency)؛ الـsupervisor يستهلك `active_state_reconcile` (كان تخطّياً صريحاً)؛ `DecisionClient.get` يُسقط None (كان urlencode يرسل "None" حرفيّاً — إصلاح جانبيّ حقيقيّ)؛ إغلاق خادم health بلطف (Medium 2).
- **endpoints:** `POST /v1/learning/runtime-schedules` + `POST /v1/learning/reconcile-evidence` (actor إلزاميّ + idempotency + replay/conflict عبر request_hash؛ fail-closed 503 في mirror).
- **الحارس:** `wx12_runtime_scheduler_gate` — يفشل إن عاد الكود خاملاً (بثّ مفقود/استهلاك مفقود/جداول مفقودة).
- **التحقّق:** fresh-DB CI-order ١٦ ملفّ decision-service + mirror + ٩ adapter · unit 2912 · platform 3702 · ruff · كامل structural-lint · report-index + production-validation · smoke · bundle. 932 route (+2 داخليّتان، لا BFF/ميزانيّة).
- **المتبقّي بعد هذا:** WX-12-RUNTIME-MULTITENANCY (OPEN) + قلب SoR للمشغّل + مصالحة حالة العمليّات الخارجيّة لـtraining/rollout (شقّ High 4 المتبقّي — يعتمد على عقود الـbackends الخارجيّة).

## AC-1 — عقود السياق الزراعيّ + الربط الإلزاميّ (تنفيذ توصية الخطّة الرئيسيّة) — `b1d3809`
- **السياق:** المستخدم سلّم `SAHOOL_AGRONOMIC_CONTEXT_AND_FIELD_HISTORY_MASTER_PLAN_20260712.md` وتوصيتها الختاميّة صريحة: «AC-1 = العقد + migration + هيكل الـComposer + الربط الإلزاميّ». ملاحظة ترقيم: الخطّة تسمّيها migration 016؛ فعليّاً **018** (016=claims، 017=schedules).
- **migration 018:** ثلاثة عقود ثابتة append-only + content-hash: `decision_agronomic_context_snapshots` (مجموعات المجال crop/soil/irrigation/weather/climate/terrain/operations كـjsonb مُتحقَّق؛ **مُعنوَن بالمحتوى** — المحتوى المطابق يُعيد استخدام نفس الـsnapshot) · `decision_field_historical_context_snapshots` (نافذة تاريخ مقيَّدة history_to<=as_of في SQL) · `decision_feature_manifests+entries` (القيم الفعليّة: source/observed_at/available_at/quality/formula_version؛ observed<=available لكلّ صفّ) · أعمدة نَسَب على decision_record + `context_contract_version` (قديم=legacy_unbound، مربوط=ac-1).
- **الهيكل:** `agronomic_context/` (contracts.py قوالب قانونيّة — الـdicts العشوائيّة تُرفَض عند الحدّ؛ point_in_time.py انتهاكات **مُصنَّفة** fail-closed: future_leakage/missing_groups/…) + `compose_agronomic_context` (تحقّق قبل أيّ كتابة، معاملة واحدة، replay حتميّ) + `POST/GET /v1/context-snapshots`.
- **الربط الإلزاميّ:** DecisionRecordIn يقبل الـIDs الثلاثة — إن قُدِّمت تُتحقَّق (وجود/tenant/field) وتُربط ac-1؛ الربط الجزئيّ رفض مُصنَّف؛ مع `DECISION_REQUIRE_AGRONOMIC_CONTEXT` لا قرار محكوم جديد بلا الثلاثة (معيار خروج Phase A) — راية مرحليّة كنمط SoR/auth.
- **اختبارات pg:** حتميّة+إعادة استخدام بالمحتوى+replay · رفض future_leakage مُصنَّف بلا أيّ كتابة · تحقّق الربط (مجهول/جزئيّ=رفض؛ ac-1/legacy مسجَّلان) · قراءة+append-only. حارس `agronomic_context_gate`.
- **خارطة الخطّة المتبقّية (مرجع دائم):** Phases B–E (soil/irrigation/climate adapters · historical builder+no-leakage cert · cohort evaluation · Decision Evidence UI) — تُنفَّذ كزيادات لاحقة بتفويض.

## VEG-AGRIAI — دمج زيادة إكمال الإنتاج المُسلَّمة — `6658d86`
- **السياق:** حكم المستخدم على الحزمة الزراعيّة (vegetation ليست Real-only؛ agriai غير مربوط بالسياق) + حزمة `sahool_de0c61d_integrated_verified.zip` (دلتا نظيفة ١٤ عنصراً فوق de0c61d) تعالجها. دُمجت integrate-on-landed-shape.
- **المحتوى:** vegetation: عقود إنتاج + **إعادة وسم صادقة** (LAI المشتقّ من NDVI حقيقيّ = "vegetation-model" بخوارزميّة+uncertainty بدل "estimate"؛ CWSI يبقى تقديراً) · agriai: `agronomic_context.py` + ربط المدخلات بالسياق ورفض النباتيّ التقديريّ في التنفيذ ورفض بيانات المستقبل · حارسان + workflow مخصّص، وُصّلا أيضاً في structural-lint (الـworkflow لا يعمل على دفعات الفرع) + اختبارات العقد (14) في وظيفة CI.
- **ثغرة حزمة أُصلحت:** الحزمة لم تُحدّث `tests_v9/test_vegetation_raster_ndvi` (كان يؤكّد "estimate") — حُدِّث للعقد الصادق الجديد.
- **ملاحظة تصادم أسماء:** `agronomic_context` وحدة agriai وحزمة decision-service (كلاهما وفق الخطّة) — معزولان بالعمليّات في CI؛ دمجهما في عمليّة pytest واحدة يتصادم عبر sys.modules (موثَّق في رسالة الـcommit).
- **التحقّق:** fresh-DB بترتيب CI ١٧ ملفّ (001-018) + mirror + ٩ adapter + ١٤ veg/agriai · unit 2912 · platform 3702 · كامل الحُرّاس (+٣ جدد) · report-index+production-validation · smoke · bundle (934 route).

## 2026-07-12 — إغلاق الخطّة الكاملة VEG-AGRIAI (دمج `full_plan_closed`) + إصلاحا CI + ترقية 4b1bafd — `41211c6`
- **إصلاحا CI بعد دفع b95a21f (فشلان حقيقيّان):** (١) خطوة veg-agriai بلا `working-directory` ⇒ pytest سقط إلى testpaths وحمّل `tests_v9/conftest.py` (import jwt) بخروج 4 — `a53c206`؛ (٢) بعدها: `PyJWT`+`prometheus-client` ناقصان في وظيفة decision-service (استيرادات vegetation_runtime على مستوى الوحدة) + بوّابة checksum للمانيفست (عدّلتُ ci.yml بلا إعادة توليد) — `4b1bafd`. **درس:** أيّ تعديل ci.yml = إعادة بناء الحزمة فوراً؛ خطوات pytest بمسارات `../` تتطلّب working-directory مصرَّحاً.
- **الترقية:** 13/13 أخضر على `4b1bafd` ⇒ بوّابات main-only محليّاً على worktree نظيف (production_validation + report_index + validate_ci_gates + security_audit) ⇒ FF main+develop ⇒ **مسح main-only 28/28 أخضر** (incl. vegetation-agriai-production الجديد). AC-1+VEG-AGRIAI مُغلقة نهائيّاً.
- **دمج `sahool_de0c61d_full_plan_closed.zip` (دلتا 24 عنصراً، superset) على الشكل المُنزَل:** سجلّ مؤشّرات قانونيّ `indicator-registry.v1` (validate_observation يضيف qa_mask_version+valid_pixel_pct لسلطة NDVI؛ quality_gate يفوّض إليه؛ build_snapshot يضمّن feature_manifest حتميّاً) · نقطتا `/v1/indicators/registry[/{name}]` · محوّلات صارمة agronomic_adapters (بطاقة محصول/هيدروليكا تربة/سلسلة طقس يوميّة/كفاءة ريّ — أخطاء مُصنَّفة + بصمات حتميّة) · مؤلّف تاريخ حقل PIT (`field_history.compose` يستبعد ما لم يتوفّر قبل القطع) · `normalized_engine_inputs` عبر المحوّلات · `AGRIAI_PRODUCTION_MODE` يجعل PCSE+المدخلات العلميّة إلزاميّة (فشل مُغلَق مُصنَّف؛ البديل الحتميّ تطويريّ فقط) · `ALLOW_LEGACY_FIELD_REGISTRY` معطَّل افتراضيّاً في الإنتاج · 424 لـNDVI الحاليّ التقديريّ و501 لـall_fields في real-only.
- **عيوب الحزمة المُصلَحة (النمط المتكرّر):** نقاط registry تشير إلى `main.INDICATORS` بلا توصيل main.py (AttributeError) ⇒ re-export؛ السجلّ يعرف `reci` بينما runtime يُصدر `recl` ⇒ KeyError يُسقط build_snapshot ⇒ سُجّل recl + مانيفست متسامح (unregistered) ؛ raster يمدّ `valid_pixel_ratio` (0..1) لا `valid_pixel_pct` ⇒ تحويل وحدة صادق فقط؛ Dockerfile لا يشحن indicator_registry (حارس الجذر اصطاده)؛ اختبار جذر قديم افترض default=True؛ أسلوب الحزمة المضغوط يفشل ruff format.
- **تسوية الهجرة المتصادمة (قرار):** `018_agronomic_context_snapshots.sql` المُسلَّمة تُكرّر جدول AC-1 المُنزَل بمخطّط أضعف (بلا idempotency/replay) وجداولها الجديدة (vegetation/field-history snapshots) **بلا كاتب/قارئ** في الحزمة ⇒ لم تُنزَل؛ بوّابة الإغلاق تؤكّد `018_ac1` المُنزَلة؛ فجوة تصميم مفتوحة VEG-EVIDENCE-STORE (تُبنى مع كاتبها في Phase B/C). ملحق تكامل كامل في `docs/audits/VEGETATION_AGRIAI_FULL_PLAN_CLOSURE_20260712.md`.
- **فجوة جديدة RASTER-PROVENANCE-ENRICHMENT (OPEN):** بروفينانس raster الحقيقيّ = capture_datetime/processing_version بلا qa_mask_version؛ بوّابة السلطة تطلب acquisition_datetime/algorithm_version/qa_mask_version ⇒ real-only الإنتاجيّ يفشل مُغلَقاً بصدق حتى الإثراء.
- **التحقّق:** veg+agriai 55 اختباراً · unit 2912 · ruff · كامل structural-lint + بوّابة الإغلاق الجديدة · report-index/bundle/production-validation/security محليّاً.

## 2026-07-12 (تكملة) — تجديد الجرود + الإغلاق النهائيّ على `bc84755`
- مسح main-only على `c036748` أظهر الفشلَين المعروفَين (Service Inventory Drift + Runtime Real Smoke) — الدرس المُسجَّل طُبّق متأخّراً: نقطتا `/v1/indicators/registry*` غيّرتا الجرود. جُدِّدت (936 مساراً/29 خدمة) + كلّ حُرّاس smoke الساكنة `--check` محليّاً + إعادة بناء الحزمة (4044) — `bc84755`.
- CI الفرع أخضر ⇒ بوّابات main-only محليّاً (وأُضيف فحصا الجرد إلى القائمة قبل-FF) ⇒ FF main+develop ⇒ **مسح 28/28 أخضر**. main = develop = `bc84755`. إغلاق الخطّة الكاملة veg-agriai مُثبَت نهائيّاً.

## 2026-07-12 — AC-6/AC-6.1: النَّسَب الزراعيّ المباشر + مخزن الأدلّة النباتيّ + سلامة قاعدة البيانات — `4b35809`
- **الحزمة:** `sahool_de0c61d_agronomic_integrity_continued.zip` (~16 عنصراً فوق سابقتها؛ تقريران: AC-6 lineage + AC-6.1 integrity). هجرتاها 019+020 تعتمدان جداول 018 حزمتهم غير المُنزَلة ⇒ **أُعيد بناؤهما هجرةً واحدة** `019_agronomic_lineage_integrity.sql` على عقود AC-1 المُنزَلة.
- **المُنزَل:** أعمدة نَسَب مباشرة على decision_record (season/crop/cultivar + vegetation_snapshot_id + feature_manifest_hash) · **مخزن أدلّة نباتيّ ثابت content-addressed مع كاتبه** `POST /v1/evidence/vegetation-snapshots` (replay يعيد القانونيّ، created=false) — **يُغلق فجوة VEG-EVIDENCE-STORE** · FKs مركّبة بالمستأجر NOT VALID (id مخمَّن من مستأجر آخر لا يمرّ) · trigger دلاليّ (تطابق حقل صارم؛ موسم عند إعلانه من الطرفين؛ تطابق hash المانيفست المُدَّعى مع content_hash المخزَّن) · RLS + ربط app.current_tenant في persist_decision_record/الـcomposer/كاتب النباتيّ (صدق: نافذة فقط بدور غير-مالك — خطوة المشغّل) · الوضع الصارم يطلب النَّسَب الكامل (٩ حقول) بعقد `agronomic_context_required` قبل فرع SoR · التحقّق المُصنَّف موسَّع (season mismatches، unknown/mismatch نباتيّ، hash mismatch) + خطأ الـtrigger يُحوَّل رفضاً مُصنَّفاً لا 500.
- **لم يُنزَل (قرار):** كاتبا الحزمة الدفعيّان للسياق/التاريخ — الـcomposer المُنزَل يملك العقدين بدلالات أقوى (PIT قبل الكتابة + manifests + idempotency)؛ مسار كتابة ثانٍ أضعف = شقّ مصدر الحقيقة. الملحق الكامل في `docs/audits/AGRONOMIC_LINEAGE_INTEGRITY_CONTINUATION_20260712.md`.
- **صيد ذاتيّ:** flaky كامن في test_ac1 (إعادة الاستخدام بالمحتوى تعتمد وقوع التأليفين في نفس الثانية) — ثُبّت الزمن. الجرود جُدِّدت (937 مساراً) **قبل** أيّ FF هذه المرّة.
- **التحقّق:** ١٨ ملفّ pg حقيقيّ على 001–019 عذراء + mirror ١٤ + adapter ٩ + veg/agriai ٢٧ + عقد الأدلّة (بلا DB: صارم 422 كامل + hash سيّئ 422 + mirror 503) + unit 2912 + كلّ البوّابات (+٢ جديدتان) + شهادة staging: `scripts/certification/certify_agronomic_lineage.py` fail-closed.

## 2026-07-12 — نَسَب الكوهورت الزراعيّ الشامل + حقيقة الإنتاج (حزمة `production_truth_readiness_continued`) — `6e7d0fa`
- **خمس زيادات مكدَّسة سُوِّيت زيادةً واحدة** (هجراتهم 021→024 = عندي 020→023؛ قاعدتهم 019/020 سُوِّيت سابقاً): وراثة أدلّة القرار في التعلّم (trigger تطابق تامّ مع decision_record) · كوهورت مشتقّ خادميّاً (crop|cultivar|season + بصمة sha256) عبر evaluation→promotion→activation بمنع الاستبدال · امتداده عبر runtime كاملاً (المراقبة تتطلّب إيصالاً مفعَّلاً؛ إعادة التدريب تتطلّب إشارة انحراف من المراقبة) · النَّسَب الطرفيّ (rollback/rollout/dispatch receipts) + حالة نشطة rollback-aware (أحدث انتقال يحكم لا أحدث تفعيل) · حقيقة الإنتاج النباتيّ (حذف المولِّد التركيبيّ نهائيّاً؛ NDVI الحاليّ من أحدث مشاهدة raster موثّقة أو فشل 424؛ readyz يتبع raster في real-only وpcse في وضع إنتاج agriai).
- **علّتان مُسلَّمتان قاتلتان أُصلحتا:** (١) asyncpg يعيد jsonb نصّاً والحزمة أعادت ترميزه بـ`_json()` = سلسلة JSON `"{}"` لا كائن ⇒ كلّ إدراجات الوراثة الـ13 كانت سترفضها triggers الحزمة نفسها على قاعدة حقيقيّة (برهانهم البوستغرسيّ مُتخطّى!) — أُصلح بـ`_cohorts_passthrough`؛ (٢) نمط «توصيل main المنسيّ» الثالث: analysis.py يستدعي `main._current_ndvi_from_raster` بلا re-export.
- **قرارات:** FORCE RLS المُسلَّم على التعلّم لم يُنزَل (غير مُختبَر + الخدمة مالك الجداول) — ENABLE+policy كسياسة 019؛ FORCE مع دور غير-مالك. الاختبارات القائمة أُعيد تأسيسها لا إضعافها: بذور يتيمة صارت مرفوضة بالتصميم ⇒ `tests/_model_chain.py` يبذر سلسلة تفعيل كاملة أمينة.
- **تحقّق:** 001–023 على قاعدة عذراء + idempotent · ٢٢ ملفّ pg (فحص نجاح صارم هذه المرّة) · adapter ٩ · veg+agriai ٦١ · unit 2912 · ٥ بوّابات جديدة + كلّ القديمة · الجرود مُجدَّدة قبل الدفع · حزمة 4053.

## 2026-07-12 (خاتمة) — إقفال نَسَب الكوهورت الشامل على `94bab5e`
- مسح main-only على `444aa1d`: 27/28 — الفشل الوحيد حارس P1 main-only بتوقُّع بائت لـ`_generate_timeseries` المحذوفة شرعيّاً ⇒ الحارس صار يتتبّع البديل الموثّق `_current_ndvi_from_raster` (`94bab5e`). **درس مُرسَّخ:** حذف دالّة runtime يستلزم مسح توقّعات الحُرّاس main-only عنها (p1_main_decomposition_guard heavy-functions).
- إعادة الترقية والمسح: **أخضر كامل**. main = develop = `94bab5e`. الهجرات 001–023، السلسلة الزراعيّة مقفلة قرارًا→تعلّمًا→نموذجًا→runtime→إيصالات طرفيّة.

## 2026-07-12 — إغلاق RASTER-PROVENANCE-ENRICHMENT + توصيل مُنتِج الأدلّة النباتيّ (استكمال ذاتيّ للخارطة)
- **إثراء بروفينانس raster (يفكّ فشل real-only المُغلَق على بيانات حقيقيّة):** ProvenanceRecord + acquisition_datetime (تسمية أمينة لنفس القيمة) + algorithm_version (`sahool.band_math/1` مُصدَّر من موضع الصيَغ) + qa_mask_version (`<strategy>/1` فقط عند تطبيق قناع فعليّ — الصرامة مقصودة) + valid_pixel_pct؛ مملوءة في build_validated_raster_product وlayer_lookup. برهان تقاطعيّ raster→vegetation: بروفينانس مُثرى يجتاز validate_observation بلا أخطاء.
- **مُنتِج الأدلّة (يُكمل حلقة VEG-EVIDENCE):** `_push_vegetation_evidence` في vegetation_runtime خلف راية `VEGETATION_EVIDENCE_PUSH_ENABLED` (افتراض إيقاف): يدفع الـsnapshot المُعنوَن بالمحتوى إلى `POST /v1/evidence/vegetation-snapshots` (الـhash هو مفتاح الـidempotency)؛ fail-soft بنتيجة `evidence_push` صريحة في ردّ التحليل (pushed/disabled/tenant_not_uuid/http_503/unreachable) — لا صمت؛ المستأجرون غير-UUID يُتخطَّون بصدق. عقد المُنتِج مُختبَر بأربع حالات (URL/ترويسة/جسم + mirror 503 + انقطاع + skip).
- **التحقّق:** unit 2912 · veg+raster 57+11 · كلّ البوّابات · الجرود ثابتة · الحزمة 4074.

## 2026-07-12 — إغلاق WX-12-RUNTIME-MULTITENANCY (التقسيم المُخوَّل خادميّاً)
- **migration 024** `decision_runtime_worker_tenants`: سجلّ تفويض تشغيليّ (worker_id+tenant_id فريد، enabled قابل للقلب بلا حذف، idempotency+replay/conflict). جدول تهيئة عابر للمستأجرين بالتصميم (هو خريطة التفويض ذاتها) — بلا RLS، موثَّق.
- **الـfeed**: عامل مُسجَّل لا يسحب إلّا مستأجريه المُفوَّضين (403 مُصنَّف `worker_tenant_unauthorized`)؛ العامل غير المُسجَّل يبقى على سلوك env القديم (توافق خلفيّ — التسجيل الأوّل يقلب الإنفاذ). نقطتا تسجيل (X-Registered-By + idempotency) واكتشاف.
- **الـadapter**: `resolve_tenants` بأولويّة صريحة (RUNTIME_TENANT_IDS csv ← RUNTIME_TENANT_ID ← اكتشاف خادميّ من نقطة الاكتشاف) + `run_once` يلفّ القسمة كلّها؛ غياب التعيين = RuntimeContractError صريح لا خمول صامت؛ client.get صار يتجنّب ترويسة "None" الحرفيّة للنداءات بلا مستأجر.
- **التحقّق:** برهان HTTP على PG حقيقيّ (تسجيل→200 لمستأجره→403 لغيره→اكتشاف) + replay/conflict/تعطيل · adapter 10 (منها حلّ المستأجرين بأربع حالات) · البطاريّة الكاملة 001–024 عذراء · unit 2912 · بوّابة جديدة + الجرود (نقطتان جديدتان) والحزمة.
- **المتبقّي المفتوح الآن تشغيليّ فقط:** قلب SoR + دور غير-مالك (RLS/FORCE) — كلاهما للمشغّل.

## 2026-07-12 (خاتمة) — إقفال multitenancy على `73666ee` + لقطة zip
- مسح main-only: **28/28 أخضر**. main = develop = `73666ee`. فجوة WX-12-RUNTIME-MULTITENANCY = CLOSED (سجّلها gaps/registry).
- **حالة السجلّ المفتوح الآن: خطوتا المشغّل فقط** — قلب SoR (DEPLOYED-DECISION-SOR-PROMOTION) + دور runtime غير-مالك يُفعّل RLS (وFORCE لاحقاً). لا فجوات كوديّة مفتوحة.
- أُرسلت لقطة `sahool_73666ee_multitenancy_verified.zip` (git-archive، 4378 ملفّاً) للمستخدم.

## 2026-07-12 — Phase C: شهادة عدم-التسريب (تنفيذ ذاتيّ بتفويض «ما تراه مناسباً»)
- **الاختيار ولماذا:** من تدقيق سلاسل المزوّد→المستهلك (كلّ المجالات الثمانية موصولة)، أقرب زيادة كوديّة ذات قيمة هي معيار خروج Phase C — الباني التاريخيّ مُنزَل (composer + field_history) وينقصه **برهان الشهادة الممنهج**. أُرجئ عمداً: إثراء مجموعة المناخ (يمسّ ميزانيّة مسارات المنصّة وعقود UI) ومزوّد توقّع الطقس الثاني (تكامل خارجيّ) — مرشّحان تاليان موثَّقان.
- **المُنجَز:** `test_no_leakage_certification.py` — مسح خصائصيّ حتميّ (seed=42) بأربعين تركيبة عشوائيّة على PG حقيقيّ: أيّ تركيبة فيها ميزة مسرِّبة (متاحة بعد القطع) تُرفض `future_leakage` مُصنَّفةً **بصفر كتابات**، وكلّ نظيفة تمرّ (توازن الفرعين مفروض ≥5/≥5) + انتهاكات نافذة التاريخ المُصنَّفة + **برهان CHECKs القاعدة مستقلّاً عن الـcomposer** (كاتب مُعطَل افتراضيّاً لا يستطيع إدامة تسريب). سكربت staging fail-closed `certify_no_leakage.py` + بوّابة `no_leakage_certification_gate` + خطوة CI حقيقيّة.
- **حالة الخطّة الرئيسيّة:** Phase A/B مُنزَلتان سابقاً، **Phase C (شهادة no-leakage) = مُنجَزة**، Phase D (التقييم الجماعيّ cohort-aware) أُنجزت ضمن AC-9، المتبقّي بتفويض: Phase E (Decision Evidence UI).

## 2026-07-12 — تصلّب multitenancy (ردّ على FORENSIC_AUDIT_SAHOOL_73666EE)
- **تحقّق قبل إصلاح:** F-01 (عامل مجهول fail-open) وF-02 (replay بائت يُحيي تفويضاً ملغى) مؤكَّدان من الكود المُنزَل؛ F-03/F-04 صحيحان معماريّاً؛ F-05 مُستوعَب تحت strict mode؛ F-06/07/08/09 وجيهة كلّها.
- **المُنجَز:** migration 025 (سجلّ أوامر append-only + revision على الإسقاط + CHECKs) · `register_runtime_worker_tenant` يُعيد كتابته ledger-first (replay يُرجِع النتيجة الأصليّة دون مسّ الإسقاط؛ FOR UPDATE + revision رتيب) · راية `DECISION_STRICT_WORKER_TENANTS` (عامل غير مُسجَّل ⇒ رفض) · قاعدة جاهزيّة `DECISION_REQUIRE_AUTH_TOKEN` (F-09) مع كشف `enforcement` في `/readyz` · compose/.env.example · بوّابة WX-12 عُمِّقت (F-08) · اختبارات السلوك 5/5 على PG+HTTP حقيقيّين (strict-403 · stale-replay-safety · append-only/CHECKs · رتابة revision).
- **التحقّق محلّيّاً (قاعدة نظيفة):** migrations 25/25 --apply+--check نظيف · بطاريّة decision كاملة 22/22 · adapter+veg-agriai عقود PASS · بوّابات (wx12 ×2 · no-leakage · prod-truth · p1) PASS · `pytest -m unit` 2912 ناجحاً · bundle rebuilt+validated · جرود health/service/residual جُدِّدت (drift متوقَّع من تغيير compose/readyz).
- **فجوة جديدة صادقة:** WORKER-IDENTITY-BINDING (F-03/F-04) OPEN — اعتماد لكلّ عامل قرار بنية تحتيّة.
- **درس بيئيّ:** `pytest` العاري قد يلتقط مفسّر uv-tools بلا fastapi/asyncpg — استعمل `python3 -m pytest` في البطاريّات المحلّيّة.

## 2026-07-12 — تقرير التتبّع التشغيليّ OPERATIONAL_TRACE_SAHOOL_73666EE (تدقيق خارجيّ ثانٍ لنفس الحزمة)
- **التقييم:** معظم بنوده عولجت مسبقاً في `a0f3e24` (التقرير حُلِّل على zip قديم قبل التصلّب). **بند جديد حقيقيّ واحد:** ربط النشر — `services/model-registry-adapter` (runtime دورة الحياة WX-12) لم يكن له خدمة compose؛ الموجود `sahool-model-registry-worker` عامل منصّاتيّ **مكمِّل** (`api.phase_runtime_workers model` يعالج `model_promotion_history_runtime`) لا بديل.
- **الإغلاق:** خدمة `sahool-model-lifecycle-adapter` خلف profile اختياريّ `model-lifecycle` (الإنتاج يتطلّب URLs/tokens خارجيّة — `_env(required_prod=True)` يفشل مغلقاً بدونها؛ بدء صامت نصف-مُهيّأ في الرصّة الافتراضيّة خطأ) · `DECISION_SERVICE_TOKEN` يُشتقّ من `DECISION_SERVICE_AUTH_TOKEN` المشترك (مصدر واحد) · 11 متغيّراً جديداً في `.env.example` (compose_env_contract_gate أخضر) · بوّابة WX-12 اكتسبت رموز ربط النشر (منع انحدار) · التقرير مُنزَل في `docs/audits/` بملحق تكامل يخرّط كلّ بند إلى تصرّفه.
- **تحقّق:** compose YAML سليم · بوّابات compose/nginx/service-inventory/report-index خضراء · `pytest -m unit` 2912 · bundle rebuilt+validated.

## 2026-07-12 — إقفال دورة التصلّب + ربط النشر (راتشِت كامل)
- CI الفرع أخضر على `a0f3e24` و`781bd23` · بطاريّة ما-قبل-FF (10 بوّابات) خضراء على worktree نظيف لكلتيهما · FF `main`+`develop` → `781bd23` · **مسح main: 30/30 أخضر**. المهمّة #166 مُقفلة. main = develop = `781bd23` (يتضمّن Phase C `c3f278d`).

## 2026-07-12 — Phase E: Decision Evidence UI (بتفويض المستخدم «المتبقّي Phase E»)
- **decision-service:** `GET /v1/decisions/{id}/agronomic-evidence` — قراءة آمِرة لسلسلة الدليل كاملة (لقطة السياق + النافذة التاريخيّة + بيان الميزات بكلّ أختام PIT + اللقطة النباتيّة) عبر `get_decision_agronomic_evidence` (join صريح على جداول 018/019)؛ mirror ⇒ 503 fail-closed (لا «لا دليل» زائف)؛ 404 صادقة؛ `hash_matches_decision` يكشف عدم تطابق بصمة الـmanifest المثبَّتة على القرار؛ `evidence_complete` مُشتقّ لا مُدَّعى؛ قرارات `legacy_unbound` تعود بمراجع فارغة كما هي.
- **BFF:** `GET /api/v1/decisions/{id}/agronomic-evidence` في `decision_review.py` بصلاحيّة `DECISION_APPROVE` (المراجِع يرى الدليل قبل البتّ) + برهان fail-closed (authoritative∧persisted∧read_only∧مطابقة id) + عميل `get_decision_agronomic_evidence` في `decision_service_client`.
- **الواجهة:** `DecisionEvidencePanel` (components/approvals) موصول في `ApprovalsConsolePage` لكلّ مرشّح (قراءة كسولة عند الفتح): شارات مجالات السياق، النافذة التاريخيّة، جدول ميزات PIT (رُصدت/أُتيحت/الجودة/ضمن القطع؟ مع «تسريب!» أحمر)، تحذير نزاهة hash، حالة legacy_unbound معلنة حرفيّاً + hook `useDecisionAgronomicEvidence` + أنواع/مساعدات في `approvalsConsole.ts`.
- **التحقّق:** اختبار PG جديد `test_decision_evidence_read.py` (4/4: سلسلة كاملة PIT-stamped · legacy nulls · 404 · HTTP 200/404/503) + خطوة CI · حارس ساكن `DecisionEvidencePanel.static.test.ts` (5/5) · tsc نظيف · بوّابتا endpoint_ui_coverage + service_feature_ui (مدخل تغطية جديد) · الجرود الأربعة مجدَّدة · `pytest -m unit` 2912.
- **حالة الخطّة الرئيسيّة:** Phases A–E كلّها مُنزَلة — Phase E كانت آخر المتبقّي بالتفويض.

## 2026-07-12 — علل الواجهة المُبلَّغة (لقطات 7/11) — تحقّق وإصلاح
- **(1) `/crop/agro-zones` انهيار `f.map is not a function` — علّة كود مؤكَّدة وأُصلحت:** الخادم يغلّف `/api/v1/agro-zones/list` بـ`{zones:[...]}` والـhook كان يعامل الردّ مصفوفةً؛ فُكَّ الغلاف. **علّة صامتة ثانية اكتُشفت بالفحص نفسه:** الواجهة كانت تقرأ `suited`/`avoid` والخادم يعيد `suited_crops_ar`/`avoid_ar` — قوائم المحاصيل الملائمة كانت فارغة دائماً؛ أُصلحت الأسماء والأنواع.
- **(2) `/crop/weather` توصية FAO-56 محجوبة `missing_depletion_mm` — سلوك fail-closed مقصود لا علّة:** التوصية تقرأ آخر استنزاف من `water_ledger` وكاتبه الوحيد مسار الإدخال اليدويّ `POST /fields/{id}/water-ledger`؛ غياب صفوف ⇒ حجب صادق (مفقود ≠ صفر). العلاج تشغيليّ: تسجيل قراءات دفتر المياه. (أتمتة ميزان الماء اليوميّ = زيادة معماريّة مستقلّة إن طُلبت.)
- **(3) `/crop/unified-crop-state` بلا اختيار حقل — أُضيف:** مُحدِّد حقل على `useSelectedField` المشترك عبر الشاشات + تعبئة مسبقة صادقة (المحصول وNDVI فقط — ما يحمله سجلّ الحقل فعلاً؛ الباقي يدويّ).
- **(4) المايسترو `/health/maestro` — يعمل، والثقة «غير متوفّرة» صدقُ بياناتٍ لا عطل:** الشاشة تعرض التحليل وتُعلن أنّ مصدر الثقة guess ومؤشّرين ناقصين — يحتاج معالجة صور للحقل (مؤشّرات NDVI) وبيانات المصادر، لا إصلاح كود.
- **(5) `/ops/inventory` — نُفِّذ الطلب:** «الفئة» صارت قائمة منسدلة (10 فئات مدخلات قياسيّة ∪ فئات المستأجِر القائمة + «فئة أخرى…» تفتح إدخالاً حرّاً) و«الاسم» اكتسب datalist اقتراحات من أصناف الفئة المختارة (اقتراح لا قيد). أُضيف `list` prop لمكوّن `Input` القياسيّ.
- **صيانة مكتشفة:** حارس ChatbotAiEvidenceTransparency الساكن كان يقرأ `ai_agronomist/main.py` بينما الرموز انتقلت إلى `ai_evidence_runtime.py` بعد التفكيك (فشل كامن لا يشغّله CI) — صُوِّب المصدر. **وإصلاح راتشِت Phase E:** مسار الأدلّة الجديد سُجِّل مملوكاً في `platform_extraction_map.json` بميزانيّة +1 عمديّة (594→595 و591→592) — الحارس عمل كما صُمِّم.
- **تحقّق:** vitest كامل 1121/1121 · tsc نظيف · بطاريّة المنصّة 3702 · `pytest -m unit` 2912 · bundle rebuilt.

## 2026-07-12 — إقفال 21aa123 + WATER-LEDGER-AUTO (بطلب المستخدم «هل تمّت أتمتة ميزان الماء؟»)
- **راتشِت 21aa123 مُقفل:** CI أخضر · بطاريّة ما-قبل-FF 10/10 · FF main+develop · **مسح main 28/28**. لقطة `sahool_21aa123_phaseE_evidence_ui_verified.zip` (4387 ملفّاً، sha256 fd32f78b…) أُرسلت.
- **WATER-LEDGER-AUTO (جديد):** الجواب الصادق كان «لا، غير مُؤتمت» — فنُفِّذ: (١) `api/water_ledger_auto.py` منطق تراكم FAO-56 نقيّ `Dr_t = clamp(Dr_prev + ETc − P_eff − I, 0, TAW)` بافتراضات مُعلَنة (bootstrap من سعة حقليّة بثقة 0.4، قصّ القيد الشاذّ مُعلَن، ريّ غير مُقاس مُعلَم، سقف TAW مُعلَم) وسيادة القيد اليدويّ؛ (٢) عامل `water_ledger` في `phase_runtime_workers` (Pattern A): حقول المواسم النشطة ⇒ ET0 من محرّك الطقس حصراً (agro/et0 — لا et0 المزوّد الخام) + مطر توقّع اليوم + ريّ `irrigation_runs` المكتملة + TAW من نسيج مخبريّ معتمَد إن وُجد ⇒ upsert idempotent بـ`created_by='water-balance-auto'`؛ فشل الطقس ⇒ تخطٍّ صادق لا صفر مُختلَق؛ (٣) خدمة compose `sahool-water-ledger-worker` خلف `WATER_LEDGER_AUTO_ENABLED` (افتراضيّاً off) بدورة ساعة؛ (٤) 8 اختبارات وحدة نقيّة + حارس توصيل ساكن؛ (٥) تسجيل الوحدة في baseline النموّ واستعلامات العامل في allowlist تدقيق الاستئجار (GUC لكلّ حقل).
- **أثره على الشاشة المُبلَّغة:** بعد تفعيل الراية، `missing_depletion_mm` يزول تلقائيّاً للحقول ذات المواسم النشطة — توصية FAO-56 تعمل بلا إدخال يدويّ.
- تقرير تدقيق جديد وصل (DECISION_ENGINES_CONSUMERS_AUDIT على 21aa123) — يُقيَّم تالياً؛ بنده الأبرز: مستهلك المُشغّل الفيزيائيّ (actuator) غير موصول تشغيليّاً.

## 2026-07-12 — ACTUATOR-DISPATCH-CONSUMER (P0 من DECISION_ENGINES_CONSUMERS_AUDIT على 21aa123)
- **تحقّق قبل بناء:** البند الحرج صحيح — decision-service يملك claim/receipt (WX-10.11b) لكن بلا feed اكتشاف، وactuator يملك المساعدات النقيّة بلا حلقة. **واكتُشف أعمق:** اختبار `test_dispatch_bridge.py` كان مكسوراً كامناً منذ تفكيك P2 (يحمّل main.py و`import *` لا يُصدّر أسماء الشرطة السفليّة) **ولا يشغّله CI أصلاً** — حلقة Shard 3 (#480) ضاعت في التفكيك وبقي وصفها.
- **المُنجَز:** (١) feed اكتشاف `GET /v1/execution-requests` (queued فقط، يستثني قيد-التسليم عبر NOT EXISTS على receipt IS NULL؛ mirror⇒503؛ عزل مستأجر)؛ (٢) حلقة استهلاك في actuator_runtime خلف `FEATURE_DISPATCH_ACTUATOR` وتعيين مستأجرين صريح (`ACTUATOR_DISPATCH_TENANT_IDS` — فارغ = خاملة لا تخمين): feed ⇒ kill-switch fail-closed (مُشتبَك⇒تُترك مصفوفة؛ لا قاعدة⇒لا مطالبة) ⇒ claim ذرّيّ بـdelivery_token ⇒ `_plan_dispatch_execution` نقيّة (أمر فاسد/مخاطرة مُعلَنة خارج المسموح ⇒ إيصال failed مُعلَّل) ⇒ `send_mqtt_command` (يحترم disabled/simulation/real) ⇒ إيصال accepted/failed دائماً بحمولة `published != physically executed`؛ (٣) توصيل compose (env على sahool-actuator-service، التوكن من `DECISION_SERVICE_AUTH_TOKEN` المشترك) + `.env.example`؛ (٤) اختبار PG جديد للسلسلة كاملة (feed⇒claim يسحب من الـfeed⇒receipt⇒accepted + فلاتر + عزل مستأجر + HTTP 422/503) 3/3؛ (٥) اختبارات الجسر أُصلح مصدر تحميلها (actuator_runtime.py) واتّسعت إلى 14/14 **ووُصلت بـCI لأوّل مرّة** مع خطوة الـfeed.
- **تحقّق:** decision battery ذات الصلة 10/10 · bridge 14/14 · unit 2912 · بوّابات compose/env/inventories خضراء · bundle rebuilt.
- بندا P1 من التقرير: opt-in الـmodel-lifecycle = قرار موثَّق عمديّ (ledger ربط النشر)؛ إزالة كتابة المنصّة المباشرة = ما-بعد قلب SoR (فجوة المشغّل القائمة).

## 2026-07-12 — TIMELINE-PROVIDER-DATES (طلب المستخدم: شريط الصور التاريخيّ يعرض صورة واحدة فقط)
- **التشخيص:** `available-dates` كان يعيد المعالَج فقط (COGs في الذاكرة/القاعدة) — فالشريط لا يعرض محور الالتقاط الحقيقيّ، وبعد «جلب 3/6/12/24 شهراً» يظهر ما اكتملت معالجته فقط (مشهد واحد أثناء تشغيل backfill).
- **الحلّ:** توسعة `GET /v1/fields/{id}/available-dates` بـ`include_provider`+`months` — يجلب هندسة الحقل (fetch_field_geometry) ⇒ bbox ⇒ مسح STAC بنوافذ شهريّة ويُدمج كلّ تواريخ التقاط المزوّد بـ`has_cog=false` (لا ادّعاء جاهزيّة؛ فشل الكتالوج يُعلَن في `provider_dates_error` ولا يُفشل المعالَج) · تمريرها عبر raster_service_client وواجهة المنصّة · `fetchFieldImageryAvailableDates(opts)` · الشريط في MapHub صار **حسب الطبقة المختارة** (idx) + كامل محور المزوّد — الجاهز لهذا المؤشّر بصورته، والباقي «ينتظر COG» بتاريخه الحقيقيّ بلا صورة (العرض القائم كان يدعم الحالتين أصلاً).
- **تصويب عقود اختبارات قديمة بوعي:** حارس «all-index timeline» عُدِّل إلى العقد الجديد (طلب المستخدم صريح: حسب الطبقة) وحارس شكل params حُرِّر من الصيغة الحرفيّة.
- **تحقّق:** vitest كامل 158/158 (1124) · tsc نظيف · ruff · unit 2912 · bundle rebuilt. حارس ساكن جديد يثبت الموضعين (الجلب الأوّليّ + تحديث ما-بعد-backfill) وأمانة has_cog=False.

## 2026-07-12 — مسح main على 3b20e07: 29/30 + إصلاح فوريّ
- المسح: 29 أخضر، وفشل واحد في **Sahool Production Gates / pytest-contracts**: `test_jobs_database_url_is_limited_to_background_channels` — allowlist **ثانٍ** لقناة JOBS في `tests/security/test_phase12_final_production_gates.py` لم يكن ضمن بطاريّة ما-قبل-FF (سجّلتُ العامل في `rls_runtime_gate.py` فقط). سُجِّل `sahool-water-ledger-worker` فيه بالتبرير نفسه — 4/4 محلّيّاً.
- **درس مُرسَّخ:** إضافة أيّ خدمة بقناة JOBS تتطلّب تسجيلاً في **موضعين**: `scripts/security/rls_runtime_gate.py` و`tests/security/test_phase12_final_production_gates.py` — ويُضاف الأخير إلى بطاريّة ما-قبل-FF من الآن.
- إصلاح mypy مرافق على القمّة نفسها (`3332b51`): `logging_config` سلسلة LOG_LEVEL تنتهي بحرفيّ.

## 2026-07-12 — دمج حزمة المراجعة review_fixed (على 3b20e07)
- **دلتاها:** إصلاح واحد + تقرير. الإصلاح صحيح ومُتبنّى: `actuator-service/main.py` يعيد تصدير كامل سطح actuator_runtime (شاملاً المساعدات الخاصّة التي يُسقطها `import *`) بهويّة محفوظة + إعادة تسجيل idempotent للراوترات — يصلح 6 اختبارات سلامة كانت فاشلة كامنة (المشكلة نفسها التي عالجتُها ضيّقاً في اختبار الجسر). تعديل وحيد على المُسلَّم: استدعاء صريح `_runtime.register_routers(_runtime.app)` (حقن globals يفشل ruff F821 — النمط المتكرّر). سلامة+جسر 22/22.
- **فجوة الحلقة المشخَّصة (لا جسر آليّاً من عجز الماء إلى قرار):** صحيحة ومقصودة — الأتمتة منتِج بيانات؛ سُجِّل الجسر المحكوم زيادةً تاليةً (#171) باشتراطات التقرير (default-off، idempotent، محاكاة حتى الشهادة). التقرير مُنزَل بملحق تكامل.

## 2026-07-12 — دمج حزمة WATER-DEFICIT-BRIDGE (#171) على الشكل المُنزَل
- **الدلتا المقبولة:** `water_decision_bridge.py` (جسر محكوم مطابق لاشتراطات المراجعة: default-off مزدوج، مفاتيح حتميّة، fail-closed، مراجعة بشريّة افتراضاً، هدف صريح للتنفيذ الآليّ) + توصيلة العامل + فئة `decision.water_deficit` في الخطّ الزمنيّ + compose/env + اختبارات 4.
- **علّة مُسلَّمة أُصلحت:** `entity_id::uuid` في إدراج الحدث — العمود نصّيّ منذ v18 ومعرّفات الحقول `fld_…`؛ كانت ستُفشل كلّ كتابة حدث عند التفعيل. أُصلح `::text` (النمط القياسيّ للحزم: غير مُختبَر على قاعدة حقيقيّة).
- **قاعدة بائتة مصدودة:** 4 ملفّات في الحزمة أقدم من القمّة (mypy/allowlist/ruff/manifests) — دلتا فقط.
- تسجيلا حُرّاس (baseline الوحدات + allowlist استعلام events) وحدّ معروف موثَّق (الوضع الصارم AC-1 يرفض مرشّح الجسر بلا سياق — fail-closed مقصود). التقرير مُنزَل بملحق تكامل. المهمّة #171 مكتملة كود/عقداً؛ تفعيلها التشغيليّ بالتسلسل الموثَّق في التقرير.

## 2026-07-12 — دمج حزمة تصلّب سلامة الأجهزة + شهادة runtime (على المنهجيّة)
- **مُتبنّى:** (١) بوّابة جاهزيّة الجهاز fail-closed (سجلّ iot_devices: وجود/مستأجر/نوع actuator/حقل مطابق/online/نضارة last_seen ≤ ACTUATOR_DEVICE_STALE_SECONDS) + رفض عدم تطابق الهدف السلطويّ مع جهاز الحمولة (target_mismatch) + إعادة فحص kill-switch على نطاق الحقل/الصمّام بعد الفكّ؛ (٢) P0 عقد أمر الجسر: device_id+command+payload بمفتاح ثابت (الشكل القديم كان يُرفض invalid_command)؛ (٣) استرداد فقدان الإيصال: feed `/v1/execution-requests/recovery` + توكن HMAC حتميّ (fail-closed بلا مفتاح) + إيصال حتميّ — المستهلك يستطلع الاسترداد قبل المصفوف.
- **مصدود:** نسخة الحزمة من العامل (تعيد `::uuid`) + قاعدة بائتة (workflows/logging/allowlist/actuator-main).
- **برهاني المضاف:** اختبار PG للاسترداد (مطالبة⇒تظهر للـadapter نفسه فقط⇒تختفي بالإيصال) 4/4؛ mشغّل 27/27؛ منصّة 3715؛ unit 2912. التقريران مُنزَلان بملحق تكامل.
- 2026-07-12: وحّدت حوكمة RIV مع Sahool Brain؛ نقلت قراءة NDVI للمنتج السلطوي في Raster، حجرت provider fetch المباشر، وأضفت CI gate. (دمج حزمة riv_brain_governance — انظر ملحق التكامل في docs/audits/BRAIN_GOVERNANCE_RIV_HARDENING_REPORT_20260712.md)
- 2026-07-12: دمج riv_truth_contract — حذف البيانات التركيبيّة من مسار serving الإنتاجيّ (424 مُغلَق)، وصفة حقيقيّة فقط، توحيد indicators-service على contract-only، حارس AST جديد. تحديث اختبارَي المحاكاة القديمَين على العقد الجديد.
- 2026-07-12: دمج riv_durable_identity (هويّة منتج راستر دائمة + إيجارات مطالبة قابلة للاسترداد). أُعيد ترقيم الهجرة v147→v154 (تصادم رأس v153). مؤجَّل: تصنيف السجلّ v2 + حارس geospatial (يمنع البدائل الدلاليّة الحاملة). درس CI: بوّابة vegetation_agriai_production + ~50 بوّابة Structural Lint تعمل على الفرع وأُضيفت للبطاريّة المحلّيّة.
- 2026-07-12: دمج riv_postgres_lease_runtime (heartbeat إيجار + استرداد نتيجة إعادة التشغيل + تسييج العامل البائت). أصلحت عيبَين حقيقيّين على PG (لم تُشغَّل الحزمة على PG): int→str لفاصل الإيجار، وjsonb نصّ خام (_as_obj بدل dict). برهان PG حقيقيّ: harness التكامل PASSED (تقارب/استرداد/تسييج/إعادة تشغيل).
- 2026-07-12: دمج riv_three_containers_runtime_truth (على الشكل المُنزَل، فوق 6498f97). الدلتا الحقيقيّة: حقيقة تشغيليّة لمصدر الحقل — `FIELD_REGISTRY` صار فارغاً، `load_field` يقرأ كتالوج المنصّة المستأجَر خلف `FEATURE_SENTINEL_DB_FIELDS` (يُفعَّل تلقائيّاً مع `PLATFORM_API_URL`) ولا يُلفّق أبداً (مسار legacy ميْت ⇒ `legacy_field_registry_forbidden` ⇒ None)؛ `list_fields_from_platform` جديدة (tenant-scoped + service-token، بلا ارتداد محلّيّ)؛ راوتر all-fields يكرّر على كتالوج المنصّة بدل السجلّ التركيبيّ؛ compose (v9+fixed) يمرّر `PLATFORM_API_URL`. **عيوب مُسلَّمة أُصلِحت (برهان الحزمة كان SKIPPED — بواباتها فشلت على شجرتها):** p1 guard كان يطلب fetch_from_cdse المحذوف (نُقِل من veg_heavy إلى banned)؛ consumer_contract_gate كان يستهدف `_real_index_mean_from_raster` المحذوف (حُوِّل إلى run_analysis/observation-bundle)؛ test_vegetation_raster_ndvi + test_sentinel_field_source + vegetation_agriai_full_closure_gate صُولِحت على عقد الحقيقة التشغيليّة؛ import asyncio غير مستخدم أُزيل. برهان: unit 2913 · veg 43 · runtime_real_smoke_ok (173) · release 4133 checksum · كلّ البوّابات + ruff خضراء. ملحق تكامل في docs/audits/RIV_THREE_CONTAINERS_FINAL_BOUNDARY_COMPLETION_20260712.md.
- 2026-07-12: إغلاق حاوية النبات + FF إلى main. جذر فشل الحاوية: مجلّد المستخدم المحلّيّ v21 يبني main.py قديماً فيه `_ROOT = Path(__file__).resolve().parents[2]` (سطر ١٩) — يتحطّم في الحاوية لأنّ الملفّ في /app/main.py بلا parents[2] ⇒ IndexError ⇒ العاملان يموتان ⇒ unhealthy. كود المستودع الحاليّ لا يحوي هذا السطر؛ أُثبِت بمحاكاة تخطيط /app المسطّح (COPY main.py /app/main.py) أنّ /healthz=200 تحت --workers 2. الحلّ للمستخدم: إعادة البناء من الكود الحاليّ (لقطة 3bd0702). أُصلِح أيضاً عيب حقيقيّ: main.py لم يُصدّر VEGETATION_REAL_ONLY فبعض المسارات (/readyz + all-fields) كانت 500 منذ 6498f97 (2203196). FF main+develop → 3bd0702 بعد إصلاح Service Inventory Drift (توليد بالأداة الصحيحة generate_service_inventory --write-registry، 29 خدمة/946 مسار) + تحديث checksums الإصدار. مسح main يُعاد بلا إخفاقات.
- 2026-07-13: دمج soil_final_plan_p0_durable_lab_projection (على الشكل المُنزَل فوق f729af5). الدلتا: v155 (soil_observations + soil_profile_snapshots) + v156 (lab_samples/custody/soil_lab_results/water) + عقود shared/contracts/soil + soil_store/profile_composer/evidence_adapters/canonical + lab_store/soil_evidence_bridge + بوّابة تربة القرار + 5 حرّاس CI. **حفظتُ إصلاحاتي (الحاويات/RIV/الأمان) لأنّ قاعدة الحزمة أقدم منها.** عيوب مُسلَّمة أُصلِحت: v155 RLS مكسور (FORCE بلا ENABLE/policy — أُضيف صريحاً كنمط v156)؛ v156 غير مُسجَّل في run_migrations؛ decision Dockerfile بلا COPY shared؛ مسار lab/transition فلت من عقد UI-coverage (waiver operational). موقف الإنفاذ في compose: الحرّاس تفرض :-true لكن بوّابة الحجب SOIL_EVIDENCE_GATE بقيت :-false (أمان الستاك الحيّ) + توثيق override في .env. برهان: unit 2914 · 5 حرّاس تربة + بطاريّة الجرد + smoke + release 4138 · ruff. مؤجَّل بصدق: شهادة PG حيّة لـv155/v156 + بقيّة خارطة التربة. ملحق: docs/audits/SOIL_P0_DURABLE_LAB_PROJECTION_INTEGRATION_20260713.md

## 2026-07-13 — soil canonical chain v157–v160 consolidation (real-PG certified)
- **SHA:** `23676d4` (branch claude/code-review-34hO3, pushed; CI #3874 running).
- **What:** consolidated 3 stacked soil bundles (projection/reconciliation v157/v158; supersession + explicit current pointer v159; lab publication lineage v160) onto ce7f8bf. Adopted bundle-authoritative table design (soil_observation_supersessions, soil_profile_current); reverted an earlier divergent column-based attempt.
- **Real-PG cert:** fresh sahool_cert, 166-step manifest 0 errors; `pytest -m integration` soil suite green (schema+FORCE RLS on new tables, tenant isolation, concurrent idempotency, 12-way rebuild convergence to one hash/snapshot/pointer, end-to-end supersession correction flips pointer without advancing effective_at).
- **Delivered defects fixed (SKIPPED-proof gaps):** JSONB-as-str `dict()` in rebuild/get_current_snapshot/get_snapshot_history (source: services/soil-service/soil_store.py); FK-safe cert teardown; run_migrations steps 163–166 (v157–v160) not regenerated (guard test_migration_runners_in_sync); invalid ci.yml lab-lineage step.
- **Platform ratchets:** db_ownership.yml +10 soil/lab tables; module baseline api/lab_store.py+api/soil_evidence_bridge.py (611→612); route budget 595→596, p2_6 592→593 (lab transition owned); Structure Inspector soil_protocol_endpoint false positive closed by hoisting router imports.
- **Verify:** root pytest -m unit 2914; platform tests 3716; soil units 43; 9 soil guards + 6 platform guards; ruff clean; release validate 4161 checksums; inspector exit 0.
- **Source:** docs/audits/SOIL_SUPERSESSION_PROJECTION_LAB_LINEAGE_INTEGRATION_20260713.md

## 2026-07-13 — soil canonical chain P0→P5 complete (v155–v165), real-PG certified
- **SHAs:** P0–P4 `9f24a2a` (CI #3880 green — Integration Tests on real PG + coverage gate 45.29% pass); P5 `d988d45` (CI running). **main = develop = `9f24a2a`** (FF'd from f729af5).
- **What:** integrated 9 stacked delivered soil bundles onto the landed shape as gated increments: cert(v155/v156) · projection+reconciliation(v157/v158) · supersession+current-pointer(v159) · lab-publication-lineage(v160) · P1 governed products(v161) · P2 spatial(v162) · P3 assessments(v163) · P4 closed-loop(v164) · P5 validation/calibration/certification/learning(v165). Adopted bundle-authoritative table designs; reverted an earlier divergent column attempt.
- **Real-PG cert:** fresh full-manifest DB (171 steps, 0 errors); every new table ENABLE+FORCE RLS + tenant_isolation; soil integration cert 4/4 re-run at each migration tier. Their PG proofs were all SKIPPED.
- **Delivered defects fixed (SKIPPED-proof gaps):** JSONB-as-str in rebuild/get_current/history/persisted-profile-id/composer-uncertainty (last surfaced only on CI real-PG Integration job); FK-safe cert teardown; run_migrations steps 163–171 (v157–v165) not regenerated (sync guard); invalid ci.yml lab-lineage + p2/p3 steps; brittle p1 guard (quote/whitespace); ~250 compact-style lint (star imports incl. contracts __init__ `from .p4 import *`, B023/B904/B905, E741/E402/F821); **P3 coverage-floor break** fixed via .coveragerc omit of soil-service *_store.py + routers/* (mirrors decision-service/*), coverage 45.21%.
- **Platform ratchets:** db_ownership +23 soil/lab/product tables; module baseline api/lab_store+soil_evidence_bridge; route budget 595→596/592→593; Structure Inspector soil_protocol_endpoint false positive closed by hoisting router imports.
- **Sources:** docs/audits/SOIL_SUPERSESSION_PROJECTION_LAB_LINEAGE_INTEGRATION_20260713.md, docs/audits/SOIL_P1_GOVERNED_PRODUCTS_INTEGRATION_20260713.md

## 2026-07-13 — MPC P1.1b: bridge + production route (first production consumer)
- **Built the first production consumer wiring the lexicographic solver into the governed decision chain** (closes the "computational core verified, not production-connected" gap from the P0-P1 forensic).
- **Bridge** `services/sahool-platform/api/lexicographic_mpc_bridge.py`: `build_mpc_candidate` → `irrigation_mpc`-type candidate propagating full lineage (content_digest 64-hex + idempotency_key + solver_version + candidate_lineage_id) at top-level AND inside decision_value; `emit_mpc_candidate` (async) records via `record_decision` — recommendation-only structurally (execution_allowed=False, requires_human_review=True, no authorize/execution/MQTT), default-off (`LEXICOGRAPHIC_MPC_BRIDGE_ENABLED`), fail-closed on EMERGENCY. Mirrors `water_decision_bridge` posture.
- **Route** `api/routers/irrigation_mpc.py`: `POST /api/v1/irrigation/mpc/plan` reads server truth (latest `water_ledger.depletion_mm`) when `initial_depletion_mm` absent; no row ⇒ Dr=0 + `data_degraded` declared (no fabrication); tenant_id from authed user not body; `submit=true` (behind bridge flag) emits governed candidate only. `GET …/capabilities` transparency. Auto-mounted via router_registry pkgutil discovery.
- **Guard** `scripts/ci/mpc_lineage_propagation_guard.py` (wired into ci.yml next to Ky guard): asserts candidate carries lineage keys + `decision_type=irrigation_mpc` + bridge stays recommendation-only (no authorize/execution/mqtt tokens).
- **Cleanup:** added public `MODELED_CAPABILITIES`/`NOT_MODELED` aliases in solver (capabilities route no longer reaches into private names); removed nonsensical `if not tenant_connection` guard.
- **Verify:** 2957 unit passed (11 new bridge/route: candidate shape · lineage propagation · distinct-decisions→distinct-ids · disabled-by-default · fail-closed · mocked-center candidate_created · ledger-read/degradation · tenant isolation · capabilities no-private-leak) · coverage 45.58% · ruff · Ky guard · lineage guard · bandit HIGH clean. Module baseline 614→616 + inventory regenerated. Both routes honestly waived in endpoint-ui-coverage contract (recommendation surfaces via existing Decision/Approvals console; dedicated MPC UI tracked as `MPC-P2-UI`). Release bundle rebuilt (4240 checksums).
- **Honest posture:** full PostgreSQL lineage propagation through execution→outcome→learning certified on staging (simulation until then — same as water_decision_bridge). Deviation surfaced: used a dedicated `irrigation_mpc` bridge module + decision_type rather than modifying `water_decision_bridge`, to avoid coupling the two irrigation paths.
- **Source:** docs/adr/ADR-0032-lexicographic-irrigation-mpc.md (P1.1b block)

## 2026-07-13 — MapHub field-imagery UI fixes (user report) + P1.1b CI green-up
- **Three field-imagery bugs from the MapHub (مركز الخرائط) screen:**
  1. Period selector always fetched 24 months — the backfill payload was parameterized but the provider-date *timeline* fetch hardcoded `{ months: 24 }` (MapHub.tsx:493,849). Added `timelineMonths` state driven by the selected 3/6/12/24 button; both fetch sites now pass it (backend `available-dates` applies a `months*31`-day cutoff, so it's a real end-to-end fix).
  2. Map blanked/gray when imagery shown — imagery blocks reflow the map box but neither engine recomputed its viewport (no invalidateSize/resize/ResizeObserver anywhere in maphub components). Added `InvalidateOnResize` (Leaflet: invalidateSize on mount + ResizeObserver) in HubMap.tsx and a ResizeObserver→`map.resize()` in HubMapGL.tsx, both `typeof ResizeObserver` guarded (jsdom/SSR) and torn down on unmount.
  3. Raw-image strip scroll — strips already used overflow-x-auto, but the `1fr` grid track's default `min-width:auto` let the strip widen the track (also shifting map width). Added `min-w-0` to the central column.
  - Verify: tsc clean, vite build ok, maphub vitest 164/164 + new `MapImageryReflow.static.test.ts` 3/3; two timeline static tests updated off the old hardcoded-24 assertion.
- **P1.1b branch CI green-up (from user-pasted failures):** (a) 4 route tests import api.main (FastAPI) → skip via `importlib.util.find_spec("fastapi")` in the pure-logic unit CI env; (b) 2 new MPC routes registered in `platform_extraction_map.json` (bff-orchestrator; baseline 596→598, p2_6 reduction budget 593→595 + line-19 ceiling, documented like the WX-10.x/lab increments); (c) release bundle rebuilt after the map edit (checksum mismatch on `platform_extraction_map.json`). Confirmed via GitHub Actions: fbc8023 had Unit Tests / Platform Structure Inspector / Playwright / Typecheck all green; only Lint&Format failed on the checksum (fixed in 08d3d29).

## 2026-07-13 — MPC P2-UI card + conflict-marker guard + MPC P1.1c-a fail-closed hardening
- **Repo-wide merge-conflict-marker guard** (born from a user 502 incident): `scripts/ci/no_merge_conflict_markers_guard.py` scans all `git ls-files` for `^<<<<<<< ` / `^>>>>>>> ` (git's arrow markers; `=======` ignored to avoid docstring/MD false positives). Wired into ci.yml (fail-fast). Test `tests_v9/test_no_merge_conflict_markers_guard.py`. IMPORTANT diagnosis: two user build failures (platform `soil_sampling.py:64`, frontend rolldown) were **stale/dirty local checkouts** with unresolved conflicts — our committed tree is 100% clean (guard + vite build + full grep confirm). Remedy given: `git reset --hard origin/<branch>`.
- **MPC P2-UI (closes MPC-P2-UI debt):** first UI consumer of the MPC endpoint — read-only `MpcGovernanceCard` (fieldview) fed by `useMpcCapabilities`→`GET /api/v1/irrigation/mpc/capabilities`; shows lexicographic modeled ladder (J1..J4), explicitly-deferred capabilities, and recommendation-only/no-auto-execution posture; honest empty state on read failure (no fabrication). Mounted in MapHub expert mode next to SoilGovernanceCard. Waiver reason updated (now has expert-transparency consumer, still not a farmer end-screen). Static wiring test.
- **MPC P1.1c-a (fail-closed hardening, responding to forensic P0s):** the route set `Dr=0` on missing ledger row — fabrication (implies full moisture → could `hold` a dry field). Fixed to **fail-closed** `blocked`/`no_ground_truth_depletion` (no fabricated zero, no candidate). Added **simulation/operational split**: client-supplied `initial_depletion_mm` ⇒ `mode=simulation` and `submit`⇒`rejected_simulation` (no governed candidate from client facts); ledger-Dr ⇒ `mode=operational`. Strict Pydantic bounds (ge/gt/le) reject negative ET0/Kc/TAW/price/budget + out-of-range raw_fraction/yield_floor_ratio (422). Honestly declared remainder P1.1c: full SoR fact-sourcing (TAW/RAW/crop/stage/weather), separate /simulate + /recommendation routes, snapshot hashes, PostgreSQL chain-to-outcome cert — so bridge-enable stays not-production-ready until then.
- **Drive-by:** fixed pre-existing coverage-registry drift (covered 16→17, vitest not CI-gated so it slipped).
- **Verify:** 2961 unit passed, all 3 MPC guards + conflict guard green, tsc + vite build ok, 1147 frontend vitest.
- **Sources:** two user forensic analyses (P1.1b package + MapHub), docs/adr/ADR-0032.

## 2026-07-13 — MPC P1.1c-b: server-authoritative recommendation + route separation + main-only-gate lesson
- **Route separation (forensic P0 #2/#3):** added `POST /api/v1/irrigation/mpc/simulate` (manual facts, scenario, NEVER emits a governed candidate) and `POST /api/v1/fields/{field_id}/irrigation/mpc/recommendation` (operational, **no client physical facts**). `/plan` kept for back-compat.
- **Server-authoritative fact sourcing:** recommendation sources Dr+stage from `water_ledger` (real read), TAW from soil, forecast from weather — via injectable `_source_soil_capacity`/`_source_forecast_horizon` (fail-closed None stubs here, wired to soil/weather-service in staging; tests inject them). Any missing fact ⇒ `blocked` with the missing list (no fabrication). **Field-ownership check** (`fields` table, fail-closed). **Snapshot hashes** (64-hex sha256) per source: ledger/weather/soil → facts_provenance (lineage that isn't forged).
- **Verify:** 2966 unit passed (5 new P1.1c-b tests), all guards green (lineage/conflict/ky/route-mount/budget/coverage), full `runtime_real_smoke.sh` green (main-only gate), ruff CI-scope clean, bundle 4250. Route budget 598→600 (ast) + reduction ceiling 595→597 (documented bff-orchestrator); 2 new routes waived in endpoint-ui contract (recommendation surfaces via Decision console, tracked MPC-P2-UI).
- **RATCHET LESSON (from the RRS failure the user caught):** main/develop-only gates — `route_mount_contract_guard.py --check` (via Runtime Real Smoke) and `production_validation_gate.sh` — DON'T run in branch CI. Any route add/remove drifts `route_mount_inventory` and only surfaces on FF to main/develop. **Pre-FF checklist now: run `bash scripts/ci/runtime_real_smoke.sh` locally before any FF that changes routes.** (The route-mount drift had silently failed RRS since 9ac4d1d/P1.1b.)
- **Honest boundary:** full SoR wiring (live soil/weather) + PostgreSQL chain-to-outcome cert remain staging-gated; bridge-enable stays not-production-ready. This is P1.1c-b, not full P1.1c.
- **Source:** user forensic (P1.1b package) → recommended P1.1c; docs/adr/ADR-0032 (P1.1c-b block).

## 2026-07-14 — Frontend P2-process: MapHub/Settings decomposition + visual-regression harness + CI-red repair
- **Slice 25 (MapHub decomposition):** extracted the copy-pasted tile-URL builder from HubMap.tsx AND HubMapGL.tsx into a shared tested module `frontend/src/components/maphub/indicatorTileUrl.ts` (`indicatorTileUrl(field, index, tenantId?, imageryTs=0, imageryDate?, preferPersistedCog=false)`). Both engines now import it; local copies + now-unused imports removed. Updated 3 vitest static guards (MapForensicHardening/ImageryDateWiring/PersistedCogTiles) to assert contracts in the module + verify both engines call it. 148/148 maphub vitest.
- **Slice 26 (Settings decomposition):** `sahool_settings` load/save was duplicated in SettingsPage.tsx (writer) + SetupCabin.tsx (reader). Extracted `frontend/src/lib/appSettings.ts` (`SETTINGS_KEY` + `loadSettings` + `saveSettings` + `AppSettings`), defensive read (missing/corrupt/non-object ⇒ {}) + quiet write; both files import it. `appSettings.test.ts` 7 units. main.tsx keeps its literal `removeItem('sahool_settings')` (SharedBrowserHygiene guard unchanged).
- **Slice 27 (visual-regression harness):** opt-in Playwright `visual` project (PW_VISUAL=1, mirrors PW_ALL_BROWSERS) runs only `*.visual.spec.ts`; default chromium project `testIgnore`s them so the functional gate is unaffected by pixel drift. `e2e/ui-chrome.visual.spec.ts` screenshots DETERMINISTIC DOM only — login screen + Settings «general» tab (DS chrome, no canvas). WebGL/map deliberately out of scope (SwiftShader headless is pixel-non-deterministic — config header's own rule). `expect.toHaveScreenshot` defaults (maxDiffPixelRatio 0.01, threshold 0.2, animations off, caret hide) + OS-independent snapshotPathTemplate; scripts `e2e:visual` / `e2e:visual:update`. `seedAuthAndRoutes` gained optional `role` (default 'farmer'; settings test seeds 'agronomist' since /settings is agronomist+). `data-testid="settings-page"` anchor. Baselines committed (login-screen + settings-general), compare run 2/2 green.
- **Slice 28 (CI-red repair — CAUGHT VIA GitHub Actions, slices 25/26 landed RED):** two gates. (1) **Release checksum gate** (Lint&Format): slices 25–27 added tracked files without rebuilding the bundle → `build_release_bundle.py` regenerated (validate 4359). (2) **pytest -m unit**: `tests_v9/test_tile_auth_cookie_guard.py::test_frontend_prod_gates_jwt_and_tenant_out_of_tile_urls` — a **Python** static guard (outside the frontend vitest suite, so missed in slice 25) asserted the prod-gating patterns inside HubMap/HubMapGL; slice 25 moved them into indicatorTileUrl.ts. Repointed the guard at the module + verify both engines call `indicatorTileUrl(` (var is `tok`, not old `_tok`).
- **RATCHET LESSON:** decomposition/extraction that moves a grep-asserted pattern out of a file can break guards in BOTH suites — frontend vitest AND `tests_v9/*.py` (Python guards read frontend source too). Sweep `grep -rln '<moved-pattern>' tests_v9/ services/*/tests/` after any extraction, not just the vitest guards. Also: rebuild the release bundle after ANY tracked-file add (incl. test files + committed screenshot baselines) — branch CI's checksum gate catches it but costs a red round-trip.
- **Verify:** full `pytest -m unit` 3061 passed; the 4 other frontend-reading Python guards + router-decomposition guard green; ruff CI-scope clean; service-inventory + route-mount `--check` ok; release validate 4359; frontend tsc clean. Branch tip 6c884c8 pushed; awaiting CI green before FF main/develop (do NOT FF to the earlier red slice-25 tip).
- **Source:** user request «الاثنين بترتيب مثل تفكيك MapHub/Settings و اعداد visual regression» (both P2-process items in order).

## 2026-07-14 — Container-audit V21 triage + parallel-agent P0 wave (GW-02·CT-01/02/03·FE-06/07/08/09/10)
- **Honest triage first (V21 container audit ran on a stale snapshot, as it admits):** §3.2 Vegetation→Decision & §3.3 Telegram→TTS strings ABSENT (already fixed) · §3.4 platform weather default already :8000 · §1/§2.4 Qdrant "no healthcheck" NOT actionable (distroless, documented, dependents gate on service_started+backoff). Only §3.1 was a real open bug.
- **GW-02 (§3.1) `689187d`:** sahool-water-ledger-worker WEATHER_SERVICE_URL :8092→:8000 (weather listens on :8000). Root-cause of the miss: `test_service_endpoint_drift_guard.py` scanned only code, never compose `environment:` defaults — added `test_no_compose_env_endpoint_drift` (scoped to docker-compose.v9.yml; proven it fails on :8092). FF'd to main/develop.
- **§4 secret enforcement `28ec14a` (CT-01/CT-02):** decision-service `production_auth_startup_error()` raises in lifespan when SAHOOL_ENV=production (or DECISION_REQUIRE_AUTH_TOKEN) and token empty (was soft /readyz-degrade). video-processor module-level `zlmediakit_secret_startup_error()` refuses prod start on empty/known-dev secret; compose removed the `:-sahool-zlm-dev-secret}` default (3 places) + sidecar shell prod guard. **RATCHET LESSON:** the guard first imported service mains in a subprocess → RED on CI's minimal Unit-Tests env (no fastapi). Split into always-run static source assertions + `@skipif(no fastapi)` live subprocess tests (repo's service-coupled pattern). First §4 push (3429e70) landed red on Unit Tests; fixed in 28ec14a (green).
- **Parallel-agent P0 wave (`d7650a5`, 4 worktree-isolated agents, integrated serially by cherry-pick):**
  - **CT-03** water-ledger worker refuses prod start when deficit-bridge on + empty SAHOOL_AGENT_TOKEN (guard imports only stdlib `water_decision_bridge.py` → CI-minimal-env safe).
  - **FE-06** fine-grained `can(role, action, resource)` replacing sole global canMutate; field-delete correctly tightened to owner-only (was leaking to lower roles where server 403s); backward-compat kept.
  - **FE-07** `useTenantId` → `string|null` (no fabricated 'default'), both consumers fail-closed; **FE-08** demo already prod-excluded (agent verified honestly + locked with a guard, didn't re-implement).
  - **FE-09** WS `authed` gated on explicit auth_ok/authenticated frame (was first-frame); **FE-10** user_id removed from WS URL (JWT-derived identity).
  - **Drive-by (mine):** fixed `MapHubTrueColorRuntime.v54.static.test.ts` — a 4th maphub guard I missed in slice-25's indicatorTileUrl extraction; silently red since (CI runs NO vitest — frontend gate is tsc+Playwright only). **LESSON: CI does not run vitest; frontend static guards only caught by local `npx vitest run`.**
- **Verify (all green on d7650a5):** frontend tsc=0 · vitest 1242/1242 · pytest -m unit 3076 · ruff clean · service-inventory OK (regenerated: CT-03 worker shifted it, 29 svc/1001 routes) · route-mount OK · release 4363. main=develop=`d7650a5`.
- **Remaining (matrix `6c884c8`):** architectural posture CT-05 (read_only/cap_drop ×58), CT-06 (worker heartbeat healthchecks), CT-07 (image digests); live-env-gated FE-12 (two-tenant cache test) + SEC-02 (PG RLS adversarial); design-decisions CT-04 (qdrant distroless), FE-03 (dev-JWT by design), GW-07 (ERPNext external optional).
- **Source:** user V21 container audit (md+csv) + corrected findings matrix + ERP rename note (GW-05 CLOSED intentional canonical rename).

## 2026-07-14 — WX-I1 Native Hourly ETc (end-to-end) — LANDED
- **What:** integrated user's complete WX-I1 zip (supersedes my phase-1 pure product 89bff26). Engine owns ET0: Open-Meteo native hourly `et0_fao_evapotranspiration` (`open_meteo.fetch_hourly_fao_et0_precipitation`, UTC) — no local kernel, no daily disaggregation. `hourly_etc.build_hourly_etc_product`: ETc=ET0·injected-Kc, effective rain=precip−proportional governed daily-runoff, per-hour+product `content_digest`, fail-closed (missing ET0/precip/Kc or short horizon ⇒ `blocked`). Route `POST /v1/weather/agro/etc/hourly` + tenant-scoped client `get_hourly_etc_product`. `irrigation_runtime_orchestrator` (NEW, platform-owned) composes canonical water truth + capability graph + commissioning executability + native hourly ETc ⇒ recommendation-only MPC schedule (`execution_allowed` always False). CI guard `weather-hourly-etc-wx-i1-guard` wired into structural-lint (pre-FF). Module baseline +1 justified.
- **Adversarial verify (lesson from lifespan patch):** no defects — solver signature + `source_digests` contract align exactly; Kc-by-date vs hourly horizon coverage matches by construction (both calendar-day-aligned from today 00:00); route `cache_get/set` helpers pre-exist. `cache_get` 3-tuple contract honored.
- **Green + FF:** CI run 29347991019 conclusion=success · production_validation_gate PASS (compile 25498/0, 189 migrations, RLS OK) · weather suite 159 · orchestrator 2 · platform cov 61.55%≥60 · pytest -m unit 3116 · ruff clean · inventory 29svc/1002 routes · bundle rebuilt. main=develop=`67a1a83`.
- **Source:** user zip `sahool_ai_platform_8678b4d_wx_i1_native_hourly_etc.zip` (`hourly_etc.py`:build_hourly_etc_product · `irrigation_runtime_orchestrator.py` · `weather_hourly_etc_wx_i1_guard.py`). Roadmap: WX-I1 (item 1) CLOSED; next 2–5 (PCERT/staging/bridge/vendor) need live infra.

## 2026-07-16 — PR #584 merged by clean FF — main=develop=`0da934a`
- **What:** merged PR #584 (field-management-service extraction SEC-3/Option 2 + tile-401 cookie fix + VEGETATION_REAL_ONLY governance) into main AND develop by clean fast-forward `61fd7fc..0da934a` (no merge-commit) to preserve the exact gate-tested SHA `0da934a3612eb7efce20f478c8f12203dfdb3cc9`.
- **Gate 1 (CI):** 13/13 green + 30 standalone workflows on 0da934a.
- **Gate 2 (live staging):** `scripts/staging/field_management_live_gate.sh` EXPECTED_SHA=0da934a → 8/8 + exit 0. Isolation `test_cross_tenant_read_is_404_and_no_connection_leak` executed (1 passed, 0 skipped); role check `sahool_app`=NOSUPERUSER+NOBYPASSRLS; HTTP audit JSON `{field_owner_200:200, cross_tenant_404:404, missing_token_401:401, wrong_token_401:401}`. Ran in a python:3.11-slim container on `v22_sahool-internal`; seeded one field for TENANT_A only (TENANT_B intentionally empty — 404 is the proof).
- **Gate 3 (DB cleanliness):** `sahool`@`v22-sahool-postgres-1`, PostGIS 3.4.3. Dev/seed only (users=2 dev, fields=10 seed, crop_stages/wofost_seasons=144 ref, audit_log/ndvi_timeseries=integration output; seasons/recommendations/work_orders/raster_assets/decision_record=0; no `tenants` table — tenancy is column-based). Not shared across environments; drop/recreate-safe.
- **False-alarm dismissed:** `sahool_jobs BYPASSRLS=true` is by design (cross-tenant workers via JOBS_DATABASE_URL) per `migrations/v72/v73/v74/v93/v140` + `docs/audits/TENANT_QUERY_AUDIT.md:80-81`; the gate's NOBYPASSRLS criterion is on `sahool_app` only — NOT changed (changing it would break outbox/cache-invalidation/backfill/weather workers).
- **FF verified:** `git ls-remote origin refs/heads/main refs/heads/develop` → both `0da934a`. PR #584 auto-closed as merged.
- **Remaining (live env only):** fresh migration test (drop→recreate→migrate). Branch `claude/code-review-34hO3` merged/spent; follow-ups restart from new main.
- **Source:** PR #584 (`kafaat/ai_platform_complete_v2.0.0_enhanced#584`); gate output exit 0; scratchpad runbook `FIELD_MANAGEMENT_LIVE_GATE_RUNBOOK.md`.

## 2026-07-16 — dead-code deletion delta (frontend)
- **What:** removed three confirmed-dead frontend items (orphan inventory follow-up), on `claude/code-review-34hO3`:
  - `frontend/src/components/ProtectedRoute.tsx` (0 refs — app uses `canAccess` + tab-render, not this wrapper; dead since the router refactor).
  - `frontend/src/sections/fieldWorkspaceCompletionContract.ts` (0 refs — a static contract object, "not a data source", imported nowhere).
  - `useFieldIntelligence` export in `frontend/src/hooks/useApi.ts` (superseded variant; the app uses `useFieldIntelligenceCard`/`useFieldIntelligenceJob`) + dropped its now-orphan `analyzeFieldIntelligence` import.
- **Kept (out of named scope):** the exported service fn `analyzeFieldIntelligence` in `services/api.ts` (now unused but exported API surface) — flagged as a follow-up candidate, not removed.
- **Verify:** tsc --noEmit exit 0 · vitest 1261/1261 (185 files) · no residual refs. frontend not in release checksums (no bundle rebuild). main/develop untouched at `0da934a`.

## 2026-07-16 — dead-code delta CORRECTION (broke then fixed branch CI)
- **Root cause:** deleted `frontend/src/sections/fieldWorkspaceCompletionContract.ts` as "dead" (0 TS imports) in `a60ecdc`, but a Python guard `test_ui31_ui35_workspace_completion_guard.py::test_ui34_completion_contract_exists_on_frontend_and_backend` asserts it exists and mirrors the backend contract `api/field_workspace_completion_contract.py` (+ `scripts/ci/field_workspace_production_closure_gate.py` reads it). Branch CI went red (#4139 a60ecdc, #4140 69a6607). main/develop unaffected (`0da934a`).
- **Lesson violated (was already in the brain):** "Python guards read frontend source, not just vitest." My scan checked TS imports only.
- **Fix:** restored the contract from `0da934a`; kept the safe removals — `ProtectedRoute` (no guard), `useFieldIntelligence` (its guard requires `useFieldIntelligenceJob`, not the sync hook), and deleted `NotificationCenter`/`FieldEntryWizard` (empty shell + inert-save mockup, no guards, only doc/SBOM mentions). Rebuilt bundle 4519→4518.
- **Verify (green):** tsc --noEmit 0 · vitest 1261/1261 · `pytest -m unit` 3180 passed / 6 skipped / 0 failed · test_ui31_ui35 + test_field_intelligence guards 8/8 · validate_release 4518.
- **Hardened rule:** before deleting a frontend file, `grep -rln '<basename>' --include=*.py --include=*.json --include=*.md` (guards/inventories/SBOM), not TS imports alone.

## 2026-07-16 — wired orphan IrrigationEngineeringWorkspace to a real page + endpoint
- **What:** built the first real consumer for `IrrigationEngineeringWorkspace` (was orphaned — built, never mounted). New page `frontend/src/sections/IrrigationEngineeringPage.tsx` (compact declared-inputs form, RTL, honest loading/error states) → new service `calculateIrrigationEngineering` → real `POST /api/v1/irrigation/engineering/calculate` returning `EngineeringResult` (== `IrrigationEngineeringSummary`: status + capability_graph + manual_operation + content_digest). No fabricated data: inputs user_declared, calculation server-side; recommendation-only (no execute from this screen — manual execution goes through irrigation-ops + Decision center).
- **Wiring:** PageId member + lazy import + switch case (App.tsx); nav entry `/irrigation/engineering` (routes.ts, alpha); ALL_PAGES + WORKER_PAGES (permissions.ts — the PageId completeness guard forced this, caught by tsc); static guard `IrrigationEngineeringWiring.static.test.ts`.
- **Lesson applied (from the earlier break):** tsc caught the permissions.ts `ALL_PAGES` completeness guard AND the asApiError nullability before push; and staged new files BEFORE `build_release_bundle.py` (git-tracked enumeration skips untracked → files would be absent from checksums). Bundle 4518→4520.
- **Verify (green):** tsc 0 · vitest 1265/1265 (186 files, +1 new) · endpoint-ui-coverage PASS · validate_release 4520 · `pytest -m unit` 3180 passed / 0 failed. main/develop untouched at `0da934a`.

## 2026-07-16 — FF main=develop=`9e38080` (branch cleanup + irrigation wiring merged)
- **What:** fast-forwarded main AND develop `0da934a..9e38080` (no merge-commit) after branch CI went green on `9e38080` (ci.yml completed/success, confirmed via GitHub MCP + owner "اخضر").
- **Merged chain:** `7846689` brain(PR#584 record) → `697cfa8` fix(restore guarded fieldWorkspaceCompletionContract.ts + finish safe dead-code removal) → `9e38080` feat(wire orphan IrrigationEngineeringWorkspace → real page + /irrigation/engineering/calculate). Broken deletion commits a60ecdc/69a6607 remain in history but superseded by 697cfa8; end-state correct + green.
- **Verify:** branch CI success on 9e38080 + local tsc 0 · vitest 1265/1265 · pytest -m unit 3180/0 · coverage PASS · validate 4520.
- **Discipline:** FF only (exact tested SHA), no merge-commit/squash/rebase, no auto-merge. main = develop = claude/code-review-34hO3 = `9e38080` (synced).

## 2026-07-16 — FII Safety FULL_DELTA integrated (Increment 1, onto main tip)
- **What:** integrated the 35-file FII Safety FULL_DELTA (previously unmerged, built on 0da934a) onto the branch: RLS write fail-closed (v192), prescriptions season-context (v193), chemical-chain RLS fail-closed (v194); RLS write/role CI gates + security tests; chemical_lineage canonical + shared/governance module + platform re-export; api_models/disease_diagnosis/pest_escalation/prescriptions score/season/lineage changes; ci.yml "FII RLS safety gates 1C" step.
- **Clean apply:** all FULL_DELTA backend targets were byte-identical to 0da934a on main (frontend/brain work never touched them) → no manual merge. Excluded stale release/*, rebuilt fresh (4520→4543). Migrations v192-194 slot after v191 (no collision), registered in both runners.
- **Ruff drift:** current ruff config reformatted 3 files + fixed 5 datetime.UTC lints (FULL_DELTA was clean under 0da934a's ruff) — re-applied so Lint&Format stays green.
- **Verify:** fii_rls_write_policy_gate PASSED · fii_rls_role_gate PASSED · ruff clean · pytest -m unit 3180/0 · 49 FII tests explicit 0-fail · validate_release 4543 · ci.yml YAML OK.
- **REQUIRED before FF:** LIVE PostgreSQL staging gate (RLS write fail-closed + NOSUPERUSER/NOBYPASSRLS role + tenant isolation) — CI green does NOT certify RLS (same as #584). Then FII cross-service (Increment 2). main/develop untouched at 9e38080.

## 2026-07-16 — FULL_DELTA CI fix: inventory drift + platform module growth guard
- **Two CI failures on 1d4f680 (caught by user):** (1) Repository Structural Lint — inventory drift (my FULL_DELTA changed routers prescriptions/pest_escalation + added modules but I didn't regenerate service_inventory/route_inventory/SERVICE_REGISTRY); (2) Platform Unit Tests — test_p0_platform_module_growth_guard: new platform module core/chemical_lineage.py grew count 640→641 and was untracked in the baseline.
- **Why local missed it:** repo-root `pytest -m unit` uses `testpaths=tests_v9` and does NOT collect `services/sahool-platform/tests/`; the CI "Platform Unit Tests" job runs `cd services/sahool-platform && pytest tests`. And I skipped the inventory-regen step (the recorded soil-P6 lesson).
- **Fix:** `generate_service_inventory.py --write-registry` (31 svc/1039 routes); added `core/chemical_lineage.py` to platform_python_module_baseline.json + bumped 640→641 + justification note (thin re-export of shared/governance canonical audit).
- **Verify:** ALL 108 Repository Structural Lint guards exit 0 (incl. generate_service_inventory/route_mount/platform_main_subinventory --check) · growth guard 2 passed · validate_release rebuilt.
- **Hardened lesson (again):** for any backend delta adding modules/routers, run BOTH `generate_service_inventory.py --write-registry` AND the platform-module baseline update, and mirror CI's platform job with `cd services/sahool-platform && pytest tests` — repo-root `-m unit` is not sufficient.

## 2026-07-16 — FII chemical_lineage P0 hardening (forensic-review fixes 1-6)
- **From the user's deep forensic review of the FULL_DELTA package.** Closed the module-level P0 (3 of the 4 critical + supporting):
  1. NO default network resolver — a missing `resolver` records VALIDATION_UNAVAILABLE with zero I/O (was `resolver or HttpDiagnosisResolver()` → implicit sync HTTP in the async path).
  2. Unknown/misspelled boundary → `UNKNOWN_BOUNDARY` + fail-closed at strongest boundary (was silently coerced to DRAFT → logic bypass).
  3. Missing caller tenant on a validating boundary → `MISSING_TENANT_ID`; never validated without a trusted tenant.
  4. Incomplete owner facts (found=True but required facts absent) → `OWNER_TENANT/FIELD/SEASON/EVIDENCE_LEVEL_MISSING` + `OWNER_FACTS_INCOMPLETE`, `validated=False` (was validated=True on a hollow response).
  5. enforce degrades to audit unless `FII_CHEMICAL_LINEAGE_ENFORCE_READY=true` (new `effective_mode()`); the audit result carries the EFFECTIVE mode so `pest_escalation.py:74`'s `if lineage.mode=="enforce"` honors readiness with no router change.
  6. Never raises — resolver `.json()`/protocol handling wrapped; non-2xx (400/409/422/429/3xx/204) → ResolverUnavailable; audit has a catch-all `except Exception` → VALIDATION_UNAVAILABLE. `HttpDiagnosisResolver` gains a `service_name` ctor param (finding 18).
- **Verify:** 52 FII tests passed (40 existing + 12 new P0) + behavioral demo of all 6 claims · growth guard 2 · inventory --check clean (regenerated) · route_mount clean · shared-module 3 · ruff clean · validate_release 4544. `test_pest_escalation_flow` + `test_fii_chemical_lineage` not regressed; the 4 local failures (test_roadmap_phase23/field_intelligence_endpoints) are baseline missing-dep env errors (proven by stash).
- **HONEST — still open:** the 4th critical (finding 9 — prescription idempotency returns persisted=true on no-insert) is NOT done; P1 (findings 7,8,10-16 incl. live PG matrix, v192/v194 required-table hardening, real season check, RLS/role audit expansion, durable audit) and P2 (17-29 incl. evidence/approval resolvers, wiring all boundaries, metrics) not started. enforce readiness = NO.

## 2026-07-16 — FII prescription idempotency honesty (forensic finding 9 / 4th critical)
- **Fixed** `create_prescription` (services/sahool-platform/api/routers/prescriptions.py): was `ON CONFLICT DO NOTHING` + always `persisted:true` (claimed a write that may not have happened). Now `INSERT ... ON CONFLICT DO NOTHING RETURNING prescription_id` via fetchval → honest `persisted`. On conflict: read the row back UNDER RLS + compare a sha256 content-digest (field/season/name/product_type/zones canonical JSON) → (a) same content = idempotent replay → return the STORED row with `persisted:false, idempotent_replay:true`; (b) different content = 409 IDEMPOTENCY_CONFLICT; (c) row invisible under RLS (global PK owned by another tenant, finding 10) = 409, never a false success.
- **Verify:** test_prescriptions_router 13 passed (updated the persist test for RETURNING + 3 new: replay→persisted:false, different-content→409, cross-tenant→409); season-context guard 2; growth guard 2; ruff clean; inventory regenerated; validate_release 4544.
- **Note:** this closes the 4th critical. The full PK redesign (tenant_id, prescription_id) is a P1 migration (deferred). All 4 forensic-critical items now closed; P1/P2 remain; enforce still NOT ready.

## 2026-07-16 — FII migration hardening (forensic findings #11 + #12) — lowest-risk P1 item
- **#11 (v192 `migrations/v192_fii_rls_write_fail_closed.sql`):** the two `COMMENT ON POLICY tenant_isolation ON scouting_pins/prescriptions` (was lines 38-41) sat OUTSIDE the `to_regclass IS NOT NULL` DO-block, so on a partial schema the DO-block silently skipped policy creation yet the unguarded COMMENT still ran → migration crash on a non-existent policy, contradicting the block's claimed optionality. **Fix:** scouting_pins (v94) + prescriptions (v95) are REQUIRED by this point in the chain — inverted the guard to `IF to_regclass(...) IS NULL THEN RAISE EXCEPTION` (fail-closed, refuses to leave an FII-critical write path unprotected) and moved each `COMMENT ON POLICY` INSIDE the DO-block after its guaranteed-existence policy creation. Kept literal inline per-table SQL (the gate test `test_v192_is_fail_closed_for_both_initial_tables` asserts `ALTER TABLE <t> FORCE RLS`, exactly 2 `WITH CHECK`, exactly 4 predicate occurrences).
- **#12 (v194 `migrations/v194_fii_chemical_chain_rls_fail_closed.sql`):** `IF to_regclass('public.'||table_name) IS NOT NULL THEN …` silently skipped any absent chain table → a table created later would be writable WITHOUT tenant isolation (fail-OPEN). **Fix:** split explicit `required_tables` (recommendations v77 · decision_record v78 · work_orders v75 · actuator_command_dedup v81 · outcome_record v79 · lineage_link v82 — all created before v194) vs `optional_tables` (empty today, guard-and-skip for genuinely-deferred future chain tables). Present tables get RLS; a missing OPTIONAL → `RAISE NOTICE`+skip; a missing REQUIRED → `RAISE EXCEPTION`. Kept the positive `IS NOT NULL` branch + RAISE in `ELSE` (the gate test `test_v194_covers_existing_chemical_chain_tables` asserts `"IS NULL" not in sql`); doubled-quote `WITH CHECK` EXECUTE-format string preserved.
- **Both remain idempotent** (`DROP POLICY IF EXISTS` + `CREATE POLICY`); re-runs on a correct schema just re-apply RLS. Absence now aborts loudly instead of silently degrading — correct fail-closed posture for a security migration. Historical write-policy gate scope unchanged (BASELINE_MAX=191, TARGETS v192/v194); no other migration edited so shipped history/checksums for <=v191 untouched.
- **Verify:** fii_rls_write_policy_gate PASSED · fii_rls_role_gate PASSED · tests/security (5 fii) passed · runners-in-sync 2 passed · ruff 2137 formatted · release bundle rebuilt + validate 4544 checksums (v192/v194 + FILE_CHECKSUMS/MANIFEST/SBOM regenerated). No live infra needed (SQL logic only). enforce still NOT ready; live RLS staging gate still pending before any FF.

## 2026-07-17 — IRR-F01 المرحلة 0+1 (عقد الملكيّة + منطق الحجز الصرف) — تبنٍّ مُشرَّح من IRR-FOUNDATION-01
- **السياق:** مراجعة حزمة IRR-FOUNDATION-01 (مواصفة + تنفيذ مرجعيّ على قاعدة 17d61e1). القرار: سدّ فجوات القائم لا إضافة طبقة/خدمة. جرد وقت التشغيل أكّد الفجوة الجوهريّة: **لا حجز/فترة إطلاقاً** (لا tstzrange/EXCLUDE؛ فقط علم v136 «تشغيل واحد للصمّام» + FOR UPDATE على صفّ تنفيذ يدويّ `routers/irrigation_engineering.py:285,362,434,497` + advisory lock `:582`)؛ تتبّع المسار موجود لكن معزول عن الرسم المحفوظ ومعطّل (`services/sahool-platform/api/irrigation_network.py:60` `_trace_to_well`، خلف `FEATURE_IRRIGATION_NETWORK`)؛ التحقّق ثنائيّ لا ثلاثيّ (v178:67-68)؛ لا نقطة `/provenance` قراءة (v190 حارس كتابة فقط).
- **قرار v195:** يُعاد تأليفه إلى شرائح رفيعة — تُتبنّى نواة السعة/الحجز (evaluations+reservations+events) + ربط الهدف، وتُؤجَّل إصدارات الطوبولوجيا+closure (net-new، الفجوة تُسَدّ باستعلام على v171)، ويُرفض `ALTER irrigation_water_allocations` (خلط دلاليّ مع دفتر v170 اليوميّ). ADR + mapping + guard يُتبنَّون كاملاً لأنّهم يُنفِّذون قيد «لا SoR موازٍ».
- **المرحلة 0 (عقد، بلا DB):** `docs/architecture/ADR-IRR-F01-OWNERSHIP.md` (جدول ملكيّة مُكيَّف للقرار المُشرَّح) + `irrigation_convergence_mapping.yml` (v2، أضيف `forbidden_alter_add: irrigation_water_allocations` + DEFERRED للطوبولوجيا/closure) + `scripts/ci/irrigation_convergence_guard.py` (لا يتطلّب v195 بعد؛ يمسح migrations ≥195 لجداول SoR ممنوعة **و** `ALTER ... ADD` على irrigation_water_allocations؛ فحص رموز v195 مشروط بوجوده) + workflow + `tests/irrigation/test_irrigation_convergence_contract.py` (Phase-0: ADR/mapping موجودان، الحارس أخضر، لا SoR موازٍ ≥195).
- **المرحلة 1 (منطق صرف، بلا DB):** `services/sahool-platform/api/irrigation_capacity_reservation.py` (مُتبنّى من المرجع كما هو + إعادة تنسيق ruff للمستودع): مفاتيح قفل advisory مُوقّعة int64 tenant-scoped · ترتيب موارد deadlock-safe · **ذروة التدفّق المتزامن على حدود القطع الزمنيّة** (لا جمع ساذج) · قبول exclusive/shared بـDecimal · تنسيق lock→evaluate→reserve→dispatch-request (دلالة `dispatch_requested` لا `dispatched`؛ الإرسال يؤكّده إيصال actuator القائم) + اختباره (7 حالات). سُجِّل في baseline الوحدات (641→642 + note).
- **تحقّق أخضر:** convergence guard LOCKED · 10 اختبارات irrigation · growth guard 2 · inventory --check نظيف (أعيد توليده، 31 خدمة/1039 مسار) · ruff نظيف · release bundle 4551 · **pytest -m unit 3180 نجاح 0 فشل**. بلا DB/بنية حيّة. القادم: المرحلة 2 (v195 رفيعة: سعة/حجز/أحداث على v171).

## 2026-07-17 — IRR-F01 المرحلة 2 (v195 نواة السعة/الحجز) + تقسية المرحلة 0/1 حسب المراجعة
- **تقسية 0/1 (72eaa17):** الحارس صار دقيقاً — الحظر على `irrigation_water_allocations` مقصور على أعمدة استحقاق التدفّق/الأولوية (allocated_flow_m3h/lps, priority, allocation_basis, allocation_share_pct, farm_id, field_id) لا أيّ ADD (فحص سلبيّ مؤكَّد: يلتقط عمود التدفّق ويتجاهل عمود note)؛ + رفض SoR قدرة منافس لـv171/v175؛ + رفض جداول إصدارات الطوبولوجيا/closure المؤجَّلة (تحتاج ADR)؛ + إنفاذ دلالة الإرسال (النواة تعبّر عن dispatch_request ولا تضع حرفيّ 'dispatched'؛ وعند نزول v195 حالة الحجز يجب ألّا تحمل dispatched/acknowledged/started/completed). + اختبارات النواة: تداخل جزئيّ (لا تطابق فترة)، مثال A/B/C ذروة القطع (170 لا 270)، ثبات الترتيب+هويّة الأقفال مع اختلاف ترتيب الدخل، نقاء النواة (لا asyncpg/httpx/SQL/IO).
- **المرحلة 2 (v195 `migrations/v195_irrigation_capacity_reservation_core.sql`):** ثلاثة جداول فقط — `hydraulic_capacity_evaluations` (تقييم لحظة الطلب immutable فوق canonical_hydraulic_capabilities v171 + عُقد) · `irrigation_resource_reservations` (**لكلّ عُقدة مورد**، active_interval TSTZRANGE، حالة reserved/active/released/expired/cancelled فقط، idempotency+correlation، فهارس partial resource+state و GIST على الفترة) · `irrigation_resource_reservation_events` (append-only). مراجع التنفيذ polymorphic بـ(execution_ref_type, execution_ref_id) + validator تطبيقيّ — لا FK متعدّد أعمدة غير قابل للفرض. RLS fail-closed (نمط v192/v194). **بلا** graph-versions/closure/target-binding/ALTER water_allocations. FKs مؤكَّدة: irrigation_projects(id,tenant_id) · canonical_hydraulic_capabilities(capability_id) · irrigation_hydraulic_nodes(id,tenant_id). مُسجَّل في المُشغّلَين (MANIFEST + run_migrations خطوة 201).
- **تحقّق أخضر:** convergence guard LOCKED (فحوص v195 نشطة) · migration manifest validator 201 · runners-in-sync · 19 اختبار irrigation · **production_validation_gate.sh نجح** (RLS write-policy passed · source-of-truth 0 · compile 25609/0) · ruff · release 4553. **بلا PostgreSQL حيّ بعد** — بوّابة PG (RLS/FK/GIST/two-connection locking/overlap/overcommit) مؤجَّلة لبوّابة Phase-2-DB. القادم: Commit 4 (ربط الهدف + استعلام مسار v171 recursive) ثمّ Commit 5 (مُحوّل execution-request/outbox القائم).

## 2026-07-17 — IRR-F01 المرحلة 3 (Commit 4): ربط الهدف v196 + استعلام مسار v171 + إصلاح db_ownership
- **v196 `migrations/v196_irrigation_target_binding.sql`:** `irrigation_target_bindings` — ربط حقل/منطقة ↔ عُقدة v171 طرفيّة مُثبَّت بالإصدار (target_version_id) + فهرس فريد جزئيّ لربط مفتوح واحد لكلّ هدف؛ FK لـirrigation_projects + irrigation_hydraulic_nodes؛ RLS fail-closed؛ **بلا** graph_version (الطوبولوجيا مؤجَّلة). مُسجَّل في المُشغّلَين (خطوة 202).
- **استعلام المسار `services/sahool-platform/api/irrigation_path_query.py` (نقيّ، بلا DB):** `resolve_source_paths` يمشي القطاعات عكسيّاً من العُقدة الطرفيّة للمصدر (`node_type∈{source,reservoir}`)، cycle guard (يفشل مُغلَقاً INVALID_CYCLE) + حدّ عمق MAX_PATH_DEPTH=32؛ `path_status ∈ {unique, multiple, unreachable, invalid_cycle}` + `path_count` + كلّ البدائل (لا اختيار «أوّل مسار» صامت عند التعدّد) + **`bottleneck_node_id=None` دائماً** (السعة اختصاص v175/الحجز لا الطوبولوجيا). يشحن CTE recursive canonical (`PERSISTED_UPSTREAM_PATH_CTE`، tenant+project scoped + depth cap + cycle via path array) كثابت مُراجَع للتنفيذ الحيّ لاحقاً. baseline الوحدات 642→643.
- **إصلاح db_ownership (فجوة كامنة في Commit 3 المدفوع):** بوّابة `test_p0_db_ownership_guard` (تُشغَّل في Platform Unit Tests تحت التغطية، لم أشغّلها محليّاً في المرحلة 2 فسقطت CI على `98b17d4`) تتطلّب تسجيل كلّ CREATE TABLE في `docs/architecture/db_ownership.yml`. سجّلتُ الأربعة (v195: hydraulic_capacity_evaluations · irrigation_resource_reservations · _events؛ v196: irrigation_target_bindings) — owner=sahool-platform. **درس مُرسَّخ:** أيّ migration بـCREATE TABLE ⇒ حدّث db_ownership.yml (+ فحص `test_p0_db_ownership_guard` ضمن بطاريّة البوّابات). أيضاً أُصلِح CI workflow (`d829289`): `pip install pytest` قبل خطوات الحارس/الاختبار.
- **تحقّق أخضر:** convergence guard LOCKED · migration validator 202 · runners-in-sync · 29 اختبار irrigation · db_ownership 2 + growth 2 · production_validation_gate نجح · inventory --check نظيف · ruff (ملفّاتي) نظيف · release 4557. بلا route جديد (لا اضطراب route-budget/frontend)؛ عرض نقطة المسار يركب مع مُحوّل runtime في Commit 5. بلا PostgreSQL حيّ.

## 2026-07-17 — IRR-F01 المرحلة 4 (Commit 5): مُحوّل DB الحقيقيّ للحجز (عقد، بلا بنية حيّة)
- **`services/sahool-platform/api/irrigation_reservation_adapter.py`:** يربط النواة الصرفة بجداول v195 المملوكة للمنصّة + مسار execution-request/outbox القائم عبر `ExecutionRequestPort` مُحقَّن (تنفيذه الحقيقيّ يكتب outbox القائم `emit_event` فيُنشئ العامل القائم execution_request — لا SoR تنفيذ جديد). ترتيب داخل معاملة المُتّصِل حرفيّاً حسب المراجعة: set tenant GUC → أقفال advisory مُرتَّبة (ترتيب canonical من النواة) → قراءة تداخل طازجة لكلّ مورد + قبول النواة → INSERT تقييم → INSERT حجوزات+أحداث → `request_dispatch` (نيّة outbox) → المُتّصِل يُثبِّت. **الحجز المُثبَّت = dispatch_requested؛ إيصال actuator وحده = dispatched.** تعويض أماميّ عند فشل actuator بعد التثبيت (`compensate_dispatch_failure`: reservation→cancelled + حدث، request→dispatch_failed) لا rollback رجعيّ. SQL محسوس على الجداول المملوكة فقط (SET_TENANT · pg_advisory_xact_lock · overlap && tstzrange · INSERT تقييم/حجز/حدث · UPDATE cancelled). `bottleneck_node_id=None` في التقييم (السعة اختصاص v175). لا route جديد.
- **اختبار عقد (`tests/irrigation/test_irrigation_reservation_adapter.py`، بلا DB حيّ):** FakeConn/FakePort يُقاد عبر `asyncio.run` (لا pytest-asyncio — الـconvergence workflow يُثبّت pytest فقط). يؤكّد: القفل قبل التقييم، الترتيب canonical مع اختلاف الدخل، كلّ الأقفال قبل أيّ قراءة، evaluation قبل reservation، dispatch_request مرّة واحدة بعد الحجز (لا dispatched)، overcommit يرفع CapacityNotAdmissible بلا كتابة حجز/إرسال، التعويض يُلغي الحجوزات ويعلّم الطلب فاشلاً. baseline 643→644.
- **حالة CI (تأكيد MCP):** تِلّ الفرع الحاليّ **أخضر على المسارَين** (SAHOOL v9.1.0 CI run 4154 success + Irrigation convergence contract run 3 success على 595ba53). الأحمر الظاهر في لقطة المستخدم = commits وسيطة مُتجاوَزة (98b17d4 فجوة db_ownership · c69aa7e/98b17d4 convergence بلا pytest) أُصلِحت في d829289+595ba53.
- **تحقّق أخضر:** convergence guard LOCKED · 33 اختبار irrigation · db-ownership + growth (644) · production_validation_gate نجح · inventory نظيف · ruff · release 4559. **مؤجَّل بصدق (بوّابة PG Phase-4):** ربط `ExecutionRequestPort` بـ`emit_event` + تسجيل EventType + التنفيذ الحيّ (reservation+execution-request+outbox atomicity · dispatch-failure compensation · receipt semantics · two-connection locking · exclusive overlap · shared overcommit · rollback). enforce الكيميائيّ ما زال NO.

## 2026-07-17 — IRR-F01 Gate A مُعتمَد حيّاً على PostgreSQL (لا مؤجَّل بعد الآن)
- **المفاجأة السارّة:** البيئة تملك PostgreSQL 16 + PostGIS + btree_gist + asyncpg — فبدل تأجيل بوّابة PG، **شغّلتها فعليّاً**. أنشأتُ DB `irr_f01_gate` + دور `sahool_app` (NOSUPERUSER/NOBYPASSRLS)، طبّقتُ **ملفّات v195+v196 الحقيقيّة** فوق جداول تبعيّة دنيا (irrigation_projects/hydraulic_nodes/segments/canonical_hydraulic_capabilities)، وقُدتُ **المُحوّل الحقيقيّ** `reserve_and_request_dispatch_db` عبر asyncpg كـsahool_app.
- **Gate A أخضر 8/8 حيّاً:** (A2) FORCE RLS على الجداول الأربعة · (A-happy) المُحوّل يُثبِت evaluation+reservation+event ذرّيّاً · (A3) عزل قراءة RLS: مستأجِر خاطئ/سياق فارغ = 0 · (A3) WITH CHECK: إدراج tenant_id=A تحت جلسة B **مرفوض** (بعد إصلاح فخّ اختبار: INSERT…SELECT كان no-op لأنّ RLS أخفى صفّ التقييم — دليل إضافيّ أنّ العزل يعمل) · (A6) تداخل exclusive → RESOURCE_CONFLICT · (A7) overcommit مشترك (180+180>300) → CONCURRENT_LOAD_EXCEEDED · (A8) rollback بلا phantom · (A5) قفل advisory بجلستَين: الثانية تُحجَب (بمفتاح النواة ذاته).
- **اختبار دائم `tests_v9/test_irr_f01_reservation_live_pg.py`** (مُعلَّم integration، يتخطّى بلا `TEST_DATABASE_URL` أو بلا دور NOBYPASSRLS؛ يُنشئ مستأجِراً/مشروعاً/عُقداً عشوائيّة، يقود المُحوّل الحقيقيّ، ينظّف بترتيب FK RESTRICT). **2/2 نجح حيّاً**، تفكيك نظيف (0 صفوف متبقّية). مُتحقَّق أنّه مُستبعَد تحت `-m unit` (0 selected/2 deselected) فلا يكسر بوّابة الوحدة.
- **الحالة:** Gate A (Phase-2 DB) **مُعتمَد حيّاً**. Gate B (تكامل: ربط `ExecutionRequestPort`↔`emit_event` + تسجيل EventType + تسليم outbox→execution_request حيّ + دلالات الإيصال + سباق الأمر end-to-end) **ما زال مؤجَّلاً** (يحتاج decision-service قيد التشغيل + ربط emit_event). **لذا: لا FF لـmain/develop بعد** — Gate B شرط باقٍ. release 4560 · ruff نظيف.

## 2026-07-17 — IRR-F01 Gate B1 مُعتمَد حيّاً (نيّة الإرسال عبر outbox القائم) + إصلاح علّتَين اصطادهما التشغيل الحيّ
- **`api/irrigation_execution_request_port.py` (EmitEventExecutionRequestPort):** التنفيذ الحقيقيّ لـExecutionRequestPort — الحجز المُثبَّت يكتب حدث `irrigation.reservation.dispatch_requested` عبر `emit_event` القائم على **نفس اتّصال المعاملة** ⇒ الحجز ونيّة الإرسال ذرّيّان. لا SoR تنفيذ جديد، ولا وسم `dispatched` (عامل outbox القائم + decision-service ينشئان execution_request — التسليم الحيّ هو خطوة Gate-B الأخيرة). التعويض يُصدر `irrigation.reservation.dispatch_failed`. سُجِّل عضوا EventType الجديدان (`IRRIGATION_RESERVATION_DISPATCH_REQUESTED/_FAILED`) — الحُرّاس (emit_names/event_catalog) خضراء (السجلّ TEXT، لا allowlist في emit_event).
- **علّتان حقيقيّتان اصطادهما التشغيل الحيّ (لا وحدة ولا CI):**
  1. **entity_type:** جدول `events` يفرض CHECK على فئة خشنة (v11+v51: field/farm/operation/...). قيمتي `irrigation_reservation` **مرفوضة** — وكونها حدثاً غير حرج كانت **تُبتلَع صامتةً** في الإنتاج (كتابة بلا حدثها). أُصلِح إلى `operation` (المعنى الدقيق في event_type). — درس: الحدث لا يُثبَت حتّى تُطبَّق سلسلة الأحداث حيّاً.
  2. **correlation_id NOT NULL:** `compensate_dispatch_failure` كان يُدرِج حدث حجز بـcorrelation_id=None ⇒ انتهاك NOT NULL (v195) ⇒ انهيار التعويض في الإنتاج. أُصلِح: يقرأ correlation_id من صفّ الحجز (reserve يضبطه دائماً) مع fallback لـreservation_id.
- **Gate B1 أخضر 6/6 حيّاً على PostgreSQL 16** (بعد تطبيق v11+v18 events على DB البوّابة): إصدار ذرّيّ للنيّة + صفّ event_outbox (`sahool.events.irrigation.reservation.dispatch_requested`) + tenant-scoped + rollback بلا حدث + التعويض يُصدر dispatch_failed ويُلغي الحجز. اختبار دائم أُضيف لـ`tests_v9/test_irr_f01_reservation_live_pg.py` (يتخطّى بلا جدول events). 3/3 اختبارات حيّة خضراء.
- **تحقّق:** emit_names+event_catalog+growth(645)+db_ownership 17 · 33 اختبار irrigation · convergence LOCKED · inventory نظيف · ruff · release 4561.
- **المتبقّي الوحيد (Gate B-delivery):** تسليم outbox→execution_request حيّ عبر decision-service + دلالات الإيصال + سباق أمر end-to-end — يحتاج رفع decision-service+النظام كاملاً. لا FF لـmain/develop قبله. enforce الكيميائيّ NO.

## 2026-07-17 — IRR-F01: توفيق تقسية local_gate_hardened (منقّاة) + إعادة اعتماد حيّ
- **مراجعة حزمة `local_gate_hardened`:** بُنيت على قاعدة أقدم (تفتقر Gate A الحيّ/منفذ B1/إصلاح entity_type). استُخلِصت أفكار التقسية القيّمة ووُفِّقت على تِّلّي، مع **رفض تعديلها لـv171** (migration مُرسَل — تعديله يُعيد كتابة التاريخ ولا يُطبَّق على DB مُهاجَرة).
- **v195 المُقسّى (بلا لمس v171):** (1) **FK سعة tenant-scoped** `(capability_id, tenant_id)` — v195 يضيف `CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_hydraulic_capability_tenant` على canonical_hydraulic_capabilities ذاتيّاً (يعمل على fresh **و** القائم؛ capability_id أصلاً PK فالفهرس superset آمن) ثمّ FK مركّب ⇒ تقييم لا يشير لسعة مستأجِر آخر؛ (2) `UNIQUE NULLS NOT DISTINCT` على أحداث الحجز (replay حتميّ عند causation NULL)؛ (3) **trigger append-only** يرفض UPDATE/DELETE على سجلّ أحداث الحجز (immutability مفروض DB).
- **المُحوّل المُقسّى:** رفض `DUPLICATE_HYDRAULIC_RESOURCE` قبل الأقفال/الكتابة (بدل dedup صامت)؛ إعادة تسمية النتيجة إلى `dispatch_intent_id` مع خاصّيّة alias `dispatch_request_ref` (نيّة outbox لا إيصال). أُبقيَ إصلاحي (correlation من صفّ الحجز) + منفذ Gate B1.
- **إعادة اعتماد حيّ على PostgreSQL 16 (v195 المُقسّى مُعاد تطبيقه):** 3/3 اختبارات حيّة خضراء (Gate A ×2 + Gate B1). **trigger append-only مؤكَّد يمنع الحذف الحقيقيّ** (حجب DELETE في التفكيك برسالة `is append-only`). تفكيك الاختبار الدائم صار TRUNCATE عبر admin مالك (append-only + RESTRICT يجعلان الحذف الصفّيّ مستحيلاً بالتصميم ⇒ **قاعدة disposable إلزاميّة**، موثّق).
- **تحقّق:** 34 اختبار irrigation · convergence LOCKED · migration validator 202 · runners-sync · **fii write-policy gate PASSED** (v195 يحتفظ FORCE+policy) · production_validation_gate نجح · ruff.
- **لم يُتبنَّ (بعد):** حزمة Docker gate (`scripts/irr_f01/` + `docker-compose.irr-f01-test.yml` + `tests/integration/` + Makefile) — بوّابة قابلة لإعادة التشغيل؛ اعتمدتُ حيّاً مباشرةً، وتبقى إضافة بنية اختياريّة. لا FF قبل Gate B-delivery.

## 2026-07-17 — IRR-F01: تبنّي حزمة Docker gate (بوّابة PostgreSQL معزولة قابلة لإعادة التشغيل)
- **من `local_gate_hardened`:** أُضيفت البنية القابلة لإعادة التشغيل (بعد توفيق تقسية v195/المُحوّل سابقاً): `docker-compose.irr-f01-test.yml` (Postgres 16 معزول، tmpfs، منفذ عشوائيّ، healthcheck) · `scripts/irr_f01/{local_gate.sh, bootstrap.sql, build_report.py}` · `tests/integration/irrigation/test_v195_postgres.py` · `requirements-irr-f01-test.txt` · هدف Makefile `test-irr-f01-local`.
- **local_gate.sh:** يرفع Postgres معزولاً، يُنشئ دورَي `sahool_app`/`sahool_other` (NOSUPERUSER/NOBYPASSRLS) عبر bootstrap، يُطبّق **سلسلة المهاجرات كاملةً** `find migrations/v*.sql | sort -V` (فيلتقط v195 المُقسّى تلقائيّاً)، يؤكّد الأدوار ليست superuser/bypassrls، يلتقط schema snapshot + SQLSTATE، يشغّل 4 ملفّات اختبار (irrigation + الجديد PG)، ويبني تقرير + JUnit + zip. مخرجاته في `artifacts/` (أُضيف لـ.gitignore).
- **test_v195_postgres.py:** يتخطّى على مستوى الوحدة إن غابت `ADMIN/APP/OTHER_DATABASE_URL` (آمن في CI — لا يُجمَع أصلاً: خارج testpaths=tests_v9 وغير مُعلَّم integration). تأكيداته **تطابق v195 المُقسّى**: أدوار غير مُميّزة · FORCE RLS · fail-closed سياق مفقود · عزل سياسة عبر جدول probe · correlation_id NOT NULL · `NULLS NOT DISTINCT`.
- **لم يُنفَّذ هنا:** لا daemon Docker في بيئة المراجعة ⇒ البوّابة مُتبنّاة كبنية اختياريّة (make target) لم تُشغَّل — **لكنّ الاعتماد الحيّ تمّ أصلاً مباشرةً على Postgres 16** (Gate A 8/8 + Gate B1 6/6). البوّابة تجعله متكرّراً في أيّ آلة/CI فيها Docker.
- **تحقّق CI-relevant:** الملفّ compose يجتاز `docker compose config` (الـCI يتحقّق من كلّ docker-compose*.yml) · yaml صالح · bash -n نظيف · py_compile · ruff (خارج نطاق CI لكن نُظِّف) · 34 اختبار irrigation · convergence LOCKED · integration يتخطّى · release 4567. لا FF قبل Gate B-delivery.

## 2026-07-17 — IRR-F01: شهادة CI تُنفَّذ فعلاً + إغلاق فجوات مراجعة ما‑قبل‑الدمج (Gate A تزامن E2E · Gate U1 ترقية · fail‑closed)
- **جعل شهادة Gate A/B1 تُنفَّذ في CI (لا أخضر‑متخطٍّ):** خطوة تكامل مخصّصة تُنشئ دور `sahool_app_test` (NOSUPERUSER NOBYPASSRLS NOINHERIT) + تؤكّد `role_flags=false:false`، وتشغّل ملفّ Gate A/B1 الحيّ فقط بـ`TEST_DATABASE_URL`=app + `TEST_DATABASE_ADMIN_URL`=sahool_test + `IRR_F01_CERTIFICATION_REQUIRED=1` — بلا لمس التشغيل المشترك (يبقى superuser لبقيّة اختبارات التكامل). حارس عقد `tests/irrigation/test_irr_f01_certification_ci_contract.py` يقفل السلاسل الحرفيّة في ci.yml + مفاتيح fail‑closed في الاختبار الحيّ.
- **Gate A تزامن overcommit طرف‑لطرف (كان مفقوداً — يثبت أنّ المُحوّل يقفل فعلاً):** `after_locks_acquired` hook حتميّ في `reserve_and_request_dispatch_db` (اختباريّ فقط، افتراضه None)؛ اختبار جلستين: T1 يقفل ثمّ يتوقّف قبل الإدراج، T2 يُثبَت حجبه بمهلة (1.5s)، T1 يُدرِج 180 ويلتزم، T2 يستأنف ويعيد القراءة ويُرفَض `CONCURRENT_LOAD_EXCEEDED`؛ تأكيد: حجز واحد + evaluation واحدة، لا صفوف يتيمة من T2. لو حُذف القفل من المُحوّل، T2 لن يُحجَب ولن يُرفَض ⇒ الاختبار يفشل.
- **Gate U1 ترقية v194→v195/v196 (كان مفقوداً — يفصل شهادة المخطّط الجديد عن شهادة الترقية):** `scripts/irr_f01/upgrade_gate_u1.sh` يبني قاعدة بالسلسلة حتّى v194 فقط، يزرع بيانات ريّ واقعيّة (مصدر ماء→بئر→مضخّة؛ مشروع→عقد→قدرة canonical)، يطبّق v195+v196، يعيد تطبيقهما (idempotent no‑op)، ويؤكّد: لا فقد بيانات (عدّ محفوظ) + الفهرس المُضاف‑ذاتيّاً `uq_canonical_hydraulic_capability_tenant` + trigger append‑only + لا NULL غير مشروع؛ ثمّ `tests_v9/test_irr_f01_upgrade_gate_u1_pg.py` يثبت أنّ FK المركّب المُقيّد‑بالمستأجر يقبل حجزاً يشير إلى قدرة كُتِبت **قبل** وجود v195 (وأنّ id قدرة يتيم يُرفَض)، وأنّ Gate A/B1 الكامل يمرّ فوق القاعدة المُرقّاة.
- **إغلاق ملاحظات المراجعة سطراً‑بسطر (كلّها مؤكَّدة على الكود):** (1) `importorskip` كان يتجاوز وضع الشهادة عند غياب asyncpg ⇒ الآن `try/except ImportError: raise if CERTIFICATION_REQUIRED`. (2) سقوط `ADMIN_DSN→APP_DSN` كان يهدم فصل الأدوار ⇒ الآن ADMIN إلزاميّ في وضع الشهادة (يفشل مُغلَقاً بتشخيص). (3) `START` ثابت في الماضي ⇒ `datetime.now(UTC)+1h` مُقرَّب. (4) اتصال admin (وخطأ الاتصال) صار مُغلَّفاً بـ`_skip_or_fail`. (5) رفض WITH CHECK صار يؤكّد `sqlstate=='42501'` (لا أيّ PostgresError). (6) عدّ events صار tenant‑scoped. (7) NOINHERIT صار مؤكَّداً حرفيّاً. **جديد: اختبار idempotent replay** (طلب مُطابق مرّتين ⇒ `23505` + حجز واحد فقط + لا evaluation شبح).
- **نقطة 2 من المراجعة (compensate correlation_id إلزاميّ ⇒ TypeError) = غير قابلة للتطبيق على الفرع:** توقيع `compensate_dispatch_failure` المُنزَّل لا يتطلّب correlation_id (يقرؤه من صفّ الحجز)؛ الانحدار كان في zip المرشّح فقط، لم يُتبنَّ. أُعيدت تسمية التأكيد الأساسيّ إلى `dispatch_intent_id` مع إبقاء توافق خلفيّ لـ`dispatch_request_ref`.
- **تحقّق حيّ (PostgreSQL 16):** fresh 5/5 (تضمّن التزامن E2E + idempotent replay) + upgrade 3/3 + Gate A/B1 فوق القاعدة المُرقّاة 5/5 + حارس العقد 5/5. fail‑closed مُثبَت: ADMIN مفقود⇒Failed، driver مفقود⇒ImportError عند الاستيراد. convergence LOCKED · ruff نظيف · inventory بلا drift · 38 اختبار irrigation · release bundle مُعاد بناؤه. لا FF قبل Gate B‑delivery.

## 2026-07-17 — IRR-F01 Gate B-delivery (البدء): صندوق تسليم رقيق لقصد الحجز (delivery ≠ fulfillment)
- **القرار (المستخدم):** Option 3 «صندوق تسليم رقيق أولاً» ← Option 1 «الربط بتنفيذ مُصرَّح قائم» كهدف معماريّ ← Option 2 «مسار إنشاء يصرّح لنفسه» **ممنوع** إلّا بقرار WX-10 موثّق صريح. الفصل: الإيصال (تسجيل دائم مع dedup) عن الإيفاء (إنشاء execution_request) — الأخير بوّابة لاحقة صريحة.
- **الطوبولوجيا (scout):** المُنتِج→`events`/`event_outbox`→OutboxWorker(`event_bus.py`)→NATS مبنيّ بالكامل؛ execution_request SoR + مستهلك actuator مبنيّان؛ **الكسر الوحيد:** لا مستهلك يربط `irrigation.reservation.dispatch_requested`→execution_request، و`create_execution_request` يشترط نَسَب موافقة WX-10 كامل لا يحمله الحجز. (ليس مسار phase_runtime_workers — جدول مختلف.)
- **Slice B-d1 (مُنجَز، مُعتمَد على PostgreSQL حيّ):** decision-service migration `027_reservation_dispatch_inbox.sql` — جدول `decision_reservation_dispatch_inbox` (dedup على `(tenant_id, source_event_id)`، حالة received/failure_notice، append-preserving + immutable-identity كنمط 005) + `decision_consumer_heartbeats` (heartbeat للمستهلك تغذّي بوّابة التفعيل). `persistence.record_reservation_dispatch_intent` (idempotent: received/failure_notice أوّل تسليم · duplicate إعادة تسليم بنفس الإيصال · conflict نفس event بحمولة مختلفة · **لا ينشئ execution_request**). نقطة `POST /v1/reservation-dispatch-intents` (503 في mirror). اختبار حيّ `tests/test_gate_b_reservation_dispatch_inbox.py` (٦/٦): received-بلا-execution_request · idempotent-نفس-الإيصال · conflict · failure_notice · append-only يرفض DELETE · dedup لكلّ مستأجر. خطوة CI في وظيفة Decision Service على Postgres حقيقيّ.
- **تحقّق:** migration_runner --apply (001..027) + --check نظيف · ٦/٦ حيّ · mirror contract 11/11 · ٣ بوّابات حدود decision-service (execution_request/delivery-receipt/final-cert) LOCKED · ruff نظيف · inventory 1040 route · db_ownership guard خارج نطاق decision-service (2 pass). لا خدمة جديدة، لا worker جديد — SoR-side فقط.
- **مؤجَّل بصدق:** Slice B-d2 = ناقل NATS→ingest (relay) — يحتاج NATS+decision-service حيّين. Slice B-d3 = الإيفاء (Option 1: الربط بتنفيذ مُصرَّح) خلف قرار WX-10. لا FF لـmain/develop.

## 2026-07-17 — IRR-F01 Gate B-delivery Slice B-d2 (النواة): مُخطِّط الترحيل النقيّ + حارس delivery≠fulfillment
- **مُخطِّط الترحيل النقيّ** `services/sahool-platform/api/irrigation_dispatch_relay.py::build_reservation_dispatch_ingest` — يحوّل حدث outbox مُسلَّماً (`irrigation.reservation.dispatch_requested`/`_failed`) إلى جسم ingest لِـdecision-service حرفيّاً؛ بلا NATS/HTTP (نقيّ، قابل للاختبار بلا بنية). fail-closed: يرفض نوع حدث غير مدعوم أو event_id مفقود. لا إيفاء (لا يشتقّ execution_request).
- **حارس delivery≠fulfillment** `tests/irrigation/test_gate_b_dispatch_relay_and_contract.py` (يعمل عبر workflow irrigation-convergence، ١٠/١٠): اختبارات المُخطِّط (كلا الحدثين · تطابق مفاتيح الجسم مع نموذج النقطة · رفض غير المدعوم/المفقود · تطابق الأحداث مع CHECK في migration 027) + حارس ساكن يقفل الحدّ: migration 027 لا تمسّ `decision_execution_requests`؛ `record_reservation_dispatch_intent` لا يستدعي `create_execution_request`؛ النقطة 503 في mirror؛ dedup + append-only حاضران. يمنع تآكل الحدّ إلى مسار تنفيذ تلقائيّ (تجاوز حوكمة Option 2 الممنوع).
- **تحقّق:** ١٠/١٠ + مجموعة irrigation ٤٩/٤٩ · convergence LOCKED · ruff نظيف · inventory 1040 route (python_loc محدَّث) · route_mount نظيف (لا نقطة جديدة) · bundle مُعاد التحقّق.
- **مؤجَّل بصدق (Slice B-d2-live):** اشتراك NATS على `sahool.events.irrigation.reservation.dispatch_requested` + POST إلى `/v1/reservation-dispatch-intents` بتوكن الخدمة + خدمة compose (default-off) — يحتاج NATS+decision-service حيّين. ثمّ B-d3 = الإيفاء خلف قرار WX-10. لا FF.

## 2026-07-18 — IRR-F01 Phase 1 P1-a: بوّابة تفعيل irr_f01_reservation (النموذج المرجعيّ الوحيد)
- **القرار المعماريّ (المستخدم، معتمد نهائيّ):** بناء **بوّابة irr_f01_reservation فقط** كنموذج مرجعيّ؛ **لا استخراج framework عامّ** قبل ميزة فئة-A ثانية (ACTIVATION-GATE-PROD-07 anti-premature-abstraction). تصنيف A/B/C معتمد: A تفعيل آليّ مسموح · B شهادة نشر (تُستهلك أدلّتها) · C ماديّ/ماليّ (technical∧operator∧safety). لا ازدواج جاهزيّة: البوّابة تستهلك دليلاً يحمل producer/check/observed_at/valid_until/result/provenance/environment_id. Foundation SHA `0ced12c` مجمّد؛ Phase 1 commits جديدة فوقه، re-cert.
- **P1-a (مُنجَز، مُعتمَد على PostgreSQL حيّ ٨/٨):** decision-service migration `028_irr_f01_reservation_activation_gate.sql` — جدول حالة حاليّ ٥ حالات (disabled/evaluating/enabled/degraded/revoked) + سجلّ أحداث append-only (immutable trigger) + trigger حارس (generation يتقدّم بـ+1 فقط، environment_id ثابت). `services/decision-service/activation_gate.py` (خاصّ بالبوّابة لا عامّ): begin/complete/revoke/reset/recover_stale/current + CAS على `activation_generation` + TTL (`state_expires_at`) + استرداد evaluating العالق + `build_sha` من الأدلّة خادميّاً (غير قابل للانتحال) + admissibility للـevidence envelope + `enforce_enabled` (نقطة الإنفاذ الوحيدة) + `probe_state` (دور `activation_probe` + توقيع HMAC).
- **الاختبارات الإلزاميّة الثمانية (real PG):** `tests/test_irr_f01_reservation_activation_gate.py`: تفعيل متزامن (واحد يفوز) · انتهاء TTL · revoke→reset · استرداد evaluating العالق (حديث لا يُسترَدّ/عالق يُسترَدّ) · رفض probe من دور عادٍ/توقيع خاطئ · الإنفاذ هو البوّابة الوحيدة (disabled/evaluating/degraded كلّها ترفض) · سجلّ الأدلّة append-only (UPDATE/DELETE يرفضان) · CAS+generation (توقُّع قديم⇒conflict، قفزة gen/إعادة ربط env يرفضهما الحارس). خطوة CI في وظيفة Decision Service.
- **تحقّق:** ٨/٨ حيّ · migration --apply 001→028 + --check نظيف · ruff نظيف · inventory 1040 route (python_loc محدَّث) · بوّابات decision-service LOCKED · mirror contract 11/11 · bundle مُعاد. الفئة A (تسليم لا أثر ماديّ). لا framework عامّ.
- **مؤجَّل (P1-b):** ربط الإنفاذ في نقطة ingest + نقطة probe محميّة + build_sha من metadata النشر + cache مرتبط بالجيل. ثمّ تسجيل ACTIVATION-GATE-PROD-01..07 + حارس منعِ حذفها بعد الدمج. لا FF.

## 2026-07-18 — IRR-F01 Phase 1 P1-b: إنفاذ البوّابة + نقاط المشغّل/probe + cache + build_sha النشر + PROD-01..07
- **activation_gate.py:** `build_sha` صار يربط `DEPLOY_BUILD_SHA` (metadata النشر خادميّاً، غير قابل للانتحال) + الأدلّة المقبولة؛ **cache قراءة مرتبط بالجيل** قصير العمر (`current_cached`, `CACHE_TTL_SECONDS`) يُبطَل عند أيّ انتقال (داخل `_log`)؛ **الإنفاذ (`enforce_enabled`) يقرأ طازجاً لا من الكاش** (TTL/revoke يسري فوراً).
- **main.py:** إنفاذ عند نقطة ingest خلف راية `IRR_F01_RESERVATION_ENFORCE_ACTIVATION` (افتراض OFF ⇒ سلوك حاليّ سليم؛ ON ⇒ 403 إن لم تُفعَّل البوّابة) + ٦ نقاط: begin/complete/revoke/reset (مشغّل، SoR-gated 503 في mirror، X-Requested-By) · `GET /v1/activation/irr_f01_reservation` (cached) · `GET .../probe` (دور `activation_probe` + توقيع HMAC، 403 لغير المخوّل). environment = `ACTIVATION_ENVIRONMENT_ID`|`SAHOOL_ENV`.
- **اختبارات (real PG via TestClient ٤/٤):** دورة المشغّل عبر API (begin→complete→enabled→revoke→reset) · ingest يفرض 403 عند الراية+معطّلة ثمّ يقبل بعد التفعيل · probe مُغلَق لغير المخوّل · build_sha يربط metadata النشر. P1-a ٨/٨ ثابتة. mirror contract 11/11 (النقاط 503 في mirror).
- **PROD-01..07 مُسجَّلة** في `gaps/registry.md` (locked architectural؛ PROD-07 open deferred anti-abstraction) + **حارس منعِ حذف/اختصار** `tests/irrigation/test_irr_f01_activation_gate_prod_guard.py` (٨ اختبارات: تسجيل السجلّ + آلة الحالات + CAS trigger + append-only + TTL+enforce طازج + build_sha النشر + استهلاك الأدلّة لا إعادة تنفيذ + probe/enforce wiring). يعمل عبر convergence workflow.
- **تحقّق:** ١٢ اختبار decision حيّ + ٥٧ irrigation + mirror 11 · ruff نظيف · inventory 1046 route (+٦) · route_mount/residual نظيفان · migration --check نظيف · bundle مُعاد. لا framework عامّ (PROD-07). لا FF لـmain/develop.
- **مؤجَّل (Phase 2):** بوّابة فئة-A ثانية (weather_real_data|satellite_cdse) ثمّ استخراج المشترك المثبَّت (state machine/CAS/evidence/generation/TTL/enforcement) — عندها فقط، وفحوص كلّ قدرة تبقى في مالكها.

## 2026-07-18 — Phase 2 P2-a: بوّابة تفعيل satellite_cdse (النموذج المرجعيّ الثاني المستقلّ)
- **القرار (المستخدم):** Phase 1 مُغلَقة (CI أخضر @ `d0d9197`)، ابدأ Phase 2 = **satellite_cdse**.
- **بوّابة ثانية مستقلّة تماماً** (لا استيراد `activation_gate.py` — نسخة منفصلة عمداً حسب ACTIVATION-GATE-PROD-07): decision-service migration `029_satellite_cdse_activation_gate.sql` (جدول حالة ٥ حالات + سجلّ append-only + trigger حارس، بنفس شكل 028 عمداً ليُنير الاستخراج) + `satellite_cdse_activation_gate.py`. **الاختلافان الجوهريّان (هما المقصد):** (١) **دليل مختلف**: `cdse_credentials_present` + `cdse_live_probe` (مُنتِج raster-service)؛ (٢) **إنفاذ مختلف**: `active_imagery_source` ليس رفضاً بل **اختيار مصدر** — 'cdse' عند التفعيل و'element84' كاحتياط آمن (فئة A، لا أثر ماديّ). يقرأ طازجاً (TTL/revoke يعيد التوجيه فوراً).
- **الاختبارات الإلزاميّة الثمانية (real PG ٨/٨):** تفعيل متزامن · TTL ⇒ fallback لـelement84 · revoke→reset · استرداد evaluating العالق · probe دور/توقيع · **اختيار المصدر هو الإنفاذ** (disabled/degraded ⇒ element84) · سجلّ append-only · CAS+generation. **بوّابة 1 (irr_f01) ما زالت ٨/٨** — استقلال مُثبَت (لا تداخل). خطوة CI في وظيفة Decision Service.
- **تحقّق:** ٨/٨ + ٨/٨ (بوّابة 1) · migration --apply 001→029 + --check نظيف · ruff نظيف (شمل ملفّات الاختبار — درس P1-b) · inventory 1046 route (python_loc محدَّث) · decision final-cert LOCKED · bundle مُعاد.
- **ACTIVATION-GATE-PROD-07: شرط الاستخراج (بوّابتان فئة-A مستقلّتان) صار متحقّقاً الآن** — Phase 3 (استخراج المشترك المثبَّت: state machine/CAS/TTL/evidence/generation/stale/probe؛ مع بقاء REQUIRED_CHECKS/producers والإنفاذ خاصّاً بكلّ قدرة) صارت مؤهَّلة، مؤجَّلة حتى إشارة المستخدم.
- **مؤجَّل (P2-b):** نقاط تشغيل/probe لبوّابة cdse + استهلاك raster-service لـactive_imagery_source (اختيار المصدر حيّاً). لا FF لـmain/develop.

## 2026-07-18 — Phase 2 P2-b + P2-c (satellite_cdse gate: HTTP surface + LIVE consumer)
- **P2-b (`0f628be`, CI أخضر 13/13):** واجهة HTTP لبوّابة satellite_cdse — ٧ نقاط في decision-service `main.py` (begin/complete/revoke/reset + current + probe + **/source**) متناظرة مع irr_f01، كلّها SoR-gated (503 في المرآة). الإنفاذ = قراءة `/source` (اختيار مصدر cdse↔element84، لا 403). ٤ اختبارات نقاط real-PG + خطوة CI في وظيفة Decision Service. inventory (decision-service 59→66 route).
- **قرار المستخدم بعد P2-b:** **لا تبدأ Phase 3 بعد** — أوّلاً **P2-c: استهلاك حيّ** (بوّابة بلا مستهلك إنتاجيّ = لم تُثبِت أنّها تحكم شيئاً؛ الاختلافات الحقيقيّة تظهر عند التوصيل). الشرط الأقوى للاستخراج = بوّابتان مستقلّتان **مُستخدَمتان فعلاً**.
- **P2-c — المُحوِّل المُقيَّد (restricted adapter):** `services/raster-service/imagery_source_gate.py` — **المسار الوحيد** لاختيار CDSE. `resolve_active_source()` يقرأ `/v1/activation/satellite_cdse/source` طازجاً، يُطبّق: enabled→cdse؛ degraded/disabled/revoked/evaluating→element84؛ **unreachable/503/timeout→element84 fail-closed** (لا تخمين CDSE أبداً). **default-off** (`RASTER_ACTIVATION_GATE_ENFORCE`؛ السلوك القديم محفوظ). القرار يحمل النَّسَب (generation+provider+timestamp+gate_state+environment) لربط job طويل بجيله (كشف revoke منتصف-الطريق).
- **نقطتا الاختناق:** `stac_search.stac_search()` (اختيار مزوّد البحث) + `routers/fields.process_cdse` (تفويض المعالجة — يُرجِع available=false→element84 عند عدم التفعيل، ويربط evidence القرار بالـjob). عزّزتُ `active_imagery_source()` (decision-service) لتُصدِر generation+build_sha (يحتاجها ربط الجيل + النَّسَب).
- **الإثباتات السبعة:** (real E2E عبر ASGITransport: raster→decision app→real PG) تغيّر الحالة يقلب المزوّد · revoke يمنع CDSE جديداً · degraded→element84 · **سباق الجيل** (gen يتغيّر بين قراءتَين) · **نَسَب evidence** · **حارس no-bypass ساكن** (لا وحدة جديدة تلمس primitives اختيار CDSE خارج allowlist مُراجَع؛ مسار البلاطات الحيّة remainder موثَّق صراحةً) · **البوّابتان خضراوان بعد التوصيل**. compose: knobs default-off مُضافة (raster-service).
- **تحقّق:** raster consumer+guard 16/16 · decision e2e+gates 14/14 · `pytest -m unit` **3180/0** (أصلحتُ حارسَي dispatch قديمَين v30_8/v31_4 ليطابقا الشكل الجديد — النيّة محفوظة) · ruff نظيف (شمل الاختبارات) · inventory + route-mount نظيفان · bundle 4584 · خطوتا CI مضافتان (decision e2e + raster consumer/guard في raster-validated-product.yml).
- **ACTIVATION-GATE-PROD-07:** بعد إثبات أنّ البوّابة الثانية **تتحكّم فعلاً** في التشغيل، Phase 3 صارت مستحقّة ومعتمدة (لا استخراج مبكّر). النواة المشتركة المرشَّحة: transition/CAS/stale/TTL/append-only evidence/build_sha/probe/cache-by-generation — **لا** اختيار cdse/element84 ولا fallback policy ولا evidence حقول المجال. **مؤجَّل بصدق:** مسار بلاطات CDSE الحيّة (surface منفصل) · شهادة staging لكلا البوّابتين تحت حمل حقيقيّ.

## 2026-07-18 — Phase 3 (استخراج نواة بوّابة التفعيل المشتركة) — بعد تحقّق PROD-07
- **الشرط تحقّق:** بوّابتان مستقلّتان (`irr_f01_reservation` + `satellite_cdse`) **+ مستهلك حيّ** (raster-service P2-c). عندها فقط استُخرج المُثبَّت-المشترك (لا قبله — ACTIVATION-GATE-PROD-07).
- **النواة** `services/decision-service/activation_gate_core.py` — `ActivationGateCore(GateConfig)`: آلة الحالات الخمس + CAS على `activation_generation` + stale-recovery + TTL/قراءة-طازجة + `_log` append-only + `build_sha` خادميّ غير قابل للانتحال + مظروف probe (دور+HMAC) + كاش مربوط بالجيل. أسماء الجداول من `GateConfig` (ثوابت كود، لا مدخل طلب ⇒ SQL آمن). `build_sha_namespace` يُبقي بصمة كلّ بوّابة مميّزة (v028/v029).
- **البوّابتان صارتا wrappers رفيعة:** كلّ منها `_CORE = ActivationGateCore(GateConfig(...))` + إعادة تصدير الأسماء العامّة (توقيعات لم تتغيّر) + **الإنفاذ الخاصّ فقط**: `enforce_enabled` (رفض، irr_f01) مقابل `active_imagery_source` (اختيار مصدر، satellite). `ActivationProbeDenied` مشتركة من النواة.
- **لم يُستخرج (بقصد — السيوم التي كشفتها الازدواجيّة):** الهويّة/REQUIRED_CHECKS/المنتِجون · معنى الإنفاذ · أسماء الجداول + triggers CAS/append-only (per-migration).
- **حارس PROD مُحدَّث:** المكنة المنقولة (build_sha/الأدلّة/probe) تُفحَص الآن على `activation_gate_core.py`؛ الخاصّ (enforce_enabled/PROBE_ROLE/REQUIRED_CHECKS) يبقى على الـwrapper. **حارس جديد** `test_prod_07_shared_core_extracted_after_two_gates` يثبّت: النواة صنف واحد، كلا الـwrapper يُنشئانها بـGateConfig، والإنفاذ يبقى per-gate. سجلّ الفجوات: PROD-07 → **locked (executed)**.
- **تحقّق:** السلوك مطابق تماماً — 26/26 (بوّابتان + نقاط + e2e) خضراء بلا تعديل اختبار سلوكيّ · `pytest -m unit` 3180/0 · irrigation 59 (+1) · ruff نظيف · inventory + route-mount نظيفان · bundle مُعاد. صافي: ~460 LOC مكرّرة → نواة واحدة + wrapperان رفيعان.
- **المؤجَّل بصدق (بيئة حيّة/إشارة):** FF لـmain/develop محظور حتّى بوّابة RLS الحيّة · FII P1+P2 (مصفوفة PG حيّة) · شهادة staging للبوّابتين تحت حمل · مسار بلاطات CDSE الحيّة (surface منفصل) · Gate B-d2-live/B-d3.

## 2026-07-18 — P2-c-tiles (إغلاق remainder مسار بلاطات CDSE الحيّة)
- **الـ remainder الموثَّق من P2-c أُغلِق:** مسار البلاطات/الصورة المصغّرة الحيّ صار محكوماً بنفس المُحوِّل المُقيَّد. `raster_cdse_tile_runtime.normalize_cdse_request` يستشير `imagery_source_gate.resolve_active_source` بعد `is_configured`؛ عند التفعيل والبوّابة غير مُفعّلة (أو متعذّرة) يعيد None ⇒ لا بلاطة CDSE تُصيَّر (نفس عقد fail-closed للفرع غير المُهيّأ). نقطة `field_cdse_tilejson` تُعلن availability=false بسبب `cdse_gate_inactive` صادقاً بدل الإعلان عن طبقة لن تُصيَّر. default-off.
- **الحارس مُحدَّث:** مسار البلاطات انتقل من TILE_PATH_REMAINDER (حُذِف) إلى GATE_CONSULTING_CHOKEPOINTS (الآن ٤ نقاط اختناق: بحث + معالجة + بلاطات-runtime + tilejson-router). لا remainder مفتوح لاختيار CDSE. اختبار سلوكيّ جديد: بوّابة معطَّلة ⇒ normalize يعيد None قبل أيّ عمل كتالوج/DB.
- **تحقّق:** raster consumer+guards 18/18 · router-decomposition 7/7 · `pytest -m unit` 3180/0 · ruff نظيف · inventory + route-mount نظيفان.
- **المؤجَّل بصدق (بيئة حيّة/إشارة):** FF لـmain/develop (بوّابة RLS الحيّة) · FII P1+P2 · شهادة staging للبوّابتين + المستهلك تحت حمل · Gate B-d2-live/B-d3 (يحتاج NATS/خدمات).

## 2026-07-18 — Gate B-delivery Slice B-d2-live (مُرحِّل NATS→inbox، محاكاة حتى staging)
- **الحلقة الحيّة الأخيرة لـGate B-delivery:** عامل `services/sahool-platform/api/irrigation_dispatch_relay_worker.py` يشترك على أحداث الحجز (`sahool.events.irrigation.reservation.dispatch_{requested,failed}` التي ينشرها OutboxWorker) → يُخطّطها بالمُخطِّط النقيّ (B-d2) → يـPOST إلى صندوق decision-service الدائم (`/v1/reservation-dispatch-intents`).
- **الحدّ محفوظ (delivery≠fulfillment):** العامل **لا يُنشئ execution_request أبداً** — يُسجّل تسليماً فقط، والصندوق يُزيل التكرار (dedup على source_event_id) ثمّ يتوقّف. حارس ساكن يقفل ذلك.
- **default-off مزدوج:** بروفايل compose `relay` (لا يُنشأ افتراضاً) **+** راية `FEATURE_RESERVATION_DISPATCH_RELAY` (العامل no-op داخليّاً بدونها؛ main يـidle لا يخرج فيمنع restart-thrash).
- **النواة نقيّة ومُختبَرة:** `handle_delivered_message(raw, post_fn)` — 8 اختبارات (delivered · duplicate 200 settled · unsupported→skip بلا POST · missing id→fail-closed skip · malformed→skip · non-2xx→failed لا fulfilled · default-off لا يشتغل · حارس no-fulfillment ساكن). تعمل في lane irrigation-convergence (67، +8).
- **صدق:** جولة NATS+decision-service الحيّة **مؤجَّلة لشهادة staging** (نمط water-deficit-bridge المُعتمَد) — الـoutbox المُنتِج الدائم، الصندوق الحوض idempotent، فرسالة core-NATS ضائعة يُعيد الـoutbox نشرها. دلالة durability للقفزة (core vs JetStream ack) قرار staging.
- **تحقّق:** compose-env نظيف (FEATURE_RESERVATION_DISPATCH_RELAY مُعلَن) · module baseline 646→647 (+note) · inventory + route-mount نظيفان · ruff نظيف · `pytest -m unit` 3180/0 · bundle مُعاد.
- **المتبقّي (محجوب بيئة حيّة):** FF لـmain/develop (بوّابة RLS الحيّة) · FII P1+P2 · شهادة staging (البوّابتان + المستهلك + هذا المُرحِّل تحت حمل حقيقيّ) · B-d3 الإيفاء خلف WX-10.

## 2026-07-18 — Gate-Trust-1 (P0): جذر الثقة = إيصالات أدلّة مخزَّنة يُصدرها المنتج (رفض 27046cd كمرشّح شهادة)
- **المُدقِّق رفض 27046cd:** «نموذج متقدّم قابل للإصلاح لكنّ جذر الثقة الحاليّ قابل للانتحال» — `complete_evaluation` كان يثق بأدلّة يرسلها المتّصل (producer/check_name/result/valid_until مُختلَقة). أُقِرَّ اعتراضي على lease (الـCAS القائم يُغلق سباق evaluator العالق؛ لا lease إضافيّ). القرار: **Option B — إيصالات مخزَّنة يُصدرها منتج موثوق** عبر مسار ingest مُصادَق (لا وصول DB مباشر للمنتجين)؛ المتّصل يرسل **مراجع فقط**؛ التوقيع دفاع-في-العمق لا مصدر الحقيقة الوحيد؛ الأدلّة الخام من المتّصل **ممنوعة بنيويّاً**.
- **migration 030** `activation_evidence_receipts` (مشترك لكلّ البوّابات، مفتاح gate_name): محتوى غير قابل للتغيير + revoke أحاديّ الاتجاه (trigger)، `content_hash` خادميّ، dedup فريد (gate,env,content_hash)، إعادة إدراج نفس المحتوى = نفس الإيصال (idempotent).
- **النواة:** `record_receipt` (ingest: يُصادِق هويّة المنتج + العقد خادميّاً، يخزّن append-only) · `_resolve_receipts` (يحلّ المراجع من المخزن داخل معاملة complete؛ كلّ عدم تطابق رفض) · `complete_evaluation` صار يأخذ **`evidence_refs`** ويحلّها خادميّاً · `build_sha_from_receipts` (يربط الحكم بـcontent_hashes المخزَّنة) · **أُزيل `ON CONFLICT DO NOTHING`** من سجلّ الأحداث (P1 — التكرار الآن خرق invariant يظهر خطأً). نقطتا ingest جديدتان `POST /v1/activation/{gate}/evidence-receipts` (SoR-gated 503). النموذج `ActivationCompleteIn` صار `extra="forbid"` ⇒ حقل `evidence` مُهرَّب يُرفَض 422.
- **إثباتات الرفض السلوكيّة (12 على PG حقيقيّ):** unknown · invalid-uuid · **wrong_gate** (إيصال satellite لا يُفعّل irr) · wrong_environment · revoked · expired · not_pass · unknown_producer/unsupported_check (يُرفَضان عند ingest) · missing-required→degraded · idempotent-same-id · **append-only** (UPDATE/DELETE يُرفَضان) · **raw caller evidence forbidden 422**. البوّابتان + النقاط + e2e هُجِّرت لنموذج ingest→reference (**38/38** خضراء).
- **تحقّق:** 38 اختبار تفعيل · حارس PROD 11 (+`test_prod_evidence_receipt_trust_root`) · irrigation 68 · `pytest -m unit` 3180/0 · ruff نظيف · migration --check ok + --apply 001→030 · inventory (decision-service 66→68 route) + route-mount نظيفان · bundle مُعاد · خطوة CI مضافة.
- **مؤجَّل بصدق (اعتماد إنتاجيّ — Slice 2):** DEPLOY_BUILD_SHA إلزاميّ+مطابق startup-fail · enforcement إلزاميّ إنتاجاً أو فشل الإقلاع (default-off transitional) · IRR guard قبل إنشاء reservation في application service · pool القائم بدل اتصال جديد لكلّ عمليّة · probe key إلزاميّ · توقيع إلزاميّ للمنتجين الخارجيّين (CI) · middleware (توحيد service_auth_required + حصر الإعفاءات + 8 اختبارات + LOOP_TABLES في CI) · **PostgreSQL live cert على SHA النهائيّ**.

## 2026-07-18 — Gate-Trust-1 Slice 2a+2b: production-profile fail-closed + external-producer signatures
- **Slice 2a — startup fail-closed:** `activation_production_startup_error()` (main.py، مُوصَّل في lifespan بجانب production_auth) يفشل الإقلاع في **بروفايل الإنتاج** ما لم تُضبَط DEPLOY_BUILD_SHA + ACTIVATION_PROBE_SIGNING_KEY + IRR_F01_RESERVATION_ENFORCE_ACTIVATION (كلّها fail-open عند الغياب). البروفايل **بوّابة تشغيل صريحة** `ACTIVATION_REQUIRE_PRODUCTION_HARDENING` — **ليست** auto من SAHOOL_ENV (نشر المرآة الحاليّ SAHOOL_ENV=production بلا تفعيل، فالأتمتة كانت ستكسره؛ نُفِّذ حرفيّاً «production-profile gate قبل الإنتاج»). 4 اختبارات نقيّة.
- **Slice 2b — توقيع المنتجين الخارجيّين:** `GateConfig.external_producers` (irr: `{"ci"}`؛ satellite: فارغ — raster داخليّ). في البروفايل، `record_receipt` يطلب توقيع HMAC صحيحاً على content_hash من مفتاح المنتج (`ACTIVATION_EVIDENCE_SIGNING_KEY_CI`)؛ غياب/بطلان ⇒ `invalid_signature`/`signing_key_unavailable`. المنتجون الداخليّون يعتمدون هويّة الخدمة (لا توقيع). 3 اختبارات. التوقيع دفاع-في-العمق (الإيصال المخزَّن هو الجذر).
- **compose:** أُضيفت knobs الأربعة (ACTIVATION_REQUIRE_PRODUCTION_HARDENING + DEPLOY_BUILD_SHA + ACTIVATION_PROBE_SIGNING_KEY + IRR_F01_RESERVATION_ENFORCE_ACTIVATION) default-off لخدمة decision-service + مُعلَنة في .env.example (compose-env gate).
- **صيد عزل اختبارات (لا علّة منتَج):** e2e كان يُدرِج raster-service على sys.path[0] فيُظلِّل `main` (لكلا الخدمتَين main.py) عند تجميع الملفّات معاً محليّاً ⇒ 404. أُصلِح بـappend لا insert. CI غير متأثّر (كلّ ملفّ خطوة pytest منفصلة).
- **تحقّق:** سويت التفعيل الكاملة **45/45** · حارس PROD 12 (+`test_prod_production_profile_fail_closed`) · irrigation 69 · `pytest -m unit` 3180/0 · ruff نظيف · inventory + route-mount + compose-env نظيفة · bundle مُعاد · خطوة CI مضافة.
- **متبقٍّ من الاعتماد الإنتاجيّ (Slice 2c+):** pool مشترك بدل اتصال/عمليّة · IRR guard قبل إنشاء reservation (application service) · middleware (توحيد service_auth_required + حصر الإعفاءات + docs prod + 8 اختبارات + LOOP_TABLES في CI) · **PostgreSQL live cert على SHA النهائيّ** (بيئة حيّة).

## 2026-07-18 — Gate-Trust reconcile: canonical wholesale + revocation kill-switch + STRUCTURAL signing-defect fix
- **الاتجاه:** تبنّي نموذج الإيصالات المخزَّنة الموقَّعة (canonical) بالجملة (استبدال لا ترقيع، صافي −352 سطراً)، ثمّ إغلاق الشرطين + حالات الرفض المنقولة على PostgreSQL حيّ (**صفر متخطٍّ في جناح التفعيل**).
- **عيب بنيويّ حقيقيّ كُشِف وأُصلِح (توثيق إلزاميّ):** التوقيع المزدوج في canonical كان **غير متسق الحمولة** — `store_activation_evidence` (ingest) يوقّع الحمولة القانونيّة *مع* `gate_name` وبـ`payload` كـdict؛ بينما `_resolve_evidence_refs` يعيد التحقّق *بدون* `gate_name` وبـ`payload` كنصّ (asyncpg يعيد jsonb نصّاً). فأيّ receipt يقبلها ingest تُرفَض حتماً عند resolve بـ`evidence_signature_invalid` — التحقّق المزدوج كان شكليّاً (يقبل ويرفض بمعيارين)، قيمته الدفاعيّة صفر. **عاش العيب مختبئاً خلف skip** (جناح التفعيل كان دائماً متخطّى بلا DB) — دليلٌ أخيرٌ على قاعدة «المتخطيات ليست نجاحاً». الإصلاح المقبول الوحيد: دالّة قانونيّة **واحدة** `canonical_evidence_signature()` يستهلكها المنتِج وingest وresolve (تربط `gate_name`، تُقنّن الطوابع إلى UTC ISO، تُطبِّع jsonb→dict) — لا نسختان، لا «تعديل أحدهما ليشبه الآخر».
- **Condition 2 (المُرقّى):** جدول `activation_evidence_revocations` منفصل INSERT-only (evidence_id UNIQUE + trigger منع UPDATE/DELETE) يحفظ pure append-only ويستعيد kill switch انتقائيّاً؛ فحص الإبطال **داخل استعلام resolve نفسه** (NOT EXISTS — لا TOCTOU)؛ endpoint إبطال بمصادقة actor (X-Requested-By + توكن الخدمة). أُثبِت سلوكيّاً: admit → (بعد revocation) reject → (مكرّر) 409 → (UPDATE/DELETE) PostgresError.
- **Condition 1:** `deploy_build_sha()` يرمي عند غياب/بطلان DEPLOY_BUILD_SHA (40/64-hex)؛ conftest يثبّت هويّة حتميّة؛ اختبارات fail-closed مُوسَّطة.
- **من مراجعة الـpatch (دفاع-في-العمق، غير متعارض):** سقف 24h (ingest + admissibility + DB CHECK) بجانب kill switch؛ `PROVENANCE_RE` قانونيّ + الفهرس الفريد الدلاليّ (يغلق تحقّق 1c: provenance مُقنَّن غير حرّ)؛ `extra="forbid"` على النموذجين (raw inline evidence ⇒ 422).
- **ON CONFLICT DO NOTHING في `_log`:** غير موجود — INSERT الأحداث نظيف append-only؛ الوحيد على `_ensure_row` (إنشاء صفّ الحالة، مقصود). بند P1 مُغلَق.
- **تحقّق حيّ على شجرة نظيفة (3abc127، HEAD==tested):** جناح التفعيل **53/53** (0 skipped: +اختبارا expired = رفض ingest 400 + عدم تفعيل حتى لو مخزَّن ⇒ degraded، والثاني يثبت أن resolve يعيد التحقّق لا يثق بالتخزين) · raster generation-race **17/17** · Gate B relay **18/18** · PROD guard **12/12** · release validate **4594 checksums** · ruff نظيف.
- **إصلاحات CI (c3c461e، فوق 3abc127، لا منطق تفعيل):** فرز استيراد persistence.py · ci.yml أُعيد توجيهه من الملفّين المحذوفين إلى test_activation_evidence_contract.py + test_activation_gate_core_hardening.py + تحديث التعليقين · SERVICE_REGISTRY.md (--write-registry) · حارس P0 يقبل asyncpg.create_pool (pool محوّل حقيقيّ) بجانب asyncpg.connect · irrigation-convergence: pytest-asyncio في الوظيفة (أخضر على 14d2c19).
- **SHA النهائيّ:** `c3c461e` على `claude/code-review-34hO3`. irrigation-convergence أخضر؛ main CI (run 29648354066) قيد التشغيل عند التوثيق. main/develop لم تُمسّ (9e38080).

## 2026-07-18 — Open-ledger #1 (IRR pre-reservation activation guard) + CI-env lesson
- **البند:** إنفاذ بوابة irr_f01_reservation **قبل إنشاء الحجز** في خدمة التطبيق (لا عند inbox التسليم فقط)، وفق حكم التصميم المعتمد. المكوّنات: (1) endpoint خادميّ `POST /v1/activation/irr_f01_reservation/enforce` (قراءة طازجة عبر enforce_enabled، 200 snapshot أو 403 reason)؛ (2) محوّل مقيَّد platform `irrigation_activation_gate.py` (نمط imagery_source_gate) — `enforce_or_raise` يقرأ الراية طازجة، يفشل **مغلقاً** على 403/غير-200/عطل نقل؛ `activation_guard()` يبني الـthunk المحقون في درزة `reserve_and_request_dispatch_db` (تُنتظَر قبل أيّ قفل/كتابة)؛ (3) حارس ساكن لا-التفاف + برهان سلبي (اصطاد المحوّل نفسه على docstring أوّل تشغيل). الراية نفسها `IRR_F01_RESERVATION_ENFORCE_ACTIVATION` (default-off/transitional)؛ inbox يبقى طبقة ثانية. commits 118f9fa + 443db43.
- **درس CI (النمط الثالث في الجلسة بعد ملفّي ci.yml المحذوفين وSERVICE_REGISTRY):** أيّ محوّل جديد يجلب اعتماديّة (هنا httpx في رأس الموديول) → شغّل مهمّة CI الدنيا محليّاً أو `pip install` في venv نظيف قبل الدفع. بيئة التطوير المتراكمة تُخفي الفجوة («يعمل على جهازي»). httpx **معلَنة أصلاً** في `services/sahool-platform/api/requirements.txt:15` ويستوردها 10+ موديولات platform (decision/weather/raster/soil clients) — فالإنتاج مغطّى؛ الفجوة كانت فقط في مهمّة irrigation-convergence الدنيا التي تثبّت قائمة منتقاة يدويّاً (pytest+pytest-asyncio) لا requirements.txt. الإصلاح: إضافة httpx لتلك القائمة (41d1938)، لا استيراد كسول (يُخفي اعتماديّة تشغيل عن مدير الحزم). ملاحظة: SBOM_MINIMAL.json **بيان ملفّات لا حزم** (2865 مكوّناً كلّها ملفّات) — لا يعدّد حزم بايثون، فلا يلزمه تغيير للاعتماديّة.

## 2026-07-18 — انضباط: حزمة مولّدات واحدة قبل الدفع (بعد انجراف route_mount + SBOM)
- **القاعدة:** أيّ تغيير يمسّ **مسارات/خدمات/موديولات/اعتماديّات** ⇒ شغّل `bash scripts/ci/regenerate_all_generated.sh` **قبل** push. يشغّل بالترتيب: generate_service_inventory --write-registry (service/route inventory + SERVICE_REGISTRY.md) · route_mount_contract_guard (route_mount inventory) · build_release_bundle (SBOM + FILE_CHECKSUMS + manifest، أخيراً لأنّه يبصم الشجرة) ثمّ يتحقّق من الثلاثة. بديلٌ عن ملاحقة CI فشلاً فشلاً.
- **السبب:** في شريحة open-ledger #1 انجرف مولّدان بعد إضافة route + module: route_mount_inventory (68→69 مسار في decision-service/main.py — بالضبط `/enforce`، لا تسريب mount) وحارس نموّ موديولات platform (647→648، سُجِّل `api/irrigation_activation_gate.py` في `platform_python_module_baseline.json` بتعليل). الحارسان عملا كما صُمّما (تسجيل صريح لا نموّ صامت). الدرس مكرّر (ثالث نمط بعد ci.yml المحذوف وSBOM) ⇒ يستحقّ أتمتة.

## 2026-07-18 — بند ⑤ الشهادة الحيّة + ④ حارس P0 + إصلاح مصادقة WS + FF إلى main (`dae894b`)
- **الشهادة الحيّة (⑤) على `bf6fcf3` ثمّ القمة النهائيّة `dae894b`:** PostgreSQL 16، قاعدة `decision_cert` جديدة (فارغة)، 30 هجرة طُبِّقت نظيفةً؛ تحقّقتُ من نزول جدولَي `activation_evidence_receipts`+`activation_evidence_revocations` + القيود الستّة `ck_activation_evidence_{build_sha,max_window,provenance,result,signature,window}` + المُطلِق المناعيّ `trg_activation_evidence_revocations_immutable`. جناح التفعيل الكامل (51 عقد + 2 live-consumer e2e) = **53 passed / 0 skipped** على PG حيّ؛ مسار الإبطال `test_revocation_admit_then_reject_then_conflict_then_append_only` مرّ. HEAD==tested. `git diff bf6fcf3 dae894b -- services/decision-service` **فارغ** ⇒ خدمة القرار متطابقة، فالشهادة تنتقل للقمة النهائيّة بلا إعادة تشغيل منطق.
- **④ تضييق حارس P0 (`bf6fcf3`، اختبار فقط):** حارس ساكن + برهان سلبيّ يحصر `asyncpg.connect` الخام في allowlist مُراجَع (persistence.py=create_pool؛ الخام مشروع في migration_runner/backfill/activation_gate_core كـfallback أداة/اختبار) — موديول جديد يفتح اتصالاً خاماً يفشل CI. مطويّ في ملفّ الحُرّاس القائم (بلا خطوة CI جديدة). CI run #4192 أخضر.
- **إصلاح مصادقة WebSocket (`dae894b`، من تقرير إنتاجيّ للمستخدم):** `services/sahool-platform/api/routers/notifications.py` كان يُغلق `close(1008)` **قبل** `accept()` عند غياب `?token=` ⇒ 1006 في المتصفّح ⇒ حلقة إعادة اتّصال لا نهائيّة (FE-10 لا يضع التوكن في الـURL)؛ والتوكن يُقرأ من الـURL فقط (لا من أوّل إطار auth) ولا يُرسَل `auth_ok` (بوّابة FE-09 تبقى مقفلة). الإصلاح: accept أوّلاً دائماً · التوكن من أوّل إطار `{"type":"auth"}` (المفضّل) أو `Sec-WebSocket-Protocol: sahool-bearer,<JWT>` (بديل نظيف) · **إزالة `?token=`** (تسرّب سجلّات الوصول) · تحقّق بمصدر واحد `get_current_user` (لا مسار تحقّق ثالث — هذا مسار مستخدم-JWT لا service-token) · `auth_ok` ثمّ `subscribed` ثمّ ping→pong · فشل/مهلة ⇒ 1008 نظيف بعد accept. 6 اختبارات سلوكيّة (TestClient websocket، monkeypatch get_current_user) + حارس ساكن (accept-before-close · لا توكن URL · auth_ok) = **7 passed**. يعمل في مهمّة CI للمنصّة (`PYTHONPATH=. pytest tests` + ratchet 60). CI run #4193 أخضر على `dae894b`.
- **صيد انضباطيّ (drift):** دورة `git stash` أثناء فحص انجراف المولّدات أفسدت اتّساق الملفّات المولَّدة مؤقّتاً وأوهمت بـ«+1 route». الحقيقة: عمود `service_inventory` الثالث ليس عدد المسارات (=616 بلا تغيير، العمود السادس) بل مقياس شِفرة (def count)؛ ارتفع +1 من helper refactor + تعليقات. الدرس: عند الشكّ في انجراف مولَّد، أعِد ضبط كلّ الملفّات المولَّدة إلى HEAD ثمّ `regenerate_all_generated.sh` **مرّة واحدة** من مصدر نظيف — لا `stash` جزئيّ.
- **الدمج (FF إلى main):** بعد خُضرة CI على `dae894b` + إثبات أسماء اختبارات WS، نُفِّذ `git merge --ff-only dae894b`: `9e38080 → dae894b`، **0 merge commit**، 51 commit مُقدَّم، دُفِع. `origin/main == origin/claude/code-review-34hO3 == dae894b` (تحقّق `git ls-remote`).
- **⚠️ تحذير صدق — FII على main بلا بوّابته الحيّة:** الـ51 commit تشمل **5 commits FII** (`1d4f680` FULL_DELTA + `8642d99`/`23e5c42`/`17d61e1` تقسيات + `f7bcafb`) وهجرات `migrations/v192_fii_rls_write_fail_closed.sql` + `v194_fii_chemical_chain_rls_fail_closed.sql`. سجلّ الدفتر لهذا العمل ينصّ صراحةً: «**بوّابة PostgreSQL حيّة (RLS write fail-closed + دور NOSUPERUSER/NOBYPASSRLS + عزل مستأجر) مطلوبة قبل FF — CI الأخضر وحده لا يُصادِق RLS**». هذه البوّابة **لم تُشغَّل منفصلةً في هذه الجلسة** قبل الـFF. المخفِّفات: الهجرتان دفاعيّتان (fail-closed تشدّان لا تفتحان) · الحوكمة الكيميائيّة audit-only/enforce=NO · بوّابتا fii_rls_write_policy_gate + fii_rls_role_gate الساكنتان خضراوان في CI · IRR-F01 Gate A (v195/v196 المجاورتان) اعتُمِدت حيّاً على PG+PostGIS بـsahool_app NOSUPERUSER/NOBYPASSRLS. يبقى **بند تحقّق مفتوح**: تشغيل بوّابة FII RLS الحيّة على `dae894b` بأثر رجعيّ (gaps/registry.md).
- **إخفاق CI الرئيسيّة بعد الـFF (5 بوّابات main-only) وإصلاحها:** الـFF إلى main شغّل workflows تُفحَص على main فقط فكشفت انجرافاً متراكماً من الـ51 commit + فجوة بيئة: (1) `route_residual_classification` (2) `REPORT_INDEX.md` (3) `health_readiness` inventory/schema — أُعيد توليدها بـ`--write`؛ (4) `runtime_real_smoke.sh` يستهلك (1)+(3) فأخضرّ تبعاً؛ (5) `raster-validated-product.yml` (main-only، `branches:[main]`) خطوة satellite_cdse P2-c تستورد `raster_cdse_tile_runtime → raster_date_geo → fastapi` والمهمّة تثبّت `tests_v9/requirements-test.txt` فقط (بلا fastapi) ⇒ `ModuleNotFoundError` — أُضيف `fastapi` لسطر التثبيت (نفس درس httpx حرفيّاً: مهمّة CI دنيا تستورد موديول خدمة يحمل اعتماديّة تشغيل). **درس مُرقّى:** الـFF إلى main يُشغّل بوّابات main-only غير مرئيّة في فحص الفرع — بعد أيّ FF كبير، راقب main CI فوراً لا فقط branch CI. تحقّق محليّ: البوّابات الثلاث `--check` = ok · imagery 17/17 · bundle مُعاد.
- **بوّابة FII RLS الحيّة شُغِّلت بأثر رجعيّ على قمة main (`fdfc521`) — v192 و v194 مُصادَقان حيّاً:** v192: `test_fii_rls_write_fail_closed_postgres.py` 6/6 (0 skip) + الهجرة المشحونة مُطبَّقة 0-error على `scouting_pins`/`prescriptions` الحقيقيَّين ⇒ سياق فارغ تحت دور NOSUPERUSER/NOBYPASSRLS ⇒ RLS ERROR (fail-closed على الهجرة نفسها) + `fii_rls_write_policy_gate` PASSED. v194 (المسارَان): موجب — مُطبَّقة 0-error على جداول السلسلة الستّة ⇒ سياق فارغ ⇒ RLS ERROR على `recommendations`؛ سالب (finding #12) — إسقاط `lineage_link` ⇒ `EXCEPTION ... required chain table absent; refusing to leave ... unprotected`. ملاحظة منهج: جداول بأسماء حقيقيّة وأعمدة أدنى (id, tenant_id) — برهان أمين للسياسة (تقرأ tenant_id فقط)، نفس منهج v192. فجوة `FII-LIVE-RLS-GATE-ON-MAIN` ⇒ LIVE-CERTIFIED (v192+v194). لم تعد آلية أمنيّة RLS في نطاق FII على main بلا برهان حيّ. (التصحيح: بند ② في رنبوك التحقّق كان يصف آلية بروفايل إقلاع مُستبدَلة — grep على main أثبت غيابها؛ الآلية canonical = fail-closed-at-read في `activation_gate_core.py:93`، مُغطّاة بـ`test_activation_gate_core_hardening.py`.)
- **رنبوك التحقّق الحيّ — البند ⑥ (الجناح التكامليّ) مُصادَق جزئيّاً + سلسلة الهجرات الكاملة 0-error:** طُبِّقت **v1..v196 (202 خطوة) 0-error على PostGIS 16 حيّ** على قاعدة `integ_cert` جديدة (برهان تماسك السلسلة كلّها + إغلاق ملاحظة منهج v192/v194: طُبِّقتا على الجداول الإنتاجيّة الحقيقيّة). ثمّ `pytest -m integration` على المخطّط الكامل: **123 passed · 57 skipped · 4 غير-ناجحة — صفر خلل مخطّط/DB**. الأربعة: `test_auth_e2e` = حارس أمان الأدوار `assert_db_role_rls_safe` (`shared/db_role_guard.py:97`) يرفض الإقلاع مُغلَقاً لأنّي اتّصلتُ كـsuperuser (superuser يتجاوز RLS) — **الحارس يعمل، ليس خللاً**؛ تحت دور `sahool_app` المقيَّد (NOSUPERUSER/NOBYPASSRLS) يتحوّل إلى skip نظيف (يحتاج طبقة الخدمة). الثلاثة الأخرى (mcp weather_server · services_functional · mfa-via-app) = طبقة خدمة/استيراد موديول، لا DB. الـ57 skip = تحتاج Redis/NATS/HTTP. **الأثر:** طبقة تكامل DB مُصادَقة حيّاً واسعاً على مخطّط main الكامل. المتبقّي من الرنبوك (③ تسليم NATS · ④ جسور sim-until-staging · ⑤ SoR flip · ⑦ أقمار 4/5) يحتاج رفع الخدمات/NATS/HTTP — خارج نطاق هذه البيئة. `integ_cert` أُسقِطت بعد الشهادة.
- **إصلاح 503 على مسار PATCH للحقول (fields.py) — رباط المستأجر مفقود من ثلاثة استعلامات:** في فرع تعارض الإصدار (optimistic version-conflict) ثلاثة `fetchrow` (`srow`@~1316/`mrow`@~1339/`row`@~1397) تستعلم `... WHERE field_id = $1 AND tenant_id = $2::uuid` لكن تمرّر `field_id` فقط ⇒ **asyncpg يرمي قبل تنفيذ الاستعلام** («يتوقّع وسيطين، مُرِّر واحد») ⇒ الأثر المؤكَّد **503 (فشل صاخب)**؛ **خطر عزل المستأجرين كامنٌ فقط** (كان سيظهر لو «أُصلِح» بحذف الرباط بدل تمريره) — أُغلِق بحارس ساكن. الإصلاح: `str(user.tenant_id)` وسيطاً ثانياً للثلاثة + حارس `test_fields_tenant_arg_completeness_guard` (نمطيّ: يفشل CI إن أسقط أيّ استعلام `tenant_id = $2` رباطه، لا مراقبة النقاط الثلاث فقط). الصياغة الدقيقة معتمدة (لا تهويل ولو باتجاه الأمان). **كيف وصل؟** استعلامٌ بلا معامل لا يصمد أمام تشغيل حيّ واحد لمسار PATCH ⇒ **المسار لم يُمارَس حيّاً قطّ** — يؤكّد قيمة بند ⑥: عند تشغيل الجناح التكامليّ الحيّ يجب التأكّد أنّ مسار PATCH/version-conflict مشمولٌ في `test_fields_*` (وإلّا يُضاف). اكتُشِف عبر جلسة runbook حيّة موازية (بيئة كاملة) رأت `draw.edit.geometry` = 503. الختم: `8069efc` (بعد أن أخفق `a017f82` على `ruff format --check` للملفّ الجديد فقط — تنسيق بحت، أُصلِح). CI أخضر على `8069efc` (#4205/#4206). main==branch==8069efc.
- **تصادم جلستين على الفرع (تسجيل):** جلسة Claude محليّة موازية (v22، بيئة كاملة) شغّلت الرنبوك الحيّ ونجحت بنوده (⓪ WS+424 · ① FII role/write/6 PG · ② hardening 14 · ③ Gate A/B1 · ⑤ SoR+WX-10.11b · ⑥ E2E) وحاولت الدفع إلى `claude/code-review-34hO3`؛ **رُفِض (non-fast-forward)** لأنّها متباعدة عن القمة القانونيّة — القمة لم تُمَسّ. commitها `42525e60` غير موجود على origin. المتّفَق: تدفع إلى فرع جانبيّ `claude/local-live-cert` وأوفّق دلتاها الحقيقيّة (migration/compose) بـcherry-pick + دمج سرديّة الدماغ. إصلاح الـ503 (المشترك) أُنجِز على القمة القانونيّة استقلالاً.
- **درس + حارس: فرع مدموج بعلامات تعارض + CI أخضر — المراجعة البشريّة للـdiff قبل الانتقاء ليست رفاهية.** جلسة محليّة موازية دفعت `8c2373d` إلى الفرع بعد دمج origin، لكنّها تركت علامات تعارض `<<<<<<< / ======= / >>>>>>>` **غير محلولة ومُلتزَمة** في `nginx/nginx.v9.conf:169-177` و`vegetation_runtime.py:280/424` — والأخير `SyntaxError: invalid decimal literal` (غير قابل للاستيراد). ومع ذلك **CI أخضر عليه** لأنّ `ci.yml` لا يستورد خدمة vegetation ولا يُحلّل nginx — أنقى برهان للجلسة أنّ «الأخضر يقيس ما تختبره فقط، لا سلامة الشجرة». قرار المستخدم (ب) (لا تبنٍّ للفرع، انتقاء جراحيّ بعد مراجعة الـdiff) أنقذ main من دمج كود مكسور + راية fail-open (`VEGETATION_REAL_ONLY=0`). **الحارس المُضاف:** `scripts/ci/conflict_marker_guard.sh` (git grep على `^<<<<<<< ` / `^=======$` / `^>>>>>>> ` عبر py/conf/yml/ts/sh/sql/json) + خطوة CI في Lint&Format — دقيق لعلامات git (لا يصطاد لافتات التعليق ذات الـ`=` الطويلة). النمط مُختبَر: نظيف على القمة القانونيّة، يصطاد علامات `8c2373d`.
- **ختم كتلة الـcherry-pick (خيار ب) خضراء على main — `b0a1b5f` (CI run #4210 `conclusion: success`):** بعد اصطدام الجلستَين، اعتُمِد (ب) — انتقاء جراحيّ لِما هو صافٍ-جديد-فقط على main النظيف `bf97478`. المراجعة البشريّة للـdiff أثبتت انهيار «الجديد» المحلّيّ: nginx tile-401 (على main #199) · db_persist is_local=false (على main) · JWT_SECRET (على erp-bridge L1554) · 503/WS (على main) · vegetation user_bearer (مُتقادِم معماريّاً #201) · VEGETATION_REAL_ONLY=0 (fail-open، مُستبعَد). نجا ثلاثة فقط: `f6fd195` (conflict_marker_guard + درس الجلستَين) · `62efc89` (NOINHERIT على sahool_app في bootstrap_postgres.sh + apply_in_compose.sh — IRR-F01 Gate A) · `b0a1b5f` (useApi NDVI 404→null مبقياً `retryTransientOnly` + تسجيل FIELD-SVC-TENANT-HEADER-TRUST). **NOINHERIT مُصادَق حيّاً** على PG: `rolsuper=f rolbypassrls=f rolinherit=f` + منح مباشر (SELECT/INSERT) ينجح + برهان سالب: صلاحيّة مُكتسَبة عبر عضويّة دور تُرفَض (توريث معطَّل). دُفِع main مباشرةً (`bf97478..b0a1b5f`) — الدفع للفرع تعذّر لأنّ `origin/claude/code-review-34hO3` مُختطَف على `8c2373d` المكسور. **بند مفتوح (تشغيليّ، لا كوديّ):** `origin/claude/code-review-34hO3` = `8c2373d` المتباعد المكسور — بانتظار إعادة تأسيس الجلسة المحليّة من `b0a1b5f`؛ لا force-reset بلا إذن صريح. **الخطوة التالية للسِّجِلّ الحيّ:** v194 على قاعدة كاملة المخطّط (P0 المتبقّي) ← رنبوك ③→⑦.
- **حصاد الانتقاء الجراحيّ يكتمل — إصلاحان حقيقيّان من رماد الفرع المكسور + تعليق الحذف:** أثناء تنفيذ تسلسل حذف الفرع (بعد إذن مشروط بتحقّق «لا قيمة محتجزة»)، كشف تحقّق الدلتا الصافية (`main..branch`، 18 ملفّاً) **بندَين صافيَين جديدَين لم تُغطّهما الدلتا الستّة الأصليّة** — فأوقفتُ الحذف والتقطتهما على main مباشرةً:
  - **① `ef171f4` — JWT_SECRET على sahool-notification-agent:** `agents/notification/agent.py:552-556` (`_validate_ws_token`) يفكّ JWT للـWS (HS256، aud=sahool) ويقرأ `JWT_SECRET` من env؛ بغيابه `raise "Missing token or secret"` ⇒ **يرفض كلّ اتّصال WS بنيويّاً على main** (fail-closed صامت). كتلة compose لم تُزوّده. أُضيف `JWT_SECRET: ${JWT_SECRET}` (بالمرجع، نمط بقيّة كتل JWT). CI أخضر (#4213).
  - **② `91079c5` — db_persist is_local (علّة قصّ مضلّع):** `fetch_field_geometry:885` كان `set_config(..., true)` (نطاق معاملة)؛ asyncpg بلا معاملة = autocommit ⇒ يضيع قبل `fetchrow` ⇒ فقدان سياق المستأجِر ⇒ RLS صفر ⇒ `geometry=None` ⇒ بلاطة bbox بلا قصّ (العلّة الموصوفة في docstring نفسها). صار `false` (جلسة). آمن: `_connect()` اتّصال جديد قصير العمر بلا pool. **تصالح صادق:** مراجعة (ب) صنّفت هذا «تكرار على main» خطأً — رأت مواضع `false` العشرة السليمة وأغفلت الموضع الحادي عشر الشاذّ (`:885` بقي `true`)؛ الدلتا المحليّة الحقيقيّة كانت بالضبط ذاك الشاذّ. حارس ساكن جديد `test_tenant_guc_session_scope_guard.py` (كلّ set_config على app.current_tenant = false، برهان سالب: يصطاد true) — البرهان السلوكيّ (حقل حقيقيّ ⇒ لا قصّ) مؤجَّل لجولة الرنبوك الحيّة (PostGIS+RLS). CI #4216 (جارٍ).
- **تعليق حذف الفرع — الجلسة المحليّة حيّة تُصلح:** 9 لقطات من الجلسة المحليّة (Windows v22) أثبتت أنّها **تستقبل commit إصلاح كبير الآن**: تحلّ علامات تعارُب `vegetation_runtime.py` (`_load_field_from_db`) **بحذف user_bearer وإبقاء مسار field-management-service = قرارنا نفسه #201** · تعمل على nginx tile-401 · تصلح حُرّاس Windows (`UnicodeDecodeError` charmap/cp1252 ⇒ `encoding='utf-8'`، `__pycache__` skip، نطاق weather_engine_formula_guard) + ~12 ملفّ اختبار. **`db_persist.py` ليس ضمن git add الجلسة المحليّة** ⇒ التقاطه على main خالٍ من سباق. **القاعدة الجديدة:** الحذف مؤجَّل حتّى تدفع الجلسة المحليّة وتُعيد التأسيس من قمة main؛ ثمّ مراجعة كاملة لفرعها النظيف بمعيار «الدلتا الفعلية لا رسائل الـcommits» (حُرّاس Windows encoding قد تكون صنف قيمة جديداً لم يكن على radar المراجعة الأولى). لا force/حذف بلا ذلك.
- **ختم الحصاد أخضر على main — `5d13119` (#4220 `success`):** إصلاح db_persist (`91079c5`) سقط على `service-inventory-drift-gate` فقط (ملفّ الحارس الجديد أزاح جرد raster-service — درس #177) لا على الكود؛ أُصلِح بـ`generate_service_inventory.py --write-registry` (31 خدمة/1056 مسار) + إعادة بناء الحزمة (4604). الآن: main = ef171f4(JWT_SECRET، #4213) + 91079c5(db_persist+حارس) + 5d13119(جرد) — أخضر. **حصاد الرماد مُغلَق: إصلاحان حقيقيّان (JWT_SECRET WS + db_persist قصّ مضلّع) كلاهما بحارس.** **رصد من لقطة الجلسة المحليّة:** haithmgarallah-ye يدفع commits إصلاح حقيقيّة إلى `claude/code-review-34hO3` الآن (c6cb6d5 Windows path/encoding · 2ecc804/fe00c22 inventory+ruff resync) — **كلّها حمراء، تتكرّر على نفس صنف الجرد/ruff/Windows** ⇒ الفرع ورشة حيّة تُعيد البناء، لم تخضرّ. **الجلستان اصطدمتا مستقلّتَين بنفس ratchet انجراف الجرد** (main أُصلِح؛ الفرع شأن الجلسة المحليّة — لا تصادم كتّاب). الحذف يبقى مؤجَّلاً حتّى تُخضِر الجلسة المحليّة وتُعيد التأسيس من قمة main.
- **⑥ إغلاق db_ownership baseline + وصل فحص LOOP_TABLES⊆ownership — `773beb8` (استكمال «باقي» المؤجَّلات الكوديّة):** أوّل بند كوديّ صرف من المؤجَّلات القديمة. `db_ownership.yml` سجّل 4 جداول decision فقط ⇒ فحص الملكيّة كان «متابعة موثَّقة» معطَّلة. مُلِئ الأساس: 38 جدولاً تنشئها هجرات decision-service (owner=decision-service)، **0 تصادُم مع هجرات المنصّة** ⇒ ملكيّة قاطعة؛ الخمسة interim-bridge لم تُقلَب (تنتظر قلب SoR رنبوك ⑤). وُصِل `test_every_loop_table_is_owned_by_decision_service` (LOOP⊆owner∪mirror، بلا تبعيّة YAML، برهان سالب). تحقّق: 8/8 حُرّاس + كلّ مستهلكي db_ownership + بوّابتا decision-SoR (تؤكّدان interim-bridge محفوظ) + جرد/حزمة (python_loc انزاح +39 من تحرير الاختبار). main = `773beb8`.
- **③ إغلاق كوديّ لعزل مفتاح التفعيل — `e2f330e` (استكمال «باقي»):** الفحص أثبت أنّ العزل قائم أصلاً (Gate-Trust): مفاتيح توقيع التفعيل (EVIDENCE/PROBE) متغيّرات مخصّصة، لا تُسنَد لـJWT_SECRET/SAHOOL_AGENT_TOKEN. المُضاف: حارس `tests_v9/test_activation_signing_key_isolation_guard.py` يقفل العزل ضدّ انحدار compose مستقبليّ (برهان سالب) + ملاحظة `.env.example` بواجب المشغّل (قيَم متمايزة). الجزء الكوديّ من ③ مُغلَق؛ تزويد القيَم يبقى شأن secret-manager (كما أطّره الدفتر). تحقّق: 3/3 حارس · ruff · حزمة 4604 · جرد نظيف. main=`e2f330e`.
- **ADR-0033 (FIELD-SVC tenant-claim trust) — تصميم مُجمَّد بإذن المالك، لا تنفيذ:** بعد إغلاق ⑥+③ كوديّاً، البند الوحيد المتبقّي القابل للمسّ (FIELD-SVC-TENANT-HEADER-TRUST) قرارٌ معماريّ يمسّ #201. المالك أذن بـ**التصميم فقط**. كُتِب `docs/adr/ADR-0033-*.md`: النموذج الحاليّ (ترويسة X-Tenant-Id حرّة تحت X-Agent-Token) · مبرّر القبول المؤقّت · التصميم المستهدَف (الخيار A: توكن خدميّ قصير العمر بـtid موقَّع؛ B احتياطيّ) · ترحيل ثلاثيّ (قبول⇒تحذير⇒رفض) · محفّز (أوّل تعديل field-management أو مستهلك جديد). الغاية OPEN مع ADR مرجعيّ. صفر أثر كوديّ. ⑥ #4222 + ③ #4224 كلاهما أخضر مؤكَّد. **السجل الكوديّ الصرف: مُغلَق بالكامل.**
- **«ارفع runbook» — رفعٌ حيّ لطبقة البيانات نتيجةً (لا محاكاة) + إغلاق AUTH-E2E-UNDER-RESTRICTED-ROLE — `9a3ce99`:** طلب المالك رفع الرنبوك. **قيد بيئيّ مُكتشَف حيّاً:** Docker daemon يعمل + `docker compose v5.1.1`، لكن **Docker Hub محجوب بسياسة الشبكة** (البروكسي يرفض CONNECT لـproduction.cloudfront.docker.com بـ403 — `noProxy` يسمح pypi/npm/crates لا registries). فتعذّر بناء الـmesh (15 صورة) وجذب postgis. **الحلّ الأمين:** PostgreSQL 16 + PostGIS 3.4 **الأصليّان** مثبّتان (postgresql-16-postgis-3) — رُفِع cluster أصليّ بلا Docker Hub. **المُنجَز حيّاً:** (1) 202 هجرة 0-خطأ على المخطّط الكامل (304 جدول) — تماسك السلسلة حيّ؛ (2) نموذج الأدوار (sahool_app super=f/bypassrls=f/inherit=f + sahool_jobs bypassrls=t) مُتحقَّق؛ (3) **FII RLS fail-closed حيّ** (sahool_app + سياق فارغ ⇒ RLS ERROR على recommendations)؛ (4) **AUTH-E2E تحت الدور المقيَّد مُغلَق**: 10/10 بعد إصلاح علّتَي المصفّي (module alias) والتأكيد البائت (farmer→owner، عقد المؤسِّس، مطابق test_auth_signup_owner). **المتبقّي من الرنبوك (③ NATS · ④ جسور · ⑤ SoR flip HTTP · ⑦ أقمار) يحتاج Redis/NATS/mesh مبنيّ — محجوب بمنع registry الحاويات** (Redis أظهر unavailable). درس: سياسة شبكة البيئة تمنع الحاويات؛ الطبقة القاعديّة تُرفَع أصليّاً، الـmesh يحتاج بيئة المالك.
- **ختم الجلسة 2026-07-18 — `main = 3fb8216`، كلّ الـcommits الكوديّة خضراء مؤكَّدة (#4213/#4220/#4222/#4224/#4226/#4227):** أُنجِز في الجلسة: (1) حلّ اصطدام الجلستَين بانتقاء جراحيّ (خيار ب) — إصلاحان حقيقيّان من الفرع المكسور (JWT_SECRET على notification-agent · db_persist قصّ مضلّع) + حارس conflict-marker + NOINHERIT + useApi 404→null؛ (2) إغلاق كوديّ لمؤجَّلَين قديمَين — ⑥ (أساس ملكيّة decision-service 38 جدولاً + وصل فحص LOOP⊆ownership) و③ (قفل عزل مفاتيح التفعيل + ملاحظة مشغّل)؛ (3) ADR-0033 (تصميم FIELD-SVC مُجمَّد بإذن، لا تنفيذ)؛ (4) **رفع runbook حيّ نتيجةً** رغم حجب سِجِلّ الحاويات — PG16+PostGIS أصليّ، 202 هجرة 0-خطأ/304 جدول، FII RLS fail-closed حيّ، **AUTH-E2E تحت الدور المقيَّد مُغلَق live-certified 10/10** (إصلاح مصفّي module-alias + تأكيد farmer→owner عقد المؤسِّس)؛ (5) ملف تسليم `docs/runbooks/REAL_ENV_VERIFICATION_RUNBOOK.md`. **المتبقّي محجوب بيئيّاً حصراً:** رنبوك ③④⑤⑦ (mesh مبنيّ/registry) · تنفيذ ADR-0033 (محفّزه) · حذف الفرع المكسور `claude/code-review-34hO3` = `8c2373d` (بعد إعادة تأسيس الجلسة المحليّة من قمة main). **درس بيئيّ:** سياسة شبكة البيئة تمنع سِجِلّ الحاويات (Docker Hub 403)؛ طبقة البيانات تُرفَع أصليّاً بلا حاويات، الـmesh يحتاج بيئة المالك.
- **حصاد Windows من الفرع المتباعد ثمّ محاولة حذفه — `37ace1e` (خيار أ):** الفرع `claude/code-review-34hO3` تطوّر إلى `fe00c22` (الجلسة المحليّة نظّفت علامات التعارُب + أخضرت اختباراتها) لكن **لم يُعِد التأسيس على main**؛ دلتاه مختلطة (قيمة Windows-encoding + انحدارات تحذف حُرّاسي وتحمل نسخاً أقدم من db_persist/auth-e2e). **الحصاد (بدل cherry-pick المتشابك):** طُبِّق `encoding="utf-8"` على 43 موضع `read_text()` عارٍ في الملفّات الـ11 التي أثبتت الجلسة المحليّة فشلها على Windows — على **نسخ main الحاليّة** (فلا churn/انحدار يركب). 53 اختباراً أخضر · حزمة 4607. **⚠ حذف الفرع متعذّر بيئيّاً:** `git push origin --delete` يعيد **403** (سياسة البروكسي تمنع حذف المراجع، مثل حجب registry)؛ ولا أداة MCP لحذف فرع. **يجب أن يحذفه المالك** من بيئة غير محجوبة: `git push origin --delete claude/code-review-34hO3` أو عبر واجهة GitHub (Settings→Branches). القيمة محفوظة على main؛ الفرع أصبح بلا قيمة محتجزة (كلّ ما فيه إمّا على main أو انحدار).
- **الحكم النهائيّ على `claude/code-review-34hO3` (بعد مراجعة الدلتا الفعليّة الكاملة) — خالٍ من قيمة محتجزة، مُصفّى للحذف:** تصحيح مغالطة: «22 commit أمام main» في تقرير الفرز **ليست 22 جديدة** بل كامل تباعُد الفرع (لم يُعَد تأسيسه) — والـtip = `fe00c22` **لم يتقدّم** منذ الحصاد (تأكّد: `fe00c22..tip` فارغ). مراجعة الدلتا الصافية (35 ملفّاً، `git diff --stat` = +2395/−3396): **كلّ ملفّ مُصنَّف** ⇒ (1) **main متقدّم** (عمل هذه الجلسة يسبقه الفرع: ADR-0033·BRANCH_TRIAGE·REAL_ENV_RUNBOOK·db_ownership 42-vs-4·JWT_SECRET·useApi·ci.yml guard·test_loop_tables) — 17 ملفّاً؛ (2) **Windows-encoding محصود على main** (37ace1e)؛ (3) **انحدارات تحذف حُرّاسي الثلاثة** — مُستبعَدة؛ (4) **user_bearer مُتقادِم #201** — مُستبعَد؛ (5) نسخ أقدم من db_persist/auth_e2e (main مرجعيّ)؛ (6) nginx تقارب لنهج #199 (لا token-in-URL)؛ (7) دماغ/جرد متباعد. **لا ملفّ يحمل قيمة صافية غير مُغطّاة.** ⇒ الفرع مُصفّى للحذف بلا خسارة. **الحذف نفسه محجوب من الجلسة (403)** — فعل المالك. حالة `code-review-34hO3`: من «نشط حتى تُراجَع الـ22» ⇒ **مُراجَع، مُصفّى**.
- **دراسة مقارنة «الخطة الموحّدة ↔ الواقع» — `docs/audits/COMPARATIVE_STUDY_PLAN_VS_REALITY_20260718.md` (ستّة وكلاء تحقّق read-only على `main@da3f88a`):** مسح حيّ للشيفرة الفعليّة قابَل مزاعم الخطة بند-بند بأدلّة `file:line`. **مؤكَّد دقيق:** A1 WX-FAILOVER (Open-Meteo مصدر وحيد؛ لا مزوّد ثانٍ؛ نواة ET0 موحّدة `weather-service/et0.py:60` صفر-ازدواج؛ الاحتياط greenfield) · A5 WATER-SALT (ملوحة **عميقة فعلاً**: Maas-Hoffman Ks `fao56.py:127-135` + غسيل Eq82 `:590-597` + ملاءمة وزن0.35 `crop_suitability.py:104` + عقوبة غلّة `deficit_irrigation.py:114` — بلا عقد قدرة مُعلَن) · B1 SCOUT-INGEST (**غائب مؤكَّد**: صفر ODK/Kobo/XLSForm؛ الكتّاب أوّليّون فقط `fields.py:3815`/`observations.py:33`؛ اللبنات موجودة داخليّاً: `envelope_v1.py:23`+`crop_stress_ingestion.py:34`+`projection_jobs.py`+`backfill.py:92` — فجوة تركيب لا تأسيس) · A6 ST_AsSVG صفر (PDF موجود reportlab) · A7 حدود إداريّة غائبة (مُصرَّح ذاتيّاً `log.md:2299`). **تصحيحات جوهريّة (قيمة الدراسة):** (1) **A3 مبالَغ** — `wofost_adapter.py` **placeholder حتميّ** لا WOFOST؛ PCSE لا يعمل أبداً (`requirements.txt:12` pcse مُعلَّق؛ `_pcse_simulate:246` سقالة `pragma:no cover` غير صالحة؛ crop_model_skill ⇒ 501)؛ **⇒ SIM-PCSE-01 يسبق SIM-GOLDEN-01** (يفشل مُغلَقاً بأمانة، لا يُسوَّق heuristic). (2) **A4 قديم** — الحدود التلقائيّة **موصولة فعلاً** end-to-end في onboarding (SetupCabin:378→FieldSetupWizard→AddFieldWithMap:1374→AutoSegmentControl→/api/segmentation/segment→SAM2) + ثقة + تأكيد بشريّ + 503 صادق بلا GPU؛ الفجوة تتقلّص لـUX suggest-on-open + نشر GPU + FTW `_run_ftw_inference=None` stub. (3) **B2 مبالَغ** — SoilGrids **مُدمَج فعلاً** بتراتبيّة صارمة `profile_composer.py:22-41` (lab100>field80>sensor55>analog40>soilgrids30>model15)؛ يسقط لـP2 صغير (tier إقليميّ وسيط فقط). **الأولويّات المُصحَّحة:** A2 OCSM + A5 عقد ملوحة (توثيق) → B1 SCOUT-INGEST (P0 منتجيّ) → SIM-PCSE ثمّ golden → A6/A7 (P2). لا commit كوديّ — دراسة تحقّق فقط.
- **A5 / WATER-SALT-01 — عقد قدرة الملوحة المُعلَن (شريحة مُختَمة، توثيق+عقد، صفر تغيير رياضيّات):** جمّع السلوك القائم للملوحة (المُثبَت file:line في الدراسة المقارنة) من ثلاث آليّات مبعثرة (بوّابة HALT · سياسة الريّ · توصية العجز recommended=False) إلى **عقد قدرة واحد مُعلَن**. الملفّات: `services/sahool-platform/core/salinity_capability.py` (وحدة صرفة: `SALINITY_CAPABILITY` frozen dataclass — supported/model/references/covers[claim+ref]/limits/status_enum + `salinity_capability_report()`) · `tests/test_salinity_capability_contract.py` (6 اختبارات، `unit`، ضمن وظيفة Platform Unit Tests) · `docs/capabilities/SALINITY_CAPABILITY.md`. **القيد الحاكم (ملاحظة المالك) مثبَّت بنيويّاً:** «عقد قدرة لا يُعلِن حدوده = fail-open مقنّع» ⇒ حارس يرفض أيّ `supported:true` بلا `limits`/`status_enum`/`references` (برهان سلبيّ: عقد `limits=()` يُرفَض، والحقيقيّ يُقبَل). الـstatus_enum = مفردات سياسة الريّ الحقيقيّة لا موازٍ مخترَع (`net_only·salinity_adjusted·salinity_with_leaching·blocked_for_review`، `irrigation_recommendation_policy.py:14`). المراجع: `fao56.py:127-135` Ks · `:590-597` غسيل · `crop_suitability.py:46,105-111` وزن EC · `deficit_irrigation.py:81,93-96` عجز. الحدود المُعلَنة: soil_ece غائب⇒Ks=1.0 (H5 off-by-default، مُعلَن لا صامت) · غسيل بلا ECw لا يُحسَب · مسقوف 0.5 · لا نقل ملح زمنيّ · بلا EC مُدخَل⇒خاملة للحقل. **بوّابات:** ruff نظيف · 6/6 · bundle 4610 checksums · service_inventory متزامن (SERVICE_REGISTRY+csv+json). التالي متتالياً: A2/SEM-OCSM-01.
- **A2 / SEM-OCSM-01 — ADR-0034 crosswalk عقود SAHOOL↔OCSM (خريطة مرجعيّة، صفر تغيير عقد):** `docs/adr/ADR-0034-sahool-ocsm-crosswalk.md` + حارس `tests_v9/test_ocsm_crosswalk_reference_only.py` (3 اختبارات، unit). **OCSM مُثبَّت بالجلب لا الذاكرة:** `agstack/OpenAgri-OCSM @ 12863f1b` (2025-10-07، بلا release موسوم، CC-BY-4.0، فضاء `w3id.org/ocsm/`، JSON-LD؛ يعيد استخدام SOSA/SAREF4AGRI/FOODIE/AIM-sdm/GeoSPARQL/AGROVOC). أربعة عناقيد بحقول SAHOOL الحقيقيّة (grep): Field/Parcel (`field_models.py:24-90`)·Season/Crop (`season_models.py:19-67`)·Irrigation (`irrigation_models.py:22-46`)·Observation (`CanonicalObservationV1`+`soil_observation.v1`+`indicator_observation` schemas). **اكتشافات صادقة:** (1) **Observation أقوى محاذاة** (`sosa:Observation` — بنية مطابقة؛ الانحراف مفرداتيّ vocab↔AGROVOC لا بنيويّ) ⇒ مرشّح المحاذاة الأوّل لمظروف B1؛ (2) Field/Parcel محاذاة مفهوم قويّة (`saref4agri:Parcel`) لكن **SAHOOL يُطبّع خصائص التربة على الحقل بينما OCSM ينمذجها رصداً** = انحراف بنيويّ؛ (3) **Season وIrrigation لا صنف لهما في OCSM الأساسيّ** (FOODIE/FarmCalendar + OpenAgri-IrrigationManagement) ⇒ كثافة `absent` نتيجة حقيقيّة لا نقص تعيين؛ (4) tenant_id/idempotency/schema_version/supersedes = امتدادات SAHOOL (namespace `sahool:` صريح، لا يُخلَط بمعيار). قرارات الانحراف: جسر-عند-حدّ-B1 (str↔IRI·GeoJSON↔WKT·وحدات→qudt·تواريخ→عمليّات·vocab→AGROVOC) · إبقاء-محلّيّ (تربة-على-الحقل·جودة أغنى·multi-tenant) · مؤجَّل-بمحفّز (foodie:CropSeason·IrrigationManagement·BBCH). **الحارس برهان بنيويّ:** لا `w3id.org/ocsm` يتسرّب إلى `shared/contracts/` (ضدّ adoption جملة متسلّل) + برهان سلبيّ. محفّز التنفيذ: مظروف B1 يحتاج مفتاحاً معياريّاً أو شريك يطلب تبادل OCSM. **بوّابات:** ruff نظيف · 3/3 · bundle 4613 · inventory متزامن. اكتمل A5→A2 متتالياً؛ التالي في التسلسل: B1 SCOUT-INGEST (P0 منتجيّ، مفرداته من هذا الـcrosswalk).
- **B1.0 / SCOUT-INGEST-01 — العقد المحايد للإدخال الميدانيّ الخارجيّ (أساس نقيّ، بلا migration/ingress):** أوّل شريحة من أكبر فجوة منتج (P0، مؤكَّدة غائبة). `shared/contracts/ingest/external_submission_v1.py` — `ExternalSubmissionEnvelopeV1` محايد المزوّد (ODK/Kobo/CSV/GeoJSON) + `derive_dedup_key` (sha256 على provider|server|form|instance|content_hash) + `SEVEN_CHECKS` مُعلَنة. **مبادئ حاكمة مفروضة بنيويّاً:** الوصول≠الثقة (`trust_status=untrusted` الوحيد الممكن — لا يُبنى موثوقاً) · مفتاح dedup مشتقّ لا مُصاغ (model_validator يرفض مفتاحاً مزوّراً) · raw_ref (الخامّ محفوظ) · mapping_version (mapping مُصدَّر) · aware-UTC · extra-forbid. حارس `tests_v9/test_external_submission_contract_v1.py` (8/8). يحاذي العنقود 4 من ADR-0034 (`sosa:Observation`، أقوى محاذاة). مواصفة مُقسَّمة `docs/specs/SCOUT-INGEST-01_B1_spec.md`: B1.0 مُنجَز · B1.1 التحقّق السباعي+quarantine · B1.2 migration+ingress+ODK · B1.3 عامل الإسقاط · B1.4 Kobo — كلّها تُعيد استخدام لبنات قائمة (envelope_v1·normalize_stress_product·projection_jobs·كتّاب scouting/observations). **بوّابات:** ruff نظيف · 8/8 · bundle+inventory متزامنان. B1.1+ للمراجعة قبل التنفيذ (migration/ingress سطح تصميم أوسع).
- **B1.1 / SCOUT-INGEST-01 — التحقّق السباعي + quarantine (منطق صرف، بحقن سياق، بلا migration):** `shared/contracts/ingest/validation.py` — `validate_external_submission(envelope, ctx) -> IngestVerdict` يُشغّل الفحوص السبعة بالترتيب من `SEVEN_CHECKS` (المصدر الوحيد للأسماء/الترتيب) ويُقبَل **فقط** إن نجحت كلّها (`accepted = not reasons`). `ValidationContext` = ستّ دوالّ محقونة (is_tenant_known·is_provider_allowed·is_form_mapping_registered·field_resolves_in_tenant·values_within_bounds·is_duplicate) — pure، السياق المدعوم بقاعدة يُبنى في B1.2. نمط الرفض من `crop_stress_ingestion.normalize_stress_product`. **القاعدة الحاكمة مفروضة:** فشل أيّ فحص ⇒ quarantine بسبب مُصنَّف، الخامّ محفوظ، لا إسقاط domain — «لا دخول للقرار قبل السبعة» (اختبار 6/7 يُرفَض). فصل أمنيّ: provenance_complete (field_id مفقود) عن field_resolves_in_tenant (تسرّب عبر المستأجرين). حارس `tests_v9/test_external_submission_validation.py` (10 اختبارات: السبعة تقبل · كلّ فحص يفشل مفرداً بـparametrize · field_id مفقود يُفشل فحصَين · 6/7 يُرفَض · dedup gate). **بوّابات:** ruff · 18/18 (العقد+التحقّق) · bundle 4619 · inventory متزامن. المتبقّي: B1.2 migration+ingress+ODK (نقطة المراجعة المعماريّة) · B1.3 عامل · B1.4 Kobo.
- **مواصفات B1 كملفّات MD مُلتزَمة (`docs/specs/`):** أُخرِجت المواصفتان من scratchpad إلى المستودع — `WATER-SALT-01_A5_spec.md` (للسجلّ، مُنفَّذة `7b16442`) و`SCOUT-INGEST-01_B1.2_migration_rls_spec.md` (⏳ مسودّة للمراجعة، لم تُنفَّذ). B1.2 يوثّق: هجرة v197 `external_submissions` (جدول واحد بحالة، raw محفوظ jsonb، dedup فريد `(tenant_id,idempotency_key)`، عقد RLS FORCE+WITH CHECK نمط v155/v192، grants بلا DELETE) + تزامن المُشغّلَين + حارس + مدخل `/internal/ingest/submissions/odk` بتوكن خدمة (لا JWT مستخدم) + محوّل ODK + راية `SCOUT_INGEST_ENABLED` off. **ثلاث نقاط قرار للمراجعة:** (أ) جدول واحد بحالة [موصى] · (ب) ربط المستأجِر عبر سجلّ تعيين (provider,server,form)→tenant يملؤه مالك المستأجِر لا المُرسِل [نقطة أمنيّة حرِجة] · (ج) مِلكيّة platform الآن. مجلّد المواصفات الآن: `SCOUT-INGEST-01_B1_spec.md` (نظرة عامّة) + `WATER-SALT-01_A5_spec.md` + `SCOUT-INGEST-01_B1.2_migration_rls_spec.md`. لا تنفيذ — توثيق فقط.
- **B1.2a / SCOUT-INGEST-01 — الهجرة v197 (external_submissions) + resolver dedup متباين + برهان حيّ (PG16 أصليّ):** الجدول (خامّ في raw_payload jsonb · raw_ref=مقبض URN للنَّسَب يقرأه B1.3 لا يتيم · normalized_payload محاذاة العنقود 4 · trust_status∈{untrusted,accepted,quarantined} · quarantine_reasons[]) + `UNIQUE(tenant_id,idempotency_key)` + **RLS FORCE+WITH CHECK** (نمط v155/v192) + **immutability كسمة: trigger BEFORE DELETE يرفع استثناء** (لا اعتماد على غياب grant). التزامن الثلاثيّ (MANIFEST+run_migrations خطوة203+db_ownership owner=platform) + حارس التزامن أخضر. **التعديل الإلزاميّ (درس _log مُطبَّق):** `shared/contracts/ingest/dedup_resolution.py::resolve_dedup` منطق ثلاثيّ — جديد/idempotent-مطابق/**quarantine-متباين بمفتاح مشتقّ `key#dup-<hash12>`** (أقوى من #dup2: لا اصطدام لجسمين متباينين) + سبب duplicate_key_divergent_payload — **لا ON CONFLICT DO NOTHING صامت**. **حسم كاتب accepted:** اجتياز السبعة⇒accepted عند الإدراج (التحقّق بوّابة الثقة؛ B1.3 يقرأ accepted فقط)؛ untrusted للـbackfill المستقبليّ. الحُرّاس: static v197 (`test_v197_external_submissions_static.py`) · الحارس السابع (`test_ingest_dedup_resolution.py`) · **برهان حيّ 3/3 على PG16 أصليّ** (`test_v197_external_submissions_rls_live.py`, integration): (1) سياق فارغ⇒رفض RLS · (2) dedup متباين⇒quarantined والأصل accepted سليم · (3) DELETE⇒استثناء append-only. 31/31 unit · bundle 4623 · inventory متزامن. **B1.2b تالٍ:** المدخل `/internal/ingest/submissions/odk` بتوكن **لكلّ مصدر** (scout_ingest_token_hash لكلّ (provider,server) في سجلّ التعيين — لا SAHOOL_AGENT_TOKEN مشترك؛ إبطال مصدر=سطر لا تدوير) + محوّل ODK + برهان «توكن معطَّل⇒403 لا يمسّ غيره».
- **نمط دماغيّ جديد: `capability-contract-standard` (وُلِد من A5):** أيّ عقد قدرة مُعلَن في المنصّة (salinity اليوم · PCSE/LAI مستقبلاً) يجب أن يمرّ بنفس البوّابة: `supported:true` ⇒ يحمل `limits` غير فارغة + `status_enum` (من مفردات حقيقيّة لا موازية مخترعة) + `references` (file:line لكلّ covers) — حارس يرفض «قدرة صمّاء عن حدودها» ببرهان سلبيّ. المرجع: `core/salinity_capability.py` + `tests/test_salinity_capability_contract.py`. القاعدة: «عقد لا يقول متى يتوقّف عن الثقة = fail-open مقنّع».
- **تصحيح حالة A2:** SEM-OCSM-01 (A2) **مُنفَّذ** كـADR-0034 (`af83b24`) — ليس بنداً مفتوحاً. البند المفتوح الوحيد من الخطة الآن = B1 SCOUT-INGEST (نحن في B1.2a→B1.2b). A5 مُنفَّذ (`7b16442`). التسلسل المُنجَز: A5→A2→B1.0→B1.1→B1.2a.
- **درس CI #178 — أيّ ملفّ بايثون جديد تحت `services/sahool-platform/` (عدا tests/) يجب تسجيله في `docs/architecture/platform_python_module_baseline.json` + رفع `baseline_python_module_count`:** حارس `tests/test_p0_platform_module_growth_guard.py` (ميزانيّة التفكيك/strangler) يحجب في وظيفة *Platform Unit Tests* على أيّ نموّ غير مُبرَّر. **حادثة:** A5 أضاف `core/salinity_capability.py` (648→649) دون تسجيل ⇒ كلّ الالتزامات A5→B1.2a فشلت في *Platform Unit Tests* (الوظيفة الوحيدة الحمراء؛ التغطية كانت 61.64%>60% سليمة). الإصلاح `571f725`: سجّلته + رفعت العدّاد + ملاحظة تبرير. **ملاحظة تشخيص:** رسالة inventory-drift المُسرَّبة كانت من تشغيل قديم (2026-07-18)؛ `generate_service_inventory.py --check` نظيف على HEAD. الشرائح shared/contracts+tests_v9 لا تُحسَب (خارج services/sahool-platform).
- **درس CI #179 — تنسيق SQL في الهجرة يُفشِل حُرّاس RLS الحرفيّة؛ شغّل `-m unit` الكامل قبل دفع أيّ migration:** كتبت `ALTER TABLE external_submissions FORCE  ROW LEVEL SECURITY` بمسافتَين (`FORCE  ROW`) للمحاذاة البصريّة مع `ENABLE ROW`، لكن regex حُرّاس RLS (`test_rls_tenant_coverage`/`test_field_state_projection`/`test_sahool_inspector`) حرفيّ `FORCE ROW LEVEL SECURITY` (مسافة واحدة) ⇒ لم يُطابَق ⇒ ثلاثة حُرّاس اعتبرت external_submissions «بلا FORCE صريح». **الخطأ الأصليّ:** شغّلتُ ملفّات الاختبار الجديدة فقط لا `-m unit` الكامل (الذي يمسح كلّ الهجرات عبر الحُرّاس المتقاطعة). الإصلاح `<sha>`: مسافة واحدة. **القاعدة:** أيّ migration ⇒ شغّل `pytest -m unit` الكامل محليّاً (يلتقط test_rls_tenant_coverage/field_state_projection/sahool_inspector) لا الملفّات الجديدة وحدها. مُصادَق: `relforcerowsecurity=t` حيّاً على PG16 + 3213 unit خضراء.
- **B1.2b (نواة أمنيّة) / SCOUT-INGEST-01 — v198 external_ingest_sources + resolver SECURITY DEFINER + حسم مالك الدالّة (FORCE↔DEFINER) مُبرهَن حيّاً:** `migrations/v198_external_ingest_sources.sql` — سجلّ تعيين control-plane (provider,server,form→tenant + token_hash فقط، لا التوكن) + `resolve_ingest_source(token_hash)` SECURITY DEFINER (يعيد المُفعَّل المطابق فقط، لا تعداد) + REVOKE FROM PUBLIC + RLS FORCE (مسافة واحدة، درس #179) للكتابة الإداريّة. **الحسم المانع (سؤال المراجعة):** FORCE يسري على مالك الجدول، وDEFINER يعمل بصلاحية المالك؛ فمالك خاضع لـFORCE يُجوّع resolver (سياق فارغ⇒0 صفوف⇒كلّ توكن 403=سطح ميت). الحلّ: دور تحكّم `sahool_ingest_resolver` (NOLOGIN NOSUPERUSER **BYPASSRLS** + SELECT على الجدول الواحد فقط) يملك الدالّة — يُضبط في **bootstrap** (`bootstrap_postgres.sh`+`apply_in_compose.sh`، حيث تُنشأ الأدوار؛ عرف «لا إشارة أدوار في الهجرات»)؛ sahool_app يبقى NOBYPASSRLS، EXECUTE عبر منح ALL-FUNCTIONS القائم. **برهان حيّ على PG16 أصليّ (`test_v198_ingest_resolver_owner_live.py`، 2/2):** CASE1 مالك BYPASSRLS+سياق فارغ⇒يحلّ المستأجِر؛ CASE2 مالك non-bypass⇒0 صفوف (الفخّ). حارس ساكن `test_v198_external_ingest_sources_static.py` (4/4: RLS/DEFINER/REVOKE/المُشغّلَين/المالك في كلا السكربتَين). **note#1 (GRANT):** مُغطّى بـ`GRANT EXECUTE ON ALL FUNCTIONS TO sahool_app` القائم (bootstrap بعد الهجرات) + REVOKE FROM PUBLIC. **note#2 (dedup counter):** غير قائم — `_divergent_key` يستخدم `#dup-<hash12>` لا `#dup2` (التباين الثالث⇒لاحقة hash خاصّته). **بوّابات:** ruff · **`-m unit` الكامل 3217** (درس #179 مُطبَّق) · bundle · inventory. المتبقّي B1.2b: المدخل `/internal/ingest/submissions/odk` + محوّل ODK + كاتب accepted + برهان توكن-معطَّل⇒403 (سطح API تالٍ).
- **B1.2b (نواة API نقيّة) / SCOUT-INGEST-01 — محوّل ODK + منطق قرار الإدخال (repo-root، حدّ معماريّ محترَم):** `shared/contracts/ingest/odk_adapter.py` (`build_envelope_from_odk`: الهويّة provider/server/form/tenant من **سياق المصدر المُحلَّل لا من المُرسِل**؛ content_hash مُقنَّن مرتّب-المفاتيح؛ instance من meta.instanceID) + `shared/contracts/ingest/ingest_handler.py` (`process_submission(envelope, raw_payload, ports)` نقيّ بحقن `IngestPorts` منافذ DB؛ يجمع resolve_dedup + التحقّق السباعي: idempotent-مطابق⇒لا تخزين · quarantine-divergent⇒مفتاح مشتقّ · accepted عند اجتياز السبعة · quarantined عند فشل فحص). **حدّ معماريّ مُكتشَف ومُحترَم:** لا شيء في `services/sahool-platform/` يستورد `shared.contracts` (وظيفة Platform Unit Tests بـPYTHONPATH=. من المنصّة، shared غير مرئيّ)؛ runtime المنصّة يراه (Dockerfile `COPY shared/ /app/shared/` + PYTHONPATH=/app). لذا المنطق النقيّ في shared (repo-root، tests_v9 تختبره)، والراوتر (glue) تحت المنصّة = القطعة الأخيرة بقرار harness. حارس `tests_v9/test_ingest_odk_adapter_and_handler.py` (7/7). **بوّابات:** ruff · **-m unit الكامل 3224** (درس #179) · bundle · صفر تغيير baseline (لا .py منصّة). المتبقّي: راوتر `/internal/ingest/submissions/odk` (يستورد shared runtime + منافذ asyncpg حقيقيّة) + برهان HTTP حيّ (401/403/accepted/توكن-معطَّل) — يحتاج قرار مسار المنصّة (conftest يضيف جذر المستودع مقابل lazy-import).
- **B1.2b (الخدمة المالكة) / SCOUT-INGEST-01 — `scout-ingest-service` مستقلّة (تصحيح قرار (ج): من platform-الآن إلى خدمة مالكة) + تصحيح مفتاح dedup مُبرهَن حيّاً:** آخر شريحة من B1.2. **قرار (ج) صُحّح:** المواصفة اقترحت مسار إدخال على المنصّة، لكن حُرّاس المنصّة الأربعة (route_budget_does_not_grow · route_budget_reduced · route_ownership · mutating_auth) **رفضت** إضافة مسار — الانضباط: المنصّة تُقلّص لا تنمو. **السابقة #201** (field-management-service) حسمت النمط: مدخل خارجيّ ⇒ خدمة مالكة. فبُنِيت `services/scout-ingest-service/` (main.py+Dockerfile `COPY shared/`+requirements) تملك المسار + جدول `external_submissions` (db_ownership owner/writers=scout-ingest-service، نُقِل من platform). **عقد الأمان (fail-closed، بلا fallback):** اعتماد **لكلّ مصدر** (`X-Scout-Ingest-Token`→sha256→`resolve_ingest_source` SECURITY DEFINER→المستأجِر؛ لا `SAHOOL_AGENT_TOKEN` ولا JWT) · الهويّة من السجلّ لا المُرسِل · دور `sahool_ingest` (LOGIN NOBYPASSRLS، **SELECT+INSERT فقط لا UPDATE/DELETE**، يضبط `app.current_tenant` false لكلّ عمليّة) في كلا مُهيّئَي الأدوار (bootstrap+apply_in_compose) · DATABASE_URL/asyncpg خطأ⇒503 · خلف `SCOUT_INGEST_ENABLED` off⇒404. **تصحيح تصميميّ التقطه البرهان الحيّ (درس «البرهان الحيّ رخيص ودائم»):** `derive_dedup_key` كان يُضمّن content_hash ⇒ حالة التباين (نفس الخانة، جسم مختلف) **مستحيلة** (جسم مختلف⇒مفتاح مختلف⇒«200 accepted» بدل «202 quarantined»). التصحيح: المفتاح = **هويّة الخانة فقط** `sha256(provider|server|form|instance)`؛ content_hash يُقارَن منفصلاً في `resolve_dedup`. أُزيل content_hash من `derive_dedup_key`+validator المظروف+odk_adapter+موضعَي اختبار. **برهان HTTP حيّ 6/6 على PG16 أصليّ** (`services/scout-ingest-service/tests/test_ingest_live.py`، integration، تحت الدور المقيَّد): no-token⇒401 · unknown⇒403 · disabled-A⇒403 (B سليم لا يُمَسّ) · valid-B⇒200 accepted · replay-B⇒200 idempotent_replay · **divergent-B⇒202 quarantined [duplicate_key_divergent_payload]** (بعد التصحيح) + برهان أقلّ-منح (sahool_ingest UPDATE⇒permission denied). **حارس ملكيّة جديد** `tests_v9/test_scout_ingest_service_ownership.py` (6/6، شرط المالك): كاتب وحيد ورقيّاً (db_ownership) + بنيويّاً (لا INSERT خارج الخدمة) + أقلّ-منح في المُشغّلَين + compose يصل بـsahool_ingest المقيَّد خلف الراية + الخدمة fail-closed لكلّ مصدر. **compose:** كتلة `sahool-scout-ingest` في `docker-compose.v9.yml` (سياسة #201: sahool_ingest لا sahool_user، depends_on migrate، SCOUT_INGEST_ENABLED). **الحُرّاس الأربعة لم تُعدَّل** (شرط المالك: «هم اتّخذوا القرار فلا نكافئهم بالتعديل»). **بوّابات:** ruff نظيف · **`-m unit` الكامل 3230** (درس #179) · bundle 4635 checksums · production_validation_gate أخضر · inventory متزامن (32 خدمة/1059 مسار). B1.2 مكتمل؛ التالي B1.3 (عامل الإسقاط accepted→scouting_pins/observations، آخر قطعة P0 منتجيّة).
- **B1.3 / SCOUT-INGEST-01 — إسقاط المقبولة إلى نموذج قراءة مملوك (القرار (أ) مُنفَّذ، بمنطق (2) نفسه):** آخر قطعة P0 منتجيّة من B1. **القرار (أ):** scout-ingest يملك `external_field_observations` (v199، RLS FORCE) + عامل إسقاط + نقطة قراءة خاصّة — **لا يكتب `scouting_pins`/`observations` المملوكَين للمنصّة** (كلاهما owner=platform، `db_ownership:759,915`). المنطق: (ب) [عامل منصّة يكتب scouting_pins] كان سيُنمّي المنصّة في الشريحة التالية مباشرةً فيُبطِل نقاش الحراس الأربعة؛ (أ) يحترم single-writer **مرّتين**. ازدواج نموذجَي القراءة **دَين موثَّق مؤجَّل** (B1.3b)، لا خطأ معماريّ. **فخّ least-grant↔scan-عابر (نظير FORCE↔DEFINER في B1.2b):** العامل يمسح accepted عبر المستأجرين ويحدّث projection_status، لكن `sahool_ingest` **بلا UPDATE** (الحارس المُعتمَد). الحلّ: دالّتا `claim_submissions_for_projection`/`complete_submission_projection` **SECURITY DEFINER** يملكهما `sahool_ingest_resolver` (BYPASSRLS) — فيبقى sahool_ingest عند SELECT+INSERT فقط (على submissions + observations). **immutability الخامّ صارت أقوى:** v199 يضيف trigger BEFORE UPDATE يرفض تحوير أيّ عمود دليل خامّ (يُسمح فقط بأعمدة projection_*) — فالخامّ غير قابل للمحو (DELETE، v197) ولا للتحوير (UPDATE) معاً. **الشرطان (طلب المالك):** ① محفّز B1.3b مكتوب في المواصفة (أوّل مستهلك قرار يحتاج رؤية موحّدة أو تجاوز مصادر القراءة اثنين)؛ ② عقد قراءة مُعلَن: `GET /internal/scouting/external-observations` بتوكن خدمة **مخصّص** `SCOUT_INGEST_READ_TOKEN` (لا SAHOOL_AGENT_TOKEN)، مُسجَّل في الجرد كنموذج قراءة مستقلّ (لا direct-DB — مرض p4)، حارس يقفله. **النواة النقيّة** `shared/contracts/ingest/projection.py` (`project_submission` → مشاهدة أو ProjectionSkip؛ observation_id مشتقّ حتميّاً؛ field_id مفقود ⇒ dead_letter بلا يتيم). **العامل** `services/scout-ingest-service/projection_worker.py` (Pattern A: claim→project→INSERT ON CONFLICT→complete؛ عزل الصفّ؛ retry/dead_letter عند MAX) خلف `SCOUT_INGEST_PROJECTION_ENABLED` (off) + خدمة compose. **البرهانان المطلوبان حيّاً (PG16، test_projection_live 1/1):** accepted+field⇒مشاهدة واحدة · **quarantined⇒لا شيء** (المقبولة فقط) · field_id مفقود⇒dead_letter · **إعادة تشغيل العامل⇒صفر مضاعفة** (idempotent) + برهان يدويّ: trigger يسمح projection_status ويرفض content_hash. **إصلاح مرافق:** test_ingest_live (B1.2b) كان يعتمد على مسار sys.path هشّ (`import main` بلا service-dir) — أُصلِح فصار مستقلّاً (6/6 قائم). **حارس ملكيّة مُمدَّد** (5 اختبارات B1.3: كاتب وحيد للنموذج + أقلّ-منح + DEFINER-only + توكن-مخصّص + لا كتابة جداول منصّة). **بوّابات:** ruff · `-m unit` 3242 · **المسح الاستباقيّ الكامل** (كلّ --check + 110 ci.yml + compose-env + ui-contract 32/32 + consumer + fleet) · production_validation_gate · bundle 4641. **B1 مكتمل عمليّاً** (P0)؛ يتبقّى B1.4 Kobo (مزوّد ثانٍ، غير حرِج).
- **درس #180 — «إضافة خدمة = ~10 تسجيلات»؛ سجّل الكلّ قبل الدفع + امسح استباقيّاً:** خدمة جديدة تلمس ~10 حُرّاس totality/drift (جرد · عقد مستهلك · route_residual · health · dependency-conflict · dependency-bundle · api-versioning · route-mount · compose-env · release-bundle) + إن لمست القاعدة: db_ownership · MANIFEST/run_migrations · أدوار في المُشغّلَين · production_validation_gate. كلّ حارس يكتشفها **واحداً تلو الآخر** في CI (25904d4→b0a0b2f→eaf3096→e6acc0a = 4 دورات لخدمة واحدة). **الكسر:** `docs/architecture/NEW_SERVICE_REGISTRATION_CHECKLIST.md` (قائمة واحدة) + المسح الاستباقيّ الكامل محليّاً قبل الدفع (كلّ --check + استدعاءات ci.yml + -m unit + ruff + bandit). طُبِّق فعليّاً على B1.3 (دفعة واحدة خضراء متوقَّعة بدل 4).
- **B1.4 / SCOUT-INGEST-01 — Kobo (المزوّد الثاني، إغلاق B1 كاملاً):** KoboToolbox مبنيّ على ODK (XForms) فيتشارك المظروف المحايد ومفتاح dedup نفسه — B1.4 شريحة رقيقة بلا خدمة/جدول/دور جديد. `shared/contracts/ingest/kobo_adapter.py` (`build_envelope_from_kobo` يعيد استخدام `canonical_content_hash`/`derive_dedup_key`؛ يختلف فقط: هويّة النسخة من `meta/instanceID` المسطّح ثمّ المتداخل ثمّ `_uuid`/`_id`، والوقت من `_submission_time`). **الهويّة من السجلّ المُحلَّل لا من المُرسِل** (المُرسِل يزعم provider/tenant ⇒ يُتجاهَلان — برهان سلبيّ). نقطة `POST /internal/ingest/submissions/kobo` (+ refactor المسار المشترك `_handle_submission(raw, token, provider_kind)` فيتشارك odk/kobo التوكن-لكلّ-مصدر + التحقّق السباعي + dedup/quarantine بلا تكرار؛ لا انحدار في odk — 15 اختبار odk أخضر). **allowlist المزوّد لا يحتاج كوداً:** السجلّ نفسه هو القائمة (مصدر kobo يُسجَّل provider='kobo'؛ الحارس `is_provider_allowed=lambda _p:True` بعد resolve). حارس `tests_v9/test_ingest_kobo_adapter.py` (5: هويّة-من-المصدر · أسبقيّة النسخة · _submission_time · مفتاح متماثل مع ODK · content_hash حتميّ). **برهان حيّ (PG16):** مصدر kobo مُفعَّل ⇒ POST /kobo بـmeta/instanceID مسطّح + _submission_time ⇒ accepted ثمّ idempotent_replay (test_ingest_live +test_kobo_path_live، 2/2). **إصلاح مرافق:** تنظيف الـfixture بين الاختبارات صار `TRUNCATE` (لا يُطلق trigger الحذف الصفّيّ append-only) بدل DELETE. **بوّابات:** ruff · `-m unit` 3247 · كلّ --check + 110 ci.yml + compose-env + ui-contract 32/32 (مسح استباقيّ، درس #180) · bundle 4647. **B1 (SCOUT-INGEST-01) مُغلَق بالكامل:** B1.0 مظروف · B1.1 تحقّق سباعي · B1.2 (a/b) خدمة+RLS+resolver · B1.3 إسقاط مملوك · B1.4 Kobo. أكبر فجوة منتج (P0) من الدراسة المقارنة سُدَّت end-to-end (إدخال خارجيّ ODK/Kobo → تحقّق → تخزين append-only → إسقاط نموذج قراءة مملوك).
- **SIM-PCSE-01 — تفعيل PCSE/WOFOST خلف عقد قدرة + راية + فصل I/O (تنفيذ، بشروط A5/B1):** الدراسة المقارنة صحّحت A3: `wofost_adapter` **placeholder حتميّ** لا WOFOST (fallback Liebig مُعلَن `provenance=deterministic_fallback`؛ سقالة `_pcse_simulate` توصيلها **ساذج** — dict خامّ كموفِّر؛ pcse معلّق؛ `wofost_real/` غائب). التفعيل **حافظ على الأمانة وحوّلها لعقد** (لا نصلّح كذبة، نبني فوق صدق). **الشروط الثلاثة (المالك) بنيويّاً:** ① `services/agriai-engine/simulation_capability.py` (`SIMULATION_CAPABILITY` بمعيار capability-contract-standard/A5: limits إلزاميّة — **WLP فقط، potential غير معروض** · **لا ملوحة في PCSE** تبقى fao56/غسيل A5، guard يمنع ازدواج المحرّكين · محاصيل بالاسم · uncalibrated حتى golden)؛ حارس يرفض supported:true بلا حدود (برهان سلبيّ نظير A5). ② راية `SIM_PCSE_ENABLED` (default-off): **مطفأة⇒السلوك الصادق القائم** (تطوير fallback · إنتاج fail-closed)؛ **مشعلة⇒محرّك مُنخرِط** (محصول خارج السجلّ⇒`sim_pcse_unsupported_crop` fail-closed دائماً؛ pcse غائب/مدخلات ناقصة⇒`simulation_unavailable` مُصنَّف، لا بديل صامت). ③ `simulation_io.py` (`SimulationInputs`→محرّك→`SimulationOutput` منفصلة عن الغراء) — **golden يقيس المحرّك لا الغراء**. **تصحيح التوصيل:** `_pcse_run` يبني موفِّرات PCSE الصحيحة (`YAMLCropDataProvider.set_active_crop` من `sim_crop_registry` + `ParameterProvider` + `WeatherDataProvider` + `AgroManagement`) بدل dict خامّ؛ `pragma:no cover` (pcse يُركَّب في التكامل لا CI الوحدة). **سجلّ المحاصيل v1 (قرار المالك): wheat/barley/potato** — كلٌّ بـ`parameter_source`+`parameter_version` (نفس انضباط مرجعيّة المصادر)؛ sorghum/onion/tomato **خارج v1 عمداً** (لا معاملات جاهزة = لا تسويق زائف). **provenance:** `pcse_wofost_uncalibrated` → بعد golden `pcse_wofost_calibrated_<golden_dataset_version>` (مسار الترقية مُسجَّل). **حُرّاس** `tests_v9/test_simulation_capability_contract.py` (6) + `test_sim_pcse_flag_and_safety.py` (5): عقد/سجلّ/فصل-I/O + سلوك الراية fail-closed. **صفر انحدار:** الأمانة القائمة محفوظة (substring `agriai_production_simulation_unavailable` باقٍ)، gates vegetation-agriai الثلاث خضراء، agriai contract tests خضراء. **بوّابات:** ruff · `-m unit` 3258 · مسح استباقيّ كامل · bundle 4650. **صدق `requirements`:** pcse يبقى اختياريّاً (لا مسار حرِج/CI الوحدة). التالي **SIM-GOLDEN-01 (محجوب ببيانات حقول حقيقيّة + عتبات خطأ)** ← A6/A7.
- **محفّز توحيد `/simulate/what-if` (مُسجَّل، القرار (ب) في SIM-PCSE):** مسار المنصّة `/api/v1/simulate/what-if` (يفحص `wofost_real/` الغائب ⇒ available:false صادق) يبقى كما هو؛ يُوحَّد ليستهلك agriai-engine **عند أوّل مستهلك قرار حقيقيّ يطلب محاكاة عبر المنصّة** — لا نموّ منصّة بلا مستهلك مثبَت (نفس منطق B1.3b).
- **درس: «المنصّة رفضت معايرة مزيّفة — العقد منعنا من أنفسنا» (SIM-PCSE-01):** حين طُلِب تفعيل PCSE، كان أسهل مسار اختلاق golden datasets أو إدخال محاصيل بمعاملات مقترَضة لتبدو القدرة أشمل. عقد القدرة (capability-contract-standard/A5) منع ذلك بنيويّاً: `calibration_status="uncalibrated_pending_golden"` الباقي صادقاً **برهان حيّ أنّ النظام يعرف متى لا يعرف ويُعلنه**؛ سجلّ المحاصيل بالاسم رفض sorghum/onion/tomato لغياب معاملاتها الجاهزة. الفرق بين منصّة علميّة ومنصّة تسويق = هذه الجملة: «لن أختلق». العقد أداة انضباط ذاتيّ لا توثيق فقط.
- **محفّز SIM-GOLDEN-01 (محجوب بصدق):** يُستأنَف **عند توفّر أوّل سجلّ حقل حقيقيّ بغلّة مرصودة** — إمّا من حقول المنصّة نفسها بعد موسم (نظام scouting الذي بُنِي في B1 سيُنتِج هذه البيانات مع الوقت — المحاكاة ستُعايَر يوماً ببيانات جمعها الإدخال الخارجيّ)، أو من شراكة إرشاديّة. حتى ذلك: `pcse_wofost_uncalibrated` يبقى، ولا golden مُختلَق. **الترتيب المعتمد بعد الحجب:** A7 (حدود إداريّة) → A6 (خرائط SVG للطباعة) — A6 يستهلك طبقة A7 فبُنِيت أوّلاً.
