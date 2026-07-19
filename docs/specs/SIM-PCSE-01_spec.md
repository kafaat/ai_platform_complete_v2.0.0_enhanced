# SIM-PCSE-01 — تفعيل محرّك PCSE/WOFOST خلف عقد قدرة (مواصفة للمراجعة)

**الحالة:** ⏳ مسودّة للمراجعة (مواصفة → مراجعة → تنفيذ). **المصدر:** الدراسة المقارنة (A3 مُصحَّح:
`wofost_adapter` **placeholder حتميّ** لا WOFOST؛ PCSE لا يعمل). **الترتيب المعتمد:** SIM-PCSE-01 →
SIM-GOLDEN-01 → A6/A7. **المبدأ الحاكم (المالك):** التفعيل يحافظ على أمانة الـ501 ويحوّلها لعقد — لا تسويق تنبؤ.

---

## 1. الواقع اليوم (المُثبَت `file:line`) — أمانة قائمة، لا محرّك

- **`services/agriai-engine/wofost_adapter.py`:** `simulate()` يُرجع **بديلاً حتميّاً موثّقاً** (قانون
  Liebig: أدنى قيد حراريّ/مائيّ) بـ`provenance="deterministic_fallback"` (`:102-151`). مسار PCSE
  (`_pcse_simulate:246`) **سقالة `pragma:no cover`**: توصيلها ساذج (يمرّر dict خامّاً كـweather/
  agromanagement providers — PCSE يرفضها). `pcse` خلف حارس استيراد (`:24-30`، غير مُركَّب). وضع الإنتاج
  (`AGRIAI_PRODUCTION_MODE`) يفشل **مُغلَقاً** بلا PCSE/مدخلات (`:294-300`) — أمانة قائمة.
- **`services/sahool-platform/api/routers/simulate.py` (`/api/v1/simulate/what-if`):** يُحمّل جذر
  `wofost_real/wofost_engine.py` — **غير موجود** (grep=0) ⇒ يعيد `available:false` دائماً بصدق (`:50-56`).
- **`supervisor-agent/skills/crop_model_skill.py`:** ينتج مقترح `run_wofost_simulation` (501/غير مُنفَّذ).

**الخلاصة:** لا محرّك علميّ يعمل؛ كلّ المسارات صادقة (fallback مُعلَن · available:false · fail-closed).
SIM-PCSE-01 يبني المحرّك الحقيقيّ **مُوصَّلاً صحيحاً**، خلف عقد + راية، مهيّأً لقياس golden — **دون** تسويق.

---

## 2. الشروط الثلاثة (المالك) — بنيويّة لا شعاريّة

### ① عقد قدرة (بمعيار `capability-contract-standard` المولود في A5)
وحدة صرفة `services/agriai-engine/simulation_capability.py` — `SIMULATION_CAPABILITY` frozen dataclass
بنفس بنية `SalinityCapability` (supported · model · references[file:line] · covers[claim+ref] · **limits** ·
**status_enum**). **الحدود المُعلَنة (تمنع fail-open):**
- **WOFOST WLP فقط** (Water-Limited Production) — لا potential/NWLP في v1.
- **لا ملوحة في PCSE** — تبقى عبر مسار `fao56`/الغسيل القائم (A5) — **لا ازدواج محرّكين**. حارس يمنع أيّ
  حدّ ملوحة يتسرّب إلى محرّك المحاكاة.
- **المحاصيل المدعومة بالاسم** — من سجلّ صريح (`sim_crop_registry`)؛ محصول خارج القائمة ⇒ فشل مُغلَق
  مُصنَّف (لا افتراض صامت).
- **المعايرة غير مُثبَتة حتى SIM-GOLDEN** — `calibration_status="uncalibrated_pending_golden"`؛ المخرَج
  يحمل `provenance="pcse_wofost_uncalibrated"` (لا يُسوَّق تنبّؤاً موثوقاً قبل golden).
**الحارس (نظير `test_salinity_capability_contract.py`):** `supported:true` بلا `limits`/`status_enum`/
`references` ⇒ يُرفَض (برهان سلبيّ).

### ② راية افتراضيّة-مطفأة `SIM_PCSE_ENABLED` (off)
- مُطفأة ⇒ **السلوك الحاليّ الصادق يبقى** (`deterministic_fallback` في التطوير · fail-closed 501/
  `simulation_capability_disabled` في الإنتاج). لا تغيير سلوك عند الطفأة.
- مُشعَلة **و** `pcse` مُركَّب **و** المدخلات كافية **و** المحصول مدعوم ⇒ يُشغَّل PCSE الحقيقيّ.
- مُشعَلة لكن أحد الشروط غائب ⇒ فشل مُغلَق مُصنَّف (لا استبدال صامت بالبديل في الإنتاج).
- النمط الانتقاليّ المعتاد (قبول⇒تحذير⇒رفض): الراية تفصل «مُهيّأ» عن «مُصادَق golden».

