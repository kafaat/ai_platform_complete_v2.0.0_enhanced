# قرار اتّجاه: ذكاء المياه (Water Intelligence) — إلهام IrriPro / FAO-56

> سجلّ اتّجاه معماريّ. لا فكرة بلا مصدر، ولا اقتباس بلا حالته الفعليّة في SAHOOL (file:line).
> الحالة: `proposed` — مراجعة وإلهام. آخر تحديث: 2026-06-23.

## المصدر (الإلهام)
- **IrriPro** (`irripro.com.cn/IrrigationSimulator.html`): محاكي ريّ تعليميّ ينقل نموذج **FAO-56**
  (`ET0 × Kc = ETc` + توازن مياه التربة اليوميّ) إلى المتصفّح بشفافيّة — كلّ يوم: مطر/ETc/رطوبة/عجز/
  قرار ريّ، مع منزلقات معاملات (Kc/التربة/الطقس عبر Open-Meteo). جوهره: **«دفتر مياه يوميّ» مرئيّ
  قابل للتدقيق** (لا صندوق أسود). يقترح المستخدم توسيعه إلى نواة 8 محرّكات لـSAHOOL.

## أين يقف SAHOOL اليوم (مُسنَد — ~٨٠٪ من النواة المقترَحة موجود)
| محرّك مقترَح | حالة SAHOOL | المصدر |
|---|---|---|
| Weather ET0 (PM + Hargreaves) | ✅ | `core/engines/et0.py` · `api/water_balance.py:112,120,142` |
| Crop Kc / Phenology | ✅ | `core/engines/fao56.py` · `api/routers/phenology.py` |
| Root-zone water balance | ✅ | `api/water_balance.py:216` · `api/routers/water_balance.py:30` |
| Irrigation trigger | ✅ | `core/engines/deficit_irrigation.py` · `supplemental_irrigation.py` · `api/routers/irrigation_plan.py:56` |
| Hydraulic feasibility | ✅ | `api/routers/irrigation_network.py` · `irrigation_method.py` |
| Scenario simulator | ✅ | `api/scenario_whatif.py` + صفحة scenario-compare |
| Explainability + confidence | ✅ | `api/decision_explainer.py` (Claude) · `api/decision_confidence.py` |
| Economic / water cost | ✅ | `core/engines/water_cost.py` |
| **Soil Water Ledger يوميّ مُخزَّن** | ⛔ **غير موجود** | لا دفتر يوميّ مُسجَّل/مُدقَّق |

**الخلاصة:** SAHOOL ليس «حاسبة ريّ» بل يملك نواة ريّ شبه كاملة (FAO-56 + هيدروليك + سيناريو + تفسير +
كلفة). التحليل يُقلّل من قدره. **لا نُعيد البناء.**

