# تكافؤ الويب والموبايل — مصفوفة موحّدة + العقد المشترَك

> **المبدأ:** الويب (React/TypeScript) والموبايل (Flutter/Dart) **منصّتان مختلفتان
> بلا قاعدة كود واجهة مشترَكة** — فلا نزعم توحيداً غير موجود. ما يوحّدهما فعلاً هو
> **العقد المشترَك**: مسارات `/api/v1/*` نفسها، ونموذج صلاحيّات (RBAC) واحد،
> ودلالات حالات صادقة واحدة. هذه الوثيقة هي المصدر الواحد لحالة التكافؤ.

**آخر قياس:** 2026-10-25 على `main@d6d07051e` (`d6d07051e002a127e218d5c3219dccc38caf502a`).
كلّ رقم أدناه مقيس من الشجرة في ذلك الـSHA ومُسنَد إلى `path:line`؛ أرقام الأسطر صالحة
لذلك الـSHA فقط. طريقة إعادة القياس في §٥. (القياس السابق — «جلسة دمج شاشات الويب»،
حزيران 2026 — كان بلا SHA ولا أرقام، فاستُبدل كلّيّاً لا رُقِّع.)

---

## ٠. الأرقام المقيسة (2026-10-25 · `d6d07051e`)

| المقياس | الويب | الموبايل |
|---|---:|---:|
| شاشات مسجَّلة بعد الدخول | **79** مساراً في `NAV_SECTIONS` (عشرة أقسام) — `frontend/src/lib/routes.ts:66`، مُسطَّحة في `ALL_ROUTES` عند `frontend/src/lib/routes.ts:203` | **23** ودجة شاشة: 20 ملفّاً في `mobile/sahool_app/lib/screens/` + `features/realtime/realtime_screen.dart` + `features/field_forms/presentation/field_form_screen.dart` + `features/field_forms/presentation/field_forms_list_screen.dart` (أُضيفت 2026-10-25) |
| نضج الشاشات | 30 `stable` · 32 `beta` · 17 `alpha` (حقل `maturity` في `frontend/src/lib/routes.ts:72-197`) | لا حقل نضج |
| شاشات ما قبل الدخول | 3: `LoginPage`/`SignupPage`/`AcceptInvitationPage` تُعرَض شرطيّاً لا كمسارات — `frontend/src/App.tsx:235-238` | 2: `LoginScreen` (`mobile/sahool_app/lib/main.dart:172`) و`OnboardingScreen` (`mobile/sahool_app/lib/main.dart:263`) — من ضمن الـ22 |
| مسارات إضافيّة | 35 اسماً مستعاراً (alias) + مساران بمعامل `/:fieldId/workspace` + `*` → `/` — `frontend/src/App.tsx:425-465` | — |
| نداءات `/api/v1` | **472** نصّاً حرفيّاً فريداً يبدأ بـ`/api/v1/` في 68 ملفّ مصدر غير اختباريّ (منها 90 في سجلّ التغطية الوصفيّ `frontend/src/config/backendCoverageRegistry.ts`) | **52** موضع نداء = **51** زوجاً فريداً (طريقة، مسار) (`POST /api/v1/fields/import` يتكرّر عند `mobile/sahool_app/lib/services/api_service.dart:777` و`:800`) |
| نداءات خارج `/api/v1` | خارج نطاق هذا القياس | 14: ثمانية `/auth/*` ثمّ `/api/vegetation` و`/api/raster` و`/api/ai-agronomist` و`/api/edge` واثنان `/api/field-forms` — `mobile/sahool_app/lib/services/api_service.dart:287-572` و`mobile/sahool_app/lib/features/field_forms/data/field_forms_api.dart:108,132`؛ وقناة WS `/ws/notifications` — `mobile/sahool_app/lib/services/websocket_service.dart:53` |

