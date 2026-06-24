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
| C5 | NDVI الحقيقيّ معلوماتيّ لا يُغيّر صلاحيّة القرار | platform/الحالة القانونيّة | `api/field_state_projection.py` (`_apply_ndvi_threshold_gating`)؛ فرع `claude/c5-ndvi-threshold-flag` | **closed (implemented, gated, calibration absent)** — علم `APPLY_NDVI_THRESHOLDS` (default off) يُعلن `insufficient_field_calibration` صراحةً؛ لا عتبات معايَرة ⇒ لا اختلاق. تفعيل فعليّ يحتاج معايرة ميدانيّة (بطاقة محصول). |
| H2 | **٧** اشتراكات NATS بلا ناشر (لا ٨) — تصنيفها «ناشر مفقود متوقَّع» لا «اشتراك ميّت»: تطابق `EVENT_EMOJI` وأنواع الأحداث (`api/main.py:1670`)، فالإصلاح = بناء ناشرين عبر outbox لا تقليم الاشتراكات (قرار معماريّ). الموضوعان `satellite.*.computed`/`sahool.events.>` لهما ناشرون (ليسا يتيمين). `weather.forecast.updated` مُعالَج خلف راية `WEATHER_GRID_PIPELINE_ENABLED` (OFF). | notification/الأحداث | فرع `claude/h2-nats-publishers-flag`؛ `api/event_bus.py` (`nats_publishers_enabled`) · `api/main.py:_start_outbox_worker`؛ `agents/notification/agent.py:340-346` | **closed (implemented, gated, env-unverified ON)** — علم `FEATURE_NATS_PUBLISHERS` (default off) يحرس تشغيل OutboxWorker؛ OFF ⇒ `record_decision_only` (الأحداث في outbox، لا تُفقَد) + إعلان السجلّ؛ ON ⇒ `publish_event`. ON يحتاج NATS حيّاً (env-unverified). الاشتراكات الخدميّة الـ8 تبقى يتيمة (خدماتها غير مُسلَّمة). |
| H4 | ET0 Hargreaves مُكرَّر بقيم Ra متعارضة — وُحِّد في `core/engines/et0.py` | platform/الأغرونوميا الكمّيّة | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:23` (#351/#356)؛ تأكيد #457 | ✅ fixed + مؤكَّد باختبارات انحدار (#457؛ متبقٍّ موثَّق: إعادتان عبر-خدمات weather_server/wofost) |
| H5 | احتياج الريّ بصيغتين (مع/بلا ملوحة) — **وُحِّد (#464):** قرار المستخدم «بلا ملوحة افتراضيّاً، قابلة للإدخال». الملوحة صارت **مفتاحاً اختياريّاً off-افتراضيّاً** في `compute_irrigation` و`water_balance` (Ks=1، تسريب=0 ⇒ المساران متّسقان)، تُفعَّل **تلقائيّاً** عبر `core/salinity_policy.salinity_decision` عند تحليل مخبريّ موثوق (ECe/ECw + حداثة<365 + ثقة≥0.8). أُزيل تكرار `leaching_requirement`. | platform/الريّ | #464؛ `core/engines/fao56.py:compute_irrigation` · `api/water_balance.py` · `core/salinity_policy.py`؛ أصل: `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:38,131` | ✅ fixed (موحّد + سياسة تفعيل تلقائيّ؛ متبقٍّ: ربط بـCanonicalFieldState/water_kernel) |
| H6 | عتبات الملوحة/pH/الحرارة مُكرَّرة — وُحِّدت في `core/thresholds.py` | platform/العتبات | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:21` (#352)؛ أصل: `:132` | fixed (يحتاج تأكيداً حيّاً) |
| C4/M1 | الموبايل: بنية push (FCM/APNs) + عميل WebSocket | mobile/الإشعارات | فرع `claude/c4-m1-mobile-push-flag`؛ `agents/notification/agent.py` (`push_decision`/`_record_push_fallback`) | **closed (implemented, gated, env-unverified ON)** — backend: علم `FEATURE_MOBILE_PUSH` (default off) + سجلّ احتياطيّ دائم `notification_delivery` بدل الإسقاط الصامت (`create_notification_record`). ON يحتاج FCM حيّاً + tokens (env-unverified). WebSocket منفَّذ أصلاً في الوكيل. عميل Flutter UI يبقى منفصلاً. |
| SAM2 | خادم استدلال SAM2 يحتاج GPU (opt-in)؛ بدونه 503 صادق | field-segmentation/sam2 | `docker-compose.v9.yml:1351` (profile=gpu)؛ `services/sam2-inference/main.py:74`؛ [`docs/SAM2_DEPLOYMENT.md`](../../docs/SAM2_DEPLOYMENT.md) | **implemented-gated-but-env-unverified** (محروس بـprofile=gpu؛ يحتاج GPU حيّاً — لا production-ready) — انظر [`../decisions/bundle-c-status.md`](../decisions/bundle-c-status.md) |
| C-Embeddings/RAG | Field Embeddings / RAG | R&D/knowledge | `services/qdrant-seed/` · `services/local-ai-rag/` · `api/decision_explainer.py:38`؛ [`../decisions/bundle-c-status.md`](../decisions/bundle-c-status.md) | **closed (implemented-as-optional-services, deployment opt-in)** — RAG لا يدخل مسار قرار إنتاجيّ بلا حراسة (مُتحقَّق)؛ إثراء شرح opt-in. لا حاجة `FEATURE_CONSERVATIVE_RAG`. |
| C-Ensemble | Multi-engine Ensemble | R&D | `core/engines/fusion.py` (fusion مؤشّرات، شيء مختلف)؛ [`../decisions/bundle-c-status.md`](../decisions/bundle-c-status.md) | **open (concept-only / not implemented)** — تصويت محرّكات متعدّدة غير منفَّذ؛ fusion.py للمؤشّرات الطيفيّة ليس هو. |
| C-Foundation | نماذج أساس (Prithvi/DINOv3) | R&D | لا كود؛ [`../decisions/bundle-c-status.md`](../decisions/bundle-c-status.md) | **not started** (رهان R&D مقترح — لا استيراد/أوزان/استدلال) |
| C-ISOXML | Machine Integration (ISOXML) | precision-ag | [`../decisions/strategy.md`](../decisions/strategy.md) (أُوقِف بصدق)؛ بديل `api/prescription_shapefile.py` (#456) | **deferred by design (#456)** (مُلاءمة اليمن — Shapefile كافٍ، لا John Deere/Trimble) |
| MAP-QA | افتراض MapLibre/WebGL ينتظر بوّابة QA حيّة (Playwright) | frontend/الخرائط | بوّابة Playwright #441 (`d23eb6b`)؛ سويت [`tests/`](../../frontend/) | open (البوّابة مُنشأة؛ ينتظر تشغيلاً حيّاً) |
| TERRAIN | `TerrainView3D` يحتاج مسار `/terrain` خادميّ | frontend/الخرائط | [`frontend/src/components/maphub/TerrainView3D.tsx`](../../frontend/src/components/maphub/TerrainView3D.tsx) | open (P2) |
| IND-SRC | مصدر مؤشّرات الموبايل الصحيح (`getFieldIndicators`) | mobile | #445 (`a7909e6`)؛ [`mobile/sahool_app/lib/services/api_service.dart`](../../mobile/sahool_app/lib/services/api_service.dart) | fixed |
| MERGE | دمج/انقسام الحقول ذرّيّاً (سدّ خطر البيانات الثلاثيّة) | platform/الحقول | #443 (`2456d2b`)؛ [`api/routers/fields.py`](../../services/sahool-platform/api/routers/fields.py)؛ اختبار [`tests_v9/test_fields_merge_split_atomic.py`](../../tests_v9/test_fields_merge_split_atomic.py) | fixed |
| NDVI-MOB | مسار سلسلة NDVI في الموبايل (404) | mobile | #444 (`9e00d0a`)؛ [`mobile/sahool_app/lib/screens/satellite_screen.dart`](../../mobile/sahool_app/lib/screens/satellite_screen.dart) | fixed |
| WUE | لا كفاءة استخدام مياه مُجمَّعة على فترة (الدفتر يوميّ فقط) | platform/المياه | #477 (`f01c468`)؛ `api/water_efficiency.py` + `routers/water_ledger.py` (`GET …/water-efficiency`) | **fixed (water-balance)** — WUE من التوازن المائيّ (ETc مقابل المُورَّد) + over_application؛ الغلّة خارج النطاق (لا حلقة)؛ needs_data/needs_irrigation_data عند النقص. |
| SUSTAIN | لا درجة استدامة مُفسَّرة لكلّ حقل (إشارات تربة/مياه مبعثرة) | platform/الاستدامة | فرع `claude/field-sustainability-index`؛ `api/field_sustainability.py` + `routers/reports.py` (`GET …/sustainability`) | **fixed (reuse-only)** — تجميع تربة+مياه يُعيد استخدام `salinity_class`/`water_stress_class` الكنسيّين (لا حساب)؛ المغذّيات `needs_data` بصدق (NPK غير مقيس)؛ بلا كربون؛ بُعد غائب يُستبعَد + إعادة تسوية. قراءة فقط، لا تغيير قرار. |

## ملاحظات

- **مصادر [حيّ] تنتظر التشغيل:** R6 (البوّابيّ)، H1 (التفويض فاشل-مفتوح، قرار)، OFFLINE
  (مزامنة Flutter كاملة) — انظر ملحق التحقّق المعماريّ في
  [`../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md`](../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md):44-74.
- **الأداة القابلة للتشغيل:** [`../../tools/sahool_inspector.py`](../../tools/sahool_inspector.py)
  (RLS coverage / router wiring / NATS subjects / endpoint authz / migration manifest).
