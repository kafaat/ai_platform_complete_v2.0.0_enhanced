مراجعة إغلاق شرائح أعطال التشغيل — 2026-09-08

نُفّذت الإصلاحات في شرائح مستقلة باستخدام وكلاء متوازيين، ثم جُمعت في commits قابلة للمراجعة.
الأساس المقارن `799842d3`؛ الشيفرة الأساسية والطفرات حتى `59c4eb8f`، وتصحيحات التحقق اللاحقة حتى `8078bda3`.
هذا الأساس هو الشجرة المتاحة للمراجعة؛ لم تُثبت مطابقته لنسخة التشغيل المحلية التي استُخدمت لإنتاج الوثيقة الأصلية.

«مُصلح محلياً» يعني وجود تعديل واختبار سلوك مناسب على الشيفرة، مع طفرات مسجلة لإرجاع أعطال ممثلة.
«معلق حياً» يعني أن قياس الخدمة المنشورة أو PostgreSQL بالأدوار المقيدة لم يُقدَّم بعد.
إصلاح عقد أو منع جواب غير مؤسس لا يعني أن القدرة أصبحت متاحة من طرف إلى طرف.
خصوصاً: الحجب عند غياب الدليل نتيجة صحيحة للإصلاح، لكنه يبقي استكمال مصدر ذلك الدليل عملاً مطلوباً.

| الشريحة | commits المجمعة | الدليل المحلي ومصدره | الحكم وحدود الإغلاق |
|---|---|---|---|
| P0-1: مسار MCP المكرر | `515bd392` | أصول URL بلا بادئة مكررة في `docker-compose.v9.yml:784`؛ التطبيع والطلب في `services/supervisor-agent/mcp_client.py:83,159` | مُصلح في العقد؛ وصول الخدمات المنشورة يحتاج قياساً حياً. |
| امتداد MCP: الهوية والنطاق والإقلاع والاكتشاف | `612bd2dc`, `515bd392`, `1c7b45fb` | منح قراءة صريحة في `services/auth/main.py:595`، ربط اعتماد كل طلب في `mcp_client.py:99`، تحقق الخادم في `services/mcp_servers/shared/oauth_middleware.py:43` | لا اعتماد على رمز خدمة مشترك بوصفه مستخدماً؛ نشر مفاتيح وهوية متطابقين وتجديد رموز المستخدمين يظلان مطلوبين. |
| P0-2: user_id والمراجعة البشرية | `36faa270` | عقد INTEGER في `services/guardrails-engine/main.py:40,52`؛ معاملة المستأجر في `human_in_loop.py:46`؛ الإدراج في `:105` | إصلاح النوع والحفظ والعزل محلياً؛ اختبار PostgreSQL الحقيقي بالأدوار المقيدة معلق. |
| P1-3: الاستثمار يتجاوز التقييم الاقتصادي | `36faa270` | عقد مالي خاص بالإجراء في `services/guardrails-engine/contracts.py:15`، وطبقة اقتصادية في `tiers/economic_tier.py:35` | الاستثمار يمر بالطبقة؛ الغياب لا يصير صفراً؛ مصدر مالي قانوني للوكيل ما زال مطلوباً. |
| P1-4: مهلة الطقس ورسالة فارغة | `ed49c948` | حد زمني للطلب وتجميع عينات في `services/weather-service/weather_runtime.py:349,371,430`؛ أخطاء معلنة في `services/sahool-platform/api/weather_service_client.py:45,96` | مُصلح محلياً؛ سلوك المزوّد والشبكة في النشر غير مقاس هنا. |
| امتداد المستشار: مهلات KG وRAG | `dc7b0901` | حد استرجاع مسمى في `services/ai_agronomist/ai_evidence_runtime.py:50` | مهلة النقل تعود بخطأ واضح؛ لا شهادة بتوافر KG/RAG أو اكتمال محتواهما. |
| P1-5: drawing_features | `36b1a6b9`, `3e186968`, `45dad915` | إنشاء الجدول والفهارس وFORCE RLS في `migrations/v230_drawing_features.sql:6,30,36`، مع إدراج الهجرة في MANIFEST ومشغّل SQL وإزالة DDL من الراوتر | إصلاح بنيوي مُنفذ؛ استثناء ملكية محدود ينتهي 2026-11-30، والتحقق بدور التطبيق في قاعدة حقيقية معلق. |
| P1-5: devices | `36b1a6b9` | استخدام `current_stage` بمراحل محددة في `services/sahool-platform/api/routers/devices.py:233` | أُصلح استعلام دورة الحياة المعيب؛ لا يوجد جدول مطلوب اسمه devices في ذلك المسار. |
| P1-5: مساحة الموسم | `ba51967d` | SAVEPOINT للاستعلامات الاختيارية وتطبيع أولوية التوصيات في `services/sahool-platform/api/routers/season_workspace.py:221` | أُصلح سبب 503 محلي مُعاد إنتاجه؛ لا ننسب إليه 503 الوثيقة دون traceback التشغيل الأصلي. |
| P1-6: استدعاء معالج خطأ GIS | `36b1a6b9` | استدعاءات بوسيطَي الفعل والاستثناء؛ أمثلة `services/sahool-platform/api/routers/gis_cloud_native.py:211,338,665` | إصلاح 16 موضعاً؛ مسارات فشل قاعدة مضبوطة تعيد 503 بدلاً من TypeError/500. |
| P2-7: النوايا العربية | `d374c7c1` | التطبيع وحدود الكلمات والأولوية في `services/supervisor-agent/router.py:11,18,80` | تغطية الأمثلة الموجبة والسالبة والتعادل؛ لا ادعاء باستيعاب كل اللهجات والصيغ. |
| P2-8: S3 فارغ | لا تغيير في سياسة التخزين | `services/raster-service/object_store.py:68,111`؛ volume مشترك في `docker-compose.v9.yml:1255,1306,1367,1402` | رُدّ استنتاج فقد البيانات بمجرد استبدال الحاوية؛ تبقى الاستعادة ونسخ المضيف والتخزين بين المضيفين غير مقاسة. |
| P2-9: جودة الحقل والجاهزية | `ba51967d` | إسقاط موحد في `services/sahool-platform/api/field_models.py:223`؛ شروط الموسم والجاهزية في `routers/season_workspace.py:75,94` | أُزيل READY الثابت؛ الجاهزية تتطلب بيانات مقبولة وحالة قانونية مناسبة، ولا تمنحها الحقول المملوءة وحدها. |
| امتداد حرج: توصية ري غير مؤسَّسة وتجاوز الحوكمة | `7dcb9097`, `5d770f22`, `59c4eb8f` | مالك الحساب في `services/supervisor-agent/skills/crop_model_skill.py:94`؛ فصل الصافي والسحب الإجمالي في `:131`؛ بوابة العرض في `routers/agent.py:33` | مُصلح كمسار إثبات وحجب؛ الأدلة المالية والمائية الكاملة لازمة قبل إمكان الموافقة. |
| امتداد السوق: نجاح أو سعر مصطنع | `515bd392`, `7dcb9097` | تحليل غلاف MCP في `services/supervisor-agent/mcp_client.py:135`؛ قارئ السوق في `services/supervisor-agent/skills/market_skill.py` | isError ليس نجاحاً؛ لا سعر صفري بديل عن غياب الرصد، ولا يُقدم التاريخ بوصفه تنبؤاً. |