**وجود الخادم (موبايل):** كلّ الـ51 زوجاً تحت `/api/v1` لها مُزخرِف FastAPI مطابق
(طريقةً ومساراً). 49 منها في `services/sahool-platform/api/routers/*` (مثلاً
`GET /api/v1/inventory/items` ← `services/sahool-platform/api/routers/inventory.py:89`)،
واثنان في خدمة `realtime-session`: `POST /api/v1/realtime/sessions` ←
`services/realtime-session/realtime_session/session_runtime.py:179` و`DELETE …/{session_id}` ←
`:202`. والـ14 خارج `/api/v1` تُحَلّ كلّها بعد إعادة كتابة البوّابة:
`/auth/*` ← `/v1/auth/*` (`nginx/nginx.v9.conf:214,223-224`) ← `services/auth/routers/session.py:27,128,184`
و`services/auth/routers/mfa.py:20,73,143` و`services/auth/routers/password_reset.py:21,41`؛
`/api/raster/*` ← `services/raster-service/routers/fields.py:1231`؛ `/api/ai-agronomist/chat` ←
`/v1/chat` ← `services/ai_agronomist/main.py:487`؛ `/api/vegetation/v1/analyze` ←
`services/sahool-platform/api/routers/compat_gateway.py:79`؛ `/api/edge/*` و`/api/field-forms/*` ←
وكيلا المنصّة `services/sahool-platform/api/routers/service_proxy.py:171,221` ← 
`services/edge-inference/main.py:222` و`services/scout-ingest-service/field_forms_api.py:392,464`.

**وجود الخادم (ويب، بلا تمييز الطريقة):** من الـ472 نصّاً: 420 يطابق مُزخرِفاً مباشرةً؛
8 هي `/api/v1/seasons*` تُعاد كتابتها إلى `/internal/seasons*` (`nginx/nginx.v9.conf:87-90,488-515`)
فتُخدَم في `services/scout-ingest-service/season_api.py:204-667`؛ 3 قوالب `${…}` متداخلة
فاتت المستخرِج وتحقّقتُ منها يدويّاً (`services/sahool-platform/api/routers/crop_operations.py:23`،
`services/sahool-platform/api/routers/decision_record.py:676`، `services/sahool-platform/api/routers/fields.py:2653`)؛
28 وصفيّة لا نداءات (أنماط `/*` و`{field_id}` في سجلّ التغطية، وتعليقان:
`frontend/src/services/api/client.ts:26` و`frontend/src/sections/HybridIndexPage.tsx:34`)؛
و**13 بلا أيّ مُزخرِف خادم** — انظر §٤.

---

## ١. العقد المشترَك (مصدر الحقيقة الوحيد لكلتا المنصّتين)

| البُعد | التفصيل |
|---|---|
| **الـAPI** | الأنظمة التشغيليّة تحت `/api/v1/*` عبر البوّابة (nginx: `location /api/v1/` ← المنصّة، `nginx/nginx.v9.conf:260,262`). الويب: `kongApi` (axios، الاسم تاريخيّ) — `frontend/src/services/api/client.ts:105`. الموبايل: `ApiService` (Dio) بـ`baseUrl = AppConfig.apiUri` — `mobile/sahool_app/lib/services/api_service.dart:41-45`. |
| **RBAC** | خمسة أدوار `owner, manager, agronomist, worker, viewer` مع تطبيع المرادفات و**fail-closed إلى viewer**: الويب `frontend/src/lib/permissions.ts:7,19`، الموبايل `mobile/sahool_app/lib/permissions.dart:7,21`. `canMutate` و`canManage` في المنصّتين (`frontend/src/lib/permissions.ts:158,165`؛ `mobile/sahool_app/lib/permissions.dart:25,28`). **فرق قائم:** الويب يضيف طبقة قدرات دقيقة `can(role, action, resource)` (`frontend/src/lib/permissions.ts:151`) وخريطة صفحات لكلّ دور (`canAccess` — `frontend/src/lib/permissions.ts:94`)؛ الموبايل يكتفي بالفحصين الخشنين. |
| **الصدق** | لا بيانات مُلفَّقة. حالة الخطأ تُعرَض كما هي (503 قاعدة معطّلة · 401 جلسة/توكن · 403 لا صلاحيّة · 404 غير موجود). الويب: `frontend/src/components/StateViews.tsx`. الموبايل: `mobile/sahool_app/lib/widgets/state_views.dart`. |
| **المستأجِر** | كلّ الاستعلامات مفهرَسة بـ`tenantId` من الجلسة؛ الخادم يطبّق RLS. (لم يُعَد قياس هذا البند في هذا التحديث.) |
| **مضيف الموبايل الافتراضيّ** | `API_URL` الافتراضيّ `https://api.sahool.ye` و`WS_URL` الافتراضيّ `wss://api.sahool.ye` — `mobile/sahool_app/lib/config/app_config.dart:7-8`. **هذا المضيف بلا سجلّ DNS** (فجوة `MOBILE-DEFAULT-API-HOST-HAS-NO-DNS-01`)، فبناءٌ بلا `--dart-define=API_URL=…` لا يصل إلى أيّ خادم. لم يُعَد قياس DNS في هذا التحديث (تجميد شبكيّ)؛ الادّعاء منقول من تسجيل الفجوة. |

