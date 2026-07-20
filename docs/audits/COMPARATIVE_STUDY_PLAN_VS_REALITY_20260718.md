# دراسة مقارنة: الخطة الموحّدة ↔ الواقع الفعليّ للمنصّة — SAHOOL

**التاريخ:** 2026-07-18 · **الأساس:** `main` عند `da3f88a` · **المنهج:** ستّة وكلاء تحقّق (read-only) مسحوا الشيفرة
الفعليّة بأدلّة `file:line`، ثمّ قُورنت مزاعم [خطّة التطوير الموحّدة](../../sahool-brain/) بند-بند بما هو **موجود
فعلاً**. القاعدة الحاكمة: **«لا تحليل يُقبل دون grep على الوجهة الفعليّة أوّلاً»** — كلّ سطر أدناه مسنود بدليل.

> **لماذا هذه الدراسة تصحيحيّة لا تأكيديّة فقط:** الخطة افترضت بعض «الموجود» أقوى ممّا هو، وبعضه الآخر
> أضعف. الدراسة تُثبت الثلاثة: ما هو **حقيقيّ** (يُبنى عليه)، ما هو **مبالَغ فيه** (يُصحَّح قبل التخطيط)،
> وما هو **فجوة حقيقيّة ذات أولوية** (يُنفَّذ). الصدق قبل الطموح.

---

## الخلاصة التنفيذيّة — جدول القرار

| البند | زعم الخطة | الواقع المُثبَت (`file:line`) | الحكم | الأثر على الأولوية |
|---|---|---|---|---|
| **A1** WX-FAILOVER | «Open-Meteo رئيسيّ؛ الاحتياط غير مُثبت» | Open-Meteo هو **المصدر الوحيد**؛ لا مزوّد ثانٍ؛ فقط قاطع دائرة + كاش بائت + null-صادق | ✅ **الزعم دقيق** | يبقى P0 تشغيليّ — **greenfield حقيقيّ** |
| **A3** SIM-GOLDEN | «wofost_adapter قائم بلا تحقّق حقول» | **placeholder حتميّ**؛ PCSE لا يعمل أبداً (غير مُثبَّت + سقالة غير صالحة) | ⚠️ **الزعم مبالَغ** | **SIM-PCSE يسبق SIM-GOLDEN** — لا معنى لـgolden قبل تشغيل محرّك حقيقيّ |
| **A4** BOUNDARY-UX | «الفجوة توصيل لا ابتكار» | **موصول فعلاً** end-to-end في onboarding + ثقة + تأكيد بشريّ | ⚠️ **الزعم قديم** | **A4 يتقلّص** — الفجوة المتبقّية أضيق (اقتراح-عند-الفتح + نشر GPU + FTW stub) |
| **A5** WATER-SALT | «الملوحة مدعومة» | **عميقة فعلاً** (Maas-Hoffman Ks + غسيل FAO-56 + ملاءمة + عقوبة غلّة) بلا عقد قدرة مُعلَن | ✅ **الزعم دقيق** | يبقى P1 — شريحة **توثيق/عقد** لا بناء |
| **B1** SCOUT-INGEST | «أكبر فجوة منتج» | **غائب مؤكَّد** (لا ODK/Kobo/CSV-observations/مظروف محايد)؛ اللبنات الداخليّة موجودة | ✅ **الزعم دقيق** | يبقى **P0 منتجيّ** — فجوة تركيب لا تأسيس |
| **B2** SOIL-SOURCE | «لا طبقة تربة مؤسسية» | **SoilGrids مُدمَج فعلاً** بتراتبيّة مصادر صارمة | ⚠️ **الزعم مبالَغ** | **B2 شبه مُنجَز** — المتبقّي طبقة «مسح إقليميّ» وسيطة فقط |
| **A6** خرائط SVG | «تقارير نقطيّة» | تقارير PDF موجودة (reportlab)؛ `ST_AsSVG` **صفر** | ✅ **الزعم دقيق** | فجوة حقيقيّة P2 |
| **A7** حدود إداريّة | «لا طبقة سياق إداريّ» | **غائبة**؛ المستودع يُصرّح بغيابها ذاتيّاً | ✅ **الزعم دقيق** | فجوة حقيقيّة P2 |

