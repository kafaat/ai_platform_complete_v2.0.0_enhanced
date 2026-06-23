# قرار تصميميّ: D2 — تحكيم الإجهاد المائيّ في `CanonicalFieldState`

> **الحالة:** `accepted` (أقرّ المستخدم العتبة، 2026-06-23 — قرار زراعيّ).
> يربط: [`strategy.md`](strategy.md) (Bundle D) · [`water-intelligence-direction.md`](water-intelligence-direction.md).
> **حسّاس — يغيّر القرار القانونيّ** (`execution_mode→human_review`).

## القرار المُقَرّ (المستخدم، 2026-06-23): نموذج أربعة مستويات + تصعيد مزدوج البوّابة
التصعيد للمراجعة البشريّة يجب أن يكون **نادراً عالي الثقة** لا حدثاً يوميّاً — «فيزياء + رصد» لا نموذج
وحده. لذا أُقِرّ:

| المستوى | الشرط | الإجراء |
|---|---|---|
| **NORMAL** | `AWF > 0.5` | تشغيل طبيعيّ |
| **WATCH** | `AWF ≤ 1−p` (Dr ≥ RAW) | تنبيه/رفع أولويّة الريّ — **لا** human_review (بدء إجهاد فسيولوجيّ روتينيّ) |
| **CRITICAL** | `AWF ≤ 0.2` (Dr ≥ 0.8·TAW) | توصية عاجلة (معلوماتيّ) |
| **ESCALATE** | `AWF ≤ 0.2 AND depletion_confidence ≥ 0.8 AND spectral_stress_detected` | **`execution_mode→human_review`** |

**جوهر القرار:** بدء الإجهاد (Dr≥RAW) **لا** يُصعّد (يُغرِق المهندس — حقول مطريّة/ريّ دوريّ). التصعيد
حصراً عند استنزاف ضارّ (AWF≤0.2) **مؤكَّداً** بثقة استنزاف ≥0.8 **و** دليل طيفيّ (NDMI منخفض أو MSI
مرتفع). قابل للتشديد لاحقاً بالمعايرة الميدانيّة.

