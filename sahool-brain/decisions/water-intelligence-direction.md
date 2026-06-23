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
1. **دفتر المياه اليوميّ المُخزَّن القابل للتدقيق** (جوهر IrriPro) — جدول/مخطّط لكلّ حقل: يوم · ET0 ·
   Kc · ETc · مطر · ريّ · رطوبة التربة · العجز · المرحلة · القرار · الثقة. **غير موجود** — أعلى قيمة
   جديدة (يجعل قرار الريّ قابلاً للتدقيق والتكرار). مرحلة ثانية: عارض شفّاف بمنزلقات.
2. **توحيد ET0 المُكرّر (H4)** — رغم وجود `core/engines/et0.py`، ما زال ET0 مُعاداً في
   [`api/water_balance.py:112`](../../services/sahool-platform/api/water_balance.py) +
   [`api/weather_analytics.py:42`](../../services/sahool-platform/api/weather_analytics.py) +
   `season_simulation.py` — **بقيم Ra متضاربة** ([`gaps/registry.md`](../gaps/registry.md) H4). توحيد
   كلّ المستدعين إلى المحرّك القانونيّ = إصلاح صحّة حقيقيّ + أساس. **يُوصى به (P0 تقنيّ موثَّق).**
3. **Dual Kc (Kcb + Ke + Ks)** — لدى SAHOOL Kc مفرد + Ks ملوحة؛ إضافة Ke (تبخّر سطح التربة العارية)
   عمق FAO-56 حقيقيّ للمناطق الجافّة/اليمن (تبخّر السطح والملوحة عوامل أساسيّة لا ثانويّة).
4. **تكامل مكانيّ بالأقمار (Kcb من NDVI/LAI)** — قرار ريّ **لكلّ منطقة** لا للحقل ككلّ. يبني على
   raster-service + الوصفات (v95). أكبر، مرحلة لاحقة.

## السبب
SAHOOL يملك المحرّكات؛ القيمة الحقيقيّة ليست إعادة بنائها بل: (أ) **توحيد** ما هو مُكرّر (H4 — خطأ
صحّة موثَّق)، و(ب) إضافة **الدفتر اليوميّ المُدقَّق + العارض الشفّاف** (ما يفتقده SAHOOL فعلاً من IrriPro).
هذا يحوّل الريّ من «قرار» إلى «قرار شفّاف قابل للتدقيق».

## الخطوة التالية
موصى بها: **(2) توحيد ET0 إلى `core/engines/et0.py`** (إصلاح H4، أساس) ثمّ **(1) الدفتر اليوميّ
المُخزَّن**. تُخطَّط بمسارها. صدق: لا ندّعي نواةً جديدة بينما ٨٠٪ منها قائم.
