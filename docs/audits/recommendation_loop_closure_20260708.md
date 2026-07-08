# تدقيق إغلاق حلقة التوصية (Recommendation Loop-Closure Audit) — 2026-07-08

> **الهدف (كما طُلِب):** إثبات أنّ الحلقة `توصية → تنفيذ → نتيجة → تعلّم → توصية لاحقة` موصولة
> **فعليّاً end-to-end** قبل بناء أيّ طبقة جديدة. تدقيق قراءة فقط (schema + كُتّاب/قرّاء) بدليل
> `file:line`. لا فبركة: كلّ حكم مسنود.

## المنهج
- استخراج أعمدة جداول الحلقة ومفاتيحها (`recommendation_id`/`decision_id`/`outcome_id`/`field_id`/
  `season_id`) ومفاتيحها الأجنبيّة من `migrations/*.sql`.
- تتبّع الكُتّاب (`INSERT INTO`) والقرّاء (`FROM`) في `services/` لكلّ جدول.
- كشف الأيتام البنيويّة (جدول بلا كاتب / رابط مصدر مفقود / لا FK).

---

## ✅ ما يعمل (السلسلة الأماميّة موصولة فعلاً)

| الوصلة | الآليّة | الدليل |
|---|---|---|
| توصية → قرار | `dispatch_decisions` يحمل `recommendation_id` **و** `decision_id` في نفس الصفّ | كاتب `api/routers/decision_dispatch.py:310` (INSERT) + `:212/:262` يمرّر `req.recommendation_id` |
| قرار → تنفيذ | `execution_ledger.decision_id` | كاتب `api/routers/decision_dispatch.py` |
| تنفيذ → تحقّق | `execution_verification_event` (`recommendation_id`+`execution_id`) | كاتب `api/phase_runtime_store.py` |
| → نتيجة (مساران) | `recommendation_outcomes` (بـ`recommendation_id`+`season_id`) و`outcome_record` (بـ`decision_id`) | كاتبان `api/routers/recommendations.py` و`api/routers/decision_record.py` |
| عمود النَّسَب | `lineage_link` (v82) يربط `decision/dispatch/command/execution/outcome` بـ`ref_type/ref_id` | كاتب `api/execution_lineage.py` |
| نتيجة → تعلّم (قراءة) | التعلّم يقرأ نتائج **حقيقيّة** لا مُفبركة | `api/routers/learning.py:81,143` (من `recommendation_outcomes`)؛ `api/learning_summary.py:59` (من `outcome_record.success`) |

**الخلاصة الإيجابيّة:** المسار الأماميّ (توصية → قرار → تنفيذ → تحقّق → نتيجة → نَسَب) **موصول
ومكتوب**، والتعلّم/التحليلات **يقرأ نتائج فعليّة** عبر RLS. ليست وحدات معزولة على الورق.

---

## ⚠️ ما هو مفصول / يحتاج جسراً (فجوات حقيقيّة)

### فجوة 1 — `recommendation_feedback` جدول ميّت (بلا كاتب)
- الجدول موجود بمفاتيحه (`recommendation_id`,`field_id`,`tenant_id`) في `v_ai_recommendation_runtime.sql`
  لكن **صفر `INSERT` في كامل الكود**. التغذية الراجعة الموجودة تمرّ عبر **حدّ منفصل**
  `services/ai_agronomist/feedback_repository.py` (dataclass، حدّ استمرار مستقلّ) لا عبر هذا الجدول.
- **الأثر:** التغذية الراجعة **مجزّأة** لا تُخزَّن ضمن الحلقة الموحّدة ⇒ `feedback بلا decision` واقع بنيويّ.

### فجوة 2 — تحديثات التعلّم بلا رابط مصدر (learning update بلا evidence)
- `online_learning_updates` (v119) أعمدته: `update_id`,`model_id`,`feature_set_id`,`label_summary`(JSONB)
  — **لا عمود `outcome_id`/`recommendation_id`/`decision_id`**، و`'learning'` **ليست** ضمن
  `ref_type` المسموح في `lineage_link` (`decision|dispatch|command|execution|outcome`).
- **الأثر:** لا يمكن الاستعلام «أيّ النتائج أنتجت هذا التحديث التعلّميّ؟» — الرابط (إن وُجد) مدفون في
  `label_summary` JSONB غير المضمون. هذا **جوهر قلق المستخدم** المُؤكَّد.

### فجوة 3 — نموذجا نتائج متوازيان
- `outcome_record` (مفتاحه `decision_id`) مقابل `recommendation_outcomes` (مفتاحه `recommendation_id`+
  `season_id`). كلاهما حقيقيّ ومكتوب، لكنّ أيّ مستهلِك (الذكاء/الإسقاط) **يجب أن يوفّق بينهما**.