الإصلاحات التي غيّرت التقييم، لا عدد الأسطر فقط:

1. لم يكن حذف بادئة MCP كافياً: عُولج ربط الطلب بهوية ونطاق المستدعي، واتساق المُصدر والمتحقق، وتشغيل وحدات الخوادم، واكتشاف الأدوات.
   اختبارات العقد في `tests_v9/test_mcp_auth_first_contract.py` تشمل الرفض الأمني، الاكتشاف، أخطاء HTTP 200، وهوية إعادة الطلب.
   هذه قياسات لتطبيقات حقيقية تحت نقل واختبارات مضبوطة؛ لا تساوي تشغيل شبكة Compose كاملة.

2. توصية الري لم تعد تُبنى من ET0 ثابت أو رطوبة مفترضة.
   الحساب يُطلب من مالكه القانوني مع التحقق من هوية الحقل ومساحته والكمية المعادة.
   `recommended_mm` احتياج صافٍ؛ حجمه يساوي `mm × ha × 10` بالمتر المكعب.
   حجم السحب الإجمالي الذي يُرسل إلى الحوكمة يساوي الحجم الصافي ÷ (الكفاءة المئوية / 100).
   كفاءة الري تُقرأ صراحةً من الحقل؛ لا تُفترض 100٪ ولا تُستنتج من اسم نظام الري.
   غيابها أو فسادها ينتج `canonical_irrigation_efficiency_required`، كما يثبت `crop_model_skill.py:140`.
   لا تُعرض تفاصيل توصية كمية عند رفض الحوكمة أو تعذرها أو نقص عقد الإجراء.

3. المبالغ المالية المفقودة أو غير المحدودة أو المنطقية أو النصية لا تدخل الحساب كأصفار.
   الإيراد الصفري الحقيقي دليل مقبول الإدخال لكنه يفرض مراجعة بشرية، ولا يثبت القدرة المالية.
   الاستثمار مدرج صراحة في عقد الإنفاق؛ المبيد لا يفلت من التقييم الاقتصادي بسبب قائمة استدعاء ناقصة.
   الموافقة التلقائية محصورة في LOW مع مرور الفحوص واختيار الموافقة التلقائية.
   اختبارات الحدود HTTP والحفظ والعزل موضعها `tests_v9/test_guardrails_contract.py`.

