# سلسلة الأنماط التشغيلية الـ17 — تحليل واستلهام

> **الغرض:** سلسلة من 17 مقالاً عن أنماط Claude التشغيلية حُلّلت كأنماط معمارية لا كميزات. القارئ استخرج الجوهر: "AI ليس Feature، بل Execution Layer". هذه المذكّرة تحوّل ذلك إلى قرارات سهول الفعلية.

---

## النقطة المنهجية المركزية

```
الخطأ الشائع:        "أضيف AI chat داخل المنصّة"
الصواب التشغيلي:     "أبني Execution Layer ينسّق الأدوات"
```

**سهول لا يحتاج chatbot.** يحتاج **مفهرس** للقدرات الزراعية الموجودة + سياق غني + ذاكرة موسمية. هذا ما يميّز:
- **Agronomic Decision Operating System** (هدفنا)
- ❌ **AI-decorated Dashboard** (الفخّ)

---

## ما هو مبنيّ فعلاً (9 من 10 مبادئ)

| المبدأ (من السلسلة) | المُحقَّق في سهول | الموقع |
|--------------------|------------------|--------|
| Skills (قدرات قابلة للاستدعاء) | 12 محرّك + 4 موصّل | `core/engines/`، `core/connectors/` |
| Context (Field-aware) | بطاقة سياق غنية | `field_bundle.py`، `district_baseline.py` |
| Memory (موسمية) | معايرة + سجل توصيات + سجل أنشطة | `learning/`، `recommendation_log`، `activity_log` |
| Grounded AI | تحقّق صارم قبل التوصية | `validate_observations`، `data_completeness`، `evidence_class` |
| Excel/CSV interop | استيراد قياسي | `historical_loader.py` |
| Decision-first viz | FarmerView/BackendDetail | الفصل المعرفي في الواجهة |
| Setup before prompting | حالات الحقل البوّابية | `field_lifecycle`، `quality_grade` |
| Operational (تنفيذ لا دردشة) | الحلقة المغلقة | `activity_log` + `implementation_verification` |
| Provenance (تتبّع التوصية) | forensic كامل | `recommendation_replay.py` |

**الفجوة الواحدة:** Tool Orchestration الصريح — سُدّت الآن (انظر تحت).

---

## ما بُني (الفجوة الوحيدة)

### `core/skills_registry.py` — Tool-Orchestrated Agronomic Intelligence

```
catalog معماري، ليس chatbot. يحتوي:

  • توقيع موحّد لكل skill (name, version, inputs, outputs, requires)
  • فلترة بحالة الحقل: حقل BLOCKED → فقط استقبال بيانات
  • تصنيف السلامة: pesticide_phi و suitability كحرجة
  • drift snapshot: 16 نسخة جاهزة لـrecommendation_replay
  • registry_health: يكشف skills ناقصة التوثيق

16 skill مسجَّلة افتراضياً:
  • 7 agronomic (fao56, supplemental_irrigation, deficit, fertility, ...)
  • 1 safety   (pesticide_phi_gate)
  • 2 spatial  (zone_detection, raster_export)
  • 2 data     (sensor_intake, historical_loader)
  • 2 learning (calibration_loop, recommendation_replay)
  • 2 connector (weather_openmeteo, copernicus_sentinel2)
```

**المبدأ المحوري:** **التسجيل صريح لا تلقائي**. لا magic auto-discovery — كل skill يُراجَع قبل التسجيل. هذا يحقّق "Setup before prompting" على مستوى البنية.

---

## استخلاص الأنماط من المقالات الـ17

### Tier 1 — مطبّق فوراً

| # | المقال | النمط المُستخلَص | التطبيق في سهول |
|---|--------|------------------|------------------|
| 1 | Claude 101 | AI يفهم المشروع كاملاً | ✅ `field_bundle` ينتج سياقاً غنياً |
| 3 | Claude Skills | قدرات قابلة للاستدعاء | ✅ `skills_registry.py` (مبنيّ الآن) |
| 6 | Best AI for Search | Grounded reasoning > model size | ✅ `evidence_class.enforce_indication_ceiling` |
| 9 | No prompt saves you | المشكلة ليست prompt بل البيانات | ✅ `validate_observations` + `data_completeness` |
| 14 | Claude as computer | Tool orchestration لا monolithic AI | ✅ `skills_registry` يحدّد العقود |
| 17 | Setup before prompting | البيئة قبل الـprompt | ✅ `field_lifecycle` (BLOCKED→READY) |

### Tier 2 — مبادئ متطابقة، يستحقّ توثيق