**الخلاصة الاستراتيجيّة المُصحَّحة:** المنصّة **أقوى** ممّا تظنّ في مكانين (الحدود التلقائيّة موصولة؛ SoilGrids
مُدمَج)، و**أضعف** ممّا تظنّ في مكان واحد حرِج (محاكاة المحصول placeholder لا WOFOST حقيقيّ). الثلاثة تُعيد
ترتيب الأولويّات بصدق.

---

## القسم 1 — التحقّق التفصيليّ بند-بند

### A1 · محرّك الطقس والاحتياط — ✅ الزعم دقيق، الفجوة greenfield

**موجود:** Open-Meteo مُدمَج كمصدر وحيد كامل — `services/weather-service/open_meteo.py` (`fetch_current:169`,
`fetch_forecast:243`, `fetch_historical:275`, `readiness_probe:453`)، موصول في `weather_runtime.py:21-32`،
ومُعلَن مصدر-السجلّ (`weather_runtime.py:115` `"source":"open-meteo+sahool-rules"`).

**ET0 موحّد (نواة واحدة):** `services/weather-service/et0.py:60` `penman_monteith_et0_mm` هي النواة الوحيدة
فوق `vapor_pressure.py` المشترك؛ كلّ المستهلكين إمّا HTTP-clients أو مُحقِّنو ET0 (MCP `weather_server.py:208-261`
يُلغي نسخته المحلّية ويفشل مُغلَقاً؛ `water_balance.py:25-26` «لا نواة ET0 محلّيّة هنا»). **لا ازدواج.**

**غائب (الفجوة الحقيقيّة):** لا مزوّد ثانٍ في كامل `services/`. عند تعذّر المصدر:
`open_meteo.py:137-138` يرفع `RuntimeError("circuit breaker is open")`؛ «الاحتياط» الوحيد كاش بائت
(`weather_runtime.py:263-266`) لا مزوّد بديل. النقاط الأربع للخطة: (a) اختيار بديل بسياسة = **غائب**؛
(b) provenance = **مصدر-واحد فقط**؛ (c) degraded = **حاضر لكن صحّة/كاش لا مزوّد**؛ (d) عدم اختلاق أصفار =
**مُحترَم** (`weather_runtime.py:848-849` `value=None`، `canonical_weather_state.py:16-17` fail-closed).

**الحكم:** A1 **greenfield نظيف** — لا تراجع، بناء طبقة تجريد مزوّد + سياسة failover + provenance عابر-مزوّدين.

---

### A3 · محاكاة المحصول — ⚠️ الزعم مبالَغ (تصحيح جوهريّ)

**الخطة قالت:** «wofost_adapter قائم بلا تحقّق من حقول حقيقيّة» — أي أنّ المحرّك موجود ويحتاج معايرة فقط.

**الواقع:** المُحوِّل **placeholder حتميّ**، لا WOFOST يعمل أبداً:
- `services/agriai-engine/wofost_adapter.py:25-30` — `pcse` استيراد محروس اختياريّ، ليس تبعيّة صلبة.
- المسار التنفيذيّ الوحيد هو heuristic قانون-الحدّ-الأدنى `_fallback_simulate:102-151`
  (`yield=min(thermal,water)`، `provenance="deterministic_fallback"`).
- `_pcse_simulate:246-271` مُعلَّم `# pragma: no cover`، ووثائقه تعترف (`:256-257`) أنّ موفِّرات PCSE **لا تُبنى فعلاً**؛
  يمرّر dicts خامّة إلى `Wofost72_WLP_FD` — يفشل لو شُغِّل.
- `requirements.txt:12` — `# pcse>=5.5` **مُعلَّق** ⇒ `_PCSE_AVAILABLE=False` دائماً في هذا النشر.
- `supervisor-agent/skills/crop_model_skill.py` ⇒ MCP `run_wofost_simulation` الذي **يرفض التشغيل** بـ501
  (`mcp_servers/wofost_server.py:144-150`)؛ الفروع الأخرى جداول ثابتة (`et0=5.0`، NPK lookup).