4. المراجعة البشرية لم تعد تعيد معرّف نجاح دون حفظ.
   كل عملية تضبط متغيرَي المستأجر محلياً داخل المعاملة، مع قفل الصف والتحقق من انتهاء الصلاحية وتكرار المراجع والتخصص.
   تعديل معلمات إجراء بعد التقييم يحتاج تحققاً جديداً، ولا تتحول الموافقة إلى اعتماد معلمات لم تُقيّم.
   حالة تعذر التخزين معلنة، وكذلك `notification_delivery: not_configured`؛ الحفظ لا يدّعي تسليم إشعار.

5. جودة الحقل موحدة بين الإنشاء والقائمة والتفاصيل ومساحة الموسم.
   جودة القراءة إسقاط للحالة القانونية المحفوظة؛ ليست قياساً جديداً للنضارة وقت كل عرض.
   الجاهزية تفصل `data_complete` عن `operational_ready`، ولا تعوّض النقاط الاختيارية عن شرط مطلوب مفقود.
   المسودة أو النتيجة غير المنشورة لا تصبح تحليلاً منشوراً؛ الموسم المغلق أو المستقبلي لا يصبح موسماً جارياً.
   الحالة النصية `invalid` لا تصبح صالحة لمجرد أن النص غير فارغ.
   الكمية الصفرية الحقيقية مثل EC=0 لا تُعامل كغياب، بينما NaN/inf والقيم المنطقية لا تُقبل قياسات.

6. أُعيد إنتاج عطل مستقل لمساحة الموسم باستخدام منتِج التوصيات الحقيقي.
   `recommendations_hub` يُصدر أولوية `high/medium/low`، والمستهلك السابق كان ينفذ `int(priority)`.
   ذلك يرفع ValueError ويغلفه المعالج العام بـ503 يوحي بفشل قاعدة البيانات؛ جرى تطبيع الأولوية قبل الترتيب.
   يبقى سبب 503 الموثق في PDF مفتوحاً حتى مطابقة النسخة والطلب وtraceback/SQLSTATE.
   كذلك الادعاء بأن season_workspaces اسم جدول يستعلمه الراوتر لم يكن صحيحاً في الشجرة.

7. طلب خطة الطقس يعيد استخدام العينة بين العمليات ويقيّد العمل المتزامن، بدلاً من تكرار السلسلة لكل عملية.
   إلغاء منتظر لا يلغي عينة يحتاجها منتظر آخر؛ مغادرة آخر منتظر تلغي العمل غير المستخدم وتجمع نتيجته.
   فشل بعض الإطارات معلن؛ المطر المفقود يبقى مفقوداً ولا يصبح صفراً آمناً.
   الساعات والنموذج محفوظان حتى الأفق المدعوم، مع زيادة أيام الطلب إلى المزوّد حسب الأفق.
   البيانات القديمة الاحتياطية قد تبقى قابلة للترتيب مع إعلان partial؛ هذه سياسة سابقة لم تُغلق في الشريحة.
   مهلة asyncio لا تقاطع استدعاءات Redis المتزامنة القائمة؛ لا تُمنح هنا شهادة حد زمني مطلق لكل بنية نشر.

8. لم يُنشأ bucket ولم تتغير سياسة التخزين لتجميل حالة P2-8.
   الوضع المحلي الصريح يستخدم named volume يراه المنتجون ومستهلك البلاطات؛ غياب S3 وحده لا يثبت ضياع الصور.
   المطلوب تشغيلياً: قيم Compose المحلولة بعد تنقيح الأسرار، والـmounts الفعلية، وقراءة ملف من المستهلك، واختبار استعادة.

ما بقي مفتوحاً ويلزم التصريح به عند الإغلاق:

