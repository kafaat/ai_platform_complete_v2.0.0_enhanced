# مراجعة وإصلاح مداخل main — 11 نوفمبر 2026

الأساس المثبت: `d022c3e650e2cb68d19466bdeb3073350002b3e4`. سُلِّمت الإصلاحات حزمةً خارجيّة (رقعة) وطُبِّقت على الفرع `claude/main-runtime-fixes-20261111`؛ الفرع والالتزام المذكوران في الحزمة الأصليّة محلّيّان لدى المُسلِّم وليسا في هذا المستودع. `fixed` يعني إصلاح الكود مع شاهد محلي؛ لا يعني `verified` في الإنتاج.

## نتائج المراجعة الخمس عشرة

الجرد الأصلي 30 ملف `main.py`. أثبتت الجولة الأولى 13 عيباً، ثم أثبتت الجولة الأعمق ترتيب إقلاع soil ورفض ZLMediaKit. ليست هذه النتائج شهادة شاملة للخدمات. رموز الصفوف أدناه مراجع داخل التقرير وليست سجلات فجوات مكررة.

| المرجع | العيب | حالة الكود المحلية | اختبار الانحدار |
|---|---|---|---|
| AUTH-01 | تجديد الجلسة يتجاوز شرط تفعيل MFA (`services/auth/routers/session.py`) | fixed — شاهد انحدار ناجح | [`tests_v9/test_auth_enrollment_http.py`](../../tests_v9/test_auth_enrollment_http.py) |
| AUTH-02 | أول مدير لا يستطيع إكمال تسجيل MFA (`services/auth/mfa_enrollment.py` + `routers/{mfa,session}.py`) | fixed بعد المراجعة (انظر §المراجعة اللاحقة) | [`tests_v9/test_auth_enrollment_http.py`](../../tests_v9/test_auth_enrollment_http.py) |
| LIFE-01 | فشل التحقق من دور قاعدة البيانات لا يمنع الإقلاع (`services/sahool-platform/api/main.py`) | fixed — شاهد انحدار ناجح | [`tests_v9/test_pool_single_owner_audit.py`](../../tests_v9/test_pool_single_owner_audit.py) |
| GEO-01 | SAM2 يسقط صورة ExG ومدخلات التوجيه (`services/field-segmentation/main.py`) | fixed — شاهد انحدار ناجح | [`services/field-segmentation/test_segmentation.py`](../../services/field-segmentation/test_segmentation.py) |
| ROUTE-01 | تلف استجابة gzip في الوسيط (`services/sahool-platform/api/routers/service_proxy.py`) | fixed — شاهد انحدار ناجح | [`services/sahool-platform/tests/test_service_proxy_transport.py`](../../services/sahool-platform/tests/test_service_proxy_transport.py) |
| LIFE-02 | مهلة الإقلاع لا تحد محاولة الاتصال المعلقة (`shared/startup_retry.py`) | fixed — شاهد انحدار ناجح | [`tests_v9/test_startup_db_connect_retry.py`](../../tests_v9/test_startup_db_connect_retry.py) |
| GEO-02 | التقسيم يحجب حلقة الأحداث (`services/field-segmentation/main.py`) | fixed — شاهد انحدار ناجح | [`services/field-segmentation/test_segmentation.py`](../../services/field-segmentation/test_segmentation.py) |
| GEO-03 | قبول مضلعات غير صالحة هندسيًا (`services/field-segmentation/main.py`) | fixed — شاهد انحدار ناجح | [`services/field-segmentation/test_segmentation.py`](../../services/field-segmentation/test_segmentation.py) |
| AI-01 | جاهزية AgriAI تعيد 200 رغم ready=false (`services/agriai-engine/main.py`) | fixed — شاهد انحدار ناجح | [`tests_v9/test_edge_agriai_entrypoint_contracts.py`](../../tests_v9/test_edge_agriai_entrypoint_contracts.py) |
| AI-02 | مدخلات Edge غير الصالحة تتحول إلى 500 (`services/edge-inference/main.py`) | fixed — شاهد انحدار ناجح | [`services/edge-inference/tests/test_entrypoint_validation_lifecycle.py`](../../services/edge-inference/tests/test_entrypoint_validation_lifecycle.py) |
| AI-03 | مزامنة Edge لا تتوقف بانتهاء lifespan (`services/edge-inference/main.py`) | fixed — شاهد انحدار ناجح | [`services/edge-inference/tests/test_entrypoint_validation_lifecycle.py`](../../services/edge-inference/tests/test_entrypoint_validation_lifecycle.py) |
| AI-04 | مهام Actuator لا تغلق قبل مسبح قاعدة البيانات (`services/actuator-service/actuator_runtime.py`) | open — مسار actuator مجمّد؛ لم يُعدّل | إيصال إعادة إنتاج خارجي؛ لا إصلاح ضمن الفرع |
| VIDEO-01 | رقم كاميرا USB يتحول إلى اسم ملف (`services/video-processor/main.py`) | fixed — شاهد انحدار ناجح | [`tests_v9/test_video_capture_source_contract.py`](../../tests_v9/test_video_capture_source_contract.py) |
| SOIL-01 | تشغيل soil المباشر يسبق تسجيل الراوترات (`services/soil-service/main.py`) | fixed — شاهد انحدار ناجح | [`tests_v9/test_soil_script_entrypoint.py`](../../tests_v9/test_soil_script_entrypoint.py) |
| VIDEO-02 | نجاح HTTP يخفي رفض ZLMediaKit داخل JSON (`services/video-processor/main.py`) | fixed — شاهد انحدار ناجح | [`tests_v9/test_video_capture_source_contract.py`](../../tests_v9/test_video_capture_source_contract.py) |