## الفجوات الحقيقيّة والنافعة (بترتيب القيمة/الجدوى)
1. **دفتر المياه اليوميّ المُخزَّن القابل للتدقيق** (جوهر IrriPro) — ✅ **منفَّذ v1 (#458):** جدول
   `water_ledger` (ترحيل `migrations/v98_water_ledger.sql`، معزول بالمستأجِر + RLS، PK مركّب
   `(field_id, ledger_date)` للـidempotency) لكلّ حقل: يوم · ET0 · Kc · ETc · مطر · ريّ · رطوبة
   التربة/عجز · العجز · المرحلة · القرار · الثقة. راوتر `api/routers/water_ledger.py` (POST upsert +
   GET بمدى تاريخ، FIELD_EDIT/VIEW، honest-503) + وحدة نقيّة `api/water_ledger_compute.py` (18 اختباراً).
   **صدق:** كلّ القيم nullable — الناقص `NULL` لا تصفير (نمط `decision_record`). **مرحلة ثانية مؤجَّلة:**
   العارض الشفّاف بمنزلقات + **Water Twin Simulator** فوق هذا الدفتر.
2. **توحيد ET0 (H4)** — ✅ **مؤكَّد (#457):** التوحيد كان مُنجَزاً (#351/#356) — `core/engines/et0.py`
   يحسب Ra per FAO-56 (لا ثابتاً)، وكلّ مستدعي api يُفوِّضون إليه. أُضيف **5 اختبارات انحدار** تُقفل
   الإصلاح (Ra يعتمد lat/DOY؛ مثال FAO-56 مُستنسَخ). **متبقٍّ موثَّق:** إعادتان في خدمتين منفصلتين
   (`mcp_servers/weather_server.py` · `wofost_engine.py`) تحسبان Ra صحيحاً لكن بلا مسار توحيد
   (ربط عبر-خدمات — مؤجَّل). فجوة H4 الصحّيّة مُغلقة.
3. **Dual Kc (Kcb + Ke + Ks)** — ✅ **منفَّذ (#457):** `compute_etc_dual` في `core/engines/fao56.py`
   (إضافيّ — المسار المفرد افتراضيّ سليم): `ETc=(Kcb·Ks+Ke)·ET0` (FAO-56 معادلات 71-80) + 17 اختباراً.
   **صدق:** Kcb مُشتقّ بإزاحة موثّقة (لا منحنى أساس مُعايَر)؛ TEW/REW جداول FAO-56؛ الافتراضات تُعرَض
   في `DualKcResult.assumptions` وقت التشغيل (لا تلفيق دقّة).
4. **تكامل مكانيّ بالأقمار (Kcb من NDVI/LAI)** — قرار ريّ **لكلّ منطقة** لا للحقل ككلّ. يبني على
   raster-service + الوصفات (v95). أكبر، مرحلة لاحقة.

## التعميق (مراجعة ثانية للمستخدم) — يؤكّد ويُثري
> «SAHOOL يملك معظم اللبنات (ET0 · Weather · Phenology · CanonicalFieldState)؛ ما ينقص هو **تجميعها
> في محرّك مياه موحّد (Water Intelligence Kernel)**.» — يطابق خلاصتنا. إضافات بارزة:
- **⭐ Water Twin Simulator** (الفكرة الأبرز): شاشة **what-if تفاعليّة** — «ماذا لو أخّرت الريّ ٣ أيّام؟
  خفّضته ٢٠٪؟ هطل مطر غداً؟» → أثر مباشر على رطوبة التربة/الإجهاد/الإنتاج/استهلاك الماء. يستثمر
  `scenario_whatif.py` القائم + الدفتر اليوميّ. **أعلى قيمة تعليم/ثقة** (يفتقده معظم المنافسين).
- **Kc ديناميكيّ = f(المرحلة, NDVI, LAI, غطاء التاج)** بدل جدول ثابت — يربط `fao56` Kc بـraster-service.
  (تطوير للفجوة 3/4 أعلاه.)
- **Field Water Digital Twin**: حالة مياه يوميّة لكلّ حقل (FC/WP/RAW/TAW/رطوبة حاليّة/ET0/ETc/مطر/أحداث ريّ).
- طبقات موصى بها (٦): توازن مائيّ FAO-56 · Kc ديناميكيّ · توأم مياه · ريّ مُفسَّر · محاكاة سيناريو · مُحسِّن اقتصاديّ.
  **ملاحظة صدق:** ٤ منها قائمة أصلاً في SAHOOL (انظر الجدول)؛ الجديد فعلاً = الدفتر/التوأم + المحاكي الشفّاف + Kc الديناميكيّ.

## السبب
SAHOOL يملك المحرّكات؛ القيمة الحقيقيّة ليست إعادة بنائها بل: (أ) **توحيد** ما هو مُكرّر (H4 — خطأ
صحّة موثَّق)، و(ب) إضافة **الدفتر اليوميّ المُدقَّق + التوأم/المحاكي الشفّاف (Water Twin)** (ما يفتقده
SAHOOL فعلاً من IrriPro). هذا يحوّل الريّ من «قرار» إلى «قرار شفّاف قابل للتدقيق».

## الخطوة التالية
موصى بها: **(2) توحيد ET0 إلى `core/engines/et0.py`** (إصلاح H4، أساس) ثمّ **(1) الدفتر اليوميّ
المُخزَّن**. تُخطَّط بمسارها. صدق: لا ندّعي نواةً جديدة بينما ٨٠٪ منها قائم.