- الأدلة المالية: لا يملك الوكيل بعد وصلة قانونية كاملة للإيراد والتكاليف والاحتياطي والعائد المتوقع؛ لذلك قد تُحجب التوصية بنقص السياق.
- مياه الموسم: يلزم مصدر موثوق لـ`season_water_used_m3_ha` ومصدر الماء المتوافق مع عقد الحوكمة؛ لا يُستبدل الغياب بصفر.
- الكفاءة: قبول قيمة قانونية صريحة في ملف الحقل لا يثبت قياس كفاءة النظام في المزرعة؛ غياب القيمة يمنع حساب السحب الإجمالي.
- التسميد: المهارة تُعلن `fertilizer_prescription_required`؛ لا وصفة كمية بديلة من جدول محصول/مرحلة ثابت.
- التخصصات: واجهة التسجيل الحالية تُصدر دور expert عاماً؛ توفير ادعاءات تخصص موثوقة ما زال مطلوباً قبل إتاحة تلك المراجعات للمتخصصين.
- الإشعارات: لا ناقل تسليم مهيّأ؛ وجود workflow في القاعدة لا يعني وصوله إلى خبير.
- PostgreSQL: تطبيق الهجرة وإعادتها، FORCE RLS، INSERT/قراءة/موافقة بدور التطبيق، وإعادة استخدام الاتصال بين مستأجرين تحتاج القياس الحي.
- العقد الآجل: إصلاح نطاق القراءة وأخطاء MCP لا ينفذ قدرة إنشاء عقد لم تكن منفذة أصلاً.
- النشر: لا تشغيل حي لجميع الخدمات ولا إثبات مطابق للنسخة الأصلية للوثيقة في هذه المراجعة.
- التخزين: النسخ الاحتياطي والاستعادة وفقد المضيف والعمل بين عدة مضيفين لم تُقَس.
- ملكية الرسم: أظهر تسجيل الكاتب القائم ديناً كان خارج جرد الملكية؛ استثناء `drawing_features` في `platform_shrink_ratchet.json` ينتهي 2026-11-30. الأساس العددي لم يرتفع، ونقل الملكية الفعلي إلى field-management-service يبقى مفتوحاً.
- زمن مكنسة الطفرات: السجل بلغ **646** طفرة بعد إضافة حارس اشتراط دليل HIL، فوق العلامة **642** وحد الانجراف **610** في `tests_v9/test_mutation_sweep_headroom.py`. اختبارا الحدّ أحمران؛ يلزم قياس CI يقرن زمن الجولة بعدد طفراتها. لا تُحذف الطفرات ولا تُرفع الحدود لمجرد الإغلاق.

التحقق وتسليم العمل:

- الاختبار المترابط الأول بعد الدمج: **123 passed** في ملفات المصادقة وMCP وعقد الحوكمة ومساحة الموسم؛ لا يُجمع هذا العدد مع أعداد الشرائح المتداخلة.
- **45 طفرة** أُضيفت في الشرائح الأصلية إلى `docs/architecture/guard_mutation_registry.json`، ثم أُضيفت طفرة اشتراط HIL في `8078bda3`: **46 إضافة جديدة**، والإجمالي الحالي **646**. أعادت طفرات الشرائح أعطالاً ممثلة وأفشلت شهود السلوك في قياساتها.
- اجتازت سلسلة `verify_all_generated.py --fix` اكتشاف المصنوعات والتحقق من اتساقها بعد دمج الشيفرة؛ استلزم إدراج تقرير الإغلاق وتصحيحات الفحوص تحديثاً تالياً للمصنوعات التابعة.
- تحقق مستقل من إصدار التوكن الحقيقي إلى المشرف ثم MCP نجح في وضعَي HS256 للتطوير وRS256 للإنتاج؛ استخدم سوقاً ذا حد قاعدة مضبوط، وليس قاعدة حية.
- اختبارات PostgreSQL بالأدوار المقيدة موجودة في `tests_v9/test_db_wiring.py` و`tests_v9/test_rls_tenant_isolation_live_pg.py`؛ لم تُقَس حياً في هذه البيئة.
- الجناح الكامل `pytest -m unit` على `1ff4a88f`: **6466 passed، 8 failed، 30 skipped، 430 deselected** خلال 458.58 ثانية. شُخّصت الإخفاقات؛ ستة أسباب عولجت بالمرجع التاريخي والتسجيل والتوثيق والمصنوعات، وبقي اختبارا زمن المكنسة أعلاه. ليس هذا إعلان جناح كامل أخضر.
- جناح `pytest tests/` على `1ff4a88f`: **747 passed، 5 failed، 8 skipped** خلال 315.99 ثانية. الأسباب: غياب origin/main، وانجراف فهرس التقرير، ومطابقة نص توثيق، وتسجيل الهجرة في مشغّل SQL.
- جناح المنصة الكامل: **4283 passed، 11 failed** خلال 52.87 ثانية؛ الإخفاقات الإحدى عشرة سببها اعتماد SOCKS الناقص في بيئة الاختبار. بعد تثبيت `socksio` نجحت ملفاتها كاملة: **16 passed**. لم يُغيَّر منطق المنصة لإرضاء إعداد الوكيل الشبكي.
- إعادة فحوص التاريخ والملكية والهجرات والدليل وحارس النص القديم بعد التصحيح على `0d1d2eaa`: **82 passed** خلال 20.40 ثانية؛ تشمل اختبار انتهاء استثناء الملكية الجديد. العدد متداخل مع الأجنحة السابقة ولا يُجمع بها.
- إصلاحات التحقق محفوظة في commits: `050ed847` لترميز UTF-8، `5267f15e` لتوضيح نص الجودة، `3e186968` لمشغّل الهجرة، `45dad915` لاستثناء الملكية المحدد، `52003234` لتعليل منع DDL، `0d1d2eaa` لعدد الهجرات في الدليل. بقي عدد المحظورات النصية بلا تعليل **99** كما في الأساس.
- قيس CI السابق مباشرة: `799842d3`، [run 34178875806 / job 101913721185](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/actions/runs/34178875806/job/101913721185)، **31m58s عند 600 طفرة**؛ و`82e56b05`، [run 34155172685 / job 101845394593](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/actions/runs/34155172685/job/101845394593)، **39m36s عند 583 طفرة**. كلاهما أسرع من المرساة المعتمدة 41.17 دقيقة عند 579، فلا يحل محلها وفق قاعدة الأبطأ. وحتى الزوج الأحدث افتراضاً يعطي حد انجراف 637، دون 645؛ لا دليل كافياً لإغلاق الاختبارين.
- أمر البوابات المجمّع `BASE=799842d3 bash scripts/ci/preflight.sh --no-fetch` بلغ المرحلة 7 ثم انقطع؛ **لم يُستكمل ولا يُعلن ناجحاً**. نجحت مرحلة زرع الطفرات المتأثرة، وأُصلح إخفاق UTF-8 المكتشف قبله، ثم قِيست أجنحة الاختبار بصورة مستقلة كما أعلاه.