**صدق إيجابيّ:** المُحوِّل **يفشل مُغلَقاً بأمانة** في وضع الإنتاج (`wofost_adapter.py:294-300`
`raise RuntimeError("agriai_production_simulation_unavailable")`) بدل تسويق heuristic كمُتنبّئ.

**provenance النموذج:** موجود للمدخلات (hashes: `agronomic_adapters.py:36-44` parameter_set_hash، soil/weather/irrigation hashes)
لكن **غائب للنموذج** — لا `model_name/model_version/calibration_status/validation_status` يرافق الغلّة (grep = صفر).

**golden files:** **غائبة** — كلّ الاختبارات إمّا synthetic (`test_agronomic_adapters.py:48` أرقام مُلقَّمة يدويّاً)
أو grep على نصّ المصدر (`test_production_readiness_truth.py`). لا مقارنة بحصاد مرصود.

**الحكم التصحيحيّ:** الترتيب الصحيح **SIM-PCSE-01 (ركّب+وصّل PCSE حقيقيّ) يسبق SIM-GOLDEN-01**. لا معنى لملفّات
ذهبيّة تُقارن مخرَج heuristic. الخطة دمجت المرحلتين؛ الواقع يفصلهما.

---

### A4 · الحدود التلقائيّة وتوصيلها بالـonboarding — ⚠️ الزعم قديم (تصحيح)

**الخطة قالت:** «الخوارزمية قائمة؛ الفجوة توصيل لا ابتكار» — بافتراض أنّ التوصيل غائب.

**الواقع:** الحدود التلقائيّة **موصولة فعلاً** end-to-end في تدفّق التسجيل:
`SetupCabin.tsx:378` → `FieldSetupWizard.tsx:96-104` → `AddFieldWithMap.tsx:1374-1379` (`AutoSegmentControl` تلقائيّ/هجين
داخل لوحة الرسم) → `handleSegment:836-914` → `api.ts:630` `POST /api/segmentation/segment` →
`field-segmentation/main.py:390-445` → SAM2 (`sam2-inference/main.py:23-101`).

**الثقة + التأكيد البشريّ حاضران:** SAM2 يُصدر `confidence` (`main.py:79,101`)؛ الواجهة تعرضه
(`AddFieldWithMap.tsx:882` `ثقة ${confidence*100}٪`, badge `:1471`)؛ الاقتراح يُحمَّل في الطبقة **القابلة للتحرير** لا يُحفَظ
تلقائيّاً («راجِعه وعدّله قبل الحفظ» `:892`).

**صدق سلبيّ (fail-closed):** بلا GPU/model ⇒ 503 صادق (`sam2_runtime.py:120-122` `cuda_unavailable`؛
`field-segmentation/main.py:416-427` `model_not_configured`) ثمّ انحدار نظيف لليدويّ.

**الفجوة الحقيقيّة المتبقّية (أضيق ممّا ظنّت الخطة):**
1. **تشغيليّ:** لا حدّ تلقائيّ حيّ حتّى يُنشَر خادم SAM2 GPU ويُضبط `SEGMENTATION_INFERENCE_URL`.
2. **FTW forward-pass ما زال stub:** `ai_agronomist/field_boundary_backends.py` — `_run_ftw_inference` يعيد `None`
   حتّى يُركِّب مُشغِّل الأوزان (مسار وكيل منفصل عن onboarding).
3. **UX:** التلقائيّ **مُطلَق بزرّ** لا **اقتراح استباقيّ عند فتح الحقل**. إن كان BOUNDARY-UX-01 يريد
   suggest-on-open، فذاك السلوك المحدّد غائب — لكن تدفّق «أكّد-حدّ-AI» نفسه حاضر.

**الحكم:** A4 يتقلّص من «توصيل كامل» إلى **شريحة UX ضيّقة** (اقتراح-عند-الفتح) + متطلّب تشغيليّ (نشر GPU).

---

### A5 · الملوحة كعقد قدرة — ✅ الزعم دقيق (عميقة، غير مُعلَنة)