## السياق
بعد D1 (#466: ET0/ETc كنسيّان) · D3 (#467: قراءة موحّدة) · Bundle B (#468: تصعيد ثقة الحدّ)، تبقّى
**D2**: أن يَحمل `CanonicalFieldState` **إجهاداً مائيّاً** ويُصعّده للمراجعة البشريّة عند بلوغه حدّاً حرجاً —
نظير تصعيد الملوحة الحرجة (`salinity_class=="critical"`) وثقة الحدّ المنخفضة. وجّه المستخدم: **«أخّره — يغيّر
القرار، يحتاج خطّة رسميّة + إقرار عتبة».** هذا المستند هو تلك الخطّة.

## ما هو موجود فعلاً (جاهز لإعادة الاستخدام — لا إعادة بناء)
| العنصر | الموقع |
|---|---|
| جسر الفيزياء **AWF = 1 − Dr/TAW** | `api/soil_water.py:107` `available_water_fraction(depletion_mm, taw_mm)` |
| **استحقاق الريّ** AWF ≤ 1−p (Dr ≥ RAW) | `api/soil_water.py:119` `irrigation_due_by_soil(...)` |
| اشتقاق **TAW/RAW** من القوام+Zr+p | `api/soil_water.py:68` `soil_water_params(...)` · `core/engines/fao56.py:425` `taw_from_root_depth` |
| **Dr مخزَّن** (depletion_mm/deficit_mm/soil_moisture_pct) | جدول `water_ledger` · `api/water_ledger_compute.py:17` |
| Ks الملوحة (Eq.81) — **نمط للحتذاء** | `core/engines/fao56.py:143` `salinity_stress_ks` |
| إشارات إجهاد طيفيّة NDMI/MSI (استرشاديّة) | `core/engines/spectral_stress_bridge.py` (`fuse_water_stress`) |
| **نمط التصعيد القائم** (الملوحة + الحدّ) | `api/field_state_projection.py:344` (ملوحة) · `:357` (Bundle B حدّ) |
| ET0/Kc/ETc الكنسيّة (D1) | `core/agronomic_state_engine.py` كتلة ② · `operational_truths` |

## ما هو ناقص (يحتاج بناءً في D2)
- **مصدر Dr في المسار الكنسيّ:** `depletion_mm` يُخزَّن في `water_ledger` لكن **لا يُشتقّ** داخل الإسقاط؛
  لا يُقرأ حاليّاً في `recompute_field_state`.
- حقل `water_stress_class` + `water_stress_awf` في `operational_truths`.
- **عتبة التصعيد** (قرار المستخدم — أدناه).
- (اختياريّ لاحق) Ks المائيّ Eq.84 · استخراج `precipitation_sum` من كاش Open-Meteo (موجود في البيانات،
  غير مقروء — `field_state_projection.py:161`).

## التصميم المقترح (مرحليّ — يحاكي مرحليّة D1/D3/B)

### المرحلة D2a — كتلة إجهاد مائيّ **إضافيّة محفوظة السلوك** (لا تصعيد)
- **مصدر Dr (صدق أوّلاً):** اقرأ أحدث `depletion_mm` (+ `soil_moisture_pct`) من `water_ledger` للحقل
  (best-effort، نظير قراءة الحدّ في Bundle B). **غياب Dr موثوق ⇒ لا كتلة، لا تصعيد** (لا اختلاق، لا قرار
  على غياب). TAW من Zr الديناميكيّ (`soil_water_params`/`taw_from_root_depth`، مُستعمَل في water_twin).
- **المقياس:** `awf = available_water_fraction(Dr, TAW)` (إعادة استخدام صرفة).
- **كتلة كنسيّة** `water_stress` على نموذج الحالة (نظير `water`/`boundary`): `{water_stress_awf, water_stress_class, depletion_mm, taw_mm, raw_fraction, source}` — **قراءة/اشتقاق صرف، بلا تغيير قرار.**
- قارئ نقيّ `api/canonical_water_stress.py` + اختبارات وحدة (نمط `canonical_water`/`canonical_boundary`).
- **لا يمسّ** التحكيم/`execution_mode`/المخطّط. آمن للدمج فوراً بعد إقرار تعريف الفئات.

### المرحلة D2b — **التصعيد** (التغيير القانونيّ — مُقفَل خلف إقرار العتبة)
- في `recompute_field_state` (نمط الملوحة/الحدّ تماماً): إذا `water_stress_class=="critical"`
  و`execution_mode=="auto"` ⇒ `human_review` + `validity` valid→degraded + سبب عربيّ. تصعيد سلامة لا
  تخفيض — لا يلمس إلّا auto/valid ولا يغيّر أرقاماً.
- اختبارات تصعيد (منخفض يُصعّد · سليم لا · لا Dr لا تصعيد) في `test_field_state_unification.py`.

## التنفيذ
- **D2a ✅ مُدمَج (#469):** كتلة `water_stress` كنسيّة بمستويات NORMAL/WATCH/CRITICAL معلوماتيّة +
  `water_stress_awf` + `depletion_confidence`، مقروءة من `water_ledger` وTAW من `soil_water_params`
  (موسومة `calibrated=False`). بلا تصعيد.
- **D2b ✅ منفَّذ (فرع `claude/bundle-d2b-spectral-escalation`) — خلف feature flag default OFF:**
  بقرار المستخدم (2026-06-23) NDMI+MSI معاً + علم معطَّل افتراضيّاً. المكوّنات:
  - **الإشارة:** هجرة `v99_imagery_spectral_indices.sql` (أعمدة `last_ndmi/msi_mean/date` على
    `imagery_automation_fields`) · خطّ الصور `imagery_automation.py` يحسب NDMI/MSI (مدعومان أصلاً في
    الراستر `IndicatorKind.ndmi/msi`) ويخزّنهما · `gather_field_freshness` يقرؤهما (SAVEPOINT منفصل،
    توافق ما-قبل-الهجرة).
  - **الأهليّة (القارئ النقيّ `canonical_water_stress`):** `fuse_water_stress(ndmi, msi)` ⇒
    `spectral_confirmation_available` (كلا المؤشّرين) · `spectral_stress_detected` (moderate/severe) ·
    `escalation_eligible = critical ∧ depletion_confidence≥0.8 ∧ تأكيد طيفيّ`. غياب أيّ مؤشّر ⇒ available=False
    و detected=None (صدق: لا تصعيد بلا رصد).
  - **العلم + التصعيد (الإسقاط):** `FEATURE_WATER_STRESS_ESCALATION` (default off؛ ليس علم راوتر ⇒ خارج
    `feature_registry.FEATURE_FLAGS`، يبقى `test_feature_flags_smoke` أخضر). الكتلة تُعلن دائماً
    `escalation_eligible`/`escalation_triggered`/`disabled_reason` (`feature_flag_off` عند الأهليّة بلا علم).
    عند العلم ON ⊕ الأهليّة ⊕ `execution_mode==auto` ⇒ `human_review` + `validity` valid→degraded + سبب.
  - **اختبارات:** ٥ قارئ (أهليّة/غياب مؤشّر/طيف صحّيّ/ثقة<0.8/watch) + ٤ إسقاط (علم OFF لا يُصعّد +
    `disabled_reason` · علم ON يُصعّد · غياب طيف لا · ثقة منخفضة لا).
- **بعد الدمج (تشغيليّ):** مراقبة ميدانيّة عدّة أسابيع (معدّل CRITICAL/الإيجابيّات الكاذبة/سلوك NDMI-MSI في
  غبار اليمن) ثمّ تفعيل العلم لمستأجرين/بيئات محدّدة. **معايرة p/TAW اليمنيّة** تبقى فجوة موثّقة.

> **فجوة معايرة موثّقة:** p/TAW اليمنيّة غير معايَرة (افتراضيّ FAO-56 عامّ، `raw_fraction=0.5`، TAW Table 19)
> — الكتلة موسومة `calibrated=False` صدقاً. العتبات قابلة للتشديد بعد المعايرة الميدانيّة.