الفرع: `fix/runtime-contract-closures-20260908`. لا إعلان تحقق تشغيل حي أو اعتماد إنتاجي؛ كل حكم أعلاه مقيد بشاهده.


متابعة الإغلاق عند `8078bda3`:

- أُغلق عيب في شاهد HIL نفسه: كان غياب PostgreSQL أو فشل الاتصال يؤدي إلى skip في CI. أصبحت وظيفة التكامل تفرض `HIL_CERTIFICATION_REQUIRED=1`، ويشترط شاهد HIL عنوان قاعدة صريحاً واتصالاً ناجحاً خلال 10 ثوانٍ. التخطّي الاختياري المحلي يبقى متاحاً حين لا يكون الإثبات مطلوباً.
- شاهد دور HIL يرفض غياب صف الدور وخصائص SUPERUSER/BYPASSRLS، ويُربط بكل استحواذ على اتصال المجمع. هذه سلامة لأداة القياس؛ لا تُثبت وحدها RLS حياً.
- نجحت **47 حالة** في `tests_v9/test_guardrails_contract.py` بعد الدمج، بينها **11 حالة جديدة**. كُذبت ستة أعطال مزروعة في شاهد الاتصال والدور وربط المجمع وعلم CI، وسُجلت طفرة CI ضمن السجل؛ الإجمالي أصبح **646**.
- تعذر تشغيل PostgreSQL محلياً بقيود هوية البيئة: UID=0، ومجموعات القدرات فارغة، وNoNewPrivs=1؛ تعذر إنشاء تعيين مستخدم غير ممتاز. لا يُزال فحص root من PostgreSQL ولا تُقدّم محاكاة بوصفها قياساً حياً.
- الموجود في CI يغطي تطبيق MANIFEST وإعادة تطبيقه، واختبار `test_create_then_get_status`، وملف `test_rls_tenant_isolation_live_pg.py` الذي يتضمن شاهد الرسم. لم يُشغّل CI جديد على هذه الإصلاحات بعد.
- فُحص الدفع دون كتابة عبر `git push --dry-run`: فشل لغياب اعتماد Git (`could not read Username`). اتصال قراءة GitHub ليس اعتماداً لرفع كائنات Git المحلية؛ لم يُنشأ PR بعيد ولا يُدّعى وجوده.
- قُرئت قواعد حماية الفرع مباشرة: [main-protection / 20645828](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/rules/20645828) نشطة وتحتوي 15 فحصاً تطابق العقد المحلي. لا تضم أسماء `Mutation Sweep 1/5` إلى `Mutation Sweep 5/5`؛ يبقى نقل المكنسة خارج Unit Tests مشروطاً بإضافة تلك الأسماء فعلياً، ولا تُعدَّل القاعدة هنا.

تدقيق المصادر المتبقية للحوكمة:

| المطلوب | المصدر الأقرب في الشجرة | ما ينقصه قبل إتاحته للحوكمة |
|---|---|---|
| استهلاك مياه موسم الحقل | `api/routers/water_ledger.py` و`api/routers/farm_operations_ledger.py:442` | فصل الصافي والسحب، اكتمال الموسم، ومنع قراءة SUM/قائمة فارغة كصفر مثبت. |
| تنفيذ مائي مقاس | `api/canonical_as_applied_irrigation.py` | يثبت تشغيلات محددة؛ يلزم اختيار الإصدار المعتمد ومنع عدّ بصمات التشغيل نفسه مرتين، وإثبات اكتمال الموسم. |
| الإيراد والتكلفة السنويان بالدولار | `api/routers/farm_operations_ledger.py:1000` و`core/simple_farm_book.py` | الأول ملخص موسم بعملة YER، والثاني معاملات؛ يلزم اكتمال سنة مالية وتحويل عملة موثق. |
| الاحتياطي النقدي | `core/simple_farm_book.py:90` | cash_balance_effect تغير نقدي، وليس رصيداً أو احتياطياً مثبتاً. |
| نوع مصدر المياه | `api/field_models.py:41` و`api/irrigation_source_binding.py:29` | مفردات الحقل والربط لا تحسم دائماً groundwater/surface؛ الخزان والقناة لا يثبتان أصل الماء. |
| تكلفة الإجراء وأثره الهامشي | سجلات العمليات وحاسبات الجدوى القائمة | تكلفة تاريخية وإيراد محصول إجمالي لا يثبتان سعر الإجراء المقترح أو زيادة الإيراد الناتجة عنه. |

