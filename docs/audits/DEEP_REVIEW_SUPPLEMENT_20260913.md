# مراجعة SAHOOL المقابلة والمكمّلة — 2026-09-13

> Historical review snapshot: source findings below were measured before the repair series. Current closure and verification status: [PATCH_CLOSURE_20260913.md](PATCH_CLOSURE_20260913.md). Source links remain pinned to their measured commits.

الأساس: `9613db9aef6ae5bb6b63081f936b083ed52f7a8d` · المراجعة الأصلية: `b86998ffd7c1d13f29ab4121e47506faf6278fbb`

المراجعة المرفقة مفيدة كخريطة أولية لحجم المنظومة ودين الإثبات، لكنها تحتاج تصحيحاً جوهرياً قبل تحويلها إلى خطة تنفيذ. بعض أعلى أولوياتها مبني على وصف قديم أو على استنتاج لا تسمح به أداة القياس. أما الفحص المكمل فكشف عيوب اتصال وتسليم وتهيئة في مكونات تعمل خارج services/ أو عند الحدود بين المنتج والمستهلك.

المصدر مثبت على main عند 9613db9a، وهو أساس المراجعة نفسها. ملف المراجعة موجود في b86998ff، والفرق عن أساسه توثيقي. جرى جرد جميع الملفات المتتبعة و32 خدمة و68 تعريف Compose، ثم قراءة مركزة لمسارات المصادقة والإشعارات والبوت وERP والحافة والأجهزة والتعافي والمراقبة والنشر وADRs. هذه ليست دعوى قراءة كل دالة أو اختبار كل قدرة.

قيس 15 شاهداً محلياً: 13 شاهداً تكشف سلوكاً معيباً، وشاهد ينقض دعوى الكود الميت، ومرشح MinIO استُبعد بعد التحكيم. نجح 94 اختباراً قائماً (72 + 22)، بلا skipped في هاتين المجموعتين. بعض الشواهد يستخرج دالة المصدر لتشغيلها بمحوّلات وهمية ومنع بدء خدمة أو اتصال. لم يُشغّل مكدس Docker أو PostgreSQL أو NATS/المتصفح أو GPU أو Flutter أو أجهزة فعلية. لا ترقية runtime_verified أو production_certified؛ تبقى أدلة التشغيل في سجلها القانوني.

## تصحيح المراجعة الأصلية

### C01 — NATS بلا مصادقة ويحمل أوامر المشغلات

**غير صحيح على الأساس المقيس**. nats.conf يفرض user/password، وv9 يمررهما كقيم مطلوبة. سجل الفجوة نفسه ينتهي بتحديث fixed بتاريخ 2026-09-08. مسار الصمام يمر عبر MQTT، وليس NATS. الباقي هو هوية وصلاحيات موضوعات لكل خدمة وTLS، وهو CONN-03.