## حدود الإصلاح والتبعيات

- المصادقة: مسار تسجيل MFA محدود الصلاحية للمدير الأول، وسياسة MFA عند التجديد وإبطال الجلسات عند التعطيل. راجع اختبارات الطلبات الفعلية، ولا تعامل رمز التسجيل كرمز دخول عام.
- التوافر: فحص دور DB يغلق عند تعذر التحقق، مهلة الاتصال تحد المحاولة، وإغلاق مهمة Edge داخل دورة الحياة. actuator يبقى مفتوحاً بسبب التجميد؛ لا تعديل ضمني للسياسة.
- GIS: عقد SAM2 صريح للتوجيه والمعالجة والإسناد، رفض الصور غير المسندة، فحص هندسة المضلعات ونقل العمل الحاجب خارج الحلقة. الاختبارات تستبدل الاستدلال؛ تشغيل أوزان GPU فعلياً `NOT_RUN`.
- الفيديو: نوع USB صحيح، وفشل رمز ZLM يبقي المصدر الأصلي. الشواهد تستخدم capture spy وHTTP بديل؛ كاميرا فعلية `NOT_RUN`.
- XTTS: صُحّحت الإرشادات ورسالة عدم التوافر فقط. `TTS==0.22.0` لا يدعم Python 3.12 في الصورة الأساسية. الفجوة القائمة `TTS-XTTS-PROVIDER-CANNOT-PRODUCE-AUDIO-01` تبقى open؛ لا ادعاء دعم XTTS كاملاً ولا تبعية جديدة.
- فحص التبعيات الموسع أنتج إيصالات resolver مستقلة. التوافق القابل للحل ليس قفلاً عابراً أو بناء صورة. الفجوة القائمة `NO-DEPENDENCY-LOCK-AND-CVE-FLOORS-BELOW-FIXES-01` تبقى open؛ إصلاحات GPU والواجهة ضمن تجميع الفرع لا تغلقها.

## حالة الأدلة

حزم العمل الخارجية تحمل `review-evidence` و`deep-evidence` و`dependency-evidence` و`fix-evidence`، وفيها سكربتات وJUnit وسجلات. هذه أسماء داخل حزم التسليم، وليست روابط مستودع إلى ملفات غائبة. اختبارات المصدر مرتبطة أعلاه.

الاختبارات المركزة: 953 نجاحاً و18 تخطياً، بعد إزالة تكرار المعرّف بين الإيصالات المختارة؛ ليست مضافة إلى أعداد الأجنحة أدناه.

| الجناح | الجولة الشاملة الأولى: نجاح / فشل / تخطي | إعادة الفشل |
|---|---|---|
| `pytest -m unit` | 13248 / 71 / 48 (571 حالة مستبعدة بالعلامة) | 31 بعد تثبيت SOCKS، و39 بعد جلب التاريخ الأصلي؛ اختبار الجرد ضمن ملف نجحت حالاته الـ17 |
| `pytest tests/` | 1092 / 3 / 15 | الثلاثة نجحت بعد استعادة التاريخ والتزام المصدر محلياً |
| جناح المنصة | 5487 / 29 / 1 | الـ29 نجحت بعد تثبيت SOCKS |

المحصلة بعد إعادة الحالات الفاشلة: **19930 نجاحاً و64 تخطياً**. هذه تسوية لثلاثة أجنحة وإعادات محددة، وليست ادعاء تشغيل واحد بلا إخفاق. أُصلحت البيئة دون تغيير اعتماديات الإنتاج: `socksio==1.0.0` للنقل الاختياري الذي تتطلبه بيئة SOCKS، واستعادة 18 التزام دمج ونطاقين تاريخيين؛ تطابقت 41 بصمة ملف مع سجلات التفويض. أُصلح تثبيت رقم سطر SAM2 باستنتاج الموضع من AST، مع حفظ تأكيد علاقة الخدمة ومزوّدها. كما تحولت علامة اختبار ACL إلى مُزخرف مباشر يفهمه الحارس.

نجح التوليد وفحص ثباته في الجولة الشاملة. يُحفظ فحص النسخة النهائية وإيصال الفرع في حزمة التسليم؛ لا يُمحى السجل الأحمر الأول. اختبار NATS هنا يختبر بروتوكول التنظيف ببدائل العملية، وليس تشغيل NATS أو Docker حياً. Docker الفعلي وGPU والأجهزة والتطبيق المحمول والنشر الحي: `NOT_RUN`.