مسارات api/core في الجدول نسبةً إلى `services/sahool-platform/`. النتيجة: توجد معاملات وتشغيلات، لكن عقد إثبات اكتمال الفترة والعملة والاحتياطي والأثر الهامشي غير مكتمل؛ لذلك لا تُوصل التجميعات الحالية إلى الحوكمة بوصفها أدلة مكتملة.

نقل العمل وتشغيل الدليل:

تُسلَّم التغييرات في حزمة Git تزيد على `799842d3` وتحفظ كائنات الـcommits ببصماتها. في نسخة المستودع ذات اعتماد دفع:

```bash
git fetch origin claude/claude-md-docs-p6qqir
git bundle verify /path/to/sahool-runtime-closures-20260908.bundle
git fetch /path/to/sahool-runtime-closures-20260908.bundle refs/heads/fix/runtime-contract-closures-20260908:refs/heads/fix/runtime-contract-closures-20260908
git push -u origin fix/runtime-contract-closures-20260908
```

يكون طلب المراجعة مسودة إلى `claude/claude-md-docs-p6qqir` لقياس الشريحة فوق أساسها. يلزم إبقاء فشل اختبارَي زمن الطفرات معلناً حتى يتوفر قياس صالح وفق العقد القائم.

لإنتاج دليل PostgreSQL مستقل على Linux مع Docker، يوفّر [run_hil_drawing_pg.sh](run_hil_drawing_pg.sh) قاعدة PostGIS مؤقتة جديدة على localhost ويستخدم مشغّل الهجرات القائم مرتين، ثم الاختبارات نفسها. ينظف معرّف الحاوية الذي أنشأه فقط. تحققنا من صياغة shell؛ لم يُنفّذ حياً هنا:

```bash
bash docs/testing/run_hil_drawing_pg.sh /absolute/path/to/repository /absolute/path/to/test-venv/bin/python
```


متابعة التحقق المكتمل على `fb82eff6`:

- اكتمل لاحقاً الأمر `BASE=799842d3 bash scripts/ci/preflight.sh --no-fetch` بوضعه **الافتراضي بجميع أجنحته**؛ خرج بـ**1**، مع **مجموعة إخفاق واحدة وصفر مجموعات متخطاة**. هذا تشغيل مكتمل ذو إخفاق معلن، ويظل التشغيل المنقطع المذكور أعلاه واقعة سابقة مستقلة. لم تُستخدم راية `--full` التي تضيف فحوصاً أخرى.
- جناح الوحدة: **6473 passed، 2 failed، 30 skipped، 430 deselected** خلال **368.28 ثانية**. الإخفاقان وحدهما في `tests_v9/test_mutation_sweep_headroom.py`: `test_the_sweep_has_not_grown_past_the_point_that_was_measured` و`test_the_anchor_is_re_measured_before_the_universe_drifts_half_the_headroom`. عدد الاختبارات المتخطاة داخل الجناح لا يساوي عدد مجموعات البوابات المتخطاة.
- جناح `pytest tests/` **نجح**؛ لم يُحفظ عدده النهائي مستقلاً، فلا يُنسب إليه عدد مستنتج. جناح المنصة اكتمل: **4294 passed** خلال **49.58 ثانية**. نجحت البوابات السابقة للأجنحة وخطوات اتساق المصنوعات الـ**75** في التشغيل نفسه.
- سجلا القياس المحليان: `diagnostics/preflight-ci-measurement.log` و`diagnostics/platform-preflight-completed.log`. هذه نتيجة محلية على `fb82eff6`، وليست جولة GitHub Actions أو إثبات PostgreSQL حي.
- تعديل شاهد HIL اللاحق في `8078bda3` له قياسه الموجه المستقل: **47 حالة ناجحة** كما سبق. لا تُنسب نتيجة الأجنحة الكاملة على `fb82eff6` إلى هذا التعديل اللاحق، ولا تحل سرعة الوحدة المحلية محل مرساة زمن المكنسة المقيسة في CI.


متابعة مراجعة #990 — 2026-09-08

