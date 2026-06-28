# 🚧 سجلّ الفجوات الحيّ (Gap Registry)

> سجلّ حيّ بالحالة. كلّ صفّ يحوي **مصدراً** (`file:line` أو `#PR`) و**حالة**
> (`open` / `fixed` / `verified`). المصدر الأساسيّ:
> [`../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md`](../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md) (تحليل ساكن
> READ-ONLY — «مؤشّر ≠ إثبات»: `fixed` = عُولِج في الكود؛ `verified` = أُكِّد حيّاً).
>
> **تنبيه دقّة:** تقرير الفجوات سجّل بعض البنود مُصلَحةً في الكود (#349–#363) لكنّها لم تُؤكَّد
> حيّاً بعد؛ نُبقيها `fixed` (لا `verified`) التزاماً بحدّ الصدق.

| ID | العنوان | المجال/الخدمة | المصدر | الحالة |
|---|---|---|---|---|
| C1/C2 | التوصية تُولَّد + تُخزَّن وتُدقَّق وتُربَط بالشرح (جدول v77 + `RECOMMENDATION_CREATED` + `GET /{rec_id}`) | platform/التوصيات | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:19` (#350)؛ أصل: `:116-117` | fixed (يحتاج تأكيداً حيّاً) |
| C5 | NDVI الحقيقيّ معلوماتيّ لا يُغيّر صلاحيّة القرار | platform/الحالة القانونيّة | `api/field_state_projection.py:206-215`؛ `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:120` | deferred — تحقّق ميدانيّ مطلوب (عتبات NDVI)؛ خارج الإصلاح الآليّ |
| H2 | **٧** اشتراكات NATS بلا ناشر (لا ٨) — تصنيفها «ناشر مفقود متوقَّع» لا «اشتراك ميّت»: تطابق `EVENT_EMOJI` وأنواع الأحداث (`api/main.py:1670`)، فالإصلاح = بناء ناشرين عبر outbox لا تقليم الاشتراكات (قرار معماريّ). الموضوعان `satellite.*.computed`/`sahool.events.>` لهما ناشرون (ليسا يتيمين). `weather.forecast.updated` مُعالَج خلف راية `WEATHER_GRID_PIPELINE_ENABLED` (OFF). | notification/الأحداث | تحقيق #458؛ `agents/notification/agent.py:340-346`؛ ناشرون: `api/event_bus.py:596` · `sentinel_hub/vegetation_real.py:680`؛ أصل: `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:128` | deferred — بناء ناشري NATS عبر outbox (قرار معماريّ، لا تقليم اشتراكات) |
| H4 | ET0 Hargreaves مُكرَّر بقيم Ra متعارضة — وُحِّد في `core/engines/et0.py` | platform/الأغرونوميا الكمّيّة | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:23` (#351/#356)؛ تأكيد #457 | ✅ fixed + مؤكَّد باختبارات انحدار (#457؛ متبقٍّ موثَّق: إعادتان عبر-خدمات weather_server/wofost) |
| H5 | احتياج الريّ بصيغتين (مع/بلا ملوحة) | platform/الريّ | `core/engines/fao56.py:249` مقابل `api/water_balance.py:183`؛ `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:38,131` | deferred — قرار زراعيّ مطلوب (صيغتا الريّ مع/بلا ملوحة) |
| H6 | عتبات الملوحة/pH/الحرارة مُكرَّرة — وُحِّدت في `core/thresholds.py` | platform/العتبات | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:21` (#352)؛ أصل: `:132` | fixed (يحتاج تأكيداً حيّاً) |
| C4/M1 | الموبايل: بنية push (FCM/APNs) + عميل WebSocket في Flutter | mobile | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:40,119,150` | deferred — يتطلّب بيئة Flutter (push/FCM/WebSocket) |
| SAM2 | خادم استدلال SAM2 يحتاج GPU (opt-in)؛ بدونه 503 صادق | field-segmentation/sam2 | `docker-compose.v9.yml:1351` (profile=gpu)؛ `services/sam2-inference/main.py:74`؛ [`docs/SAM2_DEPLOYMENT.md`](../../docs/SAM2_DEPLOYMENT.md) | by-design — opt-in خلف profile=gpu (503 صادق بدونه؛ ليس عيباً) |
| MAP-QA | افتراض MapLibre/WebGL ينتظر بوّابة QA حيّة (Playwright) | frontend/الخرائط | بوّابة Playwright #441 (`d23eb6b`)؛ سويت [`tests/`](../../frontend/) | open (البوّابة مُنشأة؛ ينتظر تشغيلاً حيّاً) |
| TERRAIN | `TerrainView3D` يحتاج مسار `/terrain` خادميّ | frontend/الخرائط | [`frontend/src/components/maphub/TerrainView3D.tsx`](../../frontend/src/components/maphub/TerrainView3D.tsx) | deferred (P2) — يحتاج مسار `/terrain` خادميّ + تكامل واجهة |
| IND-SRC | مصدر مؤشّرات الموبايل الصحيح (`getFieldIndicators`) | mobile | #445 (`a7909e6`)؛ [`mobile/sahool_app/lib/services/api_service.dart`](../../mobile/sahool_app/lib/services/api_service.dart) | fixed |
| MERGE | دمج/انقسام الحقول ذرّيّاً (سدّ خطر البيانات الثلاثيّة) | platform/الحقول | #443 (`2456d2b`)؛ [`api/routers/fields.py`](../../services/sahool-platform/api/routers/fields.py)؛ اختبار [`tests_v9/test_fields_merge_split_atomic.py`](../../tests_v9/test_fields_merge_split_atomic.py) | fixed |
| NDVI-MOB | مسار سلسلة NDVI في الموبايل (404) | mobile | #444 (`9e00d0a`)؛ [`mobile/sahool_app/lib/screens/satellite_screen.dart`](../../mobile/sahool_app/lib/screens/satellite_screen.dart) | fixed |
| RASTER-STRIPE | شرائط داكنة فوق NDVI/NDMI/الملوحة — بكسلات `finite=0.0` خارج dataMask تُلوَّن معتمة | raster-service | إصلاح المصدر #550 (`2359cea`، قناع `cog_writer`)؛ [`cog_writer.py`](../../services/raster-service/cog_writer.py)؛ اختبار [`test_cog_writer_internal_mask.py`](../../services/raster-service/test_cog_writer_internal_mask.py) | fixed + مُختبَر |
| CDSE-SCL | قناع غيوم SCL **بكسليّ** في evalscript CDSE (لا `dataMask` فقط) | raster-service | #550 (`2359cea`)؛ [`cdse_client.py`](../../services/raster-service/cdse_client.py) | fixed (يحتاج تأكيداً حيّاً بتشغيل CDSE) |
| CDSE-CLIP | قصّ بلاطات CDSE على **مضلّع الحقل** لا الـbbox (إزالة الصحراء الحمراء) — تُمرَّر `geom`؛ وإن غابت تُجلَب الهندسة من DB كي يبقى القصّ دائماً | raster-service | #558 (`522a47e`) + احتياط الجلب الدائم #564؛ [`routers/cdse_tiles.py`](../../services/raster-service/routers/cdse_tiles.py) | fixed (يحتاج تأكيداً حيّاً بتشغيل CDSE) |
| CDSE-DATE | تطبيع `date` الفارغ (الواجهة ترسل `""`) ⇒ أحدث مشهد؛ وإسقاط `date` من رابط `cdse-tilejson` حين لا يُطلَب محدَّداً | raster-service | #559 (`1bef0cf`)؛ [`routers/cdse_tiles.py`](../../services/raster-service/routers/cdse_tiles.py)؛ اختبار [`test_cdse_date_normalization.py`](../../services/raster-service/test_cdse_date_normalization.py) | fixed + مُختبَر |
| CI-MIRROR | `ci.yml` فقد خطوة مرآة السجلّ `mirror.gcr.io` (ضاعت في إعادة كتابة `main` بدفع مباشر) ⇒ رفرفة Docker Hub تُعطّل *Integration Tests* | ci | إعادة #556 (`852fb5b`)؛ [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) | fixed (أُعيدت المرآة) |
| RASTER-DECOMP | تفكيك `raster-service/main.py` (٤٥ مساراً → ١٠ `routers/`، محفوظ السلوك، CDSE محفوظة) | raster-service | #551 (`51d650c`)؛ [`router_registry.py`](../../services/raster-service/router_registry.py)؛ حارس [`test_raster_router_decomposition_guard.py`](../../services/raster-service/test_raster_router_decomposition_guard.py) | fixed (٤٩ مساراً ثابتة) |
| AUTH-DECOMP | تفكيك `auth/main.py` (٢٧ `@app` → ٩ `routers/`، محفوظ السلوك، حسّاس أمنيّاً) | auth | #557 (`f92c994`)؛ [`services/auth/router_registry.py`](../../services/auth/router_registry.py)؛ حارس [`test_router_decomposition_guard.py`](../../services/auth/tests/test_router_decomposition_guard.py) | fixed (العدد ثابت N=31) |
| SVC-DECOMP | تفكيك ٤ خدمات متجانسة: odoo-bridge (14) · video-processor (12) · vegetation-analysis (12) · supervisor-agent (14) — نفس نمط raster/auth، محفوظ السلوك، عدد المسارات ثابت | odoo/video/vegetation/supervisor | #560 (`77123b3`) · #561 (`d40f1a9`) · #562 (`0abe6de`) · #563 (`7a36511`)؛ حُرّاس تفكيك لكلٍّ + مساعِد [`tests_v9/supervisor_route_source.py`](../../tests_v9/supervisor_route_source.py) | fixed |
| MAPHUB-CDSE | MapHub كان يستخدم `tiles` (COG محلّيّ غير موجود ⇒ 404)؛ تحويله إلى `cdse-tiles` + bbox/geom/tenant + إزالة تعبئة المضلّع؛ nginx `^~ /api/raster/` يمنع اعتراض regex `.png` + `X-Tenant-Id` من `$arg_tenant_id` | frontend/nginx | **PR #564 (مفتوح، قيد CI)**؛ [`HubMap.tsx`](../../frontend/src/components/maphub/HubMap.tsx) · [`nginx.conf`](../../frontend/nginx.conf) | open (PR #564 — قيد المراجعة) |
| NOTIF-WS | WebSocket الإشعارات: توصيف `websocket: WebSocket` (وإلّا فشل المصافحة) + `python-jose` المفقود (كان `from jose import` بلا تبعيّة) + تثبيت `websockets<14` | notification | **PR #564 (مفتوح)**؛ [`agents/notification/agent.py`](../../agents/notification/agent.py) · `requirements.txt` | open (PR #564 — قيد المراجعة) |

## ملاحظات

- **إغلاق 2026-06-28:** الفجوات `C5`/`H2`/`H5`/`C4-M1`/`SAM2`/`TERRAIN` نُقِلت من `open` إلى
  **`deferred`/`by-design`** — لا واحدةَ منها قابلةٌ للإصلاح الآليّ الآمن: كلٌّ يحتاج بيئةً
  (GPU/Flutter) أو تحقّقاً ميدانيّاً أو قراراً زراعيّاً. (صدق: إغلاقُ تتبُّعٍ موثَّقٌ بالسبب، لا
  ادّعاءُ حلٍّ.) `SAM2` فعليّاً **بالتصميم** (opt-in خلف `profile=gpu` + 503 صادق) لا عيباً.
  `CI-MIRROR` صار `fixed` بإعادة #556.
- **مصادر [حيّ] تنتظر التشغيل:** R6 (البوّابيّ)، H1 (التفويض فاشل-مفتوح، قرار)، OFFLINE
  (مزامنة Flutter كاملة) — انظر ملحق التحقّق المعماريّ في
  [`../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md`](../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md):44-74.
- **الأداة القابلة للتشغيل:** [`../../tools/sahool_inspector.py`](../../tools/sahool_inspector.py)
  (RLS coverage / router wiring / NATS subjects / endpoint authz / migration manifest).