[المصدر: nats/nats.conf:43](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/nats/nats.conf#L43)

### C02 — دوال irrigation.real غير موصولة، ووسيط التربة لا يُنفّذ

**نقضه الكود والتنفيذ المحلي**. سبعة handlers للري مسجّلة بالـdecorators وتُحلّ من السجل. التعريف الحقيقي خلف FEATURE_IRRIGATION_WORKFLOW_REAL، وينتج نية تنفيذ لا حركة صمام. وسيط التربة مسجّل بـ@app.middleware("http"). لا يجوز حذفهما اعتماداً على رسم الاستدعاءات المباشرة. _apply_tenant_guc يحتاج حكماً مستقلاً ولا نعدّه موصولاً بهذه الحجة.

[المصدر: services/sahool-platform/api/workflow_definitions.py:462](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/sahool-platform/api/workflow_definitions.py#L462)

### C03 — الأطوار shared/phase9..12 لا يستوردها إلا اختبار

**غير صحيح**. الوحدات api/phase9_autonomous_farm_os.py وphase10_continuous_learning.py وphase11_federated_agents.py وphase12_marketplace_ecosystem.py تستورد العقود فعلاً؛ marketplace_plugin_runtime مستهلك آخر. هذا يثبت المستهلك البرمجي، ولا يثبت تفعيل قدرة إنتاجية.

[المصدر: services/sahool-platform/api/phase12_marketplace_ecosystem.py:29](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/sahool-platform/api/phase12_marketplace_ecosystem.py#L29)

### C04 — 62 ملفاً تستدعي fetch خارج طبقة API

**مطابقة نصية مضللة**. مطابقة substring fetch( تعطي 62 ملفاً لأنها تلتقط refetch(. مطابقة المعرّف fetch مع السماح بالفراغ تعطي 4 ملفات: WeatherTileLayer وWeatherHoverReadout وWeatherProbePopup وملف اختبار. أي 3 ملفات إنتاجية، تستخدم weatherFetchHeaders. يبقى فحص اتساقها مشروعاً، ويسقط تبرير حظر 62 موضعاً. اختلاف المجموعتين 59 ملفاً لأن ملف الاختبار يستعمل صيغة نصية/فراغاً مختلفاً.

[المصدر: frontend/src/components/maphub/weather/WeatherTileLayer.ts:198](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/frontend/src/components/maphub/weather/WeatherTileLayer.ts#L198)

### C05 — أربع خدمات بلا اختبارات إطلاقاً

**صحيح داخل مجلد الخدمة فقط**. اختبارات مركزية موجودة: test_raster_tiler_service_contract، test_weather_polygon_worker، test_weather_signal_engine، واختبارات SAM2 في tests_v9. شغّلنا اختبارات الثلاث الأولى بنجاح؛ لم نشغّل SAM2 على GPU. عدد الملفات أو ذكر الخدمة لا يساوي تغطية سلوكية.

[المصدر: tests_v9/test_raster_tiler_service_contract.py:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/tests_v9/test_raster_tiler_service_contract.py#L1)

### C06 — خمسة أيتام معمارية تعني خدمات غير موصولة

**الاستنتاج يتجاوز الرسم**. الخمس موجودة كأهداف build في v9؛ supervisor يستدعي guardrails فعلاً، وخدمة segmentation لها عنوان SAM2. الأسماء المصدرية وأسماء Compose مختلفة. الرسم المولّد محدود الحواف؛ يتطلب تطبيع الهوية وتتبع HTTP والرسائل قبل الحكم بالعزلة.

[المصدر: docker-compose.v9.yml:719](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docker-compose.v9.yml#L719)

### C07 — خمسة أسماء GUC للمستأجر

**يجب فصل الدلالات**. هناك ثلاثة أسماء tenant؛ current_role وcurrent_user_id للدور والمستخدم، وليسا بديلين للمستأجر. توحيد أسماء المستأجرين مشروع تدريجي؛ عدّ نصوص الهجرات القديمة لا يكشف السياسات النافذة بعد v192/v194. يلزم pg_policies والأدوار والمعاملات على PostgreSQL.

[المصدر: scripts/ci/tenant_guc_name_convergence_guard.py:36](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/ci/tenant_guc_name_convergence_guard.py#L36)

### C08 — 75 مخالفة لملكية الكتابة

**الأساس الحالي 73**. db_writer_ownership_baseline.json يحمل violation_count=73، مع تنبيه صريح أن بعض المواضع قد يستلزم تصحيح العقد لا تغيير الكاتب. لا يجوز تحويل العدد إلى 73 خرقاً تنفيذياً مثبتاً.

[المصدر: docs/architecture/db_writer_ownership_baseline.json:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/architecture/db_writer_ownership_baseline.json#L1)

### C09 — Helm أربع نشرات و12 قالباً

**العدّ غير صحيح**. values.yaml يعلن 6 workloads والقوالب الفعلية داخل templates عددها 8. القالب يعمل بحلقة، فلا يعدّ عدد التصريحات kind: Deployment عدد النشرات. توجد عيوب توافق فعلية موثقة في SUP-12.

[المصدر: helm/sahool/templates/deployments.yaml:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/helm/sahool/templates/deployments.yaml#L1)

### C10 — OTel Collector موجود في v9

**غير موجود في ملف التشغيل القانوني**. observability/otel-collector.yml موجود كملف إعداد؛ v9 لا يعلن خدمة collector. Prometheus وAlertmanager وGrafana وJaeger موجودة. وجود ملف إعداد لا يثبت نشره.

[المصدر: observability/otel-collector.yml:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/observability/otel-collector.yml#L1)

### C11 — الموبايل 46 ملف lib و9 اختبارات

**العدد الحالي 48 و12**. 48 ملف Dart في lib و12 ملف *_test.dart؛ الإجمالي 61 Dart يشمل ملف بيانات الاختبار. لا android/ أو ios/ أو pubspec.lock متتبعة. العائق يتجاوز غياب Flutter عن بيئة المراجع.

[المصدر: mobile/sahool_app/pubspec.yaml:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/mobile/sahool_app/pubspec.yaml#L1)

### C12 — 64% شيفرة خدمات = شيفرة منتج

**التركيز صحيح؛ تعريف LOC يحتاج ضبطاً**. العداد يشمل ملفات الاختبار: 164626 من 256943 سطراً غير فارغ وغير بادئ بتعليق. باستبعاد ملفات الاختبار/conftest يصبح 120647 من 190258، أي 63.41%. يبقى التركّز، لكن فصل المسؤوليات والعقود أهم من فرض حد سطور وحده.

[المصدر: scripts/ci/generate_service_inventory.py:288](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/ci/generate_service_inventory.py#L288)

### C13 — 1050 مساراً و638 للمنصة يمكن جمعها مباشرة

**مسطرتان مختلفتان**. execution-audit يحصي 1050 route handlers؛ مولّد service_inventory يحصي 1114 تصريحاً إجمالاً، و638 للمنصة في ذلك المسح. الميزانية الملزمة 632 خاماً، 4 بنية، 628 نطاقاً من سقف 629. لا تستبدل إحداها بالأخرى.

[المصدر: docs/architecture/generated/platform_route_budget_inventory.json:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/architecture/generated/platform_route_budget_inventory.json#L1)

### C14 — كل وظائف PR غير المطلوبة يمكنها الاحمرار بلا حجب

**استنتاج يحتاج قياس القواعد الحية**. العقد المحلي يحوي 15 اسماً مطلوباً ولا يحتوي Mutation Sweep. لكن عدد وظائف YAML ليس عدد jobs المنفذة في كل PR بسبب matrix/if/paths/needs. لم نتحقق في هذه الجولة من Ruleset الحي؛ إضافة required check قرار حوكمة موحد لا نتيجة تلقائية لعدّ السطور.

[المصدر: docs/architecture/required_status_checks_contract.json:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/architecture/required_status_checks_contract.json#L1)

## نتائج الفحص المكمل

### SUP-01 — انقسام خوارزمية المصادقة في إشعارات WebSocket

**P1 · مثبت محلياً · auth + notification + Compose · W01، W02**

المصدر auth يوقّع RS256 عند تجهيز مفاتيحه، لكن _validate_ws_token يقبل HS256 فقط ويشترط JWT_SECRET. يرفض توكن RS256 صالحاً ويقبل HS256 في SAHOOL_ENV=production. إعداد notification في v9 لا يمرر JWT_PUBLIC_KEY أو سياسة الإنتاج. هذا ليس مجرد تكرار فك JWT؛ إنه عقد اتصال مكسور.

الأثر: تسجيل الدخول قد ينجح بينما تفشل قناة الإشعارات في الويب والموبايل. الإبقاء على سر HS256 مشترك يمدد مجال الثقة بين الخدمات.

الإغلاق: توسيع سياسة التحقق المشتركة القائمة إلى notification، وتهيئة المفتاح العام وسياسة البيئة، واختبار handshake من مُصدر RS256 فعلي مع حالات issuer/audience/expiry الخاطئة. لا توسيع قبول الخوارزميات دون سياسة.

[agents/notification/agent.py:547](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L547) · [services/auth/main.py:67](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/auth/main.py#L67) · [docker-compose.v9.yml:2079](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docker-compose.v9.yml#L2079)

### SUP-02 — حدث نطاق بلا tenant يُبث إلى جميع المستأجرين

**P1 · مثبت محلياً بشرط مدخل ناقص · notification + منتجو الأحداث · W03**

dispatch يختار broadcast(data) حين يغيب user_id وtenant_id. شاهد field.created مع entity_id لحقل واحد وصل إلى متصلين من مستأجرين A وB. لا يوجد في هذا الفرع تمييز بين إعلان عام مأذون وحدث نطاق ناقص الهوية.

الأثر: خطأ منتج أو خدمة داخلية مخترقة تستطيع دفع محتوى حدث نطاق إلى مستأجرين آخرين. لا ندّعي أن حدثاً إنتاجياً مسرباً قد رُصد، أو أن مهاجماً خارج الشبكة يصل إلى NATS.

الإغلاق: رفض/عزل أحداث النطاق ناقصة الهوية قبل التسليم؛ إن كانت الإعلانات العامة مطلوبة فلتكن فئة صريحة بتفويض مستقل. اختبار تنوع المستأجرين مع نزع tenant_id من مظروف حقيقي.

[agents/notification/agent.py:348](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L348)

### SUP-03 — إقرار حدث NATS رغم فشل معالجته أو تسليم push

**P1 · مثبت بمكتبة nats-py الحقيقية ومحوّلات وهمية · notification · W04، W05**

subscribe لا يطلب manual_ack، فتغلفه nats-py بإقرار تلقائي بعد رجوع callback. handle_msg يبتلع الاستثناءات؛ dispatch يتجاهل False العائد من send_push. لذلك سجل الشاهد ack واحداً بعد الفشل. السطر msg.ack() غير منتظر ويولّد تحذيراً؛ ليس صحيحاً استنتاج إعادة تسليم لا نهائية من هذا السطر وحده، لأن auto-ack يعمل.

الأثر: قد يفقد التنبيه فرصة إعادة المحاولة بعد تعذر مقدم الخدمة أو خطأ معالجة. نجاح HTTP لا يساوي تسليم قناة خارجية.

الإغلاق: سجل تسليم دائم مع idempotency وretry/dead-letter؛ يقر الوسيط بعد ضمان حفظ العمل أو النجاح المحدد بالعقد. اختبار provider failure وprocess crash بين الحفظ والإقرار والتسليم.

[agents/notification/agent.py:399](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L399) · [agents/notification/agent.py:428](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L428) · [agents/notification/agent.py:458](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L458)

### SUP-04 — notification جاهزة مع فشل الاشتراكات التسعة

**P1 · مثبت محلياً · notification + التشغيل · W06**

أخطاء إنشاء الاشتراكات تُسجل وتُبتلع. readyz يفحص اتصال NATS وSELECT 1 فقط؛ في الشاهد فشلت الاشتراكات التسعة ثم عاد status=ready. Compose ينتظر healthz التي تعلن الحياة فقط.

الأثر: القناة قد تكون صامتة بينما التهيئة والبوابة تعتبران الخدمة جاهزة.

الإغلاق: تتبّع الاشتراكات المطلوبة وإثبات المستهلكين الفعليين في readiness مع إعادة محاولة التهيئة. لا يكفي تغيير healthz إلى readyz قبل إصلاح معيار readiness نفسه.

[agents/notification/agent.py:438](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L438) · [agents/notification/agent.py:662](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L662) · [docker-compose.v9.yml:2117](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docker-compose.v9.yml#L2117)

### SUP-05 — ERPNext يقدّم مؤشر المزامنة عند فشل الجلب

**P1 · مثبت محلياً · odoo-bridge / ERPProvider · W10، W12**

_get_list يعيد [] عند HTTP/JSON/transport failure. sync_products يفسر القائمة الفارغة كنجاح، ثم يحدّث last_sync إلى الوقت الحالي ويسجل Synced 0 products. شاهدنا ذلك باستخدام المزود الحقيقي ودالة المزامنة المستخرجة من المصدر مع مخزن تسجيل وهمي.

الأثر: عند الاستئناف باستخدام since الجديد قد تُتخطى تحديثات وقعت أثناء الانقطاع. هذا عيب اكتمال بيانات، مستقل عن الإصلاح السابق لاختيار ERPNext عند اكتمال الإعداد.

الإغلاق: عقد يميز empty-success عن unavailable؛ تثبيت watermark قبل الجلب وعدم تقدمه إلا بعد نجاح الدفعة وكتابتها. اختبار انقطاع ثم عودة بصفوف مؤرخة داخل فترة الانقطاع.

[services/odoo-bridge/erp_provider.py:145](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/odoo-bridge/erp_provider.py#L145) · [services/odoo-bridge/erp_runtime.py:266](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/odoo-bridge/erp_runtime.py#L266) · [services/odoo-bridge/erp_runtime.py:344](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/odoo-bridge/erp_runtime.py#L344)

### SUP-06 — بوت Telegram يعلن إنشاء مهمة لم تُنشأ

**P1 · مثبت بتنفيذ handler من المصدر · bots/telegram + خدمة المهام · W07**

cb_create_pest_task يستدعي edit_text وanswer فقط، وكلاهما يقول إن المهمة أُنشئت. لا استدعاء لخدمة المهام ولا معرف مهمة أو إيصال. /voice مسجل أيضاً بعد asyncio.run(main())؛ هذا تسجيل متأخر عن بدء polling ويحتاج تصحيح ترتيب منفصل.

الأثر: قد يعتقد المزارع أن متابعة المكافحة دخلت قائمة الأعمال بينما لم تُكتب أي مهمة.

الإغلاق: تمرير الإنشاء إلى المسار المحكوم القائم بصلاحية المستخدم ثم عرض task_id بعد النجاح فقط؛ اختبار فشل الخدمة والتكرار وعدم وجود توكن. لا إنشاء مسار مهام جديد.

[bots/telegram/main.py:804](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/bots/telegram/main.py#L804) · [bots/telegram/main.py:930](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/bots/telegram/main.py#L930)

### SUP-07 — مظروف الحافة يفقد field_id والتوقيت، ويعلن synced عند الفشل

**P1 · مثبت عند حدود النقل والنموذج · edge-inference + منصة edge ingest · W13، W14**

sync_result وqueue_result يضعان field_id داخل data فقط، بينما EdgeSyncRequest والـINSERT يقرآن الحقل الأعلى req.field_id. في الشاهد أصبح None في المسارين؛ مخطط edge_results يفرض NOT NULL. مسار الفشل _queue_with_key لا يحتفظ occurred_at، والـAPI يعوضه NOW(). نقطتا inference تعرضان synced بناءً على OFFLINE_MODE مع تجاهل False من sync_result.

الأثر: مزامنة تفشل أو تبقى في الطابور، وإخلال بتاريخ القياس، وحالة نجاح ظاهرة تخالف النتيجة. قيس النقل والنموذج؛ لم نشغّل INSERT على PostgreSQL.

الإغلاق: إنشاء مظروف واحد عند القياس يثبت field_id/device_id/occurred_at/idempotency_key ويحفظه في المحاولات كلها؛ اشتقاق حالة الواجهة من إيصال النقل. شاهد online→timeout→restart→offline replay يثبت صفاً واحداً بنفس الهوية والتوقيت.

[services/edge-inference/sync_service.py:69](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/edge-inference/sync_service.py#L69) · [services/sahool-platform/api/edge_models.py:17](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/sahool-platform/api/edge_models.py#L17) · [services/sahool-platform/api/routers/edge.py:25](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/sahool-platform/api/routers/edge.py#L25) · [services/edge-inference/main.py:275](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/edge-inference/main.py#L275) · [migrations/v9_new_tables.sql:68](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/migrations/v9_new_tables.sql#L68)

### SUP-08 — توقيع أمر الجهاز لا يربط الجهاز والحمولة، ومنع replay محدود

**P1 قبل التفعيل الفيزيائي · توقيع مثبت محلياً؛ سلوك الجهاز ساكن · actuator-service + firmware + إدارة هوية الجهاز · W15**

التوقيع HMAC(cmd|ts) يستخدم CMD_HMAC_SECRET واحداً في المرسل ولا يشمل tenant/device/payload/idempotency_key. في الشاهد تغيّر الجهاز والحمولة وبقي التوقيع نفسه عند timestamp واحد. firmware يحفظ آخر 16 ts في RAM بلا انتهاء زمني أو حفظ عبر إعادة التشغيل، ويرسل ACK عبر mesh بلا ts/signature/معرف تنفيذ يمكن ربطه في هذا الملف.

الأثر: عند تهيئة مفاتيح مشتركة والوصول إلى قناة MQTT، لا يمنع هذا التوقيع إعادة توجيه أمر موقع بين الأجهزة المشتركة في المفتاح. إعادة نشر العمل تولّد timestamp جديداً لا يستخدم idempotency_key الجهاز. لا ادعاء باستغلال حي أو تشغيل صمام؛ أعلام المسارات الفيزيائية افتراضياً مغلقة، وACTUATOR_MODE نفسه قد يُستنتج real من عنوان MQTT.

الإغلاق: عقد أمر واحد موقّع يربط المستأجر/الجهاز/معرف التنفيذ/الحمولة/نافذة الصلاحية، وهوية ومفتاح لكل جهاز، وdedup دائم وACK موثّق مع معرف العمل. اختبارات hardware-in-loop لإعادة التشغيل وإعادة التسليم وانقطاع CLOSE. تعديل المرسل محكوم بـGATE-01؛ لا مسار بديل حوله.

[services/actuator-service/actuator_runtime.py:570](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/actuator-service/actuator_runtime.py#L570) · [firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino:122](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino#L122) · [firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino:151](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino#L151) · [docs/architecture/gate01_policy.json:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/architecture/gate01_policy.json#L1)

### SUP-09 — إعدادات التفعيل لا تصل إلى الحاويات المستهلكة

**P1 · مثبت من تطابق القراءة مع environment · Compose + مالكو الحافة/الأوامر/الإشعارات · فحص Compose والمصدر**

v9 لا يمرر CMD_HMAC_SECRET إلى actuator؛ ولا PEST_MODEL_SHA256/YIELD_MODEL_SHA256 إلى edge رغم أن بوابة الهوية تتطلبهما؛ ولا FEATURE_MOBILE_PUSH/FCM_SERVER_KEY إلى notification، كما أن TELEGRAM_BOT_TOKEN يمرر للبوت وحده. وجود متغير في .env المضيف لا يحقنه تلقائياً داخل الحاوية. SAHOOL_CLOUD_URL للحافة مكتوب كعنوان ثابت api.sahool.local.

الأثر: قد تبقى قدرة مجهّزة بالأوزان معطلة لغياب بصمتها، أو يُنشر أمر بتوقيع فارغ ترفضه firmware، أو تبقى قنوات اختيارية غير قابلة للتفعيل في v9 وحده. لا نعد البصمات أو الأسرار الغائبة سبباً لتوليد قيم افتراضية.

الإغلاق: عقد بيئة مشتق من المستهلكين يشمل os.getenv داخل الدوال، واختبار compose config ثم readiness داخل الصورة. أبق الأعلام مطفأة حتى دليل كل قدرة؛ لا تستبدل المخطط الموحد بـoverlay غير محروس.

[docker-compose.v9.yml:1643](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docker-compose.v9.yml#L1643) · [docker-compose.v9.yml:1727](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docker-compose.v9.yml#L1727) · [docker-compose.v9.yml:2079](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docker-compose.v9.yml#L2079) · [services/edge-inference/model_artifact_gate.py:34](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/edge-inference/model_artifact_gate.py#L34)

### SUP-10 — مرحلة تنظيف نسخ PostgreSQL تفشل برمز 127

**P1 · مثبت بأدلة مؤقتة فارغة · scripts/backup_postgres.sh / التشغيل · W08**

cleanup_old يمرر log إلى xargs، لكن log دالة shell وليست ملفاً تنفيذياً؛ عاد xargs: log: No such file or directory ورمز 127 حتى على مجلدين فارغين. full يستدعي cleanup_old بعد نجاح النسخة. انحراف عنوان PostgreSQL القديم أُصلح؛ هذا خلل آخر.

الأثر: مهمة النسخ قد تنتهي بفشل بعد كتابة النسخة وإعلان مقياس النجاح، ويتوقف مسار تنظيف WAL اللاحق. لا يعني ذلك أن ملف pg_dump نفسه تالف.

الإغلاق: احسب العدد ثم استدع دالة log مباشرة، واختبر الدورة الفارغة ودورة فيها نسخ قديمة، مع اتساق exit code ومقياس المهمة الكاملة.

[scripts/backup_postgres.sh:178](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/backup_postgres.sh#L178) · [scripts/backup_postgres.sh:228](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/backup_postgres.sh#L228)

### SUP-11 — إرشادات PITR غير قابلة للتطبيق كما كُتبت

**P1 للاستعادة · مثبت ساكن؛ الاستعادة الحية غير مقيسة · Runbook النسخ والاستعادة · قراءة مصدر النسخ والاستعادة**

التعليمات تبدأ من pg_dump منطقي ثم تصف replay WAL؛ PITR يحتاج base backup فيزيائياً أو آلية مكافئة، لا pg_restore dump منطقي. المثال يسمي recovery.conf رغم PostgreSQL 16، وarchive_command المقترح يستدعي wal_archive_one بينما case ينفذ wal_archive فقط. فحص pg_restore --list يقرأ فهرس النسخة ولا يثبت استعادة البيانات كاملة.

الأثر: وجود backup script لا يغلق قدرة التعافي من فقد البيانات. قد يفشل المشغل وقت الحادث رغم نجاح التحقق الشكلي.

الإغلاق: اختيار مسار نسخ فيزيائي/WAL وتشغيل restore drill مع RPO/RTO وبصمات بيانات وأدوار/RLS. أدوات Qdrant snapshot موجودة؛ أدرج أيضاً KG SQLite وRedis state وoutbox وملفات الراستر بحسب ملكية كل مخزن، بدلاً من الاقتصار على PostgreSQL.

[scripts/backup_postgres.sh:128](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/backup_postgres.sh#L128) · [scripts/backup_postgres.sh:193](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/backup_postgres.sh#L193) · [scripts/restore_postgres.sh:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/restore_postgres.sh#L1) · [scripts/qdrant/snapshot_manager.py:62](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/qdrant/snapshot_manager.py#L62)

### SUP-12 — Helm يجتاز حارسه مع خمسة منافذ لا تطابق الصور

**P1 إذا كان Helm هدف نشر · مثبت ساكن وتشغيل الحارس · helm + صور الخدمات · validate_helm_readiness: PASS / 6 workloads**

القالب يأخذ port من values لكل من الخدمة والـprobe. القيم: raster=8000 بدلاً من 8001؛ agronomist=8093 بدلاً من 8000؛ rag=8130 بدلاً من 8000؛ KG=8140 بدلاً من 8000؛ guardrails=8097 بدلاً من 8000. الصور المسمّاة في chart لم تُسحب، ولذلك التناقض مثبت مقابل Dockerfiles الحالية. الحارس يفحص نصوصاً وسياسات عامة ولا يطابق منافذ الصور. تظهر أيضاً secretEnv باسم X_AGENT_TOKEN بدلاً من SAHOOL_AGENT_TOKEN في خدمات تستعمل الأخير.

الأثر: إذا بُنيت صور chart من هذه Dockerfiles فسوف تفشل probes والتوجيه. لا يكفي إصلاح رقم عدد النشرات أو إعلان وجود قالب production.

الإغلاق: إما إبقاء Helm هدفاً مؤجلاً معلناً، أو ربط إعداداته بعقود صور مثبتة وhelm template واختبار إقلاع/توجيه. راجع writable volumes وKG SQLite متعدد النسخ قبل اعتماد هذا النشر.

[helm/sahool/values.yaml:46](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/helm/sahool/values.yaml#L46) · [helm/sahool/templates/deployments.yaml:38](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/helm/sahool/templates/deployments.yaml#L38) · [helm/sahool/templates/services.yaml:18](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/helm/sahool/templates/services.yaml#L18) · [scripts/deploy/validate_helm_readiness.py:118](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/scripts/deploy/validate_helm_readiness.py#L118)

### SUP-13 — مراقبة NATS/nginx وOTel غير موصولة كما توحي الوثائق

**P1 للتشغيل · تطابق إعدادات ساكن؛ scrape حي غير منفذ · Prometheus + nginx + النشر · الجرد الكامل لخدمات Compose**

Prometheus يطلب /metrics من منفذ مراقبة NATS 8222 مباشرة بلا prometheus-nats-exporter، ويطلب sahool-nginx:9113 بلا exporter أو listener مطابق في إعداد nginx. collector غير معرّف في v9. هدف soil معلّق بحجة عدم وجود الخدمة رغم أنها موجودة، وهدف postgres-exporter معطّل بينما توجد قواعد إنذار تعتمد عليه.

الأثر: قد تظهر تنبيهات مضللة أو فجوات صامتة؛ up==0 لا يكتشف هدفاً لم يُسجّل أصلاً. عدد لوحات Grafana وحده لا يقيس هذه التغطية.

الإغلاق: خريطة metric→مصدر→scrape→alert مع exporters حقيقية، واختبار انقطاع/تعافٍ لكل خدمة حرجة وabsent() حيث يلزم. لا اعتبار ملف collector نشراً فعلياً.

[prometheus/prometheus.yml:97](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/prometheus/prometheus.yml#L97) · [prometheus/prometheus.yml:102](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/prometheus/prometheus.yml#L102) · [prometheus/alerts.yml:32](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/prometheus/alerts.yml#L32) · [observability/otel-collector.yml:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/observability/otel-collector.yml#L1)

### SUP-14 — مسار منتج الموبايل غير مكتمل رغم وجود analyze/test

**P2 · مكونات غائبة من الشجرة · mobile + notification · inventory.json + ci.yml**

لا مشاريع android/ios ولا pubspec.lock متتبعة. CI يجري pub get/analyze/test ولا ينتج APK/AAB/IPA. توجد شيفرة WebSocket وpush بالفعل؛ لا يصح وصفها بأنها غير موجودة. الخادم ما زال يستخدم FCM legacy /fcm/send ويصرح بأن HTTP v1 غير موصول؛ لا توجد هنا شهادة تسليم FCM/APNs.

الأثر: اجتياز Dart لا يقدم تطبيقاً أصلياً قابلاً للتوزيع أو يثبت lifecycle/push/offline بعد إعادة التشغيل.

الإغلاق: أهداف أصلية قابلة للبناء، تثبيت التبعيات، إعداد توقيع/معرفات بيئة، تكامل push مدعوم مع إيصال، واختبار offline/logout/refresh/restart على جهاز. تبقى C4/M1 وCONN-07 مفتوحتين ضمن هذا الحد.

[mobile/sahool_app/pubspec.yaml:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/mobile/sahool_app/pubspec.yaml#L1) · [.github/workflows/ci.yml:1977](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/.github/workflows/ci.yml#L1977) · [agents/notification/agent.py:203](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/agents/notification/agent.py#L203)

### SUP-15 — عداد requirements لا يغطي جميع ما يدخل الصورة

**P2 · فجوة نطاق فحص · البناء وسلسلة التوريد · Dockerfile tiler + CI manifests**

TiTiler وuvicorn يُثبتان مباشرة في Dockerfile بنطاقات إصدارات، فلا تكفي إضافة ملفات requirements السبعة عشر إلى pip-audit. تعدد الإصدارات بين صور مستقلة ليس عيباً وحده؛ يجب إثبات توافق العقود والصورة محل التسليم. كذلك nats:2-alpine مرجع متغير؛ Git SHA داخل الملصق لا يثبت بصمة كل تبعية.

الأثر: يمكن أن تتغير البايتات المعاد بناؤها من المصدر نفسه أو تبقى مكتبات runtime خارج الفحص المقصود.

الإغلاق: جرد من الصورة الفعلية وSBOM وبصمات الصور واختبار الحزم المباشرة والعبورية؛ الحفاظ على التوقيعات والإثباتات الموجودة دون الادعاء بوجود CVE لم يُفحص.

[services/raster-tiler-service/Dockerfile:23](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/raster-tiler-service/Dockerfile#L23) · [.github/workflows/ci.yml:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/.github/workflows/ci.yml#L1) · [docker-compose.v9.yml:333](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docker-compose.v9.yml#L333)

### SUP-16 — تعارض معرفات ADR وحالتها مع التنفيذ

**P2 · مثبت بالمقارنة مع الكود · المعمارية والتوثيق · ADR matrix**

ADR-0002 يصف وثيقتين مختلفتين: قاطع MCP وFarm Operations Ledger؛ ADR-0003 كذلك للتفسير والتكاليف. ADR-0033 ما زال Proposed/Deferred ويصف الثقة في header، بينما field-management يفرض assertion موقعة وreplay guard في الإنتاج، وسجل الفجوة يعرف ذلك. الوثيقة التقنية تعود إلى مايو وتجمع أهدافاً مستقبلية مع مكونات حالية.

الأثر: الإحالة بالمعرف وحده قد تقود إلى قرار خاطئ، وقد تعيد المراجعات فتح أعمال مغلقة في الكود أو تفعّل أعمالاً مؤجلة قصداً.

الإغلاق: معرفات فريدة مع روابط توافق وحالات superseded/implemented-in-code/pending-live واضحة؛ تحديث الوثيقة المعمارية من المسارات المملوكة. الحفاظ على ADR-0035 وbuild_unlock وتأجيل OCSM دون تحويلهما تلقائياً إلى أعمال تنفيذ.

[docs/adr/0002-circuit-breaker-mcp.md:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/0002-circuit-breaker-mcp.md#L1) · [docs/adr/ADR-0002-farm-operations-ledger.md:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0002-farm-operations-ledger.md#L1) · [docs/adr/ADR-0033-field-management-tenant-claim-trust.md:1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0033-field-management-tenant-claim-trust.md#L1) · [services/field-management-service/main.py:115](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/services/field-management-service/main.py#L115)

## حدود الخدمات الـ32

|الخدمة|الدور|نتيجة الفحص وحده|
|---|---|---|
|actuator-service|طابور القرار → نشر MQTT؛ publish لا يثبت التنفيذ|عقد التوقيع/إعادة التسليم وتهيئة الأسرار؛ SUP-08/09. لم يُشغّل عتاد.|
|agriai-engine|حساب وتحليل يستدعيه platform/supervisor|فُحص موضعه في النشر؛ لم تُراجع كل معادلة أو نموذج.|
|ai_agronomist|مصادر الحالة وRAG وKG إلى توصية/شرح|موصل في nginx؛ منفذ Helm مختلف. لم تُقَس دقة توصيات حية.|
|auth|مُصدر التوكن → platform وباقي المستهلكين|ربط RS256 وكشف عدم تكافؤ notification؛ لا خدمة هوية بديلة.|
|decision-service|طلبات القرار والتنفيذ وإيصالات adapters|المسار الفيزيائي يبدأ بعد الحوكمة؛ نقل SoR وشواهد PG خارج اعتماد هذه الجولة.|
|edge-inference|استدلال ONNX → طابور محلي → edge ingest|عيوب مثبتة في مظروف المزامنة والحالة؛ سلامة البصمة في الكود قائمة.|
|field-management-service|واجهة الحقل الداخلية للمستهلكين الخادميين|assertion موقعة وreplay في الإنتاج؛ ADR-0033 متأخرة عن المصدر.|
|field-segmentation|طلب رسم manual/auto/hybrid → SAM2|manual موجود؛ auto مشروط بمزود/GPU. ليست يتيمة برمجياً.|
|gis-workflow-service|نواة سير عمل GIS|غير مبنية في v9؛ لم يثبت مسار تشغيل خارجي. قرار صيانة/أرشفة بعد مسح المستهلكين.|
|guardrails-engine|حواجز يستدعيها supervisor وagronomist|استدعاء HTTP موثق؛ تصنيف orphan في الرسم لا يثبت الانقطاع.|
|indicators-service|موصّل observations/timeline من raster|يُحفظ كموصل للمصدر القانوني؛ لا اقتراح إضافة قاعدة أو broker إليه.|
|knowledge-graph|مرجع علاقات زراعية SQLite غير وصفي للعلاج|مخزن وvolume قائمان في v9؛ راجع النسخ الاحتياطي وHelm متعدد النسخ.|
|local-ai-rag|واجهة RAG قديمة/تكامل ضمن التقارب المعماري|وجودها لا يجيز حذفاً آلياً؛ الإقفال وفق خطة S3 وقراءات المستهلكين.|
|mcp_servers|أدوات weather/sentinel/wofost/market للمشرف|عدة حاويات من Dockerfile واحد؛ جرد المجلد لا يكفي لتغطية كل endpoint.|
|model-registry-adapter|تكامل دورة حياة النموذج خلف profile|موجود ضمن model-lifecycle؛ التفعيل وأدلة النموذج لم تُقَس.|
|odoo-bridge|ERP اختياري → إسقاطات/مزامنة بيانات|اختيار NullProvider صحيح عند نقص الإعداد؛ خلل watermark مستقل مثبت.|
|qdrant-seed|تهيئة corpus في Qdrant|مهمة تهيئة؛ غياب healthcheck دائم ليس بحد ذاته عيباً.|
|rag-retrieval|استرجاع dense+BM25 من Qdrant → مستهلكو AI|فحوص count/dimension موجودة؛ sparse cache محلي لكل عملية يحتاج شاهد تحديث بين replicas قبل التوسع.|
|raster-service|مالك رصد الصور → منتجات/بلاطات/مستهلكون|TiTiler القانوني محدد بالفعل؛ no new tiler path. الأداء الحقيقي لم يُقَس.|
|raster-tiler-service|TiTiler wrapper → platform/raster|اختبار مركزي 15 حالة ناجحة؛ تثبيت مكتبات داخل Dockerfile وغياب سقف ذاكرة.|
|remote-sensing-workspace-bff|تجميع واجهة workspace من المصادر القائمة|موصول في v9/nginx؛ فحص التهيئة لا يثبت كامل عقود الشاشة.|
|sahool-platform|تنسيق الواجهة والقرار والزراعة والنطاق|628 route نطاق من 629؛ التركّز ثابت، واستخراج الوحدات يتبع الملكية والبوابات.|
|sam2-inference|تقطيع الصورة في خدمة GPU|profile=gpu ومستهلك segmentation؛ اختبارات مركزية موجودة، استدلال GPU غير مقيس.|
|scout-ingest-service|استيعاب الكشوف → projection_worker|خدمتا تشغيل من أصل واحد؛ الاستعادة وتسليم JetStream تحتاجان roundtrip حي.|
|soil-service|رصد التربة → منتجات وملكية حقل|middleware مسجلة، اختبارات tenant محلية ناجحة؛ RLS حي غير منفذ.|
|supervisor-agent|توجيه الطلب → MCP/Guardrails/Decision|قاطع MCP موجود مطابق ADR؛ لا ندّعي اختبارات كل سيناريو أدوات.|
|tts-service|تحويل النص إلى صوت للبوت/التنبيهات|خدمة قائمة؛ تسليم الصوت النهائي غير مقيس.|
|vegetation-analysis-service|تفسير رصد raster ومخزن anomaly|يبقى الرصد مملوكاً لـraster؛ لا حاجة لاستعادة حساب Sentinel مباشر.|
|video-processor|تكامل الوسائط مع ZLMediaKit|طرفا النشر موجودان؛ live video/GPU/transcoding غير مقيس.|
|weather-polygon-worker|عامل الطقس على المضلعات|تشغيل Compose واختبار مركزي؛ ليس صفراً من الاختبارات.|
|weather-service|طقس وET0/GDD وحالة زراعية|أخطاء cache السابقة ليست مفتوحة تلقائياً؛ missing-data ينتقل حسب العقد.|
|weather-signal-engine|إنتاج إشارات الطقس للمستهلكين|تشغيل Compose واختبار مركزي؛ دقة الإشارة ومسار event حي غير مقيس.|

## المكونات الأخرى

**SDK Python/TypeScript + developer-portal:** ملفان لبناء عناوين URL، ولا نقل HTTP أو توزيع package مثبت أو اختبارات تكامل SDK. يُصحّح وصف نضج واجهة الشركاء قبل تبنّي SDK؛ استدعاء base_url مع /api يجب أن يكون عقداً معلناً. لا إزالة فورية دون مسح مستهلكين خارجيين.

**random_forest/agb_model.py:** get_agb_model يدرّب synthetic عند البدء، ويُرجع confidence_pct=85 وmodel_accuracy من ورقة مرجعية. لا مستهلك إنتاجي مباشر عُثر عليه في مسح services/shared. هذا نموذج تجريبي، ولا يُستعمل كدليل دقة حقول اليمن أو كمسار AGB ثانٍ. لا نعده تسرباً إنتاجياً مثبتاً.

**sentinel_hub/ وvegetation_real/:** واجهات توافق قديمة؛ facade Sentinel يعلن تعطيل الحساب المباشر ويعيد استعمال raster/vegetation. المطلوب جرد المستهلكين وإحالات التوافق، لا إعادة تفعيل مصدر رصد آخر.

**sam2-models/:** ملفات README/placeholders لتزويد الأوزان، وليست بحد ذاتها مكوناً ناقص التنفيذ. الفصل بين الرخصة والبصمة والأوزان وGPU وشاهد الاستدلال لازم.

**RAG / Qdrant / KG:** توجد فحوص تطابق أبعاد/count وإعادة بناء sparse، ومخزن KG مرجعي غير علاجي. يجب قياس تحديث BM25 بين العمليات والمخازن بعد ingest خارجي واستعادة النسخ قبل توسيع replicas. لم يثبت هنا عيب إجابة حية أو فقد corpus.

**البيانات والهجرات:** MANIFEST هو المسار القانوني. decision-service migrations تخص SoR مستقلاً؛ Alembic بلا مشغّل ظاهر في المسح الحالي، فوثّق غرضه. عدّ CREATE TABLE أو ENABLE RLS لا يثبت الحالة النهائية ولا يعوض تشغيل الهجرات وإعادة تطبيقها على volume قائم.

**النشرات البديلة وملفات الجذر:** الأسماء المختلفة في ملفات مستقلة لا تثبت فشلاً ما لم يُطلب تركيبها معاً. يُحدّد الدعم ومستهلك كل entrypoint ثم الأرشفة مع حفظ الروابط. لا نقل 277 ملفاً دفعة واحدة بناءً على الحجم فقط.

**الطقس/المياه/المحاصيل والمال:** يُحفظ rain missing ≠ 0 وترتيب أولويات اليمن وملكية Root-Zone. مشكلة الري غير المسجل وموضوعات المنتج CONN-04 تبقى ملفاتها المحكومة محجوبة. شهادة تقدم الموسم والمال ووحدة الحساس تحتاج قياساً ميدانياً؛ لا تحويل NOT_MEASURED إلى FAILED.

**الأمان وسطح الاختبارات:** بقاء 94 اختباراً أخضر مع الشواهد المكتشفة يثبت فجوة في السيناريوهات المختبرة، لا انعدام قيمة الاختبارات. استخدم اختبارات عبر حد المنتج/المستهلك؛ لا تكتف بحارس وجود نص أو بعدد طفرات أكبر.

## ADRs

[0001-erp-provider-abstraction.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/0001-erp-provider-abstraction.md#L1): قائم في ERPProvider؛ SUP-05 يكشف أن عقد الفشل لا يحفظ اكتمال المزامنة.

[0002-circuit-breaker-mcp.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/0002-circuit-breaker-mcp.md#L1): القاطع موجود، 5 إخفاقات/30 ثانية/نجاحان؛ معرف 0002 مكرر.

[0003-explainability-lineage.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/0003-explainability-lineage.md#L1): يصف تجميع تفسير قائم؛ لا يثبت سلسلة correlation عبر قواعد وخدمات التنفيذ. معرف 0003 مكرر.

[ADR-0002-farm-operations-ledger.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0002-farm-operations-ledger.md#L1): دفتر عمليات داخلي، ERP إسقاط اختياري. لا تحويله إلى ERP كامل.

[ADR-0003-farm-ledger-budget-cost-intelligence.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0003-farm-ledger-budget-cost-intelligence.md#L1): حساب تكلفة وربحية خلف العلم؛ أهلية البيانات المالية الحية تبقى شرطاً.

[ADR-0004-farm-ledger-closed-loop.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0004-farm-ledger-closed-loop.md#L1): الأعلام الافتراضية مغلقة والإسقاط ليس خصماً تنفيذياً؛ يُحافظ على الحد.

[ADR-0031-drawing-tools-engine-strategy.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0031-drawing-tools-engine-strategy.md#L1): توجّه الرسم له واجهات حالية؛ لم يُقَس WebGL بصرياً في هذه الجولة.

[ADR-0032-lexicographic-irrigation-mpc.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0032-lexicographic-irrigation-mpc.md#L1): ترتيب المحصول ثم الماء/الطاقة ثم الإنتاج ثم الهامش محفوظ؛ مرشح توصية لا أمر جهاز.

[ADR-0033-field-management-tenant-claim-trust.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0033-field-management-tenant-claim-trust.md#L1): بائتة: implemented in code + pending live، كما في main.py وسجل الفجوة.

[ADR-0034-sahool-ocsm-crosswalk.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0034-sahool-ocsm-crosswalk.md#L1): مرجع دلالي فقط؛ لا اعتماد schema/runtime ولا إعادة تسمية ميكانيكية.

[ADR-0035-physics-ai-calibration.md](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/9613db9aef6ae5bb6b63081f936b083ed52f7a8d/docs/adr/ADR-0035-physics-ai-calibration.md#L1): build_unlock محجوب بشروط دفاتر ومواسم وSIM-GOLDEN؛ لا تنفيذ تلقائي للمعايرة.

## ترتيب الإغلاق

1. **تصحيح المراجعة وفهرسة الأدلة:** إزالة الأحكام المنقوضة وربط كل حالة بمصدرها؛ دون تغيير العقود أو حدود GATE-01.

2. **الإشعارات والعزل:** SUP-01..04 وتهيئتها؛ إثبات RS256، هوية المستأجر، حفظ الرسالة، readiness، ثم اختبار WebSocket عبر nginx.

3. **اكتمال العمل والمزامنة:** ERP watermark وTelegram task_id ومظروف Edge؛ كل شريحة تعيد إنتاج العطل وتثبت سلوك الفشل والاستئناف.

4. **استعادة مقيسة واتساق النشر:** backup cleanup/PITR ثم exporters وتهيئة الصور؛ إذا كان Helm مطلوباً تُقاس مطابقة منافذه وصوره قبل اعتماده.

5. **ملف التنفيذ الفيزيائي المحكوم:** تقرير SUP-08 وعقد الأمر والـACK ضمن تحكيم GATE-01 القائم؛ لا لمس ملف مجمد أو إنشاء منتج/مستهلك بديل للالتفاف عليه.

6. **منتج الموبايل وتخفيف التركّز:** بعد تثبيت الاتصال: build أصلي وتسليم push؛ ثم استخراج مسؤوليات fields/weather تدريجياً وفق ARCH-S1→S5 وملكية SoR، مع حماية العقود والميزانية.

## إعادة القياس

```sh
git clone https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced.git sahool
git -C sahool checkout --detach 9613db9aef6ae5bb6b63081f936b083ed52f7a8d
python review_inventory.py --repo sahool --output inventory.json
python review_probes.py --repo sahool --output probes.json
python supplemental_probes.py --repo sahool --output supplemental-probes.json
# Use an isolated environment with the repository test dependencies.
# Exact pytest selections and their full logs are in evidence/test-results.json.
```

اختبارات قائمة: 72 + 22 = 94 ناجحة. 13 شاهد سلوك معيب من 15، مع استبعاد W09 وإبقاء W11 كنقض لادعاء الكود الميت. راجع JSON للشواهد كاملة وحدودها.

لا مكدس أو PostgreSQL أو أجهزة أو Flutter حي؛ لا اعتماد تشغيل أو إنتاج. لا تعديلات على كود المشروع.