المصدر: [المراجعة 5135471149](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/990#pullrequestreview-5135471149)، والتعليق [3952828845](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/990#discussion_r3952828845). المراجعة COMMENTED؛ التعليق ما زال غير محلول على GitHub وقت القراءة. الأساس المحلي لهذه الشريحة `611bae0c`، وإصلاح المصدر `4163de82`.

الملاحظة صحيحة وأثرها تشخيصي: عند اجتماع موضع مستثنى من الشهادة الذاتية مع موضع خارجي غير مثبت، كان `collect_guard_surface_evidence.py:212` يضع `self_witnessing_excluded` في أسباب الإخفاق وتفاصيل مواضعه. بقي الحكم `not_proven`؛ لم يُكتشف تجاوز يجعل الحارس ناجحاً. تُرشَّح المواضع المستثناة الآن من `reasons` و`sites` مع بقاء أحكام النجاح والاستثناء والعدّادات كما هي. قائمة `self_witnessing_excluded` العليا تخص الحرّاس المستثناة بالكامل؛ لا تُضاف إليها الحرّاس المختلطة كي لا يفسد حساب المثبت منها.

أعاد وكيل مستقل إنتاج العطل على الجرد الفعلي عند `611bae0c`: 272 حارساً و298 موضعاً. الحرّاس المختلطة المتأثرة هي `edge_model_contract_guard.py` و`edge_production_readiness_guard.py` و`production_evidence_pack_guard.py`. المقارنة المحكومة قبل الإصلاح وبعده عبر سبعة سيناريوهات أبقت كل الأحكام والعدّادات والعضوية والتشخيصات غير المختلطة متطابقة، ونقّت أسباب ومواضع الحرّاس الثلاثة. هذا قياس لمنطق الجامع محلياً، لا تشغيل لهذه الحرّاس في GitHub Actions.

- قبل الإصلاح: فشل شاهدان بسبب السبب المستثنى الزائد تحديداً.
- بعده: `tests_v9/test_collect_guard_surface_evidence.py` و`tests_v9/test_guard_mutation_guard.py` أعطيا **86 passed**؛ ملف الجامع وحده22 حالة. تشمل الحالات موضعاً خارجياً متخطى، إخفاقين خارجيين مختلفين، ونجاحاً خارجياً مع موضعين مستثنيين.
- التشغيل الفعلي `guard_mutation_guard.py --run --only scripts/ci/collect_guard_surface_evidence.py` كشف **10/10** طفرات بالشواهد المسماة؛ الطفرتان الجديدتان تعيدان الخلل إلى `reasons` و`sites` مستقلاً.
- `test_mutation_sweep_headroom.py`: **3 passed, 2 failed**. الإجمالي648 (368 حراسة و280 سلوك)، والإضافات منذ799842d3 صارت48؛ العلامة642 وحد الانجراف610 لم يتغيرا. هذه متابعة للعائق المفتوح، وليست نتيجة CI جديدة.

سجلات القياس المحلية: `diagnostics/review990-before-fix.log` و`review990-targeted-tests.log` و`review990-mutations.log` و`review990-headroom.log`. لم تُعد الأجنحة الكاملة في هذه الشريحة الضيقة؛ قياسها السابق على `fb82eff6` يبقى منسوباً إليه. إغلاق العيب في الشيفرة لا يغلق تعليق GitHub ولا يثبت نشر commit؛ اعتماد دفع Git ما زال غير متاح. `runtime_verified=0` و`production_certified=0` و`capable=false`.


تصحيح المراجعة المضادة: انحدار شهود عقد Guardrails — 2026-09-08

أثبتت مراجعة المالك للحزمة `e1c28fc0` انحداراً لم يذكره هذا التقرير: عند إعادة كتابة `tests_v9/test_guardrails_contract.py` في `36faa270` حُذف شاهدا `incomplete_context` وضُيّق اختبار العقد النقي. بقيت القاعدة في الإنتاج، وكانت أعداد الاختبارات الناجحة السابقة صحيحة لكنها لا تثبت الحفاظ على الدلالات القديمة. حذف الشهود بدلاً من تكييفها كان خطأ في شريحة الاختبارات.

`87518ec9` يستعيد أربع دوال اختبار دون تعديل مصدر الإنتاج أو workflows:

| الشاهد | الدلالة المقاسة |
|---|---|
| `test_validate_rejects_incomplete` | طلب صحيح بـuser_id=1 ثم فقد جرعته من القاموس المتداخل القابل للتعديل: المحرك يرفض HIGH مع incomplete_context وmissing_fields دقيقة، دون تشغيل طبقات السلامة أو إنشاء مراجعة بشرية. إعادة إنشاء النموذج من البيانات الناقصة تُرفض أيضاً. |
| `test_validate_passes_complete_past_contract` | السياق المكتمل لا يطلق incomplete_context ويبلغ الطبقتين البيئية والاقتصادية الحقيقيتين، مع رصد استدعائهما. |
| `test_contract_accepts_explicit_zero_and_uncontracted_harvest` | الصفر الصريح للماء والمال مقبول في العقد، والماء المفقود أو السالب مرفوض؛ harvest لا يُحجب بعقد مالي مخترع. |
| `test_contract_requires_pesticide_dosage_and_loan_revenue` | المبيد المكتمل والقرض المكتمل مقبولان في العقد؛ حذف الجرعة أو الإيراد السنوي وحده يعيد اسم الحقل الناقص بالضبط. |

تكييف الشهود ضروري: `cv("irrigation", {"water_m3": 0}, {}) == []` لم يعد شرطاً صالحاً حرفياً بعد إلزام الأدلة المالية والمائية. الشاهد الجديد يثبت الصفر مع استكمال بقية السياق. كذلك تغيير user_id وحده في اختبار الطلب الناقص القديم لا يكفي: model_validator يرفض النقص عند الإنشاء، ولذلك يُقاس حارس المحرك مستقلّاً على قاموس فقد حقلاً بعد إنشاء طلب صحيح.

التحقق عند `87518ec9`: **51 حالة Guardrails ناجحة**، منها الأربع المستعادة؛ و**7/7 طفرات مقيسة** على `main.py` و`contracts.py`، منها **6 جديدة** (تعطيل/تعميم حارس المحرك، رفض الصفر، إلزام harvest، إسقاط جرعة المبيد، وإعفاء القرض من الإيراد). لم تُحذف مواصفة قائمة. الإجمالي صار **654 = 368 + 286**؛ القياس المشترك مع headroom أعطى **54 passed, 2 failed**، وتبقى642 و610 دون تغيير. سجلات القياس المحلية: `guardrails-coverage-tests.log` و`guardrails-contracts-mutations.log` و`guardrails-engine-mutations.log` و`guardrails-coverage-and-headroom.log` تحت diagnostics.

في الحزمة الأصلية، مسّ `ci.yml` مقتصر على موضعي HIL_CERTIFICATION_REQUIRED=1 الموثقين في8078bda3؛ تشديد القياس لا إعفاء له. الشريحة الحالية لا تمسه. نتيجة preflight التي يشغلها المالك علىe1c28fc0 لم تصل وقت هذا التصحيح، ولا يُدّعى اكتمالها أو تُنسب إلى الرأس اللاحق. الحزمة الأصلية وبصمتها محفوظتان؛ تصحيح التغطية امتداد لها. يبقى runtime_verified=0 وproduction_certified=0 وcapable=false.


### 2026-09-08 — HIL SQL parameter typing, PR #991

`83e8c187` fixes the live CI failure reported at 20:49 UTC: approval UPDATE inferred parameter $1 as both text and varchar. Both uses now explicitly cast to varchar, matching migrations/v9_new_tables.sql. tests_v9/test_db_wiring.py also checks unresolved/resolved timestamps and refusal of a late rejection. Guardrails unit suite: 51 passed. PostgreSQL is unavailable locally; the corrected integration test remains NOT_MEASURED until CI reruns it. The supplied CI result was 1 failed, 131 passed, 92 skipped, 2 xfailed, 1 xpassed; this supersedes the earlier claim that only mutation headroom blocks the PR. No skip, role bypass or certification flag was weakened.

### PR #991: integration of the repaired SQL and independent review

The remote head `44a4cbcf` contains the stronger coverage repair, including
`87518ec9`, `6eb81b42` and `994da32a`. Its integration job
[102248437393](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/actions/runs/34281851595/job/102248437393)
still failed at 2026-09-08 21:43 UTC on the uncorrected HIL query (one failed,
131 passed, 92 skipped). `4456cea6` merges that remote history with the local
HIL repair without rewriting either history. `48991e6d` moves the economic-tier
docstring before its imports and removes its duplicate shebang.

Independent review confirmed that the SQL casts preserve the transaction,
row lock, tenant and role checks, expiry and approval quorum. `ab240e46`
strengthens the live witness: it reads the durable approvals after a duplicate
vote and compares the entire resolved snapshot after a refused late rejection.
The local Guardrails suite remains 51 passed. These tests with local doubles
cannot establish that PostgreSQL accepted the prepared statement; that corrected
live test still requires a new CI run.

The five successful mutation shards in run `34281851595` measure their own
execution, not the complete Unit Tests job. Cancelled earlier runs do not provide
a completed timing pair. The mutation budget must use a completed eligible
measurement under its existing formula; shard success alone cannot close it.

`531efe47` repairs the two MCP auth-order findings from review `5147072917`.
Weather and WOFOST accept a `Request` and decode/validate the body inside the
authenticated handler; their OpenAPI body schemas remain explicit. Denied
requests never read the body. Authenticated malformed JSON, invalid UTF-8 and
invalid envelopes return 422. Execution, identity-bound caching and WOFOST's
explicit unsupported-simulation response retain their witnesses. The slice
passed 63 targeted cases (23 newly parameterized cases), and its two planted
Request-to-dict regressions were detected. The merged Guardrails/MCP suite passed
106 cases. Registry total: 656 = 368 + 288. The old timing limits are retained
until an eligible completed pair is available.