> أي تغيير في عقد الخادم يجب أن يُعكَس في **الملفّين** (`frontend/src/services/api.ts`
> و`mobile/sahool_app/lib/services/api_service.dart`) وفي **منطق الصلاحيّات**
> (`permissions.ts` و`permissions.dart`) معاً.

---

## ٢. مصفوفة التكافؤ (نظام × ويب × موبايل × خلفيّة)

الويب: معرّف المسار في `frontend/src/lib/routes.ts`. الموبايل: ملفّ الشاشة في
`mobile/sahool_app/lib/screens/`. الخلفيّة: مُزخرِف أوّل نداء موبايل للنظام.

| النظام | خلفيّة `/api/v1` | ويب | موبايل | الوصول |
|---|---|---|---|---|
| لوحة المعلومات | `GET /api/v1/indicators/dashboard` — `services/sahool-platform/api/routers/indicators.py:65` | `dashboard` — `routes.ts:73` | `dashboard_screen.dart` (تبويب ١) | الكلّ |
| المؤشّرات/الأقمار | `GET /api/v1/fields/{id}/state` — `services/sahool-platform/api/routers/fields.py:4003` | `satellite`، `hybrid-index` — `routes.ts:92-93` | `satellite_screen.dart` (تبويب ٢) | الكلّ |
| الحقول | `GET/POST /api/v1/fields` — `services/sahool-platform/api/routers/fields.py:538,561` | `fields` — `routes.ts:82` | `fields_screen.dart` (تبويب ٣) + `field_create_wizard.dart` | الكلّ |
| مساحة عمل الحقل | `GET /api/v1/fields/{id}/season-workspace` — `services/sahool-platform/api/routers/season_workspace.py:271` | `field-workspace` — `routes.ts:84` | `field_workspace_screen.dart` (`mobile/sahool_app/lib/main.dart:114`) | الكلّ |
| المستشار الذكيّ | `/api/ai-agronomist/chat` ← `services/ai_agronomist/main.py:487` | `chatbot` — `routes.ts:76` | `advisor_screen.dart` (تبويب ٤) | الكلّ |
| المهام | `GET /api/v1/tasks` — `services/sahool-platform/api/routers/tasks.py:36` | `tasks` — `routes.ts:165` | `tasks_screen.dart` | الكلّ |
| **المخزون** | `services/sahool-platform/api/routers/inventory.py:39,89` | `inventory` — `routes.ts:168` | `inventory_screen.dart` | عامل+ |
| **المعدّات** | `services/sahool-platform/api/routers/equipment.py:38,93` | `equipment` — `routes.ts:170` | `equipment_screen.dart` | عامل+ |
| **أجهزة IoT** | `services/sahool-platform/api/routers/devices.py:42,97` | `devices` — `routes.ts:171` | `devices_screen.dart` | عامل+ |
| **الري التشغيلي** | `services/sahool-platform/api/routers/irrigation.py:99,156` | `irrigation-ops` — `routes.ts:110` | `irrigation_ops_screen.dart` | عامل+ |
| **البيانات المرجعيّة** | `services/sahool-platform/api/routers/master_data.py:34,95` | `master-data` — `routes.ts:191` | `master_data_screen.dart` | إدارة فقط |
| **الوثائق** | `services/sahool-platform/api/routers/documents.py:35,87` | `documents` — `routes.ts:192` | `documents_screen.dart` | إدارة فقط |
| **الحوكمة والتدقيق** | (ويب فقط) | `governance` — `routes.ts:193` | ⬜️ لا شاشة (لا ذكر لـ`governance` في `mobile/sahool_app/lib/`) | إدارة فقط |
| الإعدادات/الحساب | `/auth/*` ← `services/auth/routers/` | `settings` — `routes.ts:197` | `profile_screen.dart` + `mfa_setup_screen.dart` | الكلّ |
| المزارع | `GET/POST /api/v1/farms` — `services/sahool-platform/api/routers/farms.py:35,104` | `farm-map` — `routes.ts:83` | `farms_screen.dart` | الكلّ |
| مكالمة صوتيّة حيّة | `services/realtime-session/realtime_session/session_runtime.py:179` | خارج نطاق هذا القياس | `features/realtime/realtime_screen.dart` — خلف `SAHOOL_REALTIME_CALL_ENABLED` الافتراضيّ false (`mobile/sahool_app/lib/features/realtime/realtime_screen.dart:12`) | — |

