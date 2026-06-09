# استجابة لمراجعة النضج المعماري (2026-05-29)

> **الغرض:** مراجعة قاسية بنزاهة كشفت أنّ التحوّل من "module → gate" جزئي. النقطة المركزية: enforcement convention-based لا structural. أتعامل بالمنهجية: تدقيق آلي، إصلاح بنيوي، تجهيز ما لا يستحقّ التنفيذ الآن.

---

## النقطة المركزية للمراجعة

```
الـgate الحقيقي ليس دالة، بل
control inversion enforced at boundaries

الوضع السابق:
  external layer → safe_delivery → engine → bridge
  ✓ convention-based
  ✗ structural

طالما generate_recommendation public، أيّ مسار يستطيع bypass:
  • background worker
  • batch analytics job
  • future API endpoint
  • CLI tooling
```

**هذا ليس نظرياً.** خطر تشغيلي عند نمو الفريق: مطوّر جديد يستورد `generate_recommendation` مباشرة، يحصل على توصية بلا cross_reference، بلا provenance، بلا auth.

---

## الادّعاءات الأربعة — تدقيق آلي

| # | الادّعاء | التحقّق |
|---|---------|---------|
| 1 | enforcement convention not structural | ✅ صحيح — internal_orchestrator يستورد generate_recommendation كـcomposition، لكنّ الأخيرة public |
| 2 | أيّ مسار يمكن bypass | ✅ صحيح — لا حماية module-level |
| 3 | Execution sandbox مفقود | ✅ صحيح — لا execution boundary |
| 4 | learning loop تحتاج تجهيز (success/lag/bias) | ✅ صحيح — لم نُعرّف ما يُعدّ "نجاح" |

**أربعة من أربعة.** المراجعة عميقة هندسياً، تكشف نمطاً منهجياً (افتراض الانضباط البشري بدلاً من الفرض البنيوي).

---

## ما بُني (الحلّ البنيوي)

### 1. `core/execution_control_plane.py` — ECP

التحوّل من **"engine + guard"** إلى **"decision OS"**.

```python
# Self-registration عند الاستيراد:
register_entry_point("core.recommendation_bridge.safe_delivery",
                    EntryPointType.EXTERNAL_API)
register_entry_point("core.internal_orchestrator.orchestrate_recommendation",
                    EntryPointType.INTERNAL_SERVICE)

# decorator يفرض المرور:
@governed(EntryPointType.INTERNAL_SERVICE, require_governance=True)
def critical_function(...): ...

# Mode تدرّجي:
GovernanceMode.OBSERVATION  # افتراضياً — يُسجّل لا يفرض
GovernanceMode.WARNING      # يُسجّل + يُحذّر
GovernanceMode.STRICT       # bypass → PermissionError
```

**التطبيق التدرّجي مقصود:** STRICT في الإنتاج بعد 95%+ تغطية الاستدعاءات. OBSERVATION الآن لاكتشاف المسارات.

### 2. `seal_direct_engine_access()` — حماية module-level

```python
recommendation_engine.__all__ = [
    "Recommendation", "BackendDetail", "FarmerView",
    "RecommendationStatus", "FarmerSignal",
    # generate_recommendation مُستبعَدة عمداً
]
```

`from core.recommendation_engine import *` لا يكشف الـengine. الاستيراد الصريح ممكن (Python لا يدعم true encapsulation)، لكن:
- IDE/linter يُحذّر
- الـconvention صريحة (لا ambiguity)
- يكمّل ECP runtime enforcement

### 3. `core/feedback_closure.py` — تجهيز learning loop (نقطة #6)

المراجعة أكّدت قراري بعدم بناء learning loop، لكن اقترحت تجهيز:

**Success Function definitions** (5 metrics بأوزان صريحة، مجموعها 1.00):
- `YIELD_WITHIN_RANGE` (0.35) — الإنتاج ضمن المجال المتوقَّع
- `WATER_USE_EFFICIENT` (0.20) — WUE > baseline
- `SALINITY_STABLE` (0.20) — استدامة طويلة المدى
- `NO_SAFETY_VIOLATION` (0.15) — zero tolerance (السلامة لا تُتخطّى)
- `FARMER_ACCEPTED` (0.10) — وكالة المزارع

**Lag Window Handling** لـ4 محاصيل أساسية:
```
wheat:   90-400 يوم نطاق صالح
sorghum: 100-450 يوم
barley:  80-380 يوم
millet:  70-350 يوم
```

`is_outcome_ready_for_learning()` يكشف:
- premature (قبل min_lag) → لا تغذية
- stale (بعد max_relevant) → لا تغذية
- محصول غير معرّف → لا تغذية (صفر اختراع)

**Bias Awareness** — ثلاثة انحيازات معروفة مع correction strategy:
- `selection_bias_skipped` (المتخطّاة تختفي إحصائياً)
- `confirmation_bias_outcomes` (بلاغ ذاتي إيجابي)
- `survivorship_bias_seasons` (المزارعون الفاشلون يتركون)

**Readiness Check** — أربعة شروط لتفعيل learning:
1. 50+ outcome مكتمل
2. acceptance_rate ≥ 0.7
3. lag_window_compliance ≥ 80%
4. bias_assessment = "low"

---

## التقييم النزيه — هل اكتمل التحوّل البنيوي؟