مسار إعداد MFA مثبت على API؛ ربط الواجهة باستجابة 403 ورمز `enrollment_token` ليس منفذاً في هذا النطاق. رقعة actuator مختبرة بخمس حالات مستقلة ومحفوظة خارج الفرع؛ تطبيقها يتطلب تفويضاً موقعاً مرتبطاً بالمرشح النهائي وفق GATE-01. القفل العابر ودعم XTTS الكامل باقيان مفتوحين.

## المراجعة اللاحقة والإصلاحات (2026-11-11)

راجع سبعةُ وكلاء الحزمةَ كما سُلِّمت، ثمّ أصلح خمسةٌ على ملفّات منفصلة، وتحقّق اثنان عدائيّاً، ثمّ أُغلِق ما نُقِض. لا يُنسَب «fixed» إلّا مع اختبار يحمرّ قبل الإصلاح ويخضرّ بعده.

| ما وُجد في الحزمة | الأثر | ما تغيّر |
|---|---|---|
| حارس التفعيل يربط `updated_at`، والزناد `trg_users_updated_at` يغيّره عند استهلاك خطوة TOTP | كلّ تفعيل على Postgres حقيقيّ ⇒ 409؛ AUTH-02 لم يُصلَح فعلاً | الربط بأعمدة الأمان (كلمة السرّ/الدور/المستأجر/النشاط/السرّ المشفّر)؛ `FakeConnection` يحاكي الزناد؛ اختبار Postgres حيّ في وظيفة Integration Tests |
| `routers/mfa_enrollment.py` وحدةٌ مساعِدة داخل `routers/` | يُسقط `test_no_orphan_router_module` (Unit Tests الحاجبة) | نُقلت إلى `services/auth/mfa_enrollment.py` مع سطر `COPY` في `Dockerfile` |
| الرمز الخاطئ يُبطل الإثبات، والحدّ يُعَدّ بعد الفحص | لا إعادة محاولة؛ والطلبات المتوازية تتجاوز الحدّ | فحص غير مُتلِف ثمّ استهلاك عند النجاح؛ حجز المحاولة بـ`INCR` ذرّيّ قبل الفحص (≤5 فحوص لكلّ إثبات) |
| التسجيل بكلمة السرّ وحدها لكلّ حساب حسّاس غير مُسجَّل | توسعة سطح الهجوم عمّا كان (403) | `MFA_SELF_ENROLLMENT_SCOPE`: `bootstrap` افتراضاً (أوّل مدير في مستأجر بلا مدير مُسجَّل)، `all`، `off`؛ تهجئات التعطيل ⇒ `off` |
| إبطال الجلسات عند تعطيل MFA بلا اختبار | طفرةٌ تنجو | اختبار يحمرّ بحذف سطر الإبطال |
| الواجهة لا تعالج 403 + `enrollment_token` | الإصلاح غير قابل للوصول من أيّ واجهة | خطوة تسجيل في صفحة الدخول (setup ثمّ activate، الإثبات في الذاكرة فقط) |
| SAM2: الواجهة ترسل لقطة شاشة دائماً | كلّ طلب auto/hybrid ⇒ 422 | الواجهة لا ترسلها، والخادم يتجاهل لقطةً غير مُسنَدة؛ صندوق ExG من المكوّنات المتّصلة |
| `startup_retry` ينام آخر مهلة ثمّ يرفض بلا محاولة أخيرة | رفض إقلاعٍ كان سينجح | محاولة أخيرة مضمونة بميزانية، وسجلّ ERROR عند الرفض |
| LIFE-01 مُصلَح في المنصّة فقط | 7 خدمات تبقى fail-open | حارس دور مشترك يغلق عند الخطأ/المهلة/غياب الصفّ |
| رفض ZLMediaKit (HTTP 200 + code≠0) في record/snapshot | أحداث `recording.started` كاذبة | `code≠0` فشلٌ في كلّ العميل؛ «already exists» لا يُعاد استخدامه بل يُزال الوكيل اليتيم ويُنشأ بعنوان هذا البثّ |
| اختبارات edge-inference لا تُجمَع في CI | AI-02/AI-03 بلا حارس فعليّ | تُشغَّل في Unit Tests |

**ترتيب النشر:** `sam2-inference` قبل `field-segmentation` (الخادم الجديد يقبل العميل القديم؛ العميل الجديد أمام خادم قديم يردّ 502 صريحاً بدل ادّعاء ExG لم يُطبَّق).

**يبقى مفتوحاً (خارج هذا الفرع):** AI-04 (actuator مجمّد، GATE-01)؛ دعم XTTS الكامل والقفل العابر تحت معرّفيهما القائمين؛ تطبيق الموبايل لا يعالج 403 + `enrollment_token` بعد؛ نمط SOIL-01 في `vegetation-analysis-service` و`odoo-bridge` و`supervisor-agent`؛ كلفة تسمية مكوّنات ExG (~1–1.7 ث على نوافذ 1024² مشوّشة)؛ `mfa_enabled_at` غير مُعبّأ للحسابات القديمة (موثّق في `docs/runbooks/RAILWAY_AUTH_DEPLOYMENT.md`).