### فجوة 4 (بنيويّة) — لا مفاتيح أجنبيّة على مستوى القاعدة
- لا `FOREIGN KEY` على جداول الحلقة (الوحيد `review_decisions → recommendation_reviews(id)`).
  التكامل المرجعيّ **تطبيقيّ لا قاعديّ** ⇒ الأيتام (نتيجة بلا توصية…) **ممكنة بنيويّاً**.

---

## 🌉 ما يحتاج جسراً (مُرتَّب، صغير أوّلاً)

1. **جسر رابط التعلّم (فجوة 2 — الأعلى قيمة):** أضِف `source_ref` (نوع+معرّف: outcome/recommendation)
   إلى `online_learning_updates` **أو** وسّع `lineage_link.ref_type` بـ`'learning'` واكتب صفّ نَسَب لكلّ
   تحديث. يجعل التعلّم مُتتبَّعاً لمصدره — أرخص جسر أثراً.
2. **جسر التغذية الراجعة (فجوة 1):** إمّا توصيل كاتب لـ`recommendation_feedback`، أو **توثيق صريح** أنّ
   `feedback_repository` هو المصدر المعتمَد وإهمال الجدول الميّت (قرار تصميم، لا جدول مهجور صامت).
3. **موفِّق النتائج (فجوة 3):** دالّة قراءة واحدة توحّد `outcome_record`+`recommendation_outcomes`
   (يستهلكها `field_season_state_projection`/الذكاء) بدل تعدّد المصادر.
4. **حارس عقد الحلقة (فجوة 4):** اختبار ثابت يوثّق السلسلة المُتحقَّقة ويكشف الانحدار (جدول حلقة جديد
   بلا كاتب/بلا مفتاح ربط) — «عقد تشغيليّ» كشيفرة.

## الحكم النهائي
الحلقة **موصولة أماميّاً ومقروءة فعليّاً** (ليست وهماً)، لكنّ **ذيلها التعلّميّ ضعيف الأثر**:
تحديثات التعلّم غير مُتتبَّعة لمصدرها، والتغذية الراجعة مجزّأة، ولا FK يمنع الأيتام. **جسور صغيرة**
(خصوصاً رابط مصدر التعلّم + موفِّق النتائج) تُغلِق الذيل قبل أيّ ميزة جديدة — ثمّ يُبنى فوقها
`field_season_state_projection` كنموذج قراءة واحد. لا يُعاد بناء الذاكرة/النتيجة/الاقتصاد (موجودة).

> المصادر: كلّ صفّ أعلاه من فحص فعليّ لـ`migrations/*.sql` و`services/*` (2026-07-08). لا استنتاج بلا `file:line`.

---

## سجلّ حلّ الجسور (يُحدَّث مع التنفيذ)

- **جسر #2 — نَسَب مصدر التعلّم ✅ (`09fcc71`, migration v151):** أعمدة مصدر + `traceability_status`
  على `online_learning_updates`؛ `core.learning_source_lineage` يحكم القابليّة (traceable/pending/
  rejected)؛ التحديث بلا مصدر يُخزَّن `rejected_untraceable` **فلا يُطبِّق سياسة**.
- **جسر #3 — موفِّق النتائج ✅ (`3651764`):** `core.outcome_reconciler` يوحّد `outcome_record`
  (أثر القرار) و`recommendation_outcomes` (تعلّم الغلّة) بوسم `source_model`/`kind`، ويربطهما عبر
  `dispatch_decisions`. **متكاملان لا مكرّران** — كلٌّ مرجعيّ لسؤاله.
- **جسر #4 — إيقاف `recommendation_feedback` ✅ (migration v152):** الفحص الأعمق أثبت أنّه **مكرّر
  ميّت** لا مجرّد غير-مكتوب: القبول+الغلّة موطنها الحيّ `recommendation_outcomes`، التكلفة
  `farm_operations_ledger`، الماء `water_ledger`. لذا **لا يُوصَل كاتب** (يُعيد تجزئة جسر #3) —
  بل **إيقاف مُوثَّق** بتعليق يوجّه للمسارات المرجعيّة + حارس ساكن يمنع إضافة كاتب صامتاً. لا DROP
  (سلامة بيانات). ملاحظة: `ai_agronomist.InMemoryFeedbackRepository` في-الذاكرة (غير دائم) — التغذية
  الراجعة الدائمة تمرّ عبر `recommendation_outcomes` في المنصّة.
- **جسر #5 — تقوية FK (متبقٍّ):** لا مفاتيح أجنبيّة على جداول الحلقة (الأيتام ممكنة بنيويّاً).