**ما لا يقابله شيء في الموبايل:** 79 شاشة ويب مقابل 22 شاشة موبايل؛ الأقسام المتقدّمة
(الذكاء المتقدّم، البيانات والتحليل، التقارير، الريّ الهندسيّ…) ويبٌ فقط بالتصميم
— الموبايل تطبيق ميدانيّ لا لوحة خبير.

### ملاحظات تشغيليّة صادقة (متطابقة عبر المنصّتين)
- **الري:** `POST /api/v1/irrigation/valves/{id}/state` (`services/sahool-platform/api/routers/irrigation.py:178`) يسجّل **النيّة فقط**؛ التشغيل الفيزيائيّ بموافقة بشريّة (HIL).
- **الوثائق:** سجلّ **بيانات وصفيّة** + `storage_ref` — ليس رفع ملفّ.
- **الأجهزة:** تُعرَض القياسات **الحقيقيّة فقط** (`services/sahool-platform/api/routers/devices.py:209`).

---

## ٣. تنقّل المنصّتين

- **الويب:** شريط جانبيّ من عشرة أقسام مشتقّ من `NAV_SECTIONS` (`frontend/src/lib/routes.ts:66`)
  ومُرشَّح بـ`canAccess` (`frontend/src/lib/permissions.ts:94`؛ مستورَد في `frontend/src/App.tsx:16`).
- **الموبايل:** خمسة تبويبات — نظرة عامّة · صحّة الحقل · بيانات · تحليل · إعدادات
  (`mobile/sahool_app/lib/main.dart:251-273`). التبويب الخامس `MoreScreen` يفتح المزارع
  والأقمار والمهام والحساب وMFA و**«العمليّات»** (`mobile/sahool_app/lib/screens/more_screen.dart:37-55`)؛
  و`OperationsHubScreen` شبكة وحدات مُرشَّحة بـ`canManage` للبيانات المرجعيّة والوثائق
  (`mobile/sahool_app/lib/screens/operations_hub_screen.dart:29-44`).
  *(تصحيح للنسخة السابقة: لم يعد «العمليّات» تبويباً سادساً؛ صار بنداً داخل التبويب الخامس.)*

---

## ٤. الفجوات المتبقّية في التكافؤ (صادقة)

