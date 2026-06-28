# 📜 سجلّ الجلسات (append-only)

> ألحِق مدخلاً في نهاية كلّ جلسة. لا تُعدّل المدخلات السابقة. الأحدث في الأعلى.

---

## 2026-06-28 (ك) — إغلاق فجوات قديمة (deferred/by-design) + ختام جلسة raster/auth

**رأس `main`:** `522a47e` (#558). امتداد لمدخل (ي). اكتمل دمج كلّ عمل الجلسة (#550–#558):
تفكيك raster (#551) + المنصّة (قائم) + **auth (#557، ١٧٢١→٨٩١، ٢٧→٩ routers، ٣١ مساراً)** ·
مرآة CI `mirror.gcr.io` (#556) · واجهة CDSE (#552) · nginx `/api/raster/` (#553) · **قصّ CDSE على
مضلّع الحقل (#558)** — حلّ «الصحراء الحمراء» المرصودة (`routers/cdse_tiles.py` كان يُمرّر
`geometry=None`؛ الآن يُمرَّر المضلّع من الواجهة فيقصّ Sentinel Hub). + وثيقة v9↔fixed (#554).

**إغلاق فجوات (تتبُّع، لا حلّ مُدّعى):** `C5`/`H2`/`H5`/`C4/M1`/`SAM2`/`TERRAIN` نُقِلت من `open`
إلى **`deferred`/`by-design`** في [`gaps/registry.md`](gaps/registry.md) — لا واحدةَ قابلةٌ للإصلاح
الآليّ الآمن (تحتاج GPU/Flutter/تحقّقاً ميدانيّاً/قراراً زراعيّاً). `SAM2` بالتصميم لا عيب.

**متبقٍّ (المشغّل):** تحقّق ميدانيّ لقناع غيوم CDSE + قصّ CDSE (#548/#558) — يحتاجان تشغيل CDSE حقيقيّ.
**قيد عالق:** الفرع المكرّر `frontend-cdse-hide-date` يتعذّر حذفه (البروكسي يرفض حذف المرجع + لا أداة
حذف فرع في MCP) — يُحذف من واجهة GitHub.

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
