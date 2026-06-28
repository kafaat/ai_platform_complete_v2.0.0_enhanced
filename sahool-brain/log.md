# 📜 سجلّ الجلسات (append-only)

> ألحِق مدخلاً في نهاية كلّ جلسة. لا تُعدّل المدخلات السابقة. الأحدث في الأعلى.

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
