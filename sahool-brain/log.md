# 📜 سجلّ الجلسات (append-only)

> ألحِق مدخلاً في نهاية كلّ جلسة. لا تُعدّل المدخلات السابقة. الأحدث في الأعلى.

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