### ③ فصل الإدخال/الإخراج (تصميم PCSE: parameters/rate/state منفصلة عن I/O)
- `simulation_io.py` نقيّ: `SimulationInputs` (parameters · weather · soil · agromanagement مُهيكَلة) →
  محرّك نقيّ → `SimulationOutput` (yield/biomass/water/stages/**state**). الغراء (dict↔dataclass ·
  provenance · yield_interval) **منفصل** في الـadapter.
- الغاية: **SIM-GOLDEN يقيس المحرّك لا الغراء** — golden files من حقول حقيقيّة بعتبات خطأ مُعلَنة، يُغذّى
  `SimulationInputs` مباشرةً ويُقارَن `SimulationOutput`. لا تسويق تنبّؤ قبل golden.

---

## 3. التوصيل الصحيح (تصحيح `_pcse_simulate` الساذج)
`_pcse_run(inputs: SimulationInputs)` يبني موفِّرات PCSE **الصحيحة** (لا dict خامّ):
- `WeatherDataProvider` من السلسلة اليوميّة (لا تمرير dict مباشرة).
- `ParameterProvider(cropdata=<من sim_crop_registry>, soildata, sitedata)`.
- `AgroManagement` (تقويم زراعيّ صحيح: تاريخ الزرع/الحصاد + عمليّات الريّ).
- `Wofost72_WLP_FD(...).run_till_terminate()` → `get_summary_output()` → `SimulationOutput`.
مُهيكَل وقابل للاختبار **حين يتوفّر pcse**؛ **الشهادة الحيّة مؤجَّلة لبيئة التكامل** (pcse يُركَّب هناك؛
CI الوحدة لا يُركّبه — يبقى `pragma:no cover` للمسار الثقيل، والوحدة تختبر الغراء/العقد/السجلّ).

## 4. سجلّ المحاصيل `sim_crop_registry.py`
`name → WOFOST cropdata + source + effective_from` (لا اختلاق: كلّ محصول بمصدر معاملاته). قائمة v1
الأوّليّة (للمراجعة): المحاصيل اليمنيّة ذات معاملات WOFOST المتاحة (قمح/ذرة/ذرة رفيعة/بطاطس/طماطم/بصل —
نفس مجموعة A5/Ky حيث توفّرت). محصول خارج القائمة ⇒ `unsupported_crop` مُغلَق.

## 5. الحُرّاس + البرهان
- **حارس العقد** `test_simulation_capability_contract.py` (unit): supported بلا حدود ⇒ رفض · covers لها
  refs · status_enum من مفردات حقيقيّة · **لا حدّ ملوحة** في العقد (منع ازدواج المحرّكين).
- **حارس الراية/الأمانة** (unit): مُطفأة ⇒ السلوك القديم · مُشعَلة بلا pcse/محصول-مدعوم ⇒ فشل مُصنَّف
  (لا استبدال صامت في الإنتاج). محصول خارج السجلّ ⇒ `unsupported_crop`.
- **حارس فصل I/O** (unit): المحرّك النقيّ يقبل `SimulationInputs` ويعيد `SimulationOutput` بلا استيراد
  FastAPI/الغراء؛ الغراء لا يحسب علماً.
- **مؤجَّل لـSIM-GOLDEN-01:** golden files حقيقيّة + عتبات خطأ + برهان معايرة. **لا** ادّعاء دقّة قبله.
- **حيّ (تكامل، بيئة pcse):** تشغيل PCSE فعليّ على مُدخَل معلوم يعيد مخطّطاً موحّداً — يُشهَّد حيث يُركَّب pcse.

## 6. البوّابات + التسجيل
ruff · `pytest -m unit` الكامل · **المسح الاستباقيّ** (كلّ `--check` + ci.yml + compose-env + ui-contract،
درس #180 — agriai-engine خدمة قائمة فلا خدمة جديدة، لكن وحدات/مسارات جديدة تمسّ الجرد) · bundle. لا
migration (منطق/عقد صرف). **صدق `requirements`:** `pcse` يبقى **اختياريّاً** (لا يُضاف للمسار الحرِج —
pip-audit؛ ولا يُركَّب في CI الوحدة)؛ يُوثَّق كـextra للتكامل.

## 7. أسئلة المراجعة
- **(أ) موطن المحرّك:** agriai-engine (يملك wofost_adapter، `/simulate`) [موصى] أم نواة مشتركة؟
- **(ب) مسار المنصّة `/simulate/what-if`** (يفحص `wofost_real/` الغائب): يُترَك صادقاً `available:false`
  ويُوحَّد لاحقاً ليستهلك agriai-engine [موصى، خارج نطاق SIM-PCSE-01]، أم يُوحَّد الآن؟
- **(ج) قائمة `sim_crop_registry` v1:** المجموعة المقترَحة أعلاه كافية للبدء أم تُوسَّع/تُضيَّق؟
- **(د) `provenance` عند التشغيل قبل golden:** `pcse_wofost_uncalibrated` [موصى، أمين] أم تسمية أخرى؟