**موجود (أعمق ممّا يوحي «مدعومة»):** الرياضيّات الحقيقيّة في `core/engines/fao56.py`:
- **(a) حاجة الماء:** `salinity_stress_ks():127-135` (Maas-Hoffman، FAO-56 Eq.81)؛ يُطبَّق في `compute_irrigation_dual:525-531`
  (`ks=1.0` off-by-default، H5)؛ يظهر في `irrigation_recommendation_policy.py:139-153`.
- **(b) الغسيل:** `leaching_requirement():590-597` (Eq.82, `LR=ECw/(5·ECe−ECw)` مسقوف 0.5)؛ مشروط في
  `irrigation_recommendation_policy.py:157-170`.
- **(c) الإجهاد/الملاءمة:** `crop_suitability.py:104-111` EC معيار حاسم وزن 0.35؛ `guardrails.py:100-117` HALT/WARN؛
  `field_digital_twin.py:54-57` تصنيف مخاطر.
- **(d) الغلّة:** `deficit_irrigation.py:94-130` `salinity_risk`→`yield_penalty_pct` + `recommended=False`؛
  `variety_suitability.py:44,63` عتبات كرت-المحصول.

**غائب (هدف A5 بالضبط):** لا `salinity_supported` ولا نموذج ملوحة مُسمّى في `core/capabilities.py`.
`season_simulation.py`/`scenario_whatif.py` لا يحملان ملوحة إطلاقاً. الإشارات الحاليّة كلّها ad-hoc:
`water_balance.py:86` `salinity_applied` (يُحذَف عند False)، `irrigation_recommendation_policy.py:286-294`
سلسلة `policy` (`salinity_adjusted`/`salinity_with_leaching`/`blocked_for_review`)، `salinity_policy.py:46-70`
قرار تفعيل. **ثلاث آليّات مبعثرة** يجب على المستهلك تجميعها.

**الحكم:** A5 شريحة **توثيق/عقد** حقيقيّة القيمة: توحيد السلوك القائم في عقد قدرة مُعلَن واحد
(`salinity_supported: true` + حدوده). من «دفاع مبعثر» إلى **ميزة تسويقيّة** (سوق مياه مالحة).

---

### B1 · جسر الإدخال الميدانيّ offline — ✅ الزعم دقيق (أكبر فجوة منتج، مؤكَّدة)

**غائب مؤكَّد:** grep `odk|kobotoolbox|kobo|xlsform` ⇒ **صفر** في كامل المستودع. لا مسار
external-submission→observation:
- CSV: `historical_onboarding.py:540` `ingest_csv_string` يُنتج تقرير profiling فقط، **لا يكتب** رصداً.
- GeoJSON/KML: `fields.py:616` `POST /fields/import` حدود-فقط (polygon)، لا رصد.
- المستشعرات: `sensor_intake.py:1-23` أجهزة IoT أوّليّة لا أدوات ميدانيّة.
- الكتّاب الوحيدون أوّليّون مُصادَق عليهم: `scouting_pins` عبر `fields.py:3815` (`_persist_scouting_pin`، سجلّ لكلّ طلب)؛
  `observations` عبر `observations.py:33` (`OBSERVATION_RECORD`، سجلّ واحد). **لا مظروف عامّ** يقبل إدخالاً خارجيّاً.

**اللبنات موجودة داخليّاً (فجوة تركيب لا تأسيس):**
- مظروف محايد: `shared/contracts/remote_sensing/events/envelope_v1.py:23` `EventEnvelopeV1` (idempotency_key/tenant/producer).
- normalize→reject→project: `crop_stress_ingestion.py:34` `normalize_stress_product` (allow-list + رفض provenance ناقص) —
  لكنّه للأحداث الداخليّة فقط (غير موصول براوتر خارجيّ).
- طابور projection + dead-letter: `soil-service/projection_jobs.py` (enqueue→claim SKIP LOCKED→complete/fail→dead_letter).
- quarantine صريح: `decision-service/backfill.py:92-154` `classify_candidates` («لا تخمين، لا تحوير»، fail-closed).