| # | المقال | النمط | الحالة |
|---|--------|------|-------|
| 2 | Claude Code | Engineering Memory (architecture map) | يستحقّ بناء `docs/SKILLS_CATALOG.md` آلياً |
| 5 | Claude in Excel | الناس لن يتركوا Excel | `historical_loader` يستورد، لا exports بعد |
| 8 | Claude for your team | Shared workspace | RBAC المُؤجَّل يخدم هذا |
| 11 | Claude Cowork | AI كزميل لا قاضٍ | FarmerView/BackendDetail يحقّق ذلك |
| 13 | Interactive charts | Decision-first viz | الواجهة تحقّقه، يستحقّ توسيع |
| 15 | Cowork + Project | Persistent memory | calibration + activity_log + provenance |

### Tier 3 — يُؤجَّل بمبرّر صريح

| # | المقال | السبب |
|---|--------|------|
| 4 | Nano Banana 2 | image AI للأمراض — يحتاج dataset محلي |
| 7 | 1M followers | content pipeline — مرحلة لاحقة |
| 10 | AI Slides | تقارير آلية — يستحقّ لكن بعد بيانات كافية |
| 12 | Sound like you | style consistency — أُولويّة منخفضة |

### Tier 4 — تحذير صريح (لا أبنيه)

| # | المقال | لماذا لا |
|---|--------|---------|
| 16 | **AI Workaholic** | **أهمّ تحذير في السلسلة** — سهول لن يكون AI-spam |

---

## أهمّ تحذير من السلسلة: AI Workaholic

> القارئ أكّد: "لا تجعلوا سهول AI-heavy / recommendation-spam"

هذا يتطابق مع مبدأنا الجوهري "الصمت قرار". لكنّه يُضيف بُعداً تشغيلياً:

```
المخاطر العملية لـAI Workaholic في الزراعة:
  ✗ توصية بكل تغيير NDVI بسيط → المزارع يتجاهل النظام
  ✗ تنبيهات يومية للطقس → فقدان الثقة في "العاجل" الحقيقي
  ✗ chatbot يجيب على كل سؤال → استبدال المهندس الزراعي بالمحاكاة
  ✗ auto-recommendations → فقدان وكالة المزارع
```

**ما يحرس هذا في النواة:**
- `evidence_class.enforce_indication_ceiling`: قرينة لا تنتحل صفة دليل
- `farmer_agency`: الرفض معلومة، لا "إعادة محاولة"
- `field_lifecycle.BLOCKED`: حقل ناقص = لا توصية
- `skills_registry.available_for_field`: skill لا تظهر بدون متطلّبات

**القاعدة:** كل توصية يجب أن تجتاز **أربعة بوّابات** قبل الخروج:
1. حالة الحقل تسمح (`field_lifecycle`)
2. المدخلات الإلزامية متوفّرة (`skills_registry.available_for_field`)
3. الـskill ليست حرجة للسلامة بثقة منخفضة (`safety_critical`)
4. لم يرفض المزارع نوعها مسبقاً (`farmer_agency`)

---

## التحوّل الذهني المُؤكَّد

```
من:  Dashboard Platform مع AI chat
                ↓
إلى:  Agronomic Decision OS مع Skills Registry

  مفهرس صريح للقدرات الزراعية
       ↓
  recommendation_engine يستعلم عن الـskills المتاحة
       ↓
  ينفّذ الـskill المناسبة (لا كل skill ممكنة)
       ↓
  يحفظ provenance كاملاً (model_versions_snapshot)
       ↓
  recommendation_replay يكشف drift لاحقاً
```

هذه ليست هندسة LLM. هي **هندسة كتالوج زراعي بعقود صارمة**. المزارع لا يحتاج chatbot — يحتاج توصية مبرّرة قابلة للتتبّع.

---

## ما لم أبنه (والسبب)

| الـpattern | لم يُبنَ لأنّ |
|------------|--------------|
| LLM proxy داخل النواة | يخالف "Tool-Orchestrated" — النواة تنسّق، لا تتحدّث |
| Auto-recommendation cron | يخالف AI Workaholic — التوصية عند الطلب أو الحدث، لا دورياً |
| Image AI للأمراض | يحتاج dataset يمني محلي (غير متوفّر) |
| Style/Tone enforcement | أُولويّة منخفضة جدّاً |
| AI Slides تلقائية | تستحقّ بعد بيانات موسم كامل |

---

## الإقرار الصادق

السلسلة الـ17 ممتازة كمصدر إلهام **عمومي**، لكن القارئ أحسن صنعاً بتحويلها لسياقنا. لو طبّقتها حرفياً، كنت سأبني chatbot لا قيمة له. **الجوهر التشغيلي** هو ما ينفع — والـcatalog (`skills_registry`) يحقّقه بدون LLM إضافي.

نقطة لطيفة: 9 من 10 مبادئ كانت **مبنيّة فعلاً قبل قراءة السلسلة**. هذا تأكيد أن المنهجية صحيحة — وصلنا إلى نفس الأنماط من خلال البناء الزراعي الدقيق، لا من خلال تقليد AI patterns.

```
✅ 502/502 اختبار · 48 ملف · 17 skill مسجَّل · النواة محايدة
✅ Tool-Orchestrated Agronomic Intelligence مُحقَّق
```