| الفجوة | الدليل | شرط الإغلاق |
|---|---|---|
| مضيف الموبايل الافتراضيّ بلا DNS — `MOBILE-DEFAULT-API-HOST-HAS-NO-DNS-01` | `mobile/sahool_app/lib/config/app_config.dart:7-8` | مضيف قائم افتراضيّاً، أو رفض البناء بلا `API_URL` |
| ~~شاشة نماذج الحقل غير موصولة بالتنقّل~~ — **أُغلقت 2026-10-25** | زرّ «النماذج الميدانيّة» في شريط مساحة عمل الحقل (`mobile/sahool_app/lib/screens/field_workspace_screen.dart`) يفتح `FieldFormsListScreen` ومنها `FieldFormScreen`؛ يثبته `mobile/sahool_app/test/field_forms/field_forms_navigation_test.dart` | — |
| 13 ثابت مسار ويب بلا مُزخرِف خادم ولا نداء | سبعة `phase8` في `frontend/src/lib/globalScaleRuntime.ts:20-26` (الكائن غير مستورَد خارج ملفّه)؛ ستّة في `frontend/src/lib/enterpriseGisPhase7.ts:41-50` (collaboration sessions/events، distributed plan/jobs، `digital-twin/scenarios/simulate`، `readiness/planet-scale`) والمستعمَل منه `collaborationSocket` وحده (`:54`) | بناء المسارات أو حذف الثوابت — لا تُعرَض كقدرة |
| شاشة حوكمة للموبايل | الويب فقط (`routes.ts:193`) | جلسة بناء Flutter |
| طبقة القدرات الدقيقة في الموبايل | `can()` في الويب فقط (`frontend/src/lib/permissions.ts:151`) | نقل `can()` إلى `permissions.dart` |
| تحقّق بناء الموبايل | لا Flutter SDK في بيئة القياس | `flutter analyze` في بيئة فيها SDK |

---

## ٥. كيف يُعاد القياس

من جذر المستودع، على الـSHA المراد (ثمّ حدِّث السطر «آخر قياس» أعلاه):

```bash
git rev-parse HEAD
# الويب: شاشات مسجَّلة (كلّ عنصر قسم له path) — المتوقَّع 79 عند d6d07051e
grep -cE "^\s+\{ id: '[^']+',\s+path: '" frontend/src/lib/routes.ts
grep -oE "maturity: '[a-z]+'" frontend/src/lib/routes.ts | sort | uniq -c
grep -c '<Route path="' frontend/src/App.tsx          # 38 = 35 alias + 2 workspace + '*'
# الموبايل: شاشات — 20 + 2
ls mobile/sahool_app/lib/screens/*.dart | wc -l
find mobile/sahool_app/lib/features -name '*_screen.dart' | wc -l
# الموبايل: مواضع نداء /api/v1 — 52
grep -rhoE "'/api/v1/[^']*'" mobile/sahool_app/lib | wc -l
```

**مطابقة الخادم:** امسح `services/**/*.py` (عدا الاختبارات) بـ`ast` عن مُزخرِفات
`@<router>.get|post|put|patch|delete("…")`، وأضِف `prefix` من `APIRouter(prefix=…)` في
الملفّ نفسه (لا `include_router(prefix=…)` في المنصّة عند هذا الـSHA)، ثمّ طابِق مسار
العميل بعد استبدال `$var`/`${…}` بمقطع واحد و`{param}` بـ`[^/]+`. عند `d6d07051e`: 1099
مُزخرِفاً. ما لا يطابق مباشرةً افحصه في `nginx/nginx.v9.conf` (إعادات الكتابة:
`/auth/`، `/api/raster/`، `/api/ai-agronomist/`، `/api/v1/seasons`) وفي وكلاء
`services/sahool-platform/api/routers/service_proxy.py` قبل أن تعدّه مفقوداً. حدود
الطريقة: نصوص حرفيّة فقط (لا مسارات تُبنى ديناميكيّاً)، ومطابقة الويب لا تتحقّق من الطريقة.