**الحكم:** B1 **يبقى P0 منتجيّ**. الفجوة حقيقيّة، لكنّها **تركيب** primitives قائمة (envelope + normalize + queue + quarantine)
خلف مدخل ingress خارجيّ، لا اختراع من الصفر. ODK Central أوّلاً، Kobo ثانياً. مفردات المظروف من A2/OCSM.

---

### B2 · SoilGrids كمصدر — ⚠️ الزعم مبالَغ (شبه مُنجَز)

**الخطة قالت:** «لا طبقة تربة مؤسسية».

**الواقع:** SoilGrids **مُدمَج فعلاً** كمزوّد حيّ حامل دليل + تراتبيّة مصادر صارمة:
- `services/soil-service/soilgrids_client.py:60,86` `fetch_soil_properties` ⇒ `rest.isric.org/soilgrids/v2.0`،
  soft-fail، وسم `source:"soilgrids"`.
- سجلّ نشط: `soil_climate_sources.py:27-48` `soilgrids tier=production_baseline active=True`.
- **تراتبيّة (جوهر الزعم):** `soil-service/profile_composer.py:22-41`:
  `laboratory=100 > field=80 > sensor=55 > analog_fields=40 > soilgrids=30 > model=15`؛ ديناميكيّ للرطوبة/EC؛
  `soilgrids→MODELLED` (`:49`)، مُطبَّق في `_score:80` و`compose_snapshot:99`. **لا استبدال أعلى بأدنى.**

**الفجوة الحقيقيّة المتبقّية (أضيق):** لا طبقة **«مسح إقليميّ»** وسيطة صريحة بين local وmodeled في سلسلة الـcomposer
(الإقليميّ موجود فقط كجدول معايرة governorate منفصل `v165`، لا كمصدر مُرتَّب).

**الحكم:** B2 **شبه مُنجَز** — يُعاد تأطيره من «بناء طبقة» إلى «إضافة tier إقليميّ وسيط + توثيق العقد القائم». يسقط من P1 كبير إلى P2 صغير.

---

### A6 · خرائط SVG متجهة — ✅ الزعم دقيق (فجوة حقيقيّة)

- **موجود:** بناء تقارير + PDF — `report_builder.py:1-45` (`formats=("csv","json","pdf"):39`)؛
  `walk_plan_pdf.py:32` عبر reportlab (lazy import + RuntimeError إن غاب)؛ راوترات `routers/reports.py`، صفحات `ReportsPage.tsx`.
- **غائب:** `ST_AsSVG` **صفر** في المستودع؛ لا توليد SVG خادميّ لخرائط الحدود المتجهة؛ تقارير PDF بلا شكل خريطة متجه.

**الحكم:** فجوة حقيقيّة P2 — خريطة حقل SVG طبقية عبر `ST_AsSVG` من PostGIS داخل report-builder (300dpi للمكاتب الإرشاديّة).

---

### A7 · طبقة الحدود الإداريّة المرجعيّة — ✅ الزعم دقيق (فجوة حقيقيّة، مُصرَّح بها ذاتيّاً)

- **غائب:** المستودع يُصرّح بغيابها — `gis-workflow-service/bulletin_figure.py:72,105` (`admin_geometry_present` «يُتخطّى دائماً»)؛
  `sahool-brain/log.md:2299` `geographic_blocker=no_admin_boundaries_in_repo`.
- **الموجود بدلاً:** `field_boundaries` حدود حقل فقط (`init_v8.sql:27`)؛ `governorate` عمود نصّ (`v165`/`init_v8.sql:468`) لا هندسة admin1/admin2.
- **مرشّحون غير مُحمَّلين:** `data-inputs-catalog.md:119` يذكر OCHA HDX Yemen + geoBoundaries؛ GADM مُقيَّد الرخصة (تجنُّب).

**الحكم:** فجوة حقيقيّة P2 — تحميل OCHA/HDX (admin1/admin2 اليمن) في PostGIS كطبقة موثّقة (source/version/retrieved_at/license) تُغذّي خرائط A6.

---