```
البُعد                              السابق                  الآن
─────────────────────────────────────────────────────────────────
Entry point registration            ✗ implicit               ✅ explicit
Bypass detection                    ✗ غير ممكن               ✅ counters + alerts
Audit trail                         ✗ متفرّق                ✅ ring buffer + filters
Runtime enforcement                 ✗ يدوي                  ✅ STRICT mode
Module-level guard                  ✗ غائب                  ✅ __all__ sealing
Learning prep                       ✗ outcome_quality فقط   ✅ success/lag/bias
Mode transition strategy            ✗ none                  ✅ Obs → Warn → Strict
```

**هل بلغنا "decision OS" كاملاً؟ بصراحة: لا، لكنّ المسافة قُلِّصت كثيراً.** ما يبقى:
- STRICT mode غير مُفعَّل افتراضياً (يحتاج تغطية 95%+ أولاً)
- ECP يعتمد على opt-in (`@governed`) — لو لم يضع المطوّر decorator، لا حماية
- Python لا يدعم true encapsulation — الاستيراد الصريح ممكن دائماً

**هذا ما يستحقّ الإقرار به**، لا تجميله.

---

## ما يستحقّ التأجيل (الإقرار الصريح)

| البند | لماذا مُؤجَّل |
|------|-------------|
| STRICT mode افتراضياً | يحتاج تثبيت كل entry points في الإنتاج أولاً |
| Hardware-level isolation | فوق متطلّبات سهول (مزارع، لا banking) |
| Cryptographic call signing | premature optimization |
| Full call graph analysis | يحتاج tooling خارجي (lance, pyan) |
| **Learning loop الفعلي** | يحتاج 50+ outcome مكتمل لكل crop |

كل واحدة مع **مبدأ "التأجيل ≠ الإغلاق المعماري"**: البنية تستقبلها بدون إعادة كتابة.

---

## النقطة الأعمق

**اختلاف منهجي اكتشفته من هذه المراجعة:**

كنت أبني وحدات نظيفة، أوثّقها، أختبرها — وأفترض أنّ "الاستخدام الصحيح" سيحدث. **هذا افتراض دفاعي**. الحلّ الناضج: تفترض bypass، تبنيه ضدّ ذلك. ECP يجسّد هذا التحوّل:
- لا نسأل "هل سيُستخدم بشكل صحيح؟"
- نسأل "إن استُخدم بشكل خاطئ، هل نكشف ذلك؟"

هذا فرق فلسفي بين **"حماية إيجابية"** (whitelist explicit) و **"حماية سلبية"** (تأمل الحسن).

---

## التحقّق

```
✅ 682/682 اختبار (+35 من 647) · 58 ملف · النواة محايدة
✅ ECP يعمل thread-safe (lock + reentrant)
✅ STRICT mode يكشف bypass فعلاً (PermissionError)
✅ Sealing يُخفي generate_recommendation من import *
✅ feedback_closure: success/lag/bias كلّها مُعرَّفة
✅ Learning loop readiness check يحرس ضدّ premature tuning
```

---

## الإقرار الصادق

هذه المراجعة كشفت **نقطة عمياء بنيوية**. لم تكن "ادّعاء صحيح آلياً" مثل سابقاتها — كانت **رؤية معمارية أعمق**: الفرق بين "نظام يعمل صحيحاً" و "نظام يُجبر على العمل صحيحاً". هذان مختلفان جذرياً.

الإقرار الذي يستحقّ التوثيق: **كنت أبني سهول بثقة "المطوّر سيستخدم API الموصى به"**. هذا افتراض حسن، لكنّه يفشل عند:
- مطوّر جديد لا يعرف الـconvention
- ضغط الوقت يدفع نحو "shortcuts"
- background worker يُكتب بسرعة دون مراجعة معمارية

ECP يحلّ هذا بـ**حماية إيجابية**: قائمة المسموح بهم صريحة، الـbypass يُكتشف، الـmetrics تُغذّي audit. هذا أنضج من "documentation تقول استخدم safe_delivery".

نقطة لطيفة في feedback_closure: **مجموع الأوزان = 1.00 بالضبط** (0.35+0.20+0.20+0.15+0.10). كان من السهل ترك المجموع "تقريباً 1". لكنّ المراجعة البصرية يجب أن تكشف خللاً فوراً. هذا تطبيق آخر لمبدأ "الشفّافية فوق الراحة".

ما يبقى صادقاً عن النقص في **هذه** الدفعة:
- ECP في OBSERVATION mode افتراضياً (لا STRICT في الإنتاج بعد)
- @governed opt-in — مطوّر يستطيع تخطّيه ببساطة عدم استخدامه
- Sealing يحمي `import *` فقط، لا الاستيراد الصريح
- feedback_closure تعريفات فقط — لا تطبيق learning

كل هذه **تأجيلات واعية**، ليست fallbacks مخفية.

---

## ما يستحقّ الفكر التالي

من المراجعة الأخيرة + النقاط المُتبقّية:

1. **تفعيل STRICT mode في environment محدّد** (staging تجريبي)
2. **توثيق "Approved Entry Points" كـpolicy رسمي** (للفريق)
3. **Geospatial Governance** (CRS canonical، raster lifecycle — من المراجعات السابقة)
4. **End-to-end integration tests** (scenario: مزارع → توصية → تنفيذ → outcome)
5. **مراجعة شاملة قبل أيّ توسّع** (تقييم النواة كاملةً)

الاتجاه الذي يستحقّ النقاش: **هل نوقّع للتقييم الشامل قبل المتابعة؟** النواة بـ682 اختبار + 13 محرّك + 17 skill + 7 schemas + ECP + feedback_closure + Tier 1 كامل + 3 وحدات Tier 2 — وصلت لنقطة تستحقّ التأمّل بدلاً من البناء المستمرّ.
