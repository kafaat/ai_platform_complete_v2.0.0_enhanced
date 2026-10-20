# OPEN-METEO-COMMERCIAL-TERMS-01: Open-Meteo: الواجهة المجانية لغير التجاري فقط

حالة القرار: معلق لدى المالك. الحالة تبقى `open`. هذه وثيقة خيارات وعقد مقترح فقط؛ لا تفويض تنفيذ.

أساس المراجعة: `c9e8c15e03a60a6644b02bb453e54de9cc31f212` (main بعد #1247). مراجع الأسطر إرشادية وهي أسطر الأساس؛ النص المصدر هو المرجع.

## العطل والأدلة

وصفت الوثائق والشيفرة Open-Meteo بأنه «مجاني بلا مفتاح» دون قيد الاستخدام. شروط Open-Meteo تقصر الواجهة المجانية على الاستخدام غير التجاري، وتعد «المواقع أو التطبيقات التي لها اشتراكات أو تعرض إعلانات» و«المنتجات التجارية» استخداماً تجارياً. الاستخدام التجاري يحتاج اشتراكاً مدفوعاً بمفتاح على `customer-api.open-meteo.com`، أو نسخة مستضافة ذاتياً؛ ودليل الخادم يقول إن الاستضافة الذاتية متاحة للاستخدام التجاري وغير التجاري.

المصادر الأولية قُرئت في 2026-10-20 من مستودعي Open-Meteo الرسميين على GitHub عند SHA مثبت، لأن `open-meteo.com` محجوب DNS من بيئة الكتابة:

- [شروط الاستخدام](https://github.com/open-meteo/open-meteo-website/blob/53f0bf019395abd29d8d5a404e7a39c3457f90d7/src/routes/en/terms/%2Bpage.svelte#L34) (`open-meteo/open-meteo-website@53f0bf019395abd29d8d5a404e7a39c3457f90d7`، `src/routes/en/terms/+page.svelte`): السطر 34 «You may only use the free API services for non-commercial purposes»؛ السطر 33 حدود 10,000 طلب يومياً و5,000 بالساعة و600 بالدقيقة؛ السطر 36 قبول CC BY 4.0؛ السطر 53 تعريف Creative Commons لغير التجاري؛ السطر 70 «Websites or apps that have subscriptions or display advertisements» استخدام تجاري.
- [التسعير](https://github.com/open-meteo/open-meteo-website/blob/53f0bf019395abd29d8d5a404e7a39c3457f90d7/src/routes/en/pricing/%2Bpage.svelte#L139) (`src/routes/en/pricing/+page.svelte` في الـSHA نفسه): السطور 139-141 الاشتراك يمنح ترخيص استخدام تجاري ومفتاحاً لـ`customer-api.open-meteo.com`، والصياغة مطابقة للمجانية عدا النطاق ومعامل المفتاح؛ السطران 430-431 الطلبات تحمل `&apikey=`.
- [دليل الاستضافة الذاتية](https://github.com/open-meteo/open-meteo/blob/7afe0fdbab87fe7948518a17346af9df907680b4/docs/getting-started.md#L119) (`open-meteo/open-meteo@7afe0fdbab87fe7948518a17346af9df907680b4`، `docs/getting-started.md`): السطر 119 «Self-hosting is available for non-commercial and commercial use»؛ البيانات CC BY 4.0 وتشترط النسبة، والخادم وصورة Docker تحت AGPL-3.0، ومن يعدّل الشيفرة ويشغلها خدمة شبكية يلزمه تقديم المصدر المعدّل لمستخدميها (السطر 121). و[README الخادم](https://github.com/open-meteo/open-meteo/blob/7afe0fdbab87fe7948518a17346af9df907680b4/README.md#L5) السطر 5: الواجهة مجانية لغير التجاري.
- الخصوصية: [شروط الاستخدام](https://github.com/open-meteo/open-meteo-website/blob/53f0bf019395abd29d8d5a404e7a39c3457f90d7/src/routes/en/terms/%2Bpage.svelte#L287) السطور 287-289: سجلات خادم الواجهة المجانية قد تحوي إحداثيات جغرافية وتُحذف بعد 90 يوماً؛ والسطور 319-322 للاشتراك: تُجمع عناوين IP وURLs، وتُحذف السجلات الفردية بعد 90 يوماً وتبقى أعداد مجمعة. والمنصة ترسل إحداثيات الحقول في كل طلب.
- الأسعار: جدول الأسعار مضمّن من Stripe ولا يظهر نصاً في المصدر؛ لم تُقرأ الأسعار ولم يُتحقق منها.

في المستودع عند الأساس:

- `README.md:19` عنوان «Open-Meteo (مجاني — بلا API key)»، و`shared/wofost/engine.py:148` «مجاني 100% بدون مفتاح»، و`shared/wofost/engine.py:482` قيمة `data_source` «بلا API key»، و`services/sahool-platform/api/routers/field_intelligence.py:290` تعليق «keyless». صُحّحت صياغتها في هذا الفرع فقط.
- `docs/history/PROVIDERS_GAPS_IMPLEMENTATION.md:32` نبّه إلى أن الاستخدام التجاري يحتاج اشتراكاً، ولم يُسجَّل قرار. و`services/sahool-platform/api/connectors/openmeteo.py:4` يقول «مجاني، بدون مفتاح» ويقيّده السطر 13 «غير تجاري فقط».
- مواضع أخرى تصف Open-Meteo بأنه مجاني أو بلا مفتاح، بقيت خارج نطاق هذا الفرع وتُحدَّث عند تنفيذ القرار. بيانات في الشيفرة: سجل مصادر الطقس `services/sahool-platform/core/weather_sources.py:16-35` (`"free": True` و`"auth": "none"` وملاحظة «بلا مفتاح»)، ويشترط `services/sahool-platform/tests/test_weather_sources.py:59-61` أن تكون كل المصادر `free`؛ وتوقيع المهارة `services/sahool-platform/core/skills_registry.py:409` و`:415-416` (`description_ar` «مجاني، بلا مفتاح» و`cost_class="free"` ووسم «مجاني»). تعليقات وdocstrings: `services/sahool-platform/api/main.py:444` و`:1956`، و`services/sahool-platform/core/field_intelligence_adapters.py:489`، و`services/sahool-platform/core/field_intelligence_coordinator.py:331`، و`services/sahool-platform/core/capabilities.py:6-7` و`:35-36`، و`tests_v9/test_capabilities.py:82`. وثائق: `README.md:61` و`:96` (داخل كتلتي شيفرة)، و`services/sahool-platform/docs/LOCAL_SERVER_ARCHITECTURE.md:69`، و`services/sahool-platform/docs/SOURCE_DOCUMENTATION.md:175` و`:1167`، و`services/sahool-platform/docs/CORE_REBUILD_PROMPT.md:94`. أما `docs/history/PROVIDERS_GAPS_IMPLEMENTATION.md:29` و`docs/history/WEATHER_AUTOMATION_REVIEW.md:36` و`sahool-brain/log.md` فسجل تاريخي لا يُحرَّر. القائمة من بحث عند الأساس لا حصر مضمون؛ لإعادة البحث بعد تغيّر الأسطر: `git grep -n -i -E 'keyless|مجان|مجّان|بلا مفتاح|بدون مفتاح|"free"|cost_class'` ثم استبعاد ما لا يخص Open-Meteo.
- صفة الاستخدام: لا تكامل فوترة في الشجرة (`services/sahool-platform/api/cost_governance.py:16`). هذا لا يحسم الصفة: الوثيقة المعمارية تستهدف سوق B2B (`docs/SAHOOL_v9_Technical_Architecture.md:17`)، وأمثلة Open-Meteo للتجاري تشمل المنتجات التجارية لا الاشتراكات وحدها. من يستخدم بيئات staging والإنتاج اليوم وبأي شروط لم يُقَس هنا؛ التصنيف قرار المالك.

ما يحتاجه أي خيار في الشيفرة:

- `services/weather-service/open_meteo.py:10-11`: `OPEN_METEO_FORECAST_URL` و`OPEN_METEO_ARCHIVE_URL` تُقرأ من البيئة وافتراضيهما المضيفان المجانيان. لا معامل `apikey` في الخدمة (بحث `apikey` في `services/weather-service/*.py` لا يجد شيئاً).
- `scripts/ci/weather_service_real_contract_gate.py:65-66` يشترط النصين الحرفيين `api.open-meteo.com/v1/forecast` و`archive-api.open-meteo.com/v1/archive` في `open_meteo.py`؛ تغيير الافتراضي يُسقط البوابة ما لم تُعدَّل معه.
- أربعة مواضع تختار المضيف: weather-service أعلاه، وثلاثة تثبته بلا متغير بيئة: `services/mcp_servers/weather_server.py:33`، و`services/sahool-platform/api/connectors/openmeteo.py:190-192` (ومعها `geocoding-api`)، و`shared/wofost/engine.py:150`.

## الخيار 1: اشتراك مدفوع بمفتاح

الملفات المتأثرة: `services/weather-service/open_meteo.py` (مفتاح من سر بيئة يُلحق بكل طلب ولا يُطبع في سجل أو خطأ قاطع أو `/readyz`)، و`scripts/ci/weather_service_real_contract_gate.py`، والمستدعون الثلاثة (توجيههم إلى weather-service أو إلى الإعداد نفسه)، و`.env.example` وcompose للمتغير الجديد، وإعداد Railway.

الهجرة وGATE-01: لا هجرة ولا مسار مجمد؛ سر جديد على Railway يقرّه المالك.

اختبارات القبول والمخاطر: الطلب يذهب إلى `customer-api.open-meteo.com` ومعه المفتاح، والمفتاح لا يظهر في أي مخرج؛ غياب المفتاح في بيئة تجارية فشل معلن لا عودة صامتة إلى المضيف المجاني. المخاطر: تكلفة شهرية غير مقيسة، وسقف طلبات شهري بحسب الخطة، وبقاء سجلات المزود 90 يوماً كما أعلاه. النسبة CC BY 4.0 تبقى لازمة.

## الخيار 2: نسخة مستضافة ذاتياً غير معدّلة

الملفات المتأثرة: خدمة `open-meteo` في compose وRailway مثبتة بالبصمة (digest) لا بوسم عائم، وتوجيه `OPEN_METEO_FORECAST_URL` و`OPEN_METEO_ARCHIVE_URL` إليها، وتعديل البوابة لتقبل مضيفاً معداً، والمستدعون الثلاثة، ونص نسبة CC BY 4.0 أينما عُرضت البيانات.

الهجرة وGATE-01: لا هجرة؛ خدمة وتخزين جديدان قرار نشر.

اختبارات القبول والمخاطر: النسخة غير المعدّلة لا تستدعي التزام AGPL بتقديم مصدر معدّل؛ أي تعديل يستدعيه. البيانات تبقى CC BY 4.0. المخاطر: كلفة تشغيل وتخزين، وزمن الوصول إلى بيانات S3 العامة (الدليل يذكر المنطقة `us-west-2`)، وصيانة الإصدارات. توافر الأرشيف التاريخي والنماذج المطلوبة على النسخة الذاتية، وما يكشفه جلب الكتل من S3 عن مواقع الحقول، لم يُقاسا.

## التوصية وأسبابها

لا أوصي بالبقاء على الواجهة المجانية متى صار الاستخدام تجارياً، والقرار للمالك قبل أي مستأجر مدفوع أو إعلان أو إطلاق إنتاجي تجاري. الخيار 1 أقصر طريقاً إن كان الحجم ضمن خطة، لأن الصياغة لا تتغير عدا النطاق والمفتاح. والخيار 2 أولى إن قُدّمت خصوصية الإحداثيات أو الحجم أو الاستقلال عن المزود. وفي الحالتين خطوة مشتركة: مضيف ومفتاح من إعداد واحد في weather-service، وتوجيه المستدعين الثلاثة إليه بدل تثبيت المضيف.

## قبول التنفيذ بعد قرار المالك

- كل طلب Open-Meteo في الشجرة يمر من إعداد واحد؛ لا مضيف مجاني مثبت في بيئة معلنة تجارية، ويُثبت ذلك ببحث في الشجرة واختبار.
- للخيار 1: المفتاح يُرسل ولا يظهر في سجل أو رسالة خطأ أو حالة قاطع أو `/readyz`؛ غيابه فشل معلن. أخطاء 401/403/429 تبقى خطأ وصول لا عطل مزود.
- للخيار 2: الصورة مثبتة بالبصمة، وطلب حي يعيد ET0 والأرشيف المطلوبين، وتبقى النسبة CC BY 4.0 ظاهرة.
- البوابة `scripts/ci/weather_service_real_contract_gate.py` تُعدَّل مع الافتراضي في التزام واحد، وتبقى تشترط مزوداً حقيقياً لا بديلاً وهمياً.
- التزام التنفيذ يحدّث كل موضع يذكر هذا المعرّف خارج هذه الوثيقة وسجل الفجوات (`git grep -n OPEN-METEO-COMMERCIAL-TERMS-01`) ليطابق الخيار المختار: عنوان `README.md` وdocstring `shared/wofost/engine.py` وقيمة `data_source` فيه وتعليق `field_intelligence.py`؛ فهذه الصياغة تقول اليوم إن الواجهة المجانية لغير التجاري هي المستخدمة، وتصير مصدراً خاطئاً بعد أي خيار. ويحدّث معها المواضع المدرجة أعلاه خارج نطاق هذا الفرع، ومنها `"free"` و`"auth"` في سجل مصادر الطقس واختباره. ولا اختبار يثبّت قيمة `data_source` اليوم، فيضيف التنفيذ اختباراً يثبّت قيمتها الجديدة.

## الحدود ومستويات القبول

وثيقة وتصحيح صياغة فقط؛ open. لا تغيير سلوك: المضيفات والطلبات كما هي. لم يُقرأ موقع open-meteo.com نفسه (محجوب DNS)؛ المصدر مستودعاه الرسميان عند الـSHA المذكورين، والصفحة الحية قد تتغير بعدهما. الأسعار غير متحقق منها. هذه ليست استشارة قانونية؛ تصنيف «تجاري» وقرار الخيار للمالك.

محلي: مراجعة مصدر ووثيقة فقط. CI: غير مقيس لهذه الوثيقة. staging: غير مقيس. الإنتاج: غير مقيس. لا هجرة ولا نشر ولا دليل جهاز بهذه الوثيقة.

## مراجع الممارسات

- [Open-Meteo — Terms](https://open-meteo.com/en/terms)
- [Open-Meteo — Pricing](https://open-meteo.com/en/pricing)
- [Open-Meteo — Licence](https://open-meteo.com/en/licence)
- [Creative Commons — NonCommercial interpretation](https://wiki.creativecommons.org/wiki/NonCommercial_interpretation)
- [GNU AGPL v3](https://www.gnu.org/licenses/agpl-3.0.html)