## القسم 2 — الأولويّات المُصحَّحة (بعد الأدلّة)

```
نقطة الانطلاق (توثيق/عقد، بلا بناء ثقيل):
  A2  SEM-OCSM-01 ─────── crosswalk عقود↔OCSM (يُنتج مفردات مظروف B1)   [مُعتمَد سابقاً]
  A5  WATER-SALT-01 ───── عقد salinity_supported (السلوك عميق فعلاً — توثيقه)  يوم

P0 منتجيّ (فجوة تركيب مؤكَّدة):
  B1  SCOUT-INGEST-01 ─── مظروف محايد خارجيّ فوق primitives قائمة (envelope+normalize+queue+quarantine)

تصحيحات ترتيب (من الأدلّة):
  SIM-PCSE-01  يسبق  SIM-GOLDEN-01   ← WOFOST لا يعمل؛ لا golden قبل محرّك حقيقيّ
  A4 يتقلّص إلى UX-suggest-on-open   ← التوصيل قائم بالفعل
  B2 يسقط إلى P2 صغير                ← SoilGrids مُدمَج؛ يتبقّى tier إقليميّ

فجوات P2 حقيقيّة مؤكَّدة:
  A6  خرائط ST_AsSVG        ·   A7  طبقة حدود إداريّة OCHA/HDX

محجوب ببيانات/بيئة حيّة (بصدق):
  A1  WX-FAILOVER (greenfield، عند توفّر مزوّد ثانٍ)
  A3/SIM-PCSE (يحتاج pcse مُركَّب + بيئة تكامل)
  A4 التشغيليّ (نشر SAM2 GPU)
```

## القسم 3 — إلهام تحسين ما هو موجود (لا adoption جملة)

| المصدر الملهِم | ما يُقتبَس (لا يُتبنّى) | يُحسّن ماذا في SAHOOL | القيد |
|---|---|---|---|
| **PCSE/WOFOST** | ربط موفِّرات الطقس/التربة/الإدارة الفعليّ | يُحوّل `wofost_adapter` من placeholder إلى محرّك حقيقيّ (SIM-PCSE) | رخصة PCSE فُحِصت؛ خلف راية + تكامل |
| **ODK Central / XLSForm** | نمط submission→instance-id | يملأ B1 (idempotency: provider+server+form+instance+hash) | adapter خلف مظروف محايد، لا ربط مباشر |
| **Sen4CAP (LAI/fAPAR)** | خوارزميّات مصادَقة أوروبيّاً | B3 لاحقاً — بشرط مستهلك قرار مُثبت | مراجعة رخصة كلّ جزء منقول |
| **Map2SVG / PostGIS ST_AsSVG** | توليد متجه خادميّ | A6 — خرائط طباعة 300dpi | داخل report-builder القائم |
| **OCHA HDX / geoBoundaries** | حدود admin مفتوحة موثّقة | A7 — طبقة سياق مرجعيّة | HDX لا GADM (رخصة) |
| **AgStack GateKeeper** | مقارنة طبقة الثقة | C1 — ورقة «Operational Trust Layer» (خندقنا) | تموضع لا كود |

## قواعد عدم الانحراف (تُطبَّق على كلّ شريحة تنطلق من هذه الدراسة)

1. لا adoption جملة — مرجع يُقرأ / خوارزمية بمراجعة رخصة / adapter خلف عقد محايد.
2. لا بناء قبل مستهلك قرار مُثبت (درس «LAI لمجرّد أنّه أبعد من NDVI»).
3. الوصول ≠ الثقة — كلّ مصدر خارجيّ يدخل بـevidence + quarantine.
4. كلّ شريحة: حارس + برهان سلبيّ + regen + CI أخضر على SHA واحد.
5. لا نصف حلّ — أيّ بند لا يُدفَع حتّى يعمل مسارُه ويُتحقَّق.

---

**مصدر الأدلّة:** ستّة وكلاء تحقّق read-only، جلسة 2026-07-18، `main@da3f88a`. كلّ `file:line` أعلاه مأخوذ من مسح حيّ للشيفرة الفعليّة لا من زعم الخطة.
